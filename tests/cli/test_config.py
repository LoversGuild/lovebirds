from collections.abc import Callable
from unittest.mock import patch, MagicMock

from typeguard import TypeCheckError

from lovebirds.cli.config import Config


class TestConfigSavePeople:
    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.check_type")
    def test_dry_run_skips_save(
        self,
        mock_check: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(dry_run=True, mock_save=False)
        config.save_people()
        mock_save.assert_not_called()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.check_type")
    def test_saves_when_not_dry_run(
        self,
        mock_check: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(mock_save=False)
        config.save_people()
        mock_save.assert_called_once()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.check_type")
    @patch("builtins.input")
    def test_save_failure_retries_until_it_succeeds(
        self,
        mock_input: MagicMock,
        mock_check: MagicMock,
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
    @patch("lovebirds.cli.config.check_type")
    @patch("builtins.input")
    def test_type_check_failure_warns_but_still_saves(
        self,
        mock_input: MagicMock,
        mock_check: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        mock_check.side_effect = TypeCheckError("not a People")
        config = make_config(mock_save=False)
        config.save_people()
        mock_input.assert_called_once()
        mock_save.assert_called_once()

    @patch("lovebirds.cli.config.save_people")
    @patch("lovebirds.cli.config.check_type")
    @patch("builtins.input")
    def test_type_check_failure_in_dry_run_does_not_prompt(
        self,
        mock_input: MagicMock,
        mock_check: MagicMock,
        mock_save: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        mock_check.side_effect = TypeCheckError("not a People")
        config = make_config(dry_run=True, mock_save=False)
        config.save_people()
        mock_input.assert_not_called()
        mock_save.assert_not_called()


@patch("lovebirds.cli.config.git.commit_and_push")
@patch("lovebirds.cli.config.save_people")
@patch("lovebirds.cli.config.check_type")
class TestConfigGitPush:
    def test_no_git_flag_skips_git(
        self,
        mock_check: MagicMock,
        mock_save: MagicMock,
        mock_commit: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(no_git=True, subcommand="reformat", mock_save=False)
        config.save_people()
        mock_commit.assert_not_called()

    def test_the_saved_database_is_committed(
        self,
        mock_check: MagicMock,
        mock_save: MagicMock,
        mock_commit: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(no_git=False, subcommand="reformat", mock_save=False)
        config.save_people()
        mock_commit.assert_called_once_with(
            "/tmp/test_people.yaml", "lovebird: reformat (event: event1)"
        )

    def test_the_commit_comes_after_the_write(
        self,
        mock_check: MagicMock,
        mock_save: MagicMock,
        mock_commit: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        """Committing first would record the file's previous contents and
        leave the save itself uncommitted until some later run.
        """
        steps: list[str] = []
        mock_save.side_effect = lambda *a: steps.append("write")
        mock_commit.side_effect = lambda *a: steps.append("commit")

        config = make_config(no_git=False, subcommand="reformat", mock_save=False)
        config.save_people()

        assert steps == ["write", "commit"]

    def test_dry_run_skips_git(
        self,
        mock_check: MagicMock,
        mock_save: MagicMock,
        mock_commit: MagicMock,
        make_config: Callable[..., Config],
    ) -> None:
        config = make_config(
            dry_run=True, no_git=False, subcommand="reformat", mock_save=False
        )
        config.save_people()
        mock_commit.assert_not_called()


class TestCommitMessage:
    """The message is what makes the git history readable after the fact, so
    it is worth pinning on its own rather than through the git plumbing."""

    def test_names_the_subcommand_and_the_event(
        self, make_config: Callable[..., Config]
    ) -> None:
        config = make_config(subcommand="phase add", event_id="summer2026")
        assert config._commit_message() == "lovebird: phase add (event: summer2026)"

    def test_includes_the_detail_a_subcommand_supplied(
        self, make_config: Callable[..., Config]
    ) -> None:
        config = make_config(subcommand="phase add", event_id="summer2026")
        assert (
            config._commit_message("invited")
            == "lovebird: phase add invited (event: summer2026)"
        )

    def test_omits_the_event_when_there_is_none(
        self, make_config: Callable[..., Config]
    ) -> None:
        config = make_config(subcommand="reformat", event_id="")
        assert config._commit_message() == "lovebird: reformat"
