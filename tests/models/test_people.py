from collections.abc import Callable, Iterator
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    Genitalia,
    InformationSource,
    Participation,
    ParticipationPhase,
    ParticipationRole,
    ParticipationStatus,
    People,
    Person,
    Registration,
    sorted_people,
)


class TestPersonExperience:
    def test_no_participation(self, make_person: Callable[..., Person]) -> None:
        person = make_person()
        assert person.experience == 0

    def test_counts_participated_status(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[make_phase(status=ParticipationStatus.participated)]
                ),
                "event2": Participation(
                    phases=[make_phase(status=ParticipationStatus.participated)]
                ),
            }
        )
        assert person.experience == 2

    def test_does_not_count_accepted(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[make_phase(status=ParticipationStatus.accepted)]
                ),
            }
        )
        assert person.experience == 0


class TestPersonFullName:
    def test_both_names(self, make_person: Callable[..., Person]) -> None:
        person = make_person(first_name="Alice", last_name="Smith")
        assert person.full_name == "Alice Smith"

    def test_first_only(self, make_person: Callable[..., Person]) -> None:
        person = make_person(first_name="Alice", last_name=None)
        assert person.full_name == "Alice"

    def test_last_only(self, make_person: Callable[..., Person]) -> None:
        person = make_person(first_name=None, last_name="Smith")
        assert person.full_name == "Smith"

    def test_neither(self, make_person: Callable[..., Person]) -> None:
        person = make_person(first_name=None, last_name=None)
        assert person.full_name is None


class TestPersonAliasName:
    def test_with_aliases(self, make_person: Callable[..., Person]) -> None:
        person = make_person(
            first_name="Alice", last_name="Smith", aliases=["Ali", "Ally"]
        )
        assert person.alias_name == "Alice (Ali/Ally) Smith"

    def test_without_aliases(self, make_person: Callable[..., Person]) -> None:
        person = make_person(first_name="Alice", last_name="Smith", aliases=[])
        assert person.alias_name == "Alice Smith"

    def test_no_names_falls_back_to_email(
        self, make_person: Callable[..., Person]
    ) -> None:
        person = make_person(
            email=EmailAddress("anon@example.com"),
            first_name=None,
            last_name=None,
            aliases=[],
        )
        assert person.alias_name == "anon@example.com"


class TestPersonNamedEmail:
    def test_with_name(self, make_person: Callable[..., Person]) -> None:
        person = make_person(
            email=EmailAddress("alice@example.com"),
            first_name="Alice",
            last_name="Smith",
        )
        assert person.named_email == "Alice Smith <alice@example.com>"

    def test_without_name(self, make_person: Callable[..., Person]) -> None:
        person = make_person(
            email=EmailAddress("anon@example.com"),
            first_name=None,
            last_name=None,
        )
        assert person.named_email == "anon@example.com"


class TestRegistrationEqualInfo:
    def test_same_content_different_time_hash(
        self, make_registration: Callable[..., Registration]
    ) -> None:
        shared_operator = uuid4()
        reg1 = make_registration(
            time=datetime(2025, 1, 1), hash="abc", operator=shared_operator
        )
        reg2 = make_registration(
            time=datetime(2025, 6, 1), hash="def", operator=shared_operator
        )
        assert reg1.equal_info(reg2) is True

    def test_different_content(
        self, make_registration: Callable[..., Registration]
    ) -> None:
        reg1 = make_registration(genitalia=Genitalia.vulva)
        reg2 = make_registration(genitalia=Genitalia.penis)
        assert reg1.equal_info(reg2) is False


class TestSortedPeople:
    def test_alphabetical_sort(self, make_person: Callable[..., Person]) -> None:
        zoe = make_person(
            email=EmailAddress("zoe@example.com"), first_name="Zoe", last_name="Adams"
        )
        alice = make_person(
            email=EmailAddress("alice@example.com"),
            first_name="Alice",
            last_name="Baker",
        )
        people: People = {uuid4(): zoe, uuid4(): alice}
        result = sorted_people(people)
        values = list(result.values())
        assert values[0].email == EmailAddress("alice@example.com")
        assert values[1].email == EmailAddress("zoe@example.com")

    def test_returns_deep_copy(self, make_person: Callable[..., Person]) -> None:
        person = make_person()
        people: People = {uuid4(): person}
        result = sorted_people(people)
        result_person = list(result.values())[0]
        assert result_person is not person
        assert result_person.email == person.email


@pytest.fixture
def local_timezone() -> Iterator[Callable[[str], None]]:
    """Pin the process's local timezone for the duration of a test.

    Fixed-offset POSIX values are used rather than zone names so that no
    timezone database has to be installed. Note the POSIX sign convention is
    inverted: "XXX-3" means UTC+3.
    """
    original = os.environ.get("TZ")

    def set_tz(value: str) -> None:
        os.environ["TZ"] = value
        time.tzset()

    yield set_tz
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


class TestLastContact:
    """`last_contact` drives "who have we not spoken to in a while" queries.

    Event ids are ISO dates, so the id itself dates the event when a phase
    carries no timestamp of its own.
    """

    def test_no_participation_means_never_contacted(
        self, make_person: Callable[..., Person]
    ) -> None:
        assert make_person().last_contact is None

    def test_a_phase_timestamp_is_used_when_present(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        stamped = datetime(2026, 3, 1, tzinfo=timezone.utc)
        person = make_person(
            participation={
                "2026-06-01": Participation(
                    phases=[
                        make_phase(status=ParticipationStatus.accepted, time=stamped)
                    ]
                )
            }
        )
        assert person.last_contact == stamped

    def test_the_event_id_is_read_as_a_local_date(
        self,
        local_timezone: Callable[[str], None],
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        """A phase with no timestamp falls back to the event id, which is a
        bare date. It is naive, and astimezone() reads a naive value as local
        time -- so the answer depends on the machine's timezone. Both this test
        and the next pin the zone to make that explicit.
        """
        local_timezone("XXX-3")  # UTC+3
        person = make_person(
            participation={
                "2026-06-01": Participation(
                    phases=[make_phase(status=ParticipationStatus.accepted, time=None)]
                )
            }
        )
        assert person.last_contact == datetime(2026, 5, 31, 21, tzinfo=timezone.utc)

    def test_the_same_database_shifts_with_the_operators_timezone(
        self,
        local_timezone: Callable[[str], None],
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        """The very same record read west of Greenwich gives a different
        instant. Worth knowing before comparing last_contact across machines."""
        local_timezone("XXX8")  # UTC-8
        person = make_person(
            participation={
                "2026-06-01": Participation(
                    phases=[make_phase(status=ParticipationStatus.accepted, time=None)]
                )
            }
        )
        assert person.last_contact == datetime(2026, 6, 1, 8, tzinfo=timezone.utc)

    def test_pseudo_events_are_ignored(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        """An id that is not a date names a pseudo-event, not a real meeting."""
        person = make_person(
            participation={
                "mailing-list": Participation(
                    phases=[make_phase(status=ParticipationStatus.accepted, time=None)]
                )
            }
        )
        assert person.last_contact is None

    def test_the_most_recent_event_wins(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        early = datetime(2026, 1, 1, tzinfo=timezone.utc)
        late = datetime(2026, 9, 1, tzinfo=timezone.utc)
        person = make_person(
            participation={
                "2026-01-01": Participation(
                    phases=[make_phase(status=ParticipationStatus.accepted, time=early)]
                ),
                "2026-09-01": Participation(
                    phases=[make_phase(status=ParticipationStatus.accepted, time=late)]
                ),
            }
        )
        assert person.last_contact == late
