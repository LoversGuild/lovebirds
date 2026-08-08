from collections.abc import Callable
from uuid import uuid4

from lovebirds.cli.config import Config
from lovebirds.cli.resolve import resolve_refs
from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    Genitalia,
    Participation,
    ParticipationPhase,
    People,
    Person,
    PersonRefById,
    PersonRefByName,
    Registration,
)


class TestResolveRefs:
    def test_single_match_resolved(
        self,
        make_person: Callable[..., Person],
        make_registration: Callable[..., Registration],
        make_phase: Callable[..., ParticipationPhase],
        make_config: Callable[..., Config],
    ) -> None:
        alice = make_person(
            email=EmailAddress("alice@example.com"),
            first_name="Alice",
            last_name="Smith",
        )
        alice_id = uuid4()
        bob = make_person(
            email=EmailAddress("bob@example.com"),
            first_name="Bob",
            last_name="Jones",
            participation={
                "event1": Participation(
                    registrations=[
                        make_registration(
                            genitalia=Genitalia.penis,
                            avecs=[PersonRefByName(name="Alice Smith")],
                        )
                    ],
                    phases=[make_phase()],
                )
            },
        )
        people: People = {alice_id: alice, uuid4(): bob}
        config = make_config(people=people)
        resolve_refs(config)
        avec = bob.participation["event1"].registrations[0].avecs[0]
        assert isinstance(avec, PersonRefById)
        assert avec.id == alice_id

    def test_no_match_stays_unresolved(
        self,
        make_person: Callable[..., Person],
        make_registration: Callable[..., Registration],
        make_config: Callable[..., Config],
    ) -> None:
        bob = make_person(
            email=EmailAddress("bob@example.com"),
            first_name="Bob",
            last_name="Jones",
            participation={
                "event1": Participation(
                    registrations=[
                        make_registration(
                            genitalia=Genitalia.penis,
                            avecs=[PersonRefByName(name="Unknown Person")],
                        )
                    ]
                )
            },
        )
        people: People = {uuid4(): bob}
        config = make_config(people=people)
        resolve_refs(config)
        avec = bob.participation["event1"].registrations[0].avecs[0]
        assert isinstance(avec, PersonRefByName)

    def test_ambiguous_stays_unresolved(
        self,
        make_person: Callable[..., Person],
        make_registration: Callable[..., Registration],
        make_config: Callable[..., Config],
    ) -> None:
        alice1 = make_person(
            email=EmailAddress("alice1@example.com"),
            first_name="Alice",
            last_name="Smith",
        )
        alice2 = make_person(
            email=EmailAddress("alice2@example.com"),
            first_name="Alice",
            last_name="Smith",
        )
        bob = make_person(
            email=EmailAddress("bob@example.com"),
            first_name="Bob",
            last_name="Jones",
            participation={
                "event1": Participation(
                    registrations=[
                        make_registration(
                            genitalia=Genitalia.penis,
                            avecs=[PersonRefByName(name="Alice Smith")],
                        )
                    ]
                )
            },
        )
        people: People = {uuid4(): alice1, uuid4(): alice2, uuid4(): bob}
        config = make_config(people=people)
        resolve_refs(config)
        avec = bob.participation["event1"].registrations[0].avecs[0]
        assert isinstance(avec, PersonRefByName)

    def test_save_called(self, make_config: Callable[..., Config]) -> None:
        config = make_config()
        resolve_refs(config)
        config.save_people.assert_called_once()  # type: ignore[attr-defined]
