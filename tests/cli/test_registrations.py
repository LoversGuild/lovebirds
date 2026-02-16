from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch
from uuid import UUID, uuid4

import pytest

import lovebirds.cli.edit as edit
from lovebirds.cli.config import Config
from lovebirds.cli.registrations import (
    RawRegistration,
    _find_person_by_email_interactive,
    _group_raw_registrations,
    _register_participation,
    _registration_sort_key,
    import_registrations,
)
from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    Consent,
    ParticipationStatus,
    InformationSource,
    Genitalia,
    Interest,
    People,
    Person,
    Registration,
    StayingOvernight,
)


OPERATOR_ID = UUID("00000000-0000-0000-0000-000000000000")

RAW_EMAIL = EmailAddress("alice.smith@example.com")
RAW_PHONE = "+358401234567"
RAW_BIRTH_YEAR = 1990


def make_raw(**kwargs: Any) -> RawRegistration:
    defaults: dict[str, Any] = dict(
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        event_id="event1",
        first_name="Alice",
        last_name="Smith",
        email=RAW_EMAIL,
        phone_number=RAW_PHONE,
        birth_year=RAW_BIRTH_YEAR,
        language_preference="en",
        allergies="",
        genitalia=Genitalia.vulva,
        interest_in_sensuality_with_vulvae=Interest.high,
        interest_in_sensuality_with_penes=Interest.no,
        interest_in_sex_with_vulvae=Interest.high,
        interest_in_sex_with_penes=Interest.no,
        age_min=20,
        age_max=60,
        avecs="",
        non_gratas="",
        staying_overnight=StayingOvernight.no,
        info="",
        magic_word="",
        consent=True,
    )
    defaults.update(kwargs)
    return RawRegistration(**defaults)


class Prompts:
    """Records the interactive prompts `register` issues, and answers them.

    Every answer defaults to the value the prompt was pre-filled with, so a
    test only has to override the one answer it cares about.
    """

    def __init__(self) -> None:
        self.emails: list[str] = []
        self.email_reply: str | None = None
        self.person_action = "new"
        self.old_email_reply: str | None = None
        self.amend = False
        self.edited: list[Any] = []
        self.choices_seen: list[set[str]] = []

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def input_(
            prompt: str, default: str | None = None, init: str | None = None
        ) -> str:
            return init or default or ""

        def input_validated(
            prompt: str,
            predicate: Callable[[str], bool],
            completer: Callable[[str, int], str | None] | None = None,
            default: str | None = None,
            init: str | None = None,
        ) -> str:
            return init or default or ""

        def input_email(
            prompt: str, default: str | None = None, init: str | None = None
        ) -> EmailAddress:
            self.emails.append(init or default or "")
            return EmailAddress(self.email_reply or init or default or "")

        def input_choice(
            prompt: str,
            choices: set[str],
            default: str | None = None,
            init: str | None = None,
        ) -> str:
            self.choices_seen.append(choices)
            if choices == {"new", "update"}:
                return self.person_action
            if self.old_email_reply is not None:
                return self.old_email_reply
            return init if init in choices else sorted(choices)[0]

        def input_yes_no(prompt: str, default: bool | None = None) -> bool:
            return self.amend

        def edit_as_yaml(
            source_type: Any, target_type: Any, data: Any, prefix: str
        ) -> Any:
            """Stand in for $EDITOR: hand the record back unchanged."""
            self.edited.append(data)
            return data

        monkeypatch.setattr(edit, "input", input_)
        monkeypatch.setattr(edit, "input_validated", input_validated)
        monkeypatch.setattr(edit, "input_email", input_email)
        monkeypatch.setattr(edit, "input_choice", input_choice)
        monkeypatch.setattr(edit, "input_yes_no", input_yes_no)
        monkeypatch.setattr(edit, "edit_as_yaml", edit_as_yaml)


@pytest.fixture
def prompts(monkeypatch: pytest.MonkeyPatch) -> Prompts:
    recorder = Prompts()
    recorder.install(monkeypatch)
    return recorder


class TestRegisterEmailConfirmation:
    """A changed email address must be confirmed by the operator.

    Registrations are self-service, so a typo in the form would otherwise
    silently overwrite a known-good address, or create a duplicate person.
    """

    def _config(
        self,
        make_config: Callable[..., Config],
        people: People,
    ) -> Config:
        return make_config(
            people=people,
            operator_id=OPERATOR_ID,
            subcommand="register",
            operator="op@example.com",
            files=[],
        )

    def _matching_person(
        self, make_person: Callable[..., Person], **kwargs: Any
    ) -> Person:
        """A person whose every field matches the raw registration, so that
        only the field under test triggers a prompt."""
        defaults: dict[str, Any] = dict(
            email=RAW_EMAIL,
            first_name="Alice",
            last_name="Smith",
            birth_year=RAW_BIRTH_YEAR,
            phone=RAW_PHONE,
            languages=["en"],
        )
        defaults.update(kwargs)
        return make_person(**defaults)

    def test_changed_email_is_confirmed(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = self._matching_person(
            make_person, email=EmailAddress("alice@example.com")
        )
        person_id = uuid4()
        prompts.person_action = "update"
        config = self._config(make_config, {person_id: person})

        _register_participation(config, make_raw())

        assert prompts.emails == [RAW_EMAIL]
        assert person.email == RAW_EMAIL

    def test_operator_can_correct_a_typo(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = self._matching_person(
            make_person, email=EmailAddress("alice@example.com")
        )
        person_id = uuid4()
        prompts.person_action = "update"
        prompts.email_reply = "alice.smith@example.org"
        config = self._config(make_config, {person_id: person})

        _register_participation(config, make_raw())

        assert person.email == EmailAddress("alice.smith@example.org")

    def test_unchanged_email_is_not_confirmed(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = self._matching_person(make_person)
        config = self._config(make_config, {uuid4(): person})

        _register_participation(config, make_raw())

        assert prompts.emails == []
        assert person.email == RAW_EMAIL

    def test_new_person_email_is_confirmed(
        self,
        prompts: Prompts,
        make_config: Callable[..., Config],
    ) -> None:
        people: People = {}
        prompts.person_action = "new"
        prompts.email_reply = "alice.smith@example.org"
        config = self._config(make_config, people)

        _register_participation(config, make_raw())

        assert prompts.emails == [RAW_EMAIL]
        assert len(people) == 1
        assert next(iter(people.values())).email == EmailAddress(
            "alice.smith@example.org"
        )


class TestGroupRawRegistrations:
    def test_groups_by_event_then_by_email(self) -> None:
        regs = [
            make_raw(event_id="summer", email=EmailAddress("a@example.com")),
            make_raw(event_id="summer", email=EmailAddress("b@example.com")),
            make_raw(event_id="winter", email=EmailAddress("a@example.com")),
        ]
        grouped = _group_raw_registrations(regs)
        assert set(grouped) == {"summer", "winter"}
        assert set(grouped["summer"]) == {"a@example.com", "b@example.com"}
        assert set(grouped["winter"]) == {"a@example.com"}

    def test_one_persons_registrations_are_ordered_oldest_first(self) -> None:
        """Registrations are replayed in submission order so that a later
        amendment is applied on top of the entry it amends."""
        early = make_raw(timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc))
        late = make_raw(timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc))
        grouped = _group_raw_registrations([late, early])
        assert grouped["event1"][RAW_EMAIL] == [early, late]


class TestRegistrationSortKey:
    def test_plain_registration_sorts_on_its_own_time(
        self, make_registration: Callable[..., Registration]
    ) -> None:
        time = datetime(2026, 5, 1, tzinfo=timezone.utc)
        reg = make_registration(time=time)
        assert _registration_sort_key(reg) == (time, time)

    def test_amendment_sorts_beside_the_entry_it_amends(
        self, make_registration: Callable[..., Registration]
    ) -> None:
        """An amendment keys on the amended entry's time, so it lands directly
        after it rather than at the end of the list."""
        original_time = datetime(2026, 5, 1, tzinfo=timezone.utc)
        other_time = datetime(2026, 5, 15, tzinfo=timezone.utc)
        amend_time = datetime(2026, 6, 1, tzinfo=timezone.utc)

        original = make_registration(time=original_time)
        other = make_registration(time=other_time)
        amendment = make_registration(time=amend_time, amends=original_time)

        ordered = sorted([other, amendment, original], key=_registration_sort_key)
        assert ordered == [original, amendment, other]

    def test_registration_without_a_time_is_rejected(
        self, make_registration: Callable[..., Registration]
    ) -> None:
        with pytest.raises(ValueError, match="timestampless"):
            _registration_sort_key(make_registration(time=None))


class TestImportRegistrations:
    @patch("lovebirds.cli.registrations._register_participation")
    @patch("lovebirds.cli.registrations._load_raw_registration")
    def test_saves_after_every_registration(
        self,
        mock_load: MagicMock,
        mock_register: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        """Each registration is saved as it is processed, so an abort partway
        through keeps the ones already dealt with. Only the first save takes a
        backup: the rest of the run would just copy its own output."""
        mock_load.side_effect = [
            make_raw(email=EmailAddress("a@example.com")),
            make_raw(email=EmailAddress("b@example.com")),
        ]
        config = make_config(files=["a.gpg", "b.gpg"], operator_id=OPERATOR_ID)
        import_registrations(config)
        assert mock_register.call_count == 2
        config.save_people.assert_has_calls(  # type: ignore[attr-defined]
            [call(backup=True), call(backup=False)]
        )

    @patch("lovebirds.cli.registrations._register_participation")
    @patch("lovebirds.cli.registrations._load_raw_registration")
    def test_processes_a_persons_registrations_oldest_first(
        self,
        mock_load: MagicMock,
        mock_register: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        early = make_raw(timestamp=datetime(2026, 5, 1, tzinfo=timezone.utc))
        late = make_raw(timestamp=datetime(2026, 6, 1, tzinfo=timezone.utc))
        mock_load.side_effect = [late, early]
        config = make_config(files=["late.gpg", "early.gpg"], operator_id=OPERATOR_ID)
        import_registrations(config)
        processed = [c[0][1] for c in mock_register.call_args_list]
        assert processed == [early, late]


class TestFindPersonByEmailInteractive:
    """Matching an incoming registration to someone already in the database."""

    def _people(self, make_person: Callable[..., Person]) -> People:
        return {
            uuid4(): make_person(
                email=EmailAddress("alice@example.com"),
                first_name="Alice",
                last_name="Ahonen",
            ),
            uuid4(): make_person(
                email=EmailAddress("bob@example.com"),
                first_name="Bob",
                last_name="Berg",
            ),
        }

    def test_a_known_address_matches_without_asking(
        self, prompts: Prompts, make_person: Callable[..., Person]
    ) -> None:
        people = self._people(make_person)
        raw = make_raw(email=EmailAddress("bob@example.com"))
        found = _find_person_by_email_interactive(people, raw)
        assert found is not None and found.first_name == "Bob"
        assert prompts.choices_seen == [], "no question should have been asked"

    def test_answering_new_creates_nobody_here(
        self, prompts: Prompts, make_person: Callable[..., Person]
    ) -> None:
        """Returning None is how it signals `make a new person for this'."""
        people = self._people(make_person)
        prompts.person_action = "new"
        assert _find_person_by_email_interactive(people, make_raw()) is None

    def test_answering_update_picks_the_person_by_their_old_address(
        self, prompts: Prompts, make_person: Callable[..., Person]
    ) -> None:
        """Someone who mistyped their address, or changed it since last time,
        is matched to their existing record rather than duplicated."""
        people = self._people(make_person)
        prompts.person_action = "update"
        prompts.old_email_reply = "alice@example.com"
        found = _find_person_by_email_interactive(people, make_raw())
        assert found is not None and found.first_name == "Alice"
        assert {"new", "update"} in prompts.choices_seen

    def test_the_old_address_is_offered_as_a_closed_choice(
        self, prompts: Prompts, make_person: Callable[..., Person]
    ) -> None:
        """Only addresses already in the database may be picked, so a typo
        cannot invent a person."""
        people = self._people(make_person)
        prompts.person_action = "update"
        prompts.old_email_reply = "bob@example.com"
        _find_person_by_email_interactive(people, make_raw())
        offered = prompts.choices_seen[-1]
        assert offered == {"alice@example.com", "bob@example.com"}


class TestRegisterParticipationHandling:
    def _config(self, make_config: Callable[..., Config], people: People) -> Config:
        return make_config(
            people=people,
            operator_id=OPERATOR_ID,
            subcommand="register",
            operator="op@example.com",
            files=[],
        )

    def test_a_locked_person_keeps_their_lock(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """A lock means `do not touch this record automatically'. The
        registration is still filed, but neither the lock nor the consent
        fields are rewritten from the form."""
        person = make_person(email=RAW_EMAIL, locked=True)
        person.consent = Consent(legacy=True, valid=False)
        config = self._config(make_config, {uuid4(): person})
        _register_participation(config, make_raw())
        assert person.locked is True
        assert person.consent.valid is False, "consent must be left as it was"
        assert person.consent.legacy is True
        assert len(person.participation["event1"].registrations) == 1

    def test_registering_clears_a_legacy_consent(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Filling in the form is fresh consent, so the legacy marker goes."""
        person = make_person(email=RAW_EMAIL)
        person.consent = Consent(legacy=True, valid=False)
        config = self._config(make_config, {uuid4(): person})
        _register_participation(config, make_raw())
        assert person.consent.valid is True
        assert person.consent.legacy is False

    def test_the_same_registration_is_not_imported_twice(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Re-running register over the same file must not duplicate entries."""
        person = make_person(email=RAW_EMAIL)
        config = self._config(make_config, {uuid4(): person})
        raw = make_raw()
        _register_participation(config, raw)
        _register_participation(config, raw)
        assert len(person.participation["event1"].registrations) == 1

    def test_amending_appends_an_organizer_entry_linked_to_the_original(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """History is append-only: the amendment is a new record pointing at
        the one it corrects, not an edit of it."""
        person = make_person(email=RAW_EMAIL)
        config = self._config(make_config, {uuid4(): person})
        prompts.amend = True
        raw = make_raw()
        _register_participation(config, raw)

        registrations = person.participation["event1"].registrations
        assert len(registrations) == 2
        original, amendment = registrations
        assert original.source is InformationSource.registration_form
        assert amendment.source is InformationSource.organizer
        assert amendment.amends == original.time
        assert amendment.hash is None, "an amendment is not a form submission"
        assert prompts.edited, "the operator should have been shown the record"

    def test_declining_to_amend_leaves_one_entry(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        person = make_person(email=RAW_EMAIL)
        config = self._config(make_config, {uuid4(): person})
        prompts.amend = False
        _register_participation(config, make_raw())
        assert len(person.participation["event1"].registrations) == 1

    def test_a_second_registration_updates_the_existing_registered_phase(
        self,
        prompts: Prompts,
        make_person: Callable[..., Person],
        make_config: Callable[..., Config],
    ) -> None:
        """Signing up again does not stack another `registered' phase; the
        existing one is refreshed instead."""
        person = make_person(email=RAW_EMAIL)
        config = self._config(make_config, {uuid4(): person})
        _register_participation(config, make_raw())
        phases_after_first = list(person.participation["event1"].phases)
        assert [p.status for p in phases_after_first] == [
            ParticipationStatus.registered
        ]

        _register_participation(config, make_raw(info="Changed my mind about food"))
        phases = person.participation["event1"].phases
        assert [p.status for p in phases] == [ParticipationStatus.registered]
        assert len(person.participation["event1"].registrations) == 2
