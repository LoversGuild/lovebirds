# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Edit participation database in $EDITOR."""

import logging

from lovebirds.cli.config import Config
from lovebirds.cli.edit import edit_as_yaml
from lovebirds.models.people import People


EDIT_PREFIX = "Editing people database. Save and close editor when done."


def edit_people(config: Config) -> None:
    if config.args.dry_run:
        # save_people would drop the edits without a word. Say so before the
        # editor opens, rather than after a session's worth of typing.
        logging.warning("Dry run: the database will not be saved.")

    # `People` is a `type` alias for a dict rather than a class, so mypy sees
    # a TypeAliasType where edit_as_yaml declares `type[S]`. Mashumaro
    # resolves the alias happily at run time; only mypy needs appeasing, and
    # TestEditPeople covers the round trip the suppression hides.
    config.people = edit_as_yaml(
        People, People, config.people, EDIT_PREFIX  # type: ignore[arg-type]
    )
    config.save_people()
