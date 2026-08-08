# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Participation phase management commands."""

from datetime import datetime
import logging

from lovebirds.cli.config import Config
from lovebirds.models.events import EventId
from lovebirds.models.people import *
from lovebirds.templates.eval import eval_string
from lovebirds.templates.person import person_to_dict
from lovebirds.utils import local_now, parse_datetime, show_datetime


def add_phase(config: Config) -> None:
    def add(
        operator: PersonId,
        source: InformationSource | None,
        person: Person,
        event_id: EventId,
        role: ParticipationRole | None,
        status: ParticipationStatus,
        comment: str | None,
        time: datetime,
    ) -> None:
        if (participation := person.participation.get(event_id)) is None:
            participation = Participation()
            person.participation[event_id] = participation

        if len(participation.phases) != 0:
            phase = participation.phases[-1]
            if role is None:
                role = phase.role

            if comment is None:
                comment = phase.comment

            if phase.status == status:
                if source is None:
                    source = phase.source
                if (
                    phase.role == role
                    and phase.comment == comment
                    and phase.source == source
                    and phase.operator == operator
                    and phase.time is not None
                ):
                    # Nothing to change
                    return

                logging.info(
                    f"Changing last phase of `{person.named_email}': role {phase.role} -> {role}, status {phase.status} -> {status}, comment {phase.comment} -> {comment}, source {phase.source} -> {source}, operator {phase.operator} -> {operator}, time {show_datetime(phase.time)} -> {show_datetime(time)}"
                )

                # Note: assigning to previous object preserves some data—currently the comments attached to the phase
                phase.operator = operator
                phase.source = source
                phase.role = role
                phase.status = status
                phase.comment = comment
                phase.time = time
                return

        if role is None:
            logging.info(f"Skipping `{person.named_email}': no role defined")
            return
        if source is None:
            logging.info(f"Skipping `{person.named_email}': no source defined")
            return
        phase = ParticipationPhase(
            source=source,
            operator=operator,
            role=role,
            status=status,
            comment=comment or "",
            time=time,
        )
        participation.phases.append(phase)
        logging.info(
            f"Adding new phase for `{person.named_email}' to `{event_id}': {phase}"
        )

    event_id = config.args.event_id
    if config.args.expr is None:
        raise RuntimeError("No expression defined for `phase add'")

    time: datetime | None = None
    if config.args.time is not None:
        time = parse_datetime(config.args.time)
    source = (
        InformationSource(config.args.source)
        if config.args.source is not None
        else None
    )

    assert config.operator_id is not None

    for p in config.people.values():
        if p.locked or p.consent.legacy:
            logging.debug(f"Skipping locked/legacy account `{p.named_email}'")
            continue

        vars = person_to_dict(p, event_id)
        result = eval_string("%" + config.args.expr, vars, "<command line>")
        if result is True:
            add(
                operator=config.operator_id,
                source=source,
                person=p,
                event_id=event_id,
                role=(
                    ParticipationRole(config.args.new_role)
                    if config.args.new_role is not None
                    else None
                ),
                status=ParticipationStatus(config.args.new_status),
                comment=config.args.new_comment,
                time=time or local_now(),
            )
        elif result is not False:
            raise RuntimeError(
                f"Evaluating condition for `{p.named_email}' returned `{repr(result)}', should be `bool'"
            )

    config.save_people()
