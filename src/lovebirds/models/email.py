# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Type for email addresses which validates addresses."""

import re
from typing import Self, override

from mashumaro.types import SerializableType

__all__ = ["EmailAddress", "is_valid_email_address"]


class EmailAddress(str, SerializableType):
    @override
    def __new__(cls, value: str) -> Self:
        if is_valid_email_address(value):
            return super().__new__(cls, value)
        else:
            raise ValueError(f"Invalid email address: {value}")

    @override
    def _serialize(self) -> str:
        return str(self)

    @override
    @classmethod
    def _deserialize(cls, value: str) -> Self:
        return cls(value)


_valid_email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def is_valid_email_address(email: str) -> bool:
    """
    Validates if the given string is a valid email address using a simple regex.

    Args:
        email (str): The email address to validate.

    Returns:
        bool: True if the email is valid, False otherwise.
    """
    return re.match(_valid_email_pattern, email) is not None
