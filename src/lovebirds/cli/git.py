# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Git operations on the repository holding the participation database.

The database is expected to live in a git work tree, and git is what makes a
save durable: an edit that has been written but not committed is an edit that
can be lost. Pulling and pushing therefore prompt for a retry instead of
giving up, and every operation names its repository explicitly with `git -C`.
"""

import logging
import os
import subprocess
import traceback

__all__ = [
    "check_work_tree",
    "commit_and_push",
    "pull",
]


def check_work_tree(people_file: str) -> None:
    """Exit with an error unless people_file lies inside a git work tree."""

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                _repo_dir(people_file),
                "rev-parse",
                "--is-inside-work-tree",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise SystemExit(
            "Error: git is not installed.\nUse --no-git to run without it."
        )
    except subprocess.CalledProcessError as exc:
        # Being outside a repository is only one of the reasons git rejects
        # this: a mistyped path and a refused ownership check land here too,
        # and telling the operator to pass --no-git would be poor advice for
        # either. Let git say what actually went wrong.
        raise SystemExit(
            f"Error: cannot manage {people_file} with git: {exc.stderr.strip()}\n"
            "Use --no-git to bypass this check."
        )

    # Inside a bare repository, or inside a .git directory, git answers the
    # question rather than refusing it: exit status 0 and "false" on stdout.
    # Committing there would fail later, after the database has been written.
    if result.stdout.strip() != "true":
        raise SystemExit(
            f"Error: {people_file} is inside a git repository, but not inside "
            "a work tree.\nUse --no-git to bypass this check."
        )


def pull(people_file: str) -> None:
    """Update the repository holding people_file from its remote, if any."""

    repo_dir = _repo_dir(people_file)
    if not _has_upstream(repo_dir):
        logging.info("No remote tracking branch. Skipping pull.")
        return
    _run_until_success(["git", "-C", repo_dir, "pull"], "Git pull failed.")


def commit_and_push(people_file: str, message: str) -> None:
    """Commit people_file, and only people_file, and push it if there is a
    remote tracking branch to push to.
    """

    repo_dir = _repo_dir(people_file)
    # Absolute, because every git invocation below runs with -C repo_dir:
    # a relative pathspec would be resolved against repo_dir instead of the
    # directory the user ran lovebird from.
    people_file = os.path.abspath(people_file)

    # `git commit <pathspec>` bypasses the index, but it refuses a path git
    # does not track yet, so a database file saved for the first time has to
    # be added before it can be committed.
    subprocess.run(["git", "-C", repo_dir, "add", people_file], check=True)

    if not _is_staged(repo_dir, people_file):
        logging.info("Nothing to commit.")
        return
    subprocess.run(
        ["git", "-C", repo_dir, "commit", people_file, "-m", message],
        check=True,
    )

    if not _has_upstream(repo_dir):
        logging.info("No remote tracking branch. Skipping push.")
        return
    _run_until_success(["git", "-C", repo_dir, "push"], "Git push failed.")


### Internal ###


def _repo_dir(people_file: str) -> str:
    """Directory to hand to `git -C`: the one holding the database file.

    Absolute, so that a database named without any directory component still
    yields a directory to work in.
    """

    return os.path.dirname(os.path.abspath(people_file))


def _has_upstream(repo_dir: str) -> bool:
    """Whether the checked-out branch tracks a remote branch."""

    result = subprocess.run(
        [
            "git",
            "-C",
            repo_dir,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def _is_staged(repo_dir: str, path: str) -> bool:
    """Whether the staged content of path differs from HEAD.

    Asked before committing, because `git commit` exiting non-zero does not
    distinguish "there was nothing to commit" from a commit that genuinely
    failed — an unset user.email, or a hook that said no. Reporting the
    latter as the former would tell the operator their save needed no commit
    when in fact it never got one.
    """

    result = subprocess.run(
        ["git", "-C", repo_dir, "diff", "--cached", "--quiet", "--", path]
    )
    return result.returncode != 0


def _run_until_success(cmd: list[str], failure_message: str) -> None:
    """Run cmd, prompting for a retry until it succeeds.

    Networked git operations fail for reasons that go away on their own — no
    connectivity, a race with another operator — so abandoning the run would
    lose work that a second attempt would have saved.
    """

    while True:
        try:
            subprocess.run(cmd, check=True)
            return
        except subprocess.CalledProcessError:
            traceback.print_exc()
            input(f"{failure_message} Press enter to retry.")
