# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""List people's information"""

import logging
import sys
from typing import Any

import jinja2

from lovebirds.cli.config import Config
from lovebirds.models.people import ParticipationStatus
from lovebirds.templates.eval import eval_string
from lovebirds.templates.person import person_to_dict


def list_people(config: Config) -> None:
    event_id = config.args.event_id
    headers = config.args.columns.copy()
    headers = [hdr.replace("_", " ") for hdr in headers]

    if config.args.enumerate:
        headers.insert(0, "#")

    rows = []
    for p in config.people.values():
        globals = person_to_dict(p, event_id)

        # Find preferences
        if (
            event_id is not None
            and (participation := p.participation.get(event_id)) is not None
            and len(participation.registrations) != 0
        ):
            prf = participation.registrations[-1].preferences
        else:
            prf = None

        # Build statistics string
        stats: dict[str, int] = {}
        for part in reversed(p.participation.values()):
            # Update preferences, if they are not known
            if prf is None and len(part.registrations) != 0:
                prf = part.registrations[-1].preferences
            for phase in part.phases:
                if phase.status.name not in stats:
                    stats[phase.status.name] = 1
                else:
                    stats[phase.status.name] += 1
        stats_str = " ".join(
            [key[0] + str(value) for key, value in sorted(stats.items())]
        )
        globals["statistics"] = stats_str

        if prf is not None:
            if prf.sensuality is not None:
                orientation = f"⚘:{prf.sensuality.vulvae.value}→{prf.sex.vulvae.value},▲:{prf.sensuality.penes.value}→{prf.sex.penes.value}"
            else:
                orientation = f"⚘:→{prf.sex.vulvae.value},▲:→{prf.sex.penes.value}"
        else:
            orientation = None
        globals["orientation"] = orientation
        values = []

        include = False
        try:
            include = eval_string(
                "%" + config.args.filter_expr, globals, "<command line -f>"
            )
        except jinja2.TemplateRuntimeError as exc:
            logging.error(f"Template evaluation failed for {p.named_email}: {exc}")
            if event_id is not None and event_id not in p.participation:
                continue
            else:
                raise
        if include is False:
            continue
        elif include is not True:
            logging.error(
                f"Filter expression `{config.args.filter_expr}' returned non-boolean value: `{include}'"
            )

        if config.args.sort_key is not None:
            try:
                sort_key = eval_string(
                    "%" + config.args.sort_key, globals, "<command line -s>"
                )
            except jinja2.TemplateRuntimeError as exc:
                logging.error(
                    f"Sort key template evaluation failed for {p.named_email}: {exc}"
                )

                if event_id is not None and event_id not in p.participation:
                    sort_key = ""
                else:
                    raise
        else:
            sort_key = ""

        for expr in config.args.columns:
            val = eval_string("%" + expr, globals, f"<command line>")
            values.append(val)
        rows.append([sort_key] + values)

    if config.args.sort_key is not None:
        rows.sort(key=lambda v: v[0])

    # Remove sort_king key and add enumeration
    for num, row in enumerate(rows):
        del row[0]
        if config.args.enumerate:
            row.insert(0, num + 1)

    if config.args.html:
        output = table_to_html(headers, rows)
    else:
        output = table_to_text(headers, rows)
    sys.stdout.write(output)


def table_to_html(headers: list[str], rows: list[list[Any]]) -> str:
    import html

    def htmlify(value: Any) -> str:
        if value is None:
            value = "❌"
        elif value == "":
            value = "—"
        else:
            value = str(value)
        return html.escape(value)  # type: ignore

    doc = [
        "<!DOCTYPE html>",
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="fi" xml:lang="fi">',
        '<head> <meta charset="utf-8" /> </head>',
        "<body><table><tr>",
    ]
    doc.extend(["<th>" + htmlify(hdr) + "</th>" for hdr in headers])
    doc.append("</tr>")

    for row in rows:
        doc.append(
            "<tr>"
            + " ".join(["<td>" + htmlify(cell) + "</td>" for cell in row])
            + "</tr>"
        )
    doc.append("</table></body></html>\n")
    return "\n".join(doc)


def table_to_text(headers: list[str], rows: list[list[Any]]) -> str:
    import texttable

    table = texttable.Texttable()
    table.set_deco(table.HEADER | table.VLINES)
    table.set_max_width(160)
    table.header(headers)
    table.add_rows(rows, header=False)
    return table.draw() + "\n"  # type: ignore
