# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Registration managament subcommands."""

import copy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
import sys
import uuid
import yaml


from mashumaro.codecs.json import JSONDecoder, JSONEncoder
from mashumaro.codecs.basic import BasicEncoder

from lovebirds.cli.config import Config
from lovebirds.io import gpg_decrypt
import lovebirds.cli.edit as edit
from lovebirds.models.email import EmailAddress
from lovebirds.models.events import EventId
from lovebirds.models.people import *
from lovebirds.models.schema_config import GlobalSchemaConfig
from lovebirds.utils import FilePath, is_valid_iso_datetime, local_now


@dataclass(kw_only=True)
class RawRegistration:
    Config = GlobalSchemaConfig

    timestamp: datetime
    event_id: EventId
    first_name: str
    last_name: str
    email: EmailAddress
    phone_number: str
    birth_year: int
    language_preference: str
    allergies: str
    genitalia: Genitalia
    interest_in_sensuality_with_vulvae: Interest
    interest_in_sensuality_with_penes: Interest
    interest_in_sex_with_vulvae: Interest
    interest_in_sex_with_penes: Interest
    age_min: int
    age_max: int
    avecs: str
    non_gratas: str
    staying_overnight: StayingOvernight
    info: str
    magic_word: str
    consent: bool

    def compute_hash(self) -> str:
        return hashlib.sha256(
            _raw_registration_encoder.encode(self).encode("UTF-8")
        ).hexdigest()


@dataclass(kw_only=True)
class PersonLists:
    Config = GlobalSchemaConfig

    avecs: list[str]
    personae_non_gratae: list[str]


_raw_registration_decoder = JSONDecoder(RawRegistration)
_raw_registration_encoder = JSONEncoder(RawRegistration)
_registration_encoder = BasicEncoder(Registration)

### Loading raw registration data ###


def _load_raw_registration(filename: FilePath) -> RawRegistration:
    return _raw_registration_decoder.decode(gpg_decrypt(filename))


def _find_person_by_email_interactive(
    people: People, raw: RawRegistration
) -> Person | None:
    """Interactively find a person by email address. If matching person is not found, prompt to update a pre-existing person's email address, or return None to signal that a new person needs to be created."""

    # Create mapping from email addresses to ids
    email_id_map = {
        person.email: id for id, person in people.items() if person.email is not None
    }

    # If the person can be found straight away, return them
    if (person_id := email_id_map.get(raw.email)) is not None:
        return people[person_id]

    name = f"{raw.first_name} {raw.last_name}"

    logging.info(f"There is no person with email address `{raw.email}' in database.")
    logging.info(f"The address should belnog to `{name}'.")
    logging.info(
        "Type `new' to add a new person, `update' to update a pre-existing person's email address."
    )
    match edit.input_choice("What to do? ", {"new", "update"}):
        case "new":
            return None
        case "update":
            old_email = edit.input_choice(
                prompt="Enter email address of a person in database: ",
                choices=set(email_id_map.keys()),
                init=raw.email,
            )
            old_email = EmailAddress(old_email)
            id = email_id_map[old_email]

            return people[id]
        case _:
            raise RuntimeError("Impossible!")


def _registration_sort_key(reg: Registration) -> tuple[datetime, datetime]:
    if reg.time is None:
        raise ValueError(
            "Cannot sort registrtation list containing timestampless registrations"
        )
    if reg.amends is not None:
        return (reg.amends, reg.time)
    return (reg.time, reg.time)


def _register_participation(config: Config, raw: RawRegistration) -> None:
    """Interactively register a user."""

    def sanitize(data: str) -> str:
        return "\n".join(
            line.strip() for line in data.replace("\r\n", "\n").splitlines()
        )

    raw_hash = raw.compute_hash()

    person = _find_person_by_email_interactive(config.people, raw)
    is_new_person = person is None
    if person is None:
        logging.info(
            f"Adding new person `{raw.first_name} {raw.last_name} <{raw.email}>'"
        )

        # Only fill mandatory fields as the rest is done when importing registration information.
        person = Person(
            email=raw.email,
            languages=[],
        )
        person_id = uuid.uuid4()
        config.people[person_id] = person
    elif person.locked:
        logging.warning(f"Registration for a locked person: `{person.named_email}'")
        logging.warning("The lock will stay in effect!")
    else:
        person.consent.valid = True
        person.consent.legacy = False

    if (participation := person.participation.get(raw.event_id)) is None:
        participation = Participation()
        person.participation[raw.event_id] = participation

    # Check if this registration has already been processed
    old_hashes = {reg.hash for reg in participation.registrations if reg.hash}
    if raw_hash in old_hashes:
        logging.info(
            f"Skipping already processed registration for `{person.named_email}'..."
        )
        return

    # Don't use person.named_email below as person names are not necessarily set yet
    logging.info(
        f"Importing registration for `{person.first_name or raw.first_name} {person.last_name or raw.last_name} <{raw.email}>'..."
    )

    if raw.email != person.email or is_new_person:
        person.email = edit.input_email(
            prompt="Email address changed! Confirm new email: ",
            init=raw.email,
        )

    is_valid_name = lambda val: len(val) > 0 and val.strip() == val

    new_first_name = raw.first_name.strip()
    if person.first_name != new_first_name:
        new_first_name = edit.input_validated(
            prompt="First name changed! Confirm new first name: ",
            predicate=is_valid_name,
            init=new_first_name,
        )
    person.first_name = new_first_name

    new_last_name = raw.last_name.strip()
    if person.last_name != new_last_name:
        new_last_name = edit.input_validated(
            prompt="Last name changed! Confirm new last name: ",
            predicate=is_valid_name,
            init=new_last_name,
        )
    person.last_name = new_last_name

    is_valid_birth_year = lambda val: val.isdigit() and int(val) in range(
        raw.timestamp.year - 150, raw.timestamp.year
    )
    new_birth_year = raw.birth_year
    if person.birth_year != new_birth_year:
        new_birth_year = int(
            edit.input_validated(
                prompt="Birth year changed! Confirm new birth year: ",
                predicate=is_valid_birth_year,
                init=str(new_birth_year),
            )
        )
    person.birth_year = new_birth_year

    is_valid_phone = lambda val: len(val) == 0 or (
        val[0:1] == "+" and val[1:].isdigit()
    )
    new_phone = raw.phone_number.strip()
    if new_phone[0:1] == "0":
        new_phone = "+358" + new_phone[1:]
    if person.phone != new_phone:
        new_phone = edit.input_validated(
            prompt="Phone number changed! Confirm new phone number: ",
            predicate=is_valid_phone,
            init=new_phone,
        )
    person.phone = new_phone if new_phone else None

    # Move or add preferred language to the beginning of the preference list.
    # Use an intermediate dict to preserve ordering.
    person.languages = list(
        {lang: True for lang in [raw.language_preference] + person.languages}.keys()
    )

    # List handling
    sanitized_avecs = sanitize(raw.avecs)
    sanitized_non_gratae = sanitize(raw.non_gratas)
    no_persons = {"", "-", "∅"}
    person_strings = PersonLists(
        avecs=[sanitized_avecs] if sanitized_avecs not in no_persons else [],
        personae_non_gratae=(
            [sanitized_non_gratae] if sanitized_non_gratae not in no_persons else []
        ),
    )
    if len(person_strings.avecs) != 0 or len(person_strings.personae_non_gratae) != 0:
        person_lists = edit.edit_as_yaml(
            PersonLists,
            PersonLists,
            person_strings,
            prefix="Format the following data as YAML lists. Canonicalize names and change them to match existing person names.",
        )
    else:
        person_lists = person_strings

    assert config.operator_id is not None
    reg = Registration(
        time=raw.timestamp,
        source=InformationSource.registration_form,
        operator=config.operator_id,
        allergies=sanitize(raw.allergies),
        genitalia=raw.genitalia,
        preferences=Preferences(
            approximation=False,
            sensuality=GenitalPreferences(
                vulvae=raw.interest_in_sensuality_with_vulvae,
                penes=raw.interest_in_sensuality_with_penes,
            ),
            sex=GenitalPreferences(
                vulvae=raw.interest_in_sex_with_vulvae,
                penes=raw.interest_in_sex_with_penes,
            ),
            age=AgeRange(min=raw.age_min, max=raw.age_max),
        ),
        avecs=[PersonRefByName(name=p) for p in person_lists.avecs],
        personae_non_gratae=[
            PersonRefByName(name=p) for p in person_lists.personae_non_gratae
        ],
        staying_overnight=raw.staying_overnight,
        info=sanitize(raw.info),
        hash=raw_hash,
    )

    participation.registrations.append(reg)
    participation.registrations.sort(key=_registration_sort_key)

    reg = participation.registrations[-1]
    sys.stdout.write(f"Effective registration for `{person.named_email}':\n")
    yaml.dump(
        _registration_encoder.encode(reg),
        sys.stderr,
        yaml.CSafeDumper,
        allow_unicode=True,
        default_flow_style=None,
        indent=2,
        sort_keys=False,
    )

    if not reg.amends:
        amend = edit.input_yes_no("Do you wish to amend this registration? ")
    else:
        amend = False

    if amend:
        amended_reg = copy.copy(reg)
        amended_reg.source = InformationSource.organizer
        amended_reg.hash = None
        amended_reg.time = None
        amended_reg = edit.edit_as_yaml(
            Registration,
            Registration,
            amended_reg,
            prefix="Amend the registration below in YAML format.",
        )

        # Set `time` and `amends` fields afterwards as it is critical that these are correct
        amended_reg.time = local_now()
        amended_reg.amends = reg.time
        participation.registrations.append(amended_reg)

    pre_registered_status = [
        None,
        ParticipationStatus.invited,
        ParticipationStatus.declined,
    ]
    current_phase = participation.phases[-1] if len(participation.phases) != 0 else None
    current_status = current_phase.status if current_phase is not None else None
    if current_status in pre_registered_status:
        if current_phase is None:
            role = ParticipationRole(
                edit.input_validated(
                    prompt="Enter participation role: ",
                    predicate=lambda val: val in ParticipationRole,
                    init="participant",
                )
            )
        else:
            role = current_phase.role
        logging.info(f"Marking `{person.named_email}' as `registered'...")
        comment = edit.input("Enter comment for sign-in: ").strip()
        participation.phases.append(
            ParticipationPhase(
                time=local_now(),
                role=role,
                status=ParticipationStatus.registered,
                source=InformationSource.organizer,
                operator=config.operator_id,
            )
        )
    else:
        registered_phase = next(
            (
                phase
                for phase in reversed(participation.phases)
                if phase.status == ParticipationStatus.registered
            ),
            None,
        )
        if registered_phase is not None:
            logging.info(f"Updating registered phase for `{person.named_email}'...")
            registered_phase.comment = edit.input(
                "Edit comment for sign-in: ", init=registered_phase.comment
            ).strip()
            prev_time_str = (
                registered_phase.time.isoformat()
                if registered_phase.time is not None
                else None
            )
            time_str = edit.input_validated(
                prompt="Edit sign-in time (leave empty for current time): ",
                predicate=lambda val: val == "" or is_valid_iso_datetime(val),
                init=prev_time_str,
            ).strip()
            registered_phase.time = (
                datetime.fromisoformat(time_str) if time_str != "" else local_now()
            )
        else:
            logging.info(
                f"Not marking `{person.named_email}' as `registered' due to current post-registered status: `{current_status}'"
            )


def _group_raw_registrations(
    registrations: list[RawRegistration],
) -> dict[EventId, dict[EmailAddress, list[RawRegistration]]]:
    """Group a list of registrations into a dict of list of registrations
    keyed by event id and user email address.
    """

    grouped_regs: dict[EventId, dict[EmailAddress, list[RawRegistration]]] = {}
    for raw in sorted(registrations, key=lambda v: v.timestamp):
        grouped_regs.setdefault(raw.event_id, {}).setdefault(raw.email, []).append(raw)
    return grouped_regs


def import_registrations(config: Config) -> None:
    registrations = [_load_raw_registration(filename) for filename in config.args.files]
    try:
        for event_id, person_id_to_reg_list_map in _group_raw_registrations(
            registrations
        ).items():
            logging.info(f"Processing registrations for {event_id}...")
            for raw_reg_list in person_id_to_reg_list_map.values():
                for raw in raw_reg_list:
                    _register_participation(config, raw)
                    # Written, not committed: an import is a long interactive
                    # session, and answers already given must survive an abort
                    # partway through. The commit happens once, below.
                    config.write_people()
    finally:
        # In the finally, so that an import abandoned halfway — Ctrl-C at a
        # prompt — still commits the registrations already dealt with,
        # instead of leaving them written but outside the history.
        config.commit_people()
