from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from uuid import UUID, uuid4

from lovebirds.cli.config import Config
from lovebirds.cli.phase import add_phase
from lovebirds.models.people import (
    Consent,
    InformationSource,
    Participation,
    ParticipationRole,
    ParticipationStatus,
    People,
    Person,
)


class TestAddPhase:
    def _config(
        self,
        make_config: Callable[..., Config],
        people: People,
        **kwargs: Any,
    ) -> Config:
        defaults: dict[str, Any] = dict(
            expr="True",
            new_status="accepted",
            new_role="participant",
            new_comment=None,
            source="organizer",
            operator="op@example.com",
            time=None,
        )
        defaults.update(kwargs)
        return make_config(
            people=people,
            operator_id=UUID("00000000-0000-0000-0000-000000000000"),
            **defaults,
        )

    def test_new_participation_created(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        person = make_person()
        people: People = {uuid4(): person}
        config = self._config(make_config, people)
        add_phase(config)
        assert "event1" in person.participation
        assert len(person.participation["event1"].phases) == 1
        assert (
            person.participation["event1"].phases[0].status
            == ParticipationStatus.accepted
        )

    def test_phase_appended_to_existing(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
    ) -> None:
        person = make_person(
            participation={
                "event1": make_participation(
                    status=ParticipationStatus.invited,
                ),
            }
        )
        people: People = {uuid4(): person}
        config = self._config(make_config, people)
        add_phase(config)
        assert len(person.participation["event1"].phases) == 2

    def test_same_status_updates_in_place(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
    ) -> None:
        person = make_person(
            participation={
                "event1": make_participation(
                    status=ParticipationStatus.accepted,
                ),
            }
        )
        people: People = {uuid4(): person}
        config = self._config(make_config, people)
        add_phase(config)
        assert len(person.participation["event1"].phases) == 1

    def test_locked_person_skipped(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        person = make_person(locked=True)
        people: People = {uuid4(): person}
        config = self._config(make_config, people)
        add_phase(config)
        assert "event1" not in person.participation

    def test_legacy_person_skipped(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        person = make_person()
        person.consent = Consent(legacy=True)
        people: People = {uuid4(): person}
        config = self._config(make_config, people)
        add_phase(config)
        assert "event1" not in person.participation

    def test_false_expression_no_phase(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        person = make_person()
        people: People = {uuid4(): person}
        config = self._config(make_config, people, expr="False")
        add_phase(config)
        assert "event1" not in person.participation

    def test_save_people_called_with_the_status_as_commit_detail(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        """The status goes into the commit message, so a glance at the git log
        says what each run did rather than just that a phase was added.
        """
        person = make_person()
        people: People = {uuid4(): person}
        config = self._config(make_config, people)
        add_phase(config)
        config.save_people.assert_called_once_with(  # type: ignore[attr-defined]
            commit_detail="accepted"
        )

    def test_role_is_inherited_from_the_previous_phase(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
    ) -> None:
        """Omitting --role keeps whatever the person already was, so a status
        change does not quietly demote an organiser to a participant."""
        person = make_person(
            participation={
                "event1": make_participation(
                    status=ParticipationStatus.invited,
                    role=ParticipationRole.organizer,
                )
            }
        )
        people: People = {uuid4(): person}
        add_phase(self._config(make_config, people, new_role=None))
        phases = person.participation["event1"].phases
        assert len(phases) == 2, "a new phase should have been appended"
        assert phases[-1].status is ParticipationStatus.accepted
        assert phases[-1].role is ParticipationRole.organizer

    def test_comment_is_inherited_from_the_previous_phase(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., Any],
        make_config: Callable[..., Config],
    ) -> None:
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[
                        make_phase(
                            status=ParticipationStatus.invited,
                            comment="Met at the spring party",
                        )
                    ]
                )
            }
        )
        people: People = {uuid4(): person}
        add_phase(self._config(make_config, people, new_comment=None))
        phases = person.participation["event1"].phases
        assert len(phases) == 2, "a new phase should have been appended"
        assert phases[-1].status is ParticipationStatus.accepted
        assert phases[-1].comment == "Met at the spring party"

    def test_person_with_no_history_and_no_role_is_skipped(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        """With nothing to inherit from, a role has to be given explicitly.

        Note the empty Participation left behind: add_phase creates it before
        deciding to skip, so the person ends up recorded as taking part in the
        event with no phases at all.
        """
        person = make_person()
        people: People = {uuid4(): person}
        add_phase(self._config(make_config, people, new_role=None))
        assert person.participation["event1"].phases == []

    def test_person_with_no_history_and_no_source_is_skipped(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        """Same for the information source. The run still exits successfully,
        so the log line is the only sign that nothing happened."""
        person = make_person()
        people: People = {uuid4(): person}
        add_phase(self._config(make_config, people, source=None))
        assert person.participation["event1"].phases == []

    def test_source_is_inherited_when_the_status_is_unchanged(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., Any],
        make_config: Callable[..., Config],
    ) -> None:
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[
                        make_phase(
                            status=ParticipationStatus.accepted,
                            source=InformationSource.email,
                        )
                    ]
                )
            }
        )
        people: People = {uuid4(): person}
        add_phase(
            self._config(
                make_config, people, source=None, new_comment="Confirmed by phone"
            )
        )
        phases = person.participation["event1"].phases
        assert len(phases) == 1
        assert phases[0].source is InformationSource.email
        assert phases[0].comment == "Confirmed by phone"

    def test_explicit_time_is_used_for_the_new_phase(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        """--time backdates a phase, e.g. marking attendance after the event."""
        person = make_person()
        people: People = {uuid4(): person}
        add_phase(self._config(make_config, people, time="2026-07-18T23:00:00+03:00"))
        recorded = person.participation["event1"].phases[-1].time
        assert recorded == datetime.fromisoformat("2026-07-18T23:00:00+03:00")

    def test_missing_expression_is_an_error(
        self, make_config: Callable[..., Config]
    ) -> None:
        with pytest.raises(RuntimeError, match="No expression defined"):
            add_phase(self._config(make_config, {}, expr=None))

    def test_non_boolean_expression_is_an_error(
        self, make_person: Callable[..., Person], make_config: Callable[..., Config]
    ) -> None:
        """A filter that returns a string is a mistake, not a truthy match."""
        people: People = {uuid4(): make_person()}
        with pytest.raises(RuntimeError, match="should be `bool'"):
            add_phase(self._config(make_config, people, expr="email"))
