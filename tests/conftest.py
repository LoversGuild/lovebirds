from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from datetime import datetime, timezone

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
)


@pytest.fixture
def make_person() -> Callable[..., Person]:
    def _make(**kwargs: Any) -> Person:
        defaults: dict[str, Any] = dict(
            email=EmailAddress("test@example.com"),
            first_name="Test",
            last_name="Person",
            languages=["en"],
            birth_year=1990,
        )
        defaults.update(kwargs)
        return Person(**defaults)

    return _make


@pytest.fixture
def make_phase() -> Callable[..., ParticipationPhase]:
    def _make(**kwargs: Any) -> ParticipationPhase:
        defaults: dict[str, Any] = dict(
            status=ParticipationStatus.accepted,
            role=ParticipationRole.participant,
            source=InformationSource.organizer,
            operator=uuid4(),
        )
        defaults.update(kwargs)
        return ParticipationPhase(**defaults)

    return _make


@pytest.fixture
def make_registration() -> Callable[..., Registration]:
    def _make(**kwargs: Any) -> Registration:
        defaults: dict[str, Any] = dict(
            genitalia=Genitalia.vulva,
            source=InformationSource.registration_form,
            operator=uuid4(),
        )
        defaults.update(kwargs)
        return Registration(**defaults)

    return _make


@pytest.fixture
def make_participation(
    make_phase: Callable[..., ParticipationPhase],
) -> Callable[..., Participation]:
    def _make(
        status: ParticipationStatus = ParticipationStatus.accepted,
        role: ParticipationRole = ParticipationRole.participant,
        **kwargs: Any,
    ) -> Participation:
        phases = kwargs.pop("phases", None)
        if phases is None:
            phases = [make_phase(status=status, role=role)]
        return Participation(phases=phases, **kwargs)

    return _make


@pytest.fixture
def sample_people(
    make_person: Callable[..., Person],
    make_phase: Callable[..., ParticipationPhase],
    make_registration: Callable[..., Registration],
) -> People:
    alice = make_person(
        email=EmailAddress("alice@example.com"),
        first_name="Alice",
        last_name="Smith",
        birth_year=1990,
        participation={
            "event1": Participation(
                phases=[
                    make_phase(status=ParticipationStatus.accepted),
                ],
                registrations=[make_registration()],
            ),
        },
    )
    bob = make_person(
        email=EmailAddress("bob@example.com"),
        first_name="Bob",
        last_name="Jones",
        birth_year=1985,
        participation={
            "event1": Participation(
                phases=[
                    make_phase(status=ParticipationStatus.participated),
                ],
                registrations=[
                    make_registration(genitalia=Genitalia.penis),
                ],
            ),
        },
    )
    carol = make_person(
        email=EmailAddress("carol@example.com"),
        first_name="Carol",
        last_name="Brown",
        birth_year=1995,
    )
    people: People = {
        uuid4(): alice,
        uuid4(): bob,
        uuid4(): carol,
    }
    return people
