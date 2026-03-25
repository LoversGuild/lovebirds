# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""
Data types for events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from lovebirds.models.schema_config import GlobalSchemaConfig

__all__ = [
    "Event",
    "EventId",
    "MailConfig",
    "MessageFilterConfig",
    "MessageInfo",
    "SmtpConfig",
]


@dataclass(kw_only=True)
class Event:
    Config = GlobalSchemaConfig

    event_id: EventId
    mail: MailConfig
    variables: dict[str, Any]
    messages: dict[str, MessageInfo]


type EventId = str


@dataclass(kw_only=True)
class MailConfig:
    Config = GlobalSchemaConfig

    message_filter: MessageFilterConfig
    headers: dict[str, str]
    smtp: SmtpConfig


@dataclass(kw_only=True)
class MessageFilterConfig:
    Config = GlobalSchemaConfig

    html: str
    plain: str


@dataclass(kw_only=True)
class MessageInfo:
    Config = GlobalSchemaConfig

    locked: bool = False
    condition: str
    translations: list[str]
    filename: str
    headers: dict[str, str] = field(default_factory=dict)
    variables: dict[str, Any]


@dataclass(kw_only=True)
class SmtpConfig:
    Config = GlobalSchemaConfig

    server: str
    tls: bool = True
    messages_per_connection: int | None = None
