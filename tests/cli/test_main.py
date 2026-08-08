from typing import Any
from unittest.mock import patch, MagicMock

from lovebirds.cli.main import parse_arguments
from lovebirds.models.people import People


# --no-git is a global option, so it has to precede the subcommand.
ARGV = ["lovebird", "-p", "/tmp/repo/people.yaml"]
SUBCOMMAND = ["reformat"]


class TestGitWiring:
    @patch("lovebirds.cli.main.load_people")
    @patch("lovebirds.cli.main.git")
    def test_the_database_is_pulled_before_it_is_read(
        self, mock_git: MagicMock, mock_load: MagicMock
    ) -> None:
        """Reading first would edit a stale database and push the result over
        whatever the pull would have brought in, so the order is the point.
        """
        steps: list[str] = []
        mock_git.check_work_tree.side_effect = lambda *a: steps.append("check")
        mock_git.pull.side_effect = lambda *a: steps.append("pull")

        def load(*args: Any) -> People:
            steps.append("load")
            return {}

        mock_load.side_effect = load

        with patch("sys.argv", ARGV + SUBCOMMAND):
            parse_arguments()

        assert steps == ["check", "pull", "load"]

    @patch("lovebirds.cli.main.load_people", return_value={})
    @patch("lovebirds.cli.main.git")
    def test_no_git_touches_the_repository_not_at_all(
        self, mock_git: MagicMock, mock_load: MagicMock
    ) -> None:
        with patch("sys.argv", ARGV + ["--no-git"] + SUBCOMMAND):
            parse_arguments()

        mock_git.check_work_tree.assert_not_called()
        mock_git.pull.assert_not_called()
        mock_load.assert_called_once()
