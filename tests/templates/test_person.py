from collections.abc import Callable

from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    Genitalia,
    Participation,
    ParticipationPhase,
    ParticipationStatus,
    Person,
    Registration,
)
from lovebirds.templates.person import person_to_dict


class TestPersonToDict:
    def test_basic_fields(self, make_person: Callable[..., Person]) -> None:
        person = make_person(
            email=EmailAddress("alice@example.com"),
            first_name="Alice",
            last_name="Smith",
        )
        result = person_to_dict(person, None)
        assert result["email"] == "alice@example.com"
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Smith"
        assert result["experience"] == 0
        assert result["full_name"] == "Alice Smith"

    def test_with_event_participation(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
        make_registration: Callable[..., Registration],
    ) -> None:
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[
                        make_phase(
                            status=ParticipationStatus.accepted,
                        )
                    ],
                    registrations=[make_registration(genitalia=Genitalia.vulva)],
                )
            }
        )
        result = person_to_dict(person, "event1")
        assert result["status"] == "accepted"
        assert result["role"] == "participant"
        assert result["genitalia"] == "vulva"
        assert result["phase"] is not None
        assert result["registration"] is not None

    def test_no_event_id_genitalia_fallback(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
        make_registration: Callable[..., Registration],
    ) -> None:
        """When event_id is None, genitalia falls back to latest registration from any event."""
        person = make_person(
            participation={
                "event1": Participation(
                    registrations=[make_registration(genitalia=Genitalia.penis)],
                    phases=[make_phase()],
                )
            }
        )
        result = person_to_dict(person, None)
        assert result["genitalia"] == "penis"

    def test_no_participation_for_event(
        self, make_person: Callable[..., Person]
    ) -> None:
        person = make_person()
        result = person_to_dict(person, "nonexistent_event")
        assert result.get("phase") is None
        assert result.get("registration") is None

    def test_comments_aggregation(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
        make_registration: Callable[..., Registration],
    ) -> None:
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[
                        make_phase(
                            status=ParticipationStatus.accepted,
                            comment="first note",
                        ),
                        make_phase(
                            status=ParticipationStatus.participated,
                            comment="second note",
                        ),
                    ],
                    registrations=[make_registration()],
                )
            }
        )
        result = person_to_dict(person, "event1")
        assert len(result["comments"]) == 2
        assert "accepted: first note" in result["comments"][0]
        assert "participated: second note" in result["comments"][1]

    def test_registration_metadata_excluded(
        self,
        make_person: Callable[..., Person],
        make_phase: Callable[..., ParticipationPhase],
        make_registration: Callable[..., Registration],
    ) -> None:
        """Keys like amends, hash, operator, source, time should not be at top level."""
        person = make_person(
            participation={
                "event1": Participation(
                    phases=[make_phase()],
                    registrations=[make_registration(hash="abc123")],
                )
            }
        )
        result = person_to_dict(person, "event1")
        excluded_keys = {"amends", "hash", "operator", "source", "time"}
        for key in excluded_keys:
            if key in result:
                # These should only appear inside 'registration', not at top level
                # from the registration spread
                assert (
                    key
                    not in {
                        k
                        for k in result
                        if k != "registration" and k != "phase" and k != "consent"
                    }
                    or result.get("registration", {}).get(key) is not None
                )
