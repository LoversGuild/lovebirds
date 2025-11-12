# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Convert person objects to easily accessible jinja2 template variables"""

from typing import Any

from lovebirds.models.events import EventId
from lovebirds.models.people import Person
from lovebirds.templates.eval import to_dict_recursive

__all__ = ["person_to_dict"]


def person_to_dict(person: Person, event_id: EventId | None) -> dict[str, Any]:
    result: dict[str, Any] = to_dict_recursive(person)
    participation = person.participation.get(event_id) if event_id is not None else None
    if participation is not None:
        registration = (
            participation.registrations[-1]
            if len(participation.registrations) != 0
            else None
        )
        phase = participation.phases[-1] if len(participation.phases) != 0 else None
    else:
        phase = None
        registration = None

    # Add current phase
    if phase is not None:
        phase_dict = to_dict_recursive(phase)
        result["phase"] = phase_dict
        for key in {"comment", "role", "status"}:
            result[key] = phase_dict[key]

        assert participation is not None
        result["comments"] = [
            f"{p.status.name}: {p.comment}" for p in participation.phases if p.comment
        ]

    # Handle current registration
    if registration is not None:
        reg_dict = to_dict_recursive(registration)
        result["registration"] = reg_dict

        excluded_reg_keys = {"amends", "hash", "operator", "source", "time"}
        result.update(
            {
                key: value
                for key, value in reg_dict.items()
                if key not in excluded_reg_keys
            }
        )
    else:
        # Find genitalia from latest registration
        all_participations = reversed(person.participation.values())
        latest_registration = next(
            (
                part.registrations[-1]
                for part in all_participations
                if len(part.registrations) != 0
            ),
            None,
        )
        result["genitalia"] = (
            latest_registration.genitalia.name
            if latest_registration is not None
            else None
        )

    return result
