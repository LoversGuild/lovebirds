# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Main command-line interface to Lovebirds."""

import argparse
import logging
import os
import sys

from lovebirds.cli import git
from lovebirds.cli.config import Config
from lovebirds.cli.edit_cmd import edit_people
from lovebirds.cli.list import list_people
from lovebirds.cli.phase import add_phase
from lovebirds.cli.reformat import reformat_people
from lovebirds.cli.registrations import import_registrations
from lovebirds.cli.resolve import resolve_refs
from lovebirds.cli.sendmail import send_messages
from lovebirds.io import load_event, load_people
from lovebirds.models.people import (
    InformationSource,
    ParticipationRole,
    ParticipationStatus,
    find_person_id_by_email,
)
from lovebirds.statistics import get_event_participants_statistics

__all__ = ["main"]


def parse_arguments() -> Config:
    def add_event_id_option(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-e",
            "--event",
            metavar="EVENT_ID",
            required=True,
            type=str,
            dest="event_id",
            help="Manage participation for event EVENT_ID",
        )

    def add_operator_option(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-o",
            "--operator",
            metavar="OPERATOR_ID",
            type=str,
            dest="operator",
            required=True,
            help="Email address of the person to be marked as an operator",
        )

    def add_source_option(parser: argparse.ArgumentParser, required: bool) -> None:
        parser.add_argument(
            "-S",
            "--source",
            metavar="SOURCE",
            required=required,
            choices=sorted(list(InformationSource.__members__.keys())),
            default=None,
            dest="source",
            help="Set information source of records to SOURCE.",
        )

    def add_time_option(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "-t",
            "--time",
            metavar="TIME_SPEC",
            required=False,
            type=str,
            default=None,
            dest="time",
            help=(
                "Set time of records to TIME_SPEC."
                "TIME_SPEC can be in one of the ISO formats or in RFC 5322 email message format."
            ),
        )

    root = argparse.ArgumentParser(
        description="A tool for participation management for The Lovers’ Guild’'s events"
    )

    # Common options
    root.add_argument(
        "-p",
        "--people-file",
        metavar="FILE",
        dest="people_file",
        type=str,
        required=True,
        help="File to load and save participant information from",
    )
    root.add_argument(
        "-l",
        "--log-level",
        metavar="LEVEL",
        dest="log_level",
        choices=["critical", "error", "warning", "info", "debug"],
        default="info",
        help="Set logging level",
    )
    root.add_argument(
        "-n",
        "--dry-run",
        dest="dry_run",
        default=False,
        action="store_true",
        help="Only show what would be done, don't execute actions.",
    )
    root.add_argument(
        "--no-git",
        dest="no_git",
        default=False,
        action="store_true",
        help="Don't automatically pull before loading or commit and push after saving the database file.",
    )

    # Subcommands of root
    root_sub = root.add_subparsers(title="Subcommands")

    list_cmd = root_sub.add_parser(
        "list", help="List participation information for an event"
    )
    list_cmd.add_argument(
        "columns",
        metavar="EXPRESSION",
        type=str,
        nargs="+",
        help="An expression to be evaluated and printed as a column of the table.",
    )
    add_event_id_option(list_cmd)
    list_cmd.add_argument(
        "-f",
        "--filter",
        metavar="EXPR",
        type=str,
        dest="filter_expr",
        default="true",
        help="Filter people by boolean expression",
    )
    list_cmd.add_argument(
        "--html",
        dest="html",
        default=False,
        action="store_true",
        help="Write output as HTML table.",
    )
    list_cmd.add_argument(
        "-n",
        "-enumerate",
        dest="enumerate",
        default=False,
        action="store_true",
        help="Enumerate entries of the table",
    )
    list_cmd.add_argument(
        "-s",
        "--sort",
        metavar="EXPR",
        type=str,
        dest="sort_key",
        default=None,
        help="An expression evaluated to get the sorting key",
    )
    list_cmd.set_defaults(function=list_people, subcommand="list")

    phase = root_sub.add_parser("phase", help="Manage participation phases")
    add_event_id_option(phase)

    phase_sub = phase.add_subparsers(title="Phase subcommands")
    phase_add = phase_sub.add_parser("add", help="Add a new participation phase record")
    phase_add.add_argument(
        "-c",
        "--comment",
        metavar="COMMENT",
        required=False,
        default=None,
        dest="new_comment",
        type=str,
        help="Set comment",
    )
    add_operator_option(phase_add)
    phase_add.add_argument(
        "-r",
        "--role",
        metavar="ROLE",
        choices=sorted(list(ParticipationRole.__members__.keys())),
        default=None,
        dest="new_role",
        required=False,
        help=(
            "Set role of the person to ROLE."
            "If not given, value is inherited from the latest record"
        ),
    )
    phase_add.add_argument(
        "-s",
        "--status",
        metavar="STATUS",
        choices=sorted(list(ParticipationStatus.__members__.keys())),
        dest="new_status",
        required=True,
        help="Set participation status of the person to STATUS",
    )
    add_source_option(phase_add, required=False)
    add_time_option(phase_add)
    phase_add.add_argument(
        "-x",
        "--expression",
        metavar="EXPR",
        type=str,
        dest="expr",
        default=None,
        help="An jinja2 expression that returns a bool when evaluated. If True, a new participation phase is added for the person.",
    )
    phase_add.set_defaults(function=add_phase, subcommand="phase add")

    reformat = root_sub.add_parser(
        "reformat",
        help="Parse and rewrite participation database file.",
        description="This command is useful for reformatting the database after manual editing.",
    )
    reformat.set_defaults(function=reformat_people, subcommand="reformat")

    edit = root_sub.add_parser(
        "edit",
        help="Open participation database in $EDITOR for manual editing.",
    )
    edit.set_defaults(function=edit_people, subcommand="edit")

    register = root_sub.add_parser(
        "register", help="Import signups from the retistration form"
    )
    register.add_argument(
        "files",
        metavar="FILES",
        type=str,
        nargs="+",
        help="Names of encrypted registration files created by Lentopusu",
    )
    add_operator_option(register)
    register.set_defaults(function=import_registrations, subcommand="register")

    resolve = root_sub.add_parser(
        "resolve-refs", help="Replace named person references with person identifiers"
    )
    resolve.set_defaults(function=resolve_refs, subcommand="resolve-refs")

    send = root_sub.add_parser(
        "send", help="Send a mass e-mail message to participants"
    )
    send.add_argument(
        "msg_name",
        metavar="MESSAGE_NAME",
        type=str,
        help="Name of a message to be sent",
    )
    send.add_argument(
        "-e",
        "--event-file",
        metavar="EVENT_FILE",
        required=True,
        type=str,
        dest="event_file",
        help="File to read event and message descriptions from",
    )
    add_operator_option(send)

    # Mailbox commands
    send.add_argument(
        "-f",
        "--fcc",
        metavar="MAILBOX_PATH",
        type=str,
        dest="mailbox_path",
        default=None,
        help="Write messaegs to a mailbox file or directory after sending",
    )
    send.add_argument(
        "-F",
        "--test-fcc",
        metavar="MAILBOX_PATH",
        type=str,
        dest="test_mailbox_path",
        default=None,
        help="Write messaegs to a mailbox file or directory in addition to sending (even in dry-run mode)",
    )
    send.add_argument(
        "--test-fcc-delete",
        action="store_true",
        dest="test_mailbox_delete",
        default=False,
        help="Delete all messages from the test Fcc mailbox before adding new ones (even in dry-run mode)",
    )
    send.add_argument(
        "-t",
        "--mailbox-type",
        metavar="TYPE",
        dest="mailbox_type",
        choices=["maildir", "mbox"],
        default="maildir",
        help="Set mailbox type for --fcc and --test-fcc",
    )

    send.set_defaults(function=send_messages, subcommand="send")

    args = root.parse_args()

    program_name = os.path.basename(sys.argv[0])
    log_format = f"{program_name}: %(levelname)s: %(message)s"
    logging.basicConfig(level=args.log_level.upper(), format=log_format)
    logging.debug(f"Setting log level to {args.log_level}")

    if not args.no_git:
        git.check_work_tree(args.people_file)
        git.pull(args.people_file)

    # Load people
    people = load_people(args.people_file)
    if "operator" in args:
        operator_id = find_person_id_by_email(people, args.operator)
        if operator_id is None:
            raise RuntimeError(f"Undefined operator id: {args.operator}")
    else:
        operator_id = None

    # Load event data, if needed
    if "event_id" in args:
        event = None
        event_id = args.event_id
    elif "event_file" in args:
        event = load_event(args.event_file)
        event_id = event.event_id
    else:
        event_id = None
        event = None

    event_participants_stats = (
        get_event_participants_statistics(event_id, people)
        if event_id is not None
        else None
    )
    config = Config(
        args=args,
        event=event,
        event_id=event_id,
        event_participants_stats=event_participants_stats,
        operator_id=operator_id,
        people=people,
    )
    return config


def main() -> None:
    config = parse_arguments()

    # Run selected action
    config.args.function(config)


if __name__ == "__main__":
    main()
