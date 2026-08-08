# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""CLI configuration data types."""

import argparse
from dataclasses import dataclass
import logging
import traceback
from typing import Any

from typeguard import TypeCheckError, check_type

from lovebirds.cli import git
from lovebirds.models.events import Event, EventId
from lovebirds.io import save_people
from lovebirds.models.people import People, PersonId
from lovebirds.statistics import EventParticipantsStatistics


@dataclass(kw_only=True)
class Config:
    args: argparse.Namespace
    event: Event | None
    event_id: EventId
    people: People
    event_participants_stats: EventParticipantsStatistics | None = None
    operator_id: PersonId | None

    def save_people(self, commit_detail: str = "") -> None:
        """Write the database out and record it in git.

        commit_detail adds a subcommand's own words to the commit message —
        which status a phase set, say.
        """

        self.write_people()
        self.commit_people(commit_detail)

    def write_people(self) -> None:
        """Write the database out without recording it in git.

        For subcommands that save repeatedly: `send` writes after each
        message, so that an interrupted mailing still knows who has already
        been written to, but commits once at the end rather than leaving one
        commit and one push per recipient.
        """

        try:
            check_type(self.people, People)
        except TypeCheckError as exc:
            logging.error(f"Type checking of people failed: {exc}.")
            if not self.args.dry_run:
                logging.error("Continuing may be dangerous.")
                input("Hit <Enter> to continue anyway...")

        if self.args.dry_run:
            return

        # Saving is critical: loop until we succeed.
        while True:
            try:
                save_people(self.args.people_file, self.people)
                break
            except BaseException as exc:
                traceback.print_exc()
                input("Database saving failed. Press enter to retry.")

    def commit_people(self, commit_detail: str = "") -> None:
        """Record the database, as it now stands on disk, in git.

        Safe to call when nothing was written: git reports that there is
        nothing to commit and no empty commit is made.
        """

        if self.args.dry_run or self.args.no_git:
            return
        git.commit_and_push(self.args.people_file, self._commit_message(commit_detail))

    def _commit_message(self, commit_detail: str = "") -> str:
        """Describe the save for the git history: which subcommand made it,
        what it did, and which event it belonged to.
        """

        parts = [f"lovebird: {self.args.subcommand}"]
        if commit_detail:
            parts.append(commit_detail)
        if self.event_id:
            parts.append(f"(event: {self.event_id})")
        return " ".join(parts)
