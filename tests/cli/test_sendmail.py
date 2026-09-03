import email.message
import pathlib
import subprocess
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import jinja2
import pytest

from lovebirds.cli.config import Config
from lovebirds.cli.sendmail import (
    _SmtpProxy,
    _is_maildir,
    _make_message,
    _run_message_filter,
    send_messages,
)
from lovebirds.models.email import EmailAddress
from lovebirds.models.events import (
    Event,
    MailConfig,
    MessageFilterConfig,
    MessageInfo,
    SmtpConfig,
)
from lovebirds.models.people import (
    Consent,
    Participation,
    People,
    Person,
    SentMessageInfo,
)


EVENT_ID = "event1"


def make_event(**message_kwargs: Any) -> Event:
    defaults: dict[str, Any] = dict(
        condition="% True",
        translations=["en"],
        filename="message.md",
        headers={},
        variables={},
    )
    defaults.update(message_kwargs)
    return Event(
        event_id=EVENT_ID,
        mail=MailConfig(
            message_filter=MessageFilterConfig(html="cat", plain="cat"),
            headers={"From": "The Guild <guild@example.com>"},
            smtp=SmtpConfig(server="localhost", tls=False),
        ),
        variables={},
        messages={"invitation": MessageInfo(**defaults)},
    )


def make_message() -> email.message.EmailMessage:
    msg = email.message.EmailMessage()
    msg.add_header("Message-ID", "<abc@example.com>")
    msg.add_header("To", "someone@example.com")
    return msg


def send_config(
    make_config: Callable[..., Config],
    people: People,
    **kwargs: Any,
) -> Config:
    defaults: dict[str, Any] = dict(
        msg_name="invitation",
        dry_run=False,
        mailbox_path=None,
        mailbox_type="maildir",
        test_mailbox_path=None,
        test_mailbox_delete=False,
        event_file="/tmp/event.yaml",
    )
    defaults.update(kwargs)
    return make_config(
        people=people,
        event=make_event(),
        event_id=EVENT_ID,
        operator_id=next(iter(people), None),
        **defaults,
    )


class TestSendMessagesRecipientSelection:
    """Who a mass mailing reaches. Every skip here protects someone from a
    message they should not get, or from getting it twice."""

    @pytest.fixture(autouse=True)
    def _isolate_sending(self) -> Any:
        with (
            patch("lovebirds.cli.sendmail._SmtpProxy") as smtp,
            patch("lovebirds.cli.sendmail.make_environment"),
            patch("lovebirds.cli.sendmail._make_message") as make_msg,
        ):
            make_msg.return_value = make_message()
            self.smtp = smtp.return_value
            self.make_msg = make_msg
            yield

    def _person(
        self, make_person: Callable[..., Person], in_event: bool = True, **kwargs: Any
    ) -> Person:
        person = make_person(**kwargs)
        if in_event:
            person.participation[EVENT_ID] = Participation()
        return person

    def _database(self, person: Person) -> tuple[People, UUID]:
        """A one-person database plus the id used as the operator."""
        person_id = uuid4()
        return {person_id: person}, person_id

    def test_sends_to_an_eligible_recipient(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        people, _ = self._database(self._person(make_person))
        send_messages(send_config(make_config, people))
        self.smtp.send_message.assert_called_once()

    def test_skips_a_locked_account(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        people, _ = self._database(self._person(make_person, locked=True))
        send_messages(send_config(make_config, people))
        self.smtp.send_message.assert_not_called()

    def test_skips_a_legacy_consent_account(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = self._person(make_person)
        person.consent = Consent(legacy=True)
        people, _ = self._database(person)
        send_messages(send_config(make_config, people))
        self.smtp.send_message.assert_not_called()

    def test_skips_someone_not_taking_part_in_this_event(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        people, _ = self._database(self._person(make_person, in_event=False))
        send_messages(send_config(make_config, people))
        self.smtp.send_message.assert_not_called()

    def test_does_not_send_the_same_message_twice(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Re-running send after an interruption must not mail the people who
        were already reached on the first run."""
        person = self._person(make_person)
        people, operator = self._database(person)
        person.participation[EVENT_ID].sent_messages["invitation"] = SentMessageInfo(
            operator=operator
        )
        send_messages(send_config(make_config, people))
        self.smtp.send_message.assert_not_called()

    def test_skipping_the_condition_sends_nothing(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """_make_message returns None when the message's condition excludes the
        recipient."""
        self.make_msg.return_value = None
        people, _ = self._database(self._person(make_person))
        send_messages(send_config(make_config, people))
        self.smtp.send_message.assert_not_called()

    def test_a_sent_message_is_recorded_and_saved(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = self._person(make_person)
        people, operator = self._database(person)
        config = send_config(make_config, people)
        send_messages(config)

        record = person.participation[EVENT_ID].sent_messages["invitation"]
        assert record.message_id == "<abc@example.com>"
        assert record.operator == operator
        assert record.time is not None
        assert config.write_people.call_count == 1  # type: ignore[attr-defined]

    def test_a_mailing_leaves_one_commit_however_many_recipients(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Committing per recipient would turn one mailing into N commits and
        N serial pushes, and the first push to fail would abort the mailing
        part-way through, with the SMTP connection still open.
        """
        people: People = {uuid4(): self._person(make_person) for _ in range(3)}
        config = send_config(make_config, people)

        send_messages(config)

        assert config.write_people.call_count == 3  # type: ignore[attr-defined]
        config.commit_people.assert_called_once_with(  # type: ignore[attr-defined]
            "invitation"
        )

    def test_an_interrupted_mailing_still_commits_what_it_sent(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Otherwise the messages that did go out stay written but
        uncommitted, and the next run's `git pull` refuses to touch a dirty
        work tree.
        """
        people: People = {uuid4(): self._person(make_person) for _ in range(2)}
        config = send_config(make_config, people)
        self.smtp.send_message.side_effect = [None, OSError("connection reset")]

        with pytest.raises(OSError, match="connection reset"):
            send_messages(config)

        assert config.write_people.call_count == 1  # type: ignore[attr-defined]
        config.commit_people.assert_called_once_with(  # type: ignore[attr-defined]
            "invitation"
        )

    def test_dry_run_neither_sends_nor_records(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = self._person(make_person)
        people, _ = self._database(person)
        config = send_config(make_config, people, dry_run=True)
        send_messages(config)
        self.smtp.send_message.assert_not_called()
        assert person.participation[EVENT_ID].sent_messages == {}
        config.save_people.assert_not_called()  # type: ignore[attr-defined]


class TestSendMessagesRefusals:
    def test_unknown_message_name_is_rejected(
        self, make_config: Callable[..., Config]
    ) -> None:
        config = send_config(make_config, {}, msg_name="nonexistent")
        with pytest.raises(RuntimeError, match="not defined"):
            send_messages(config)

    def test_a_locked_message_is_never_sent(
        self, make_config: Callable[..., Config]
    ) -> None:
        """Locking a message is how an organiser marks it as already delivered
        or not ready; sending it anyway would mail people by accident."""
        config = send_config(make_config, {})
        assert config.event is not None
        config.event.messages["invitation"].locked = True
        with pytest.raises(RuntimeError, match="locked message"):
            send_messages(config)


class TestIsMaildir:
    def test_missing_path_is_unknown(self, tmp_path: pathlib.Path) -> None:
        assert _is_maildir(tmp_path / "nope") is None

    def test_directory_with_the_three_subdirs_is_a_maildir(
        self, tmp_path: pathlib.Path
    ) -> None:
        for name in ("cur", "new", "tmp"):
            (tmp_path / name).mkdir()
        assert _is_maildir(tmp_path) is True

    def test_any_other_directory_is_not(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "cur").mkdir()
        assert _is_maildir(tmp_path) is False


class TestRunMessageFilter:
    def test_content_goes_through_the_filter(self) -> None:
        assert _run_message_filter("tr a-z A-Z", "hello") == "HELLO"

    def test_a_failing_filter_is_an_error(self) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            _run_message_filter("exit 3", "hello")


def template_env(body: str = "Hello {{ recipient.first_name }}.") -> jinja2.Environment:
    return jinja2.Environment(loader=jinja2.DictLoader({"message.md": body}))


class TestMakeMessage:
    """Turning a template plus a recipient into the mail that goes out."""

    def _recipient(self, make_person: Callable[..., Person], **kwargs: Any) -> Person:
        person = make_person(**kwargs)
        person.participation[EVENT_ID] = Participation()
        return person

    def _build(
        self,
        make_config: Callable[..., Config],
        recipient: Person,
        **event_kwargs: Any,
    ) -> Any:
        people, _ = {uuid4(): recipient}, None
        config = send_config(make_config, people)
        assert config.event is not None
        if event_kwargs:
            config.event.messages["invitation"] = MessageInfo(
                **{
                    **dict(
                        condition="% True",
                        translations=["en"],
                        filename="message.md",
                        headers={},
                        variables={},
                    ),
                    **event_kwargs,
                }
            )
        message = config.event.messages["invitation"]
        return _make_message(config, recipient, message, template_env())

    def test_builds_a_multipart_alternative(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        recipient = self._recipient(make_person, first_name="Alice")
        msg = self._build(make_config, recipient)
        assert msg is not None
        assert msg.get_content_type() == "multipart/alternative"
        subtypes = [
            part.get_content_type()
            for part in msg.walk()
            if part.get_content_maintype() != "multipart"
        ]
        assert subtypes == ["text/plain", "text/html"]

    def test_the_template_sees_the_recipient(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        recipient = self._recipient(make_person, first_name="Alice")
        msg = self._build(make_config, recipient)
        assert msg is not None
        body = msg.get_payload(0).get_payload(decode=True).decode()
        assert "Hello Alice." in body

    def test_headers_are_evaluated_as_templates(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        recipient = self._recipient(make_person)
        msg = self._build(
            make_config, recipient, headers={"Subject": "For {{ event_id }}"}
        )
        assert msg is not None
        assert msg["Subject"] == f"For {EVENT_ID}"

    def test_recipient_is_addressed_by_name(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        recipient = self._recipient(
            make_person,
            first_name="Alice",
            last_name="Ahonen",
            email=EmailAddress("alice@example.com"),
        )
        msg = self._build(make_config, recipient)
        assert msg is not None
        assert msg["To"] == "Alice Ahonen <alice@example.com>"

    def test_a_false_condition_produces_no_message(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        recipient = self._recipient(make_person)
        assert self._build(make_config, recipient, condition="% False") is None

    def test_a_non_boolean_condition_is_an_error(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        recipient = self._recipient(make_person)
        with pytest.raises(RuntimeError, match="Condition expression failed"):
            self._build(make_config, recipient, condition="% recipient.email")

    def test_the_recipients_preferred_language_is_chosen(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Languages are in preference order, so the first one the message has
        been translated into wins."""
        recipient = self._recipient(make_person, languages=["fi", "en"])
        msg = self._build(
            make_config,
            recipient,
            translations=["en", "fi"],
            headers={"Subject": "{{ language }}"},
        )
        assert msg is not None
        assert msg["Subject"] == "fi"

    def test_untranslatable_recipient_leaves_language_unset_in_templates(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """The fallback is broken, and this pins the current behaviour.

        When no translation matches, _make_message logs "sending in `en'
        anyway" and reassigns its local `language`. But vars_and_globals was
        already built from the globals dict, so the template namespace still
        holds language=None. Headers, filename and body all render None.
        """
        recipient = self._recipient(make_person, languages=["sv"])
        msg = self._build(
            make_config,
            recipient,
            translations=["en", "fi"],
            headers={"Subject": "{{ language }}"},
        )
        assert msg is not None
        assert msg["Subject"] == "None", "would be 'en' if the fallback worked"

    def test_untranslatable_recipient_breaks_a_language_keyed_filename(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """The practical consequence: the standard `msg.{{ language }}.md'
        filename pattern resolves to `msg.None.md' and the send run dies part
        way through."""
        recipient = self._recipient(make_person, languages=["sv"])
        config = send_config(make_config, {uuid4(): recipient})
        assert config.event is not None
        config.event.messages["invitation"] = MessageInfo(
            condition="% True",
            translations=["en"],
            filename="msg.{{ language }}.md",
            headers={},
            variables={},
        )
        env = jinja2.Environment(loader=jinja2.DictLoader({"msg.en.md": "hi"}))
        with pytest.raises(jinja2.TemplateNotFound, match="msg.None.md"):
            _make_message(config, recipient, config.event.messages["invitation"], env)


class TestMakeMessageSenderValidation:
    """A bad From line means bounces or silent spam filtering, so it is
    rejected before anything is sent."""

    def _build_with_from(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
        from_header: str | None,
    ) -> Any:
        recipient = make_person()
        recipient.participation[EVENT_ID] = Participation()
        config = send_config(make_config, {uuid4(): recipient})
        assert config.event is not None
        config.event.mail.headers = {} if from_header is None else {"From": from_header}
        return _make_message(
            config,
            recipient,
            config.event.messages["invitation"],
            template_env(),
        )

    def test_a_missing_from_header_is_rejected(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        with pytest.raises(RuntimeError, match="sender not defined"):
            self._build_with_from(make_person, make_config, None)

    def test_a_malformed_sender_address_is_rejected(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        with pytest.raises(RuntimeError, match="not a valid e-mail address"):
            self._build_with_from(
                make_person, make_config, "The Guild <not-an-address>"
            )

    def test_a_sender_without_a_display_name_is_rejected(
        self,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        with pytest.raises(RuntimeError, match="refusing to send"):
            self._build_with_from(make_person, make_config, "guild@example.com")


class TestSmtpProxy:
    """Connection handling. Servers commonly cap messages per session, so the
    proxy reconnects rather than having the rest of the run rejected."""

    def _proxy(self, limit: int | None) -> _SmtpProxy:
        proxy = _SmtpProxy(
            SmtpConfig(server="localhost", tls=False, messages_per_connection=limit)
        )
        proxy.username = "user"
        proxy.password = "pass"
        return proxy

    @patch("lovebirds.cli.sendmail.smtplib.SMTP_SSL")
    def test_connects_and_logs_in_once_for_several_messages(
        self, mock_smtp: MagicMock
    ) -> None:
        proxy = self._proxy(None)
        for _ in range(3):
            proxy.send_message(make_message())
        mock_smtp.assert_called_once_with("localhost")
        mock_smtp.return_value.login.assert_called_once_with("user", "pass")
        assert mock_smtp.return_value.send_message.call_count == 3

    @patch("lovebirds.cli.sendmail.smtplib.SMTP_SSL")
    def test_reconnects_once_the_per_connection_limit_is_reached(
        self, mock_smtp: MagicMock
    ) -> None:
        proxy = self._proxy(2)
        for _ in range(5):
            proxy.send_message(make_message())
        assert mock_smtp.call_count == 3, "2 + 2 + 1 messages over three sessions"
        assert mock_smtp.return_value.quit.call_count == 2

    @patch("lovebirds.cli.sendmail.smtplib.SMTP_SSL")
    def test_starttls_is_used_when_configured(self, mock_smtp: MagicMock) -> None:
        proxy = _SmtpProxy(SmtpConfig(server="localhost", tls=True))
        proxy.username, proxy.password = "user", "pass"
        proxy.send_message(make_message())
        mock_smtp.return_value.starttls.assert_called_once()

    @patch("lovebirds.cli.sendmail.smtplib.SMTP_SSL")
    def test_a_zero_limit_is_rejected_rather_than_looping(
        self, mock_smtp: MagicMock
    ) -> None:
        proxy = self._proxy(0)
        with pytest.raises(RuntimeError, match="messages_per_connection"):
            proxy.send_message(make_message())
