# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Edit participation database in $EDITOR."""

import logging

from lovebirds.cli.config import Config
from lovebirds.cli.edit import edit_as_yaml, input
from lovebirds.models.people import People


EDIT_PREFIX = "Editing people database. Save and close editor when done."


def edit_people(config: Config) -> None:
    if config.args.dry_run:
        # save_people would drop the edits without a word. Say so before the
        # editor opens, rather than after a session's worth of typing — and
        # wait to be acknowledged, because the editor takes over the terminal
        # as soon as this returns and would scroll the warning away unread.
        logging.warning("Dry run: the database will not be saved.")
        input("Press <Enter> to continue...")

    original = config.people
    # `People` is a `type` alias for a dict rather than a class, so mypy sees
    # a TypeAliasType where edit_as_yaml declares `type[S]`. Mashumaro
    # resolves the alias happily at run time; only mypy needs appeasing.
    edited: People = edit_as_yaml(
        People, People, config.people, EDIT_PREFIX  # type: ignore[arg-type]
    )

    # An editing session that changed nothing — a look around, or a change
    # undone before saving — has nothing to write and nothing to say in a
    # commit message, so do not ask for one.
    if edited == original:
        logging.info("Database unchanged. Nothing to save.")
        return

    config.people = edited
    config.write_people()

    if config.args.dry_run:
        return

    # Unlike every other subcommand, `edit` cannot describe what it did: only
    # the person who did the editing knows. Ask them, and let them decline —
    # the edits are on disk either way, and an uncommitted change is left for
    # the operator to commit by hand.
    message = input("Commit message (empty line for no commit): ")
    if message:
        config.commit_people(message)
    else:
        logging.info("No commit message given. Leaving the changes uncommitted.")
