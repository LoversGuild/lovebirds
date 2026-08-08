# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Resolve references to people by name."""

import logging
import sys

from lovebirds.cli.config import Config
from lovebirds.models.email import EmailAddress
from lovebirds.models.people import PersonId, PersonRef, PersonRefById, PersonRefByName


def resolve_refs(config: Config) -> None:
    name_map: dict[str, list[PersonId]] = {}

    def do_resolve(items: list[PersonRef], path: str) -> None:
        nonlocal name_map
        path_shown = False
        for index, item in enumerate(items):
            if not isinstance(item, PersonRefByName):
                # Already resolved
                continue
            if not path_shown:
                sys.stderr.write(f"{path}:\n")
                path_shown = True
            if (resolvees := name_map.get(item.name)) is None:
                sys.stderr.write(f"  Cannot resolve: `{item.name}'\n")
            elif len(resolvees) == 1:
                id = resolvees[0]
                sys.stderr.write(f"  Resolving `{item.name}' to `{id}'\n")
                items[index] = PersonRefById(id=id)
            else:
                sys.stderr.write(
                    f"  Cannot resolve `{item.name}' as there are multiple candidates: {resolvees}\n"
                )

    # Collect names of all people, do it in a loop to check for name collisions
    for id, person in config.people.items():
        # Build space separated name
        name = ""
        if person.first_name:
            name += person.first_name
        if name:
            name += " "
        if person.last_name:
            name += person.last_name
        if not name:
            logging.warning(f"No known names for `{id}', skipping...")
            continue

        name_map.setdefault(name, []).append(id)

    # Now walk through all registrations and resolve references
    for person in config.people.values():
        for event_id, part in person.participation.items():
            for reg in part.registrations:
                do_resolve(reg.avecs, f"{person.named_email} / {event_id} / avecs")
                do_resolve(
                    reg.personae_non_gratae,
                    f"{person.named_email} / {event_id} / personae non-gratae",
                )

    if config.args.dry_run:
        logging.info("Skipping real action in dry-run mode.")
    config.save_people()
