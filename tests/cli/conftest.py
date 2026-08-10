import argparse
import subprocess
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from lovebirds.cli.config import Config
from lovebirds.models.events import Event
from lovebirds.models.people import People, PersonId

type GitRun = Callable[..., subprocess.CompletedProcess[bytes]]


@pytest.fixture
def fake_git() -> Callable[..., GitRun]:
    """Build a subprocess.run stand-in that behaves like git.

    Commands succeed unless a word of the command line is named below, which
    keeps a test's setup down to the one thing it is about:

        returncodes -- exit with this code rather than 0
        fail        -- fail every time
        fail_once   -- fail on the first call only

    A failure raises CalledProcessError only when the caller passed
    check=True, exactly as subprocess.run does. Honouring that matters: a
    stand-in that always raised would report a retry loop as working whether
    or not the code under test asked for the exit status to be fatal.
    """

    def _make(
        returncodes: dict[str, int] | None = None,
        fail: frozenset[str] = frozenset(),
        fail_once: frozenset[str] = frozenset(),
    ) -> GitRun:
        failed: set[str] = set()

        def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
            cmd = args[0]
            for word in cmd:
                if word in fail or (word in fail_once and word not in failed):
                    failed.add(word)
                    if kwargs.get("check"):
                        raise subprocess.CalledProcessError(1, cmd)
                    return subprocess.CompletedProcess(args=cmd, returncode=1)
                if returncodes and word in returncodes:
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=returncodes[word]
                    )
            return subprocess.CompletedProcess(args=cmd, returncode=0)

        return run

    return _make


@pytest.fixture
def make_config() -> Callable[..., Config]:
    def _make(
        people: People | None = None,
        event_id: str = "event1",
        dry_run: bool = False,
        no_git: bool = True,
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
            no_git=no_git,
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
            # All three, because a subcommand may write and commit separately
            # rather than going through save_people.
            config.save_people = MagicMock()  # type: ignore[method-assign]
            config.write_people = MagicMock()  # type: ignore[method-assign]
            config.commit_people = MagicMock()  # type: ignore[method-assign]
        return config

    return _make
