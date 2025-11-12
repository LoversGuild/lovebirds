# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""CLI configuration data types."""

import argparse
from dataclasses import dataclass
import logging
import traceback

from typeguard import TypeCheckError, check_type

from lovebirds.models.events import Event, EventId
from lovebirds.io import backup_file, save_people
from lovebirds.models.people import People


@dataclass(kw_only=True)
class Config:
    args: argparse.Namespace
    event: Event | None
    event_id: EventId
    people: People

    def save_people(self, backup: bool = True) -> None:
        try:
            check_type(self.people, People)
        except TypeCheckError as exc:
            logging.error(f"Type checking of people failed: {exc}.")
            if not self.args.dry_run:
                logging.error("Continuing may be dangerous.")
                input("Hit <Enter> to continue anyway...")

        if self.args.dry_run:
            return

        if backup:
            backup_file(self.args.people_file)

        # Saving is critical: loop until we succeed.
        while True:
            try:
                save_people(self.args.people_file, self.people)
                break
            except BaseException as exc:
                traceback.print_exc()
                input("Database saving failed. Press enter to retry.")
