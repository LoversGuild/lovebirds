import logging
from collections.abc import Callable
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest

from lovebirds.cli.config import Config
from lovebirds.cli.edit_cmd import EDIT_PREFIX, edit_people
from lovebirds.models.people import People, Person


@patch("lovebirds.cli.edit_cmd.input")
@patch("lovebirds.cli.edit_cmd.edit_as_yaml")
class TestEditPeople:
    def test_an_edited_database_is_written_and_committed_with_the_given_message(
        self,
        mock_edit: MagicMock,
        mock_input: MagicMock,
        make_config: Callable[..., Config],
        make_person: Callable[..., Person],
    ) -> None:
        people: People = {}
        edited: People = {uuid4(): make_person(first_name="Alice")}
        mock_edit.return_value = edited
        mock_input.return_value = "Add Alice"
        config = make_config(people=people, subcommand="edit")

        edit_people(config)

        mock_edit.assert_called_once_with(People, People, people, EDIT_PREFIX)
        assert config.people is edited
        config.write_people.assert_called_once()  # type: ignore[attr-defined]
        config.commit_people.assert_called_once_with(  # type: ignore[attr-defined]
            "Add Alice"
        )

    def test_an_empty_commit_message_writes_but_does_not_commit(
        self,
        mock_edit: MagicMock,
        mock_input: MagicMock,
        make_config: Callable[..., Config],
        make_person: Callable[..., Person],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Declining to commit must not mean losing the edits: they stay on
        disk, uncommitted, for the operator to deal with by hand.
        """
        mock_edit.return_value = {uuid4(): make_person(first_name="Alice")}
        mock_input.return_value = ""
        config = make_config(subcommand="edit")

        with caplog.at_level(logging.INFO):
            edit_people(config)

        config.write_people.assert_called_once()  # type: ignore[attr-defined]
        config.commit_people.assert_not_called()  # type: ignore[attr-defined]
        assert "uncommitted" in caplog.text

    def test_an_unchanged_database_is_neither_written_nor_committed(
        self,
        mock_edit: MagicMock,
        mock_input: MagicMock,
        make_config: Callable[..., Config],
        make_person: Callable[..., Person],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Closing the editor without changing anything is a common way to
        leave it. Asking for a commit message then would be asking what to
        say about nothing — so no prompt, no write, no commit.

        The comparison is by value: the editor round trip always yields a
        fresh dict, so identity would call every session a change.
        """
        person_id = uuid4()
        people: People = {person_id: make_person(first_name="Alice")}
        mock_edit.return_value = {person_id: make_person(first_name="Alice")}
        config = make_config(people=people, subcommand="edit")

        with caplog.at_level(logging.INFO):
            edit_people(config)

        mock_input.assert_not_called()
        config.write_people.assert_not_called()  # type: ignore[attr-defined]
        config.commit_people.assert_not_called()  # type: ignore[attr-defined]
        assert "unchanged" in caplog.text

    def test_a_dry_run_says_the_edits_will_be_discarded_before_the_editor_opens(
        self,
        mock_edit: MagicMock,
        mock_input: MagicMock,
        make_config: Callable[..., Config],
        make_person: Callable[..., Person],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """--dry-run makes saving a no-op, so a whole editing session would
        otherwise vanish without a word. The warning alone is not enough: the
        editor takes over the terminal the moment it opens, so the run has
        to wait for an acknowledgement first.
        """
        events = MagicMock()
        events.attach_mock(mock_input, "input")
        events.attach_mock(mock_edit, "edit")
        mock_edit.return_value = {uuid4(): make_person(first_name="Alice")}
        config = make_config(subcommand="edit", dry_run=True)

        edit_people(config)

        assert "not be saved" in caplog.text
        # One prompt — the pause — and it precedes the editor. No commit
        # message is asked for afterwards: there is nothing it could apply to.
        assert [name for name, _, _ in events.mock_calls] == ["input", "edit"]


class TestEditPeopleRoundTrip:
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
