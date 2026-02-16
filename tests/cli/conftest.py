import argparse
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from lovebirds.cli.config import Config
from lovebirds.models.events import Event
from lovebirds.models.people import People, PersonId


@pytest.fixture
def make_config() -> Callable[..., Config]:
    def _make(
        people: People | None = None,
        event_id: str = "event1",
        dry_run: bool = False,
        subcommand: str = "test",
        mock_save: bool = True,
        operator_id: PersonId | None = None,
        event: Event | None = None,
        **extra_args: Any,
    ) -> Config:
        if people is None:
            people = {}
        args_dict: dict[str, Any] = dict(
            dry_run=dry_run,
            people_file="/tmp/test_people.yaml",
            subcommand=subcommand,
            event_id=event_id,
        )
        args_dict.update(extra_args)
        args = argparse.Namespace(**args_dict)
        config = Config(
            args=args,
            event=event,
            event_id=event_id,
            people=people,
            operator_id=operator_id,
        )
        if mock_save:
            config.save_people = MagicMock()  # type: ignore[method-assign]
        return config

    return _make
