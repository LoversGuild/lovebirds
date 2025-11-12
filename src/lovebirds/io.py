# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""
IO operations for registry data.
"""

__all__ = [
    "load_event",
    "load_people",
    "save_people",
]

from datetime import datetime
import logging
import os
import tempfile
import shutil
import sys
from typing import Any

from mashumaro.codecs.yaml import YAMLDecoder
from mashumaro.codecs import BasicEncoder
import yaml

import lovebirds.models.events as e
import lovebirds.models.people as p
from lovebirds.utils import FilePath


def backup_file(filename: str | os.PathLike[str]) -> None:
    """Make backup copy of the named file.
    Timestamp of current local file is appended to the original filename.
    Returns None
    """

    if not os.path.isfile(filename):
        raise FileNotFoundError(f"backup_file: File `{filename}' does not exist")

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest_name = f"{filename}.{timestamp}"
    if os.path.exists(dest_name):
        raise FileExistsError(
            f"backup_file: Backup destination file `{filename}' already exists"
        )

    logging.info(f"Making backup copy of `{filename}' as `{dest_name}'")

    shutil.copy(filename, dest_name, follow_symlinks=False)


def load_event(filename: FilePath) -> e.Event:
    with open(filename, "r", encoding="utf-8") as file:
        return _event_decoder.decode(file.read())


def load_people(filename: FilePath) -> p.People:
    with open(filename, "r", encoding="utf-8") as file:
        return _people_decoder.decode(file.read())


def save_people(filename: FilePath, people: p.People) -> None:
    # We use BasicEncoder instead of YAMLEncoder as we want to control the
    # YAML output formatting precisely.
    sorted_people = p.sorted_people(people)
    dict_data = _people_encoder.encode(sorted_people)

    # We try to acheive YAML output taht is as easy to edit by humans as
    # possible. Therefore we prefer to use flow-style for containers which
    # only contain scalar values. With a long line length, these items are
    # easy to delete or move in a text editor.
    yaml_data = yaml.safe_dump(
        dict_data,
        stream=None,
        allow_unicode=True,
        default_flow_style=None,
        encoding="utf-8",
        indent=2,
        sort_keys=False,
        width=512,
    )
    _safe_write_file(filename, yaml_data)


### Internal ###

_event_decoder = YAMLDecoder(e.Event)

_people_decoder: YAMLDecoder[p.People] = YAMLDecoder(p.People)
_people_encoder: BasicEncoder[p.People] = BasicEncoder(p.People)


def _safe_write_file(filename: FilePath, data: bytes) -> None:
    """Safely write a file by first writing the data to a temporary file
    and then renaming that to the destination file.
    """

    temp_file = tempfile.NamedTemporaryFile(
        delete=False, dir=os.path.dirname(filename), mode="wb"
    )
    try:
        temp_file.write(data)
        temp_file.close()
        os.replace(temp_file.name, filename)
    except:
        os.remove(temp_file.name)
        raise
