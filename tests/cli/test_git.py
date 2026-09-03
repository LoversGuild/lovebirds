import os
import subprocess
from collections.abc import Callable
from unittest.mock import patch, MagicMock

import pytest

from lovebirds.cli import git

from .conftest import GitRun

DB = "/tmp/repo/people.yaml"

# What `git diff --cached --quiet` reports about the staged database: it exits
# non-zero when there is a difference, so 1 means there is something to commit.
STAGED = {"--quiet": 1}
UNCHANGED = {"--quiet": 0}


def commands(mock_run: MagicMock) -> list[list[str]]:
    """The git command lines the code under test ran, in order."""
    return [call.args[0] for call in mock_run.call_args_list]


def subcommands(mock_run: MagicMock) -> list[str]:
    """The git subcommand of each command line: the word after `-C <dir>`."""
    return [cmd[3] for cmd in commands(mock_run)]


class TestCheckWorkTree:
    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_work_tree_is_accepted(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="true\n"
        )
        git.check_work_tree(DB)
        assert commands(mock_run) == [
            ["git", "-C", "/tmp/repo", "rev-parse", "--is-inside-work-tree"]
        ]

    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_bare_repository_is_refused(self, mock_run: MagicMock) -> None:
        """git answers this question inside a bare repository instead of
        refusing it — exit status 0, "false" on stdout. Reading only the exit
        status would let the run get as far as writing the database, and fail
        at `git add` with nothing committed.
        """
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="false\n"
        )
        with pytest.raises(SystemExit, match="not inside a work tree"):
            git.check_work_tree(DB)

    @patch("lovebirds.cli.git.subprocess.run")
    def test_git_explains_why_it_refused(self, mock_run: MagicMock) -> None:
        """git rejects this for more reasons than "not a repository" — a
        mistyped path and a refused ownership check among them — and telling
        the operator to pass --no-git suits none of them. Pass git's own
        message through so they can tell which one they hit.
        """
        mock_run.side_effect = subprocess.CalledProcessError(
            128, "git", stderr="fatal: detected dubious ownership in repository\n"
        )
        with pytest.raises(SystemExit, match="detected dubious ownership"):
            git.check_work_tree(DB)

    @patch("lovebirds.cli.git.subprocess.run")
    def test_missing_git_is_reported_as_such(self, mock_run: MagicMock) -> None:
        """Without git on PATH subprocess raises FileNotFoundError, which
        would otherwise reach the user as a traceback.
        """
        mock_run.side_effect = FileNotFoundError(2, "No such file or directory")
        with pytest.raises(SystemExit, match="git is not installed"):
            git.check_work_tree(DB)


class TestPull:
    @patch("lovebirds.cli.git.subprocess.run")
    def test_pulls_when_the_branch_tracks_a_remote(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
        git.pull(DB)
        assert [cmd[-1] for cmd in commands(mock_run)] == ["@{u}", "pull"]

    @patch("lovebirds.cli.git.subprocess.run")
    def test_no_tracking_branch_skips_the_pull(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        mock_run.side_effect = fake_git(returncodes={"@{u}": 128})
        git.pull(DB)
        assert ["git", "-C", "/tmp/repo", "pull"] not in commands(mock_run)

    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_failed_pull_is_fatal(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        """Being offline, or hitting a conflict, must not silently skip the
        pull: the run would then edit a database that is out of date. Nor is
        it retried: nothing has been written yet, so nothing is at stake, and
        the operator can pull by hand once the cause is dealt with.
        """
        mock_run.side_effect = fake_git(fail=frozenset({"pull"}))
        with pytest.raises(subprocess.CalledProcessError):
            git.pull(DB)
        assert commands(mock_run).count(["git", "-C", "/tmp/repo", "pull"]) == 1


class TestCommitAndPush:
    @patch("lovebirds.cli.git.subprocess.run")
    def test_adds_commits_and_pushes_the_database_alone(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        mock_run.side_effect = fake_git(returncodes=STAGED)
        git.commit_and_push(DB, "lovebird: reformat")
        assert commands(mock_run) == [
            ["git", "-C", "/tmp/repo", "add", DB],
            ["git", "-C", "/tmp/repo", "diff", "--cached", "--quiet", "--", DB],
            ["git", "-C", "/tmp/repo", "commit", DB, "-m", "lovebird: reformat"],
            [
                "git",
                "-C",
                "/tmp/repo",
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ],
            ["git", "-C", "/tmp/repo", "push"],
        ]

    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_relative_database_path_is_staged_absolutely(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        """git -C resolves a pathspec against the -C directory, not the cwd.

        Passing the path as the user typed it makes `git add` fail with
        "did not match any files" for any relative path, and since that runs
        after the database has already been written, the save is left
        uncommitted.
        """
        mock_run.side_effect = fake_git(returncodes=STAGED)
        git.commit_and_push("db/people.yaml", "lovebird: reformat")

        absolute = os.path.abspath("db/people.yaml")
        add, _diff, commit, *_ = commands(mock_run)
        assert add == ["git", "-C", os.path.dirname(absolute), "add", absolute]
        assert absolute in commit

    @patch("lovebirds.cli.git.subprocess.run")
    def test_an_unchanged_database_is_not_committed(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        mock_run.side_effect = fake_git(returncodes=UNCHANGED)
        git.commit_and_push(DB, "lovebird: reformat")
        assert subcommands(mock_run) == ["add", "diff"]

    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_failing_commit_is_not_mistaken_for_an_empty_one(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        """`git commit` exits non-zero both when there is nothing to commit
        and when the commit is refused — by a hook, or an unset user.email.
        Reporting the second as the first would tell the operator no commit
        was needed when in fact their save never got one.
        """
        mock_run.side_effect = fake_git(returncodes=STAGED, fail=frozenset({"commit"}))
        with pytest.raises(subprocess.CalledProcessError):
            git.commit_and_push(DB, "lovebird: reformat")

    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_failing_add_is_not_swallowed(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        """An `add` that fails stages nothing, so the commit that follows
        would find no change and report "Nothing to commit" — announcing
        success over a save that never reached the history.
        """
        mock_run.side_effect = fake_git(returncodes=STAGED, fail=frozenset({"add"}))
        with pytest.raises(subprocess.CalledProcessError):
            git.commit_and_push(DB, "lovebird: reformat")

    @patch("lovebirds.cli.git.subprocess.run")
    def test_no_tracking_branch_skips_the_push(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        mock_run.side_effect = fake_git(returncodes=STAGED | {"@{u}": 128})
        git.commit_and_push(DB, "lovebird: reformat")
        assert ["git", "-C", "/tmp/repo", "push"] not in commands(mock_run)

    @patch("lovebirds.cli.git.subprocess.run")
    def test_a_failed_push_is_fatal(
        self, mock_run: MagicMock, fake_git: Callable[..., GitRun]
    ) -> None:
        """A push that fails — no network, a race with another operator — is
        reported, not retried. The commit it was meant to publish is already
        in the local history, so nothing is lost, and `git push` from the
        command line finishes the job once the cause is dealt with.
        """
        mock_run.side_effect = fake_git(returncodes=STAGED, fail=frozenset({"push"}))
        with pytest.raises(subprocess.CalledProcessError):
            git.commit_and_push(DB, "lovebird: reformat")
        assert commands(mock_run).count(["git", "-C", "/tmp/repo", "push"]) == 1
