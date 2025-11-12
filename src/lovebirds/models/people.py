# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""
Data types for people and participation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import copy

from lovebirds.models.email import EmailAddress
from lovebirds.models.events import EventId
from lovebirds.models.schema_config import GlobalSchemaConfig

__all__ = [
    "AgeRange",
    "Consent",
    "GenitalPreferences",
    "Genitalia",
    "InformationSource",
    "Interest",
    "Preferences",
    "Participation",
    "ParticipationRole",
    "ParticipationStatus",
    "People",
    "Person",
    "PersonId",
    "PersonRef",
    "PersonRefById",
    "PersonRefByName",
    "ParticipationPhase",
    "Registration",
    "SentMessageInfo",
    "StayingOvernight",
    "sorted_people",
]


@dataclass(kw_only=True)
class AgeRange:
    Config = GlobalSchemaConfig

    min: int
    max: int


@dataclass(kw_only=True)
class Consent:
    Config = GlobalSchemaConfig

    legacy: bool = False
    valid: bool = False
    log: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class GenitalPreferences:
    Config = GlobalSchemaConfig

    vulvae: Interest
    penes: Interest


class Genitalia(Enum):
    vulva = "vulva"
    penis = "penis"
    other = "other"


class InformationSource(Enum):
    organizer = "organizer"
    email = "email"
    registration_form = "registration_form"
    private = "private"
    indirect = "indirect"
    other = "other"
    unknown = "unknown"


class Interest(Enum):
    high = "<3"
    medium = ":*"
    curious = ":)"
    selective = ":/"
    no = ":|"


@dataclass(kw_only=True)
class Participation:
    Config = GlobalSchemaConfig

    registrations: list[Registration] = field(default_factory=list)
    phases: list[ParticipationPhase] = field(default_factory=list)
    sent_messages: dict[str, SentMessageInfo] = field(default_factory=dict)


class ParticipationRole(Enum):
    participant = "participant"
    assistant = "assistant"
    organizer = "organizer"


@dataclass(kw_only=True)
class ParticipationPhase:
    Config = GlobalSchemaConfig

    time: datetime | None = None
    status: ParticipationStatus
    role: ParticipationRole
    comment: str = ""
    source: InformationSource
    operator: PersonId


class ParticipationStatus(Enum):
    invited = "invited"
    signed = "signed"
    accepted = "accepted"
    participated = "participated"
    absent = "absent"
    removed = "removed"
    withdrew = "withdrew"
    cancelled = "cancelled"
    queued = "queued"
    rejected = "rejected"
    declined = "declined"
    resolved = "resolved"


type People = dict[PersonId, Person]


@dataclass(kw_only=True)
class Person:
    Config = GlobalSchemaConfig

    # The order of the fields below matters when working with the database manually.
    # We try to keep most useful information at the top.
    email: EmailAddress
    first_name: str | None = None
    last_name: str | None = None
    aliases: list[str] = field(default_factory=list)
    locked: bool = False
    comment: str | None = None
    birth_year: int | None = None
    languages: list[str]
    phone: str | None = None
    participation: dict[EventId, Participation] = field(default_factory=dict)
    consent: Consent = field(default_factory=Consent)

    @property
    def experience(self) -> int:
        return sum(
            1
            for part in self.participation.values()
            for phase in part.phases
            if phase.status == ParticipationStatus.participated
        )

    @property
    def full_name(self) -> str | None:
        names = []
        if self.first_name:
            names.append(self.first_name)
        if self.last_name:
            names.append(self.last_name)
        if len(names) == 0:
            return None
        else:
            return " ".join(names)

    @property
    def alias_name(self) -> str:
        names = []
        if self.first_name:
            names.append(self.first_name)
        if len(self.aliases) > 0:
            names.append(f"({'/'.join(self.aliases)})")

        if self.last_name:
            names.append(self.last_name)

        if len(names) == 0:
            return self.email
        else:
            return " ".join(names)

    @property
    def named_email(self) -> str:
        name = self.full_name
        if name is None:
            return self.email
        else:
            return f"{name} <{self.email}>"


type PersonId = EmailAddress


type PersonRef = PersonRefById | PersonRefByName


@dataclass(kw_only=True)
class PersonRefById:
    Config = GlobalSchemaConfig

    id: PersonId


@dataclass(kw_only=True)
class PersonRefByName:
    Config = GlobalSchemaConfig

    name: str


@dataclass(kw_only=True)
class Preferences:
    Config = GlobalSchemaConfig

    sensuality: GenitalPreferences | None = None
    sex: GenitalPreferences
    description: str | None = None
    approximation: bool = False
    age: AgeRange | None = None


@dataclass(kw_only=True)
class Registration:
    Config = GlobalSchemaConfig

    time: datetime | None = None
    genitalia: Genitalia
    preferences: Preferences | None = None
    staying_overnight: StayingOvernight | None = None
    allergies: str | None = None
    avecs: list[PersonRef] = field(default_factory=list)
    personae_non_gratae: list[PersonRef] = field(default_factory=list)
    info: str | None = None
    amends: datetime | None = None
    source: InformationSource
    operator: PersonId
    hash: str | None = None

    def equal_info(self, other: Registration) -> bool:
        """Determine if two Registration objects are equal, if their timestamps and hashes are disregarded."""
        if type(self) != type(other):
            return False
        d1 = asdict(self)
        del d1["hash"]
        del d1["time"]

        d2 = asdict(other)
        del d2["hash"]
        del d2["time"]

        return d1 == d2


@dataclass(kw_only=True)
class SentMessageInfo:
    Config = GlobalSchemaConfig

    time: datetime | None = None
    message_id: str | None = None
    operator: PersonId


class StayingOvernight(Enum):
    yes = "yes"
    probably_yes = "probably_yes"
    maybe = "maybe"
    probably_not = "probably_not"
    no = "no"


def sorted_people(people: People) -> People:
    """Sort people by their "Name <email_address>" string.
    Returns a new copy of people.
    """

    def ref_sorter(ref: PersonRef) -> str:
        nonlocal people
        if isinstance(ref, PersonRefById):
            return people[ref.id].named_email
        elif isinstance(ref, PersonRefByName):
            return ref.name
        else:
            raise ValueError(f"Invalid person reference: {ref}")

    # Sort Persons by
    people_copy = copy.deepcopy(people)
    new_people = dict(
        sorted(people_copy.items(), key=lambda item: item[1].named_email.lower())
    )

    for person in new_people.values():
        person.participation = dict(sorted(person.participation.items()))
        for event_id, part in person.participation.items():
            for reg in part.registrations:
                reg.avecs.sort(key=ref_sorter)
                reg.personae_non_gratae.sort(key=ref_sorter)
    return new_people
