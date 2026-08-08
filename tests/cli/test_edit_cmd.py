from collections.abc import Callable
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest

from lovebirds.cli.config import Config
from lovebirds.cli.edit_cmd import EDIT_PREFIX, edit_people
from lovebirds.models.people import People, Person


class TestEditPeople:
    @patch("lovebirds.cli.edit_cmd.edit_as_yaml")
    def test_the_edited_database_is_kept_and_saved(
        self, mock_edit: MagicMock, make_config: Callable[..., Config]
    ) -> None:
        people: People = {}
        edited: People = {}
        mock_edit.return_value = edited
        config = make_config(people=people, subcommand="edit")

        edit_people(config)

        mock_edit.assert_called_once_with(People, People, people, EDIT_PREFIX)
        assert config.people is edited
        config.save_people.assert_called_once()  # type: ignore[attr-defined]

    @patch("lovebirds.cli.edit_cmd.edit_as_yaml")
    def test_a_dry_run_says_the_edits_will_be_discarded(
        self,
        mock_edit: MagicMock,
        make_config: Callable[..., Config],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """--dry-run makes save_people a no-op, so a whole editing session
        would otherwise vanish without a word.
        """
        config = make_config(subcommand="edit", dry_run=True)
        mock_edit.return_value = {}

        edit_people(config)

        assert "not be saved" in caplog.text

    @patch("lovebirds.cli.edit.edit_file")
    def test_an_untouched_database_survives_the_round_trip(
        self,
        mock_edit_file: MagicMock,
        make_config: Callable[..., Config],
        make_person: Callable[..., Person],
    ) -> None:
        """`People` is a type alias, not a class, so the call in edit_cmd
        needs a `type: ignore` — which means mypy is not checking the one
        thing this subcommand does. Exercise the real encode/dump/decode
        path: closing the editor without a change must give back what went in.
        """
        people: People = {uuid4(): make_person(first_name="Alice")}
        config = make_config(people=people, subcommand="edit")

        edit_people(config)

        mock_edit_file.assert_called_once()
        assert config.people == people
