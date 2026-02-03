# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Participant statistics to template conversion."""

import datetime
from statistics import mean
from typing import Any


from lovebirds.cli.config import Config
from lovebirds.models.events import EventId
from lovebirds.models.people import ParticipationStatus, People, Person
from lovebirds.utils import calculate_age

__all__ = ["participants_info_as_dict"]


def participants_info_as_dict(event_id: EventId, people: People) -> dict[str, Any]:
    def participates(p: Person) -> bool:
        nonlocal event_id
        if (
            (part := p.participation.get(event_id)) is not None
            and len(part.phases) != 0
            and part.phases[-1].status
            in [ParticipationStatus.accepted, ParticipationStatus.participated]
        ):
            return True
        else:
            return False

    def get_age(p: Person) -> int | None:
        if p.birth_year is None:
            return None

        # Assume everybody is born on July the first as this is the best approximation for a birthday
        birthday = datetime.datetime(
            year=p.birth_year, month=7, day=1, tzinfo=datetime.timezone.utc
        )
        age = calculate_age(birthday)
        if age < 18:
            # Our assumption about birthday was incorrect
            return 18
        return age

    participants = [p for p in people.values() if participates(p)]
    count = len(participants)
    if count == 0:
        return {}

    ages: list[int] = []
    for p in participants:
        age = get_age(p)
        if age is not None:
            ages.append(age)

    min_age = min(ages)
    max_age = max(ages)

    return {
        "count": count,
        "min_age": min_age,
        "max_age": max_age,
        "age_range": f"{min_age}–{max_age}",
        "age_average": round(mean(ages)),
    }
