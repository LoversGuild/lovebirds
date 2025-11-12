# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Mail sending utilities."""

from datetime import datetime
import email.message
import email.utils
from getpass import getpass
import jinja2
import logging
import mailbox
import os
import smtplib
import subprocess
from typing import Any, cast

from lovebirds.models.email import EmailAddress, is_valid_email_address
from lovebirds.models.events import MessageInfo, SmtpConfig
from lovebirds.models.people import Person, Participation, SentMessageInfo
from lovebirds.utils import utc_now
from lovebirds.cli.config import Config
from lovebirds.templates.eval import eval_string, eval_variables, make_environment
from lovebirds.templates.person import person_to_dict


def send_messages(config: Config) -> None:
    assert config.event is not None

    sent_count = 0
    sent_total = 0
    try:
        message = config.event.messages[config.args.msg_name]
    except KeyError:
        raise RuntimeError(f"Message {config.args.msg_name} not defined")

    if message.locked:
        raise RuntimeError(
            f"Will not proceed with a locked message `{config.args.msg_name}'"
        )

    smtp: _SmtpProxy | None = None
    mbox: mailbox.Mailbox | None = None
    test_mbox: mailbox.Mailbox | None = None

    try:
        # Set up mailboxes
        if config.args.mailbox_path and not config.args.dry_run:
            mbox = _make_mailbox(
                config.args.mailbox_path, config.args.mailbox_type, delete_all=False
            )
        else:
            mbox = None

        if config.args.test_mailbox_path:
            test_mbox = _make_mailbox(
                config.args.test_mailbox_path,
                config.args.mailbox_type,
                delete_all=config.args.test_mailbox_delete,
            )
        else:
            test_mbox = None

        # Connect to SMTP server
        if not config.args.dry_run:
            smtp = _SmtpProxy(config.event.mail.smtp)

        # Create jinja2 template evaluation environment
        event_file_dir = os.path.abspath(os.path.dirname(config.args.event_file))
        env = make_environment(event_file_dir)

        # Backup participant database before sending the first message. No
        # backups in dry-run mode.
        backup = not config.args.dry_run

        # Loop over all people, render message and send it
        for recipient in config.people.values():
            # Prechecks: should we send this message at all
            if recipient.locked:
                logging.debug(f"Skipping locked account `{recipient.named_email}'")
                continue
            if recipient.consent.legacy:
                logging.debug(f"Skipping legacy account `{recipient.named_email}'")
                continue

            if config.event_id not in recipient.participation:
                logging.debug(
                    f"Skipping {recipient.named_email}, not imported into event `{config.event_id}'. Use 'phase' subcommand to add participation."
                )
                continue

            participation = recipient.participation[config.event_id]
            if config.args.msg_name in participation.sent_messages:
                logging.debug(
                    f"Skipping {recipient.named_email} - message already sent"
                )
                sent_total += 1
                continue

            # Generate message
            msg = _make_message(config, recipient, message, env)
            if msg is None:
                # This may happen if the message sending condition was not met
                continue

            msg_id = msg["Message-ID"]
            assert msg_id
            msg_id = str(msg_id)

            if not config.args.dry_run and smtp:
                logging.info(
                    f"Sending `{config.args.msg_name}' to `{recipient.named_email}'..."
                )
                send_time = utc_now()
                smtp.send_message(msg)

                logging.debug("Updating recipient status...")
                participation.sent_messages[config.args.msg_name] = SentMessageInfo(
                    operator=EmailAddress(config.args.operator),
                    message_id=msg_id,
                    time=send_time,
                )
                config.save_people(backup=backup)
                backup = False
            else:
                logging.info(
                    f"Would send `{config.args.msg_name}' to `{recipient.named_email}'"
                )
            sent_count += 1
            sent_total += 1

            if mbox is not None:
                mbox.add(msg)
            if test_mbox is not None:
                test_mbox.add(msg)
    finally:
        if smtp is not None:
            smtp.close()
        if mbox is not None:
            mbox.close()
        if test_mbox is not None:
            test_mbox.close()

        if not config.args.dry_run:
            logging.info(f"{sent_count} messages sent, {sent_total} sent in total")
        else:
            logging.info(
                f"{sent_count} messages would have been sent, {sent_total} in total"
            )


class _SmtpProxy:
    config: SmtpConfig
    message_count: int = 0
    password: str | None = None
    smtp: smtplib.SMTP_SSL | None = None
    username: str | None = None

    def __init__(self, config: SmtpConfig) -> None:
        self.config = config

    def close(self) -> None:
        if self.smtp is not None:
            self.smtp.quit()
            self.smtp = None

    def connect(self) -> None:
        if self.smtp is not None:
            raise RuntimeError("_SmtpProxy.connect: Already connected to a server")

        # Prompt user for authentication credentials if they are not set
        if self.username is None:
            self.username = input(f"SMTP username for {self.config.server}: ")

        if self.password is None:
            self.password = getpass(f"SMTP password for {self.username}: ")

        logging.debug(f"Connecting to {self.config.server}...")
        self.smtp = smtplib.SMTP_SSL(self.config.server)

        if self.config.tls:
            self.smtp.starttls()

        self.smtp.login(self.username, self.password)
        self.message_count = 0

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def send_message(self, message: email.message.EmailMessage) -> None:
        if self.smtp is None:
            self.connect()
            assert self.smtp is not None

        limit = self.config.messages_per_connection
        if limit is not None:
            if limit < 1:
                raise RuntimeError(
                    f"Cannot send a single message—messages_per_connection is {limit}"
                )
            if self.message_count > limit:
                logging.debug("Messages per connection limit reached, reconnecting...")
                self.reconnect()

        self.smtp.send_message(message)
        self.message_count += 1


def _is_maildir(path: str | os.PathLike[str]) -> bool | None:
    """
    Check if the specified path points to a Maildir mailbox.

    A directory is considered a Maildir if it contains
    exactly three subdirectories: 'cur', 'new', and 'tmp',
    and no other files or directories.

    Parameters:
        path (FilePath): The path to check.

    Returns:
        bool | None: True if the path is a Maildir,
               False if it exists but is not a Maildir,
               None if the path does not exist.
    """
    if not os.path.exists(path):
        return None

    if not os.path.isdir(path):
        return False

    entries = set(os.listdir(path))
    expected_dirs = {"cur", "new", "tmp"}

    if expected_dirs != entries:
        return False

    return all((os.path.isdir(os.path.join(path, d)) for d in entries))


def _make_mailbox(
    path: str | os.PathLike[str], type: str, delete_all: bool
) -> mailbox.Mailbox:
    box: mailbox.Mailbox
    match type:
        case "maildir":
            if _is_maildir(path) is False:
                raise RuntimeError(f"Not a maildir mailbox: {path}")
            box = cast(mailbox.Mailbox, mailbox.Maildir(path, create=True))
        case "mbox":
            if os.path.exists(path) and not os.path.isfile(path):
                raise RuntimeError(
                    f"Not a regular file - cannot contain an mbox mailbox: {path}"
                )
            box = cast(mailbox.Mailbox, mailbox.mbox(path, create=True))
        case _:
            raise ValueError(f"Bad mailbox type: {type}")

    box.lock()
    if delete_all:
        box.clear()
    return box


def _make_message(
    config: Config,
    recipient: Person,
    message: MessageInfo,
    env: jinja2.Environment,
) -> email.message.EmailMessage | None:
    assert config.event is not None

    participation = recipient.participation[config.event_id]

    # Choose language for the participant
    language = next(
        (lang for lang in recipient.languages if lang in message.translations), None
    )

    # Evaluate variables
    unevaluated_variables = {
        **config.event.variables,
        **message.variables,
    }
    globals = {
        "event_id": config.event.event_id,
        "language": language,
        "recipient": person_to_dict(recipient, config.event.event_id),
    }

    vars, complete = eval_variables(unevaluated_variables, globals=globals)

    if complete is not True:
        raise RuntimeError(f"Could not completely evaluate all variables: {complete}!")
    vars_and_globals = {**globals, **vars}

    # Check whether the recipient should receive this message
    result = eval_string(message.condition, vars_and_globals)
    if result is False:
        logging.debug(f"Skipping {recipient.named_email} - condition returned false")
        return None
    elif result is not True:
        raise RuntimeError(
            f"Condition expression failed for {recipient.named_email}: return value {repr (result)}"
        )

    # Show warning about bad language now after sending condition has been checked
    if language is None:
        language = message.translations[0]
        logging.warning(
            f"No suitable translation available for {recipient.named_email}, sending in `{language}' anyway!"
        )

    # Evaluate message headers
    unevaluated_headers = config.event.mail.headers
    headers, complete = eval_variables(unevaluated_headers, globals=vars_and_globals)

    if complete is not True:
        raise RuntimeError(
            f"Could not completely evaluate all message headers: {complete}!"
        )

    # Find and render content template
    filename = eval_string(message.filename, vars_and_globals)
    tmplt = env.get_template(filename)
    contents = tmplt.render(vars_and_globals)
    plain = _run_message_filter(config.event.mail.message_filter.plain, contents)
    html = _run_message_filter(config.event.mail.message_filter.html, contents)

    # Build a message
    msg = email.message.EmailMessage()

    # Find out and validate sender address and domain
    sender = next(
        (
            value
            for name, value in headers.items()
            if name.lower() in ["from", "sender"]
        ),
        None,
    )
    if sender is None:
        raise RuntimeError(f'Message sender not defined -- set "From" header')
    sender_name, sender_address = email.utils.parseaddr(sender)
    if not is_valid_email_address(sender_address):
        raise RuntimeError(
            f"Sender address `{sender_address}' is not a valid e-mail address"
        )
    if sender_name == "":
        raise RuntimeError(
            f"Sender address `{sender}' is defined without the naname part, refusing to send."
        )

    sender_domain = sender_address.split("@")[1]
    if sender_domain == "":
        raise RuntimeError(
            f"Failed to extract domain name from sender address: `{sender}'"
        )

    # Generate headers
    msg.add_header("Return-Path", f"<{sender_address}>")
    msg.add_header("Message-ID", email.utils.make_msgid(domain=sender_domain))
    msg.add_header("Date", email.utils.format_datetime(datetime.now().astimezone()))
    msg.add_header("From", sender)
    msg.add_header("To", recipient.named_email)

    # Add remaining headers, but don't add duplicates
    for name, value in headers.items():
        if name not in msg:
            msg.add_header(name, value)

    # Make this message a multipart/alternative
    msg.make_alternative()
    msg.add_alternative(plain, subtype="plain")
    msg.add_alternative(html, subtype="html")

    return msg


def _run_message_filter(filter_cmd: str, contents: str) -> str:
    result = subprocess.run(
        filter_cmd,
        input=contents,
        text=False,
        shell=True,
        check=True,
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    return result.stdout
