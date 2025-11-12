# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Generalally useful utilities."""

import datetime
from email.utils import parsedate_to_datetime
import os


__all__ = [
    "calculate_age",
    "is_valid_iso_datetime",
    "local_now",
    "parse_datetime",
    "show_datetime",
    "utc_now",
    "FilePath",
]


type FilePath = str | bytes | os.PathLike[str] | os.PathLike[bytes]


def calculate_age(
    birth_date: datetime.datetime, current_date: datetime.datetime | None = None
) -> int:
    """Calculate the age of a person by comparing two datetime objects.
    If current_date is not given, system time is used.

    Return the number of years as int.
    """

    if current_date is None:
        current_date = datetime.datetime.now()

    # Compute the difference between current year and birth year
    tentative_age = current_date.year - birth_date.year

    # Now determine if a birthday has occurred this year
    birthday_passed = (current_date.month, current_date.day) >= (
        birth_date.month,
        birth_date.day,
    )

    # Adjust age based on whether the birthday has passed
    if birthday_passed:
        return tentative_age
    else:
        return tentative_age - 1


def is_valid_iso_datetime(value: str) -> bool:
    try:
        return isinstance(datetime.datetime.fromisoformat(value), datetime.datetime)
    except ValueError:
        return False


def local_now() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def parse_datetime(data: str) -> datetime.datetime:
    """Parse a time string in either one of the ISO formats or in RFC 5322 email message format."""
    try:
        return datetime.datetime.fromisoformat(data)
    except ValueError:
        try:
            return parsedate_to_datetime(data)
        except ValueError:
            raise ValueError(f"Not an ISO or RFC5322 email date-time: {data}")


def show_datetime(dt: datetime.datetime | None) -> str:
    """Convert a datetime to a format used by command-line tools."""
    return dt.isoformat() if dt is not None else "None"


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)
