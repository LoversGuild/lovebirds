from collections.abc import Callable
from unittest.mock import MagicMock, patch
from uuid import uuid4

from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    Participation,
    ParticipationPhase,
    ParticipationStatus,
    People,
    Person,
)
from lovebirds.statistics import (
    EventParticipantsStatistics,
    get_event_participants_statistics,
)


def _person_with_event(
    make_person: Callable[..., Person],
    make_participation: Callable[..., Participation],
    email: str,
    birth_year: int | None = 1990,
    status: ParticipationStatus = ParticipationStatus.accepted,
) -> Person:
    return make_person(
        email=EmailAddress(email),
        birth_year=birth_year,
        participation={
            "event1": make_participation(status=status),
        },
    )


class TestGetEventParticipantsStatistics:
    @patch("lovebirds.statistics.calculate_age")
    def test_basic_statistics(
        self,
        mock_age: MagicMock,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
    ) -> None:
        mock_age.side_effect = [25, 30, 35]
        people: People = {
            uuid4(): _person_with_event(
                make_person, make_participation, "a@e.com", 1999
            ),
            uuid4(): _person_with_event(
                make_person, make_participation, "b@e.com", 1994
            ),
            uuid4(): _person_with_event(
                make_person, make_participation, "c@e.com", 1989
            ),
        }
        result = get_event_participants_statistics("event1", people)
        assert result is not None
        assert result.count == 3
        assert result.min_age == 25
        assert result.max_age == 35
        assert result.age_average == 30
        assert "\u2013" in result.age_range  # en-dash

    def test_no_participants_returns_none(self) -> None:
        people: People = {}
        result = get_event_participants_statistics("event1", people)
        assert result is None

    @patch("lovebirds.statistics.calculate_age")
    def test_filters_by_last_phase(
        self,
        mock_age: MagicMock,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
    ) -> None:
        """A person who was accepted then withdrew should be excluded."""
        mock_age.return_value = 30
        person = make_person(
            email=EmailAddress("x@e.com"),
            birth_year=1994,
            participation={
                "event1": Participation(
                    phases=[
                        make_phase(status=ParticipationStatus.accepted),
                        make_phase(status=ParticipationStatus.withdrew),
                    ]
                )
            },
        )
        people: People = {uuid4(): person}
        result = get_event_participants_statistics("event1", people)
        assert result is None

    @patch("lovebirds.statistics.calculate_age")
    def test_both_accepted_and_participated_included(
        self,
        mock_age: MagicMock,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
    ) -> None:
        mock_age.side_effect = [25, 30]
        people: People = {
            uuid4(): _person_with_event(
                make_person,
                make_participation,
                "a@e.com",
                status=ParticipationStatus.accepted,
            ),
            uuid4(): _person_with_event(
                make_person,
                make_participation,
                "b@e.com",
                status=ParticipationStatus.participated,
            ),
        }
        result = get_event_participants_statistics("event1", people)
        assert result is not None
        assert result.count == 2

    @patch("lovebirds.statistics.calculate_age")
    def test_age_clamped_to_18(
        self,
        mock_age: MagicMock,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
    ) -> None:
        mock_age.return_value = 16
        people: People = {
            uuid4(): _person_with_event(
                make_person, make_participation, "a@e.com", 2008
            ),
        }
        result = get_event_participants_statistics("event1", people)
        assert result is not None
        assert result.min_age == 18

    @patch("lovebirds.statistics.calculate_age")
    def test_age_range_uses_en_dash(
        self,
        mock_age: MagicMock,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
    ) -> None:
        mock_age.side_effect = [25, 35]
        people: People = {
            uuid4(): _person_with_event(make_person, make_participation, "a@e.com"),
            uuid4(): _person_with_event(make_person, make_participation, "b@e.com"),
        }
        result = get_event_participants_statistics("event1", people)
        assert result is not None
        assert result.age_range == "25\u201335"
