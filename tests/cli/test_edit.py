import os
import pathlib
import stat
import subprocess
import tempfile
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import lovebirds.cli.edit as edit
from lovebirds.models.email import EmailAddress
from lovebirds.models.people import AgeRange


class TestGetUserEditor:
    def test_visual_wins_over_editor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VISUAL", "myvisual")
        monkeypatch.setenv("EDITOR", "myeditor")
        assert edit.get_user_editor() == "myvisual"

    def test_editor_used_when_visual_is_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.setenv("EDITOR", "myeditor")
        assert edit.get_user_editor() == "myeditor"

    def test_falls_back_to_vi(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("VISUAL", raising=False)
        monkeypatch.delenv("EDITOR", raising=False)
        assert edit.get_user_editor() == "vi"


class TestEditFile:
    @patch("lovebirds.cli.edit.subprocess.run")
    def test_runs_the_editor_on_the_file(
        self, mock_run: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EDITOR", "myeditor")
        monkeypatch.delenv("VISUAL", raising=False)
        edit.edit_file("/tmp/some.yaml")
        mock_run.assert_called_once_with(["myeditor", "/tmp/some.yaml"], check=True)

    def test_editor_failure_is_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        """An editor exiting non-zero means the edit was abandoned. Ignoring it
        would let the caller act on whatever happened to be in the file.

        Runs a real failing command rather than a mock: a mock raises whatever
        it is told to, so it would pass with or without check=True.
        """
        monkeypatch.setenv("EDITOR", "false")
        monkeypatch.delenv("VISUAL", raising=False)
        target = tmp_path / "some.yaml"
        target.write_text("unchanged")
        with pytest.raises(subprocess.CalledProcessError):
            edit.edit_file(target)


class TestInputValidated:
    @patch("builtins.input")
    def test_returns_accepted_input(self, mock_input: MagicMock) -> None:
        mock_input.return_value = "yes"
        assert edit.input_validated("? ", predicate=lambda v: v == "yes") == "yes"

    @patch("builtins.input")
    def test_reprompts_until_the_predicate_accepts(self, mock_input: MagicMock) -> None:
        mock_input.side_effect = ["no", "also no", "yes"]
        assert edit.input_validated("? ", predicate=lambda v: v == "yes") == "yes"
        assert mock_input.call_count == 3

    @patch("builtins.input")
    def test_empty_input_takes_the_default(self, mock_input: MagicMock) -> None:
        mock_input.return_value = ""
        result = edit.input_validated(
            "? ", predicate=lambda v: False, default="fallback"
        )
        assert result == "fallback"

    @patch("builtins.input")
    def test_input_is_stripped(self, mock_input: MagicMock) -> None:
        mock_input.return_value = "  spaced  "
        assert edit.input_validated("? ", predicate=lambda v: True) == "spaced"

    @patch("builtins.input")
    def test_eof_does_not_end_the_prompt(self, mock_input: MagicMock) -> None:
        """Ctrl-D must not be taken as an answer: the value is needed, so the
        prompt is repeated until something valid arrives."""
        mock_input.side_effect = [EOFError, "yes"]
        assert edit.input_validated("? ", predicate=lambda v: v == "yes") == "yes"


class TestInputChoice:
    @patch("builtins.input")
    def test_accepts_a_listed_choice(self, mock_input: MagicMock) -> None:
        mock_input.return_value = "update"
        assert edit.input_choice("? ", {"new", "update"}) == "update"

    @patch("builtins.input")
    def test_rejects_anything_else(self, mock_input: MagicMock) -> None:
        mock_input.side_effect = ["maybe", "new"]
        assert edit.input_choice("? ", {"new", "update"}) == "new"
        assert mock_input.call_count == 2

    def test_a_default_outside_the_choices_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="not a valid choice"):
            edit.input_choice("? ", {"new", "update"}, default="nonsense")


class TestInputEmail:
    @patch("builtins.input")
    def test_returns_a_validated_email_address(self, mock_input: MagicMock) -> None:
        mock_input.return_value = "alice@example.com"
        result = edit.input_email("? ")
        assert result == EmailAddress("alice@example.com")
        assert isinstance(result, EmailAddress)

    @patch("builtins.input")
    def test_reprompts_on_a_malformed_address(self, mock_input: MagicMock) -> None:
        mock_input.side_effect = ["not-an-address", "alice@example.com"]
        assert edit.input_email("? ") == EmailAddress("alice@example.com")
        assert mock_input.call_count == 2


class TestInputYesNo:
    @pytest.mark.parametrize(
        "answer,expected",
        [
            ("y", True),
            ("yes", True),
            ("Y", True),
            ("YES", True),
            ("n", False),
            ("no", False),
            ("N", False),
            ("No", False),
        ],
    )
    @patch("builtins.input")
    def test_recognised_answers(
        self, mock_input: MagicMock, answer: str, expected: bool
    ) -> None:
        mock_input.return_value = answer
        assert edit.input_yes_no("? ") is expected

    @patch("builtins.input")
    def test_empty_input_takes_the_default(self, mock_input: MagicMock) -> None:
        mock_input.return_value = ""
        assert edit.input_yes_no("? ", default=True) is True
        assert edit.input_yes_no("? ", default=False) is False

    @patch("builtins.input")
    def test_reprompts_on_anything_else(self, mock_input: MagicMock) -> None:
        mock_input.side_effect = ["maybe", "y"]
        assert edit.input_yes_no("? ") is True
        assert mock_input.call_count == 2


class TestEditAsYaml:
    @patch("lovebirds.cli.edit.edit_file")
    def test_the_file_is_private_before_any_plaintext_reaches_it(
        self, mock_edit: MagicMock
    ) -> None:
        """This file holds decrypted personal data — for `edit`, the entire
        database — in the shared system temp directory, so no one else may
        read it at any point.

        The mode is sampled twice: as the file is created, before a byte has
        been written, and again once the editor has it. The first is the one
        that matters, and it holds because mkstemp sets the mode in the same
        syscall that creates the file, leaving no window to widen.
        """
        modes: list[int] = []
        real_temp_file = tempfile.NamedTemporaryFile

        def recording_temp_file(*args: Any, **kwargs: Any) -> Any:
            handle = real_temp_file(*args, **kwargs)
            modes.append(stat.S_IMODE(os.stat(handle.name).st_mode))
            return handle

        mock_edit.side_effect = lambda name: modes.append(
            stat.S_IMODE(os.stat(name).st_mode)
        )

        with patch(
            "lovebirds.cli.edit.tempfile.NamedTemporaryFile", recording_temp_file
        ):
            edit.edit_as_yaml(AgeRange, AgeRange, AgeRange(min=25, max=55), "prefix")

        assert modes == [0o600, 0o600]

    @patch("lovebirds.cli.edit.edit_file")
    def test_round_trips_an_unchanged_record(self, mock_edit: MagicMock) -> None:
        """Leaving the file untouched must yield an equal record: the dump has
        to be something the decoder accepts back."""
        original = AgeRange(min=25, max=55)
        result = edit.edit_as_yaml(AgeRange, AgeRange, original, "prefix")
        assert result == original
        mock_edit.assert_called_once()

    @patch("lovebirds.cli.edit.pager")
    @patch("lovebirds.cli.edit.edit_file")
    def test_reopens_the_editor_until_the_yaml_parses(
        self, mock_edit: MagicMock, mock_pager: MagicMock
    ) -> None:
        attempts = 0

        def write(filename: Any) -> None:
            nonlocal attempts
            attempts += 1
            text = "this: is: not: valid" if attempts == 1 else "min: 30\nmax: 40\n"
            with open(filename, "w", encoding="utf-8") as fh:
                fh.write(text)

        mock_edit.side_effect = write
        result = edit.edit_as_yaml(AgeRange, AgeRange, AgeRange(min=1, max=2), "prefix")
        assert result == AgeRange(min=30, max=40)
        assert mock_edit.call_count == 2
        mock_pager.assert_called_once()

    @patch("lovebirds.cli.edit.edit_file")
    def test_temp_file_is_removed(
        self, mock_edit: MagicMock, tmp_path: pathlib.Path
    ) -> None:
        seen: list[str] = []
        mock_edit.side_effect = lambda name: seen.append(str(name))
        edit.edit_as_yaml(AgeRange, AgeRange, AgeRange(min=1, max=2), "prefix")
        assert seen and not pathlib.Path(seen[0]).exists()
