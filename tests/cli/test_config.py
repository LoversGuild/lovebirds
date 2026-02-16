from collections.abc import Callable
from unittest.mock import patch, MagicMock

from typeguard import TypeCheckError

from lovebirds.cli.config import Config
from lovebirds.models.people import People


class TestConfigSavePeople:
    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.backup_file")
    @patch("lovebirds.cli.config.check_type")
    def test_dry_run_skips_save(
        self,
        mock_check: MagicMock,
        mock_backup: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(dry_run=True, mock_save=False)
        config.save_people()
        mock_save.assert_not_called()
        mock_backup.assert_not_called()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.backup_file")
    @patch("lovebirds.cli.config.check_type")
    def test_backup_true_calls_backup(
        self,
        mock_check: MagicMock,
        mock_backup: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(mock_save=False)
        config.save_people(backup=True)
        mock_backup.assert_called_once_with("/tmp/test_people.yaml")
        mock_save.assert_called_once()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.backup_file")
    @patch("lovebirds.cli.config.check_type")
    def test_backup_false_skips_backup(
        self,
        mock_check: MagicMock,
        mock_backup: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(mock_save=False)
        config.save_people(backup=False)
        mock_backup.assert_not_called()
        mock_save.assert_called_once()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.backup_file")
    @patch("lovebirds.cli.config.check_type")
    @patch("builtins.input")
    def test_save_failure_retries_until_it_succeeds(
        self,
        mock_input: MagicMock,
        mock_check: MagicMock,
        mock_backup: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        """Saving is the one step that must not be abandoned: losing it would
        discard the edit the subcommand just made."""
        mock_save.side_effect = [OSError("disk full"), None]
        config = make_config(mock_save=False)
        config.save_people()
        assert mock_save.call_count == 2
        mock_input.assert_called_once()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.backup_file")
    @patch("lovebirds.cli.config.check_type")
    @patch("builtins.input")
    def test_type_check_failure_warns_but_still_saves(
        self,
        mock_input: MagicMock,
        mock_check: MagicMock,
        mock_backup: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        mock_check.side_effect = TypeCheckError("not a People")
        config = make_config(mock_save=False)
        config.save_people()
        mock_input.assert_called_once()
        mock_save.assert_called_once()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.backup_file")
    @patch("lovebirds.cli.config.check_type")
    @patch("builtins.input")
    def test_type_check_failure_in_dry_run_does_not_prompt(
        self,
        mock_input: MagicMock,
        mock_check: MagicMock,
        mock_backup: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        mock_check.side_effect = TypeCheckError("not a People")
        config = make_config(dry_run=True, mock_save=False)
        config.save_people()
        mock_input.assert_not_called()
        mock_save.assert_not_called()
