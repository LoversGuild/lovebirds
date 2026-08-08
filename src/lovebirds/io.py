# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""
IO operations for registry data.
"""

__all__ = [
    "gpg_decrypt",
    "load_event",
    "load_people",
    "save_people",
]

from datetime import datetime
import logging
import os
import shutil
import subprocess
import sys
import tempfile
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
    if _is_gpg_file(filename):
        data = gpg_decrypt(filename)
        return _people_decoder.decode(data.decode("utf-8"))
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
    _safe_write_file(filename, _encrypt_if_gpg(filename, yaml_data))


def gpg_decrypt(filename: FilePath) -> bytes:
    """Decrypt a GPG-encrypted file and return its plaintext."""

    result = subprocess.run(
        ["gpg", "--batch", "--decrypt", os.fsdecode(filename)],
        stdout=subprocess.PIPE,
        check=True,
    )
    return result.stdout


### Internal ###

# The database is encrypted when its name ends in _GPG_SUFFIX. Its recipients
# and their public keys are configured by two siblings of the database file.
_GPG_SUFFIX = ".gpg"
_GPG_ID_FILENAME = ".gpg-id"
_GPG_PUBKEYS_DIRNAME = ".gpg-pubkeys"


def _encrypt_if_gpg(filename: FilePath, data: bytes) -> bytes:
    """Encrypt data to the recipients named in .gpg-id when the destination is
    a GPG file. Return it unchanged otherwise.
    """

    if not _is_gpg_file(filename):
        return data
    # Recipients may be unknown to this keyring — a co-organizer who has just
    # been added, say — so make their keys importable before encrypting.
    _import_gpg_pubkeys(filename)
    return _gpg_encrypt(data, _read_gpg_ids(filename))


def _is_gpg_file(filename: FilePath) -> bool:
    return os.fsdecode(filename).endswith(_GPG_SUFFIX)


def _sibling_path(database_path: FilePath, name: str) -> str:
    """Path of the entry called `name` in the database file's own directory."""

    return os.path.join(os.path.dirname(os.fsdecode(database_path)), name)


def _read_gpg_ids(database_path: FilePath) -> list[str]:
    gpg_id_path = _sibling_path(database_path, _GPG_ID_FILENAME)
    if not os.path.isfile(gpg_id_path):
        raise FileNotFoundError(
            f"No {gpg_id_path} file found. "
            f"Required for encrypting {os.fsdecode(database_path)}."
        )
    with open(gpg_id_path, "r", encoding="utf-8") as f:
        ids = [
            stripped
            for line in f
            if (stripped := line.strip()) and not stripped.startswith("#")
        ]
    if not ids:
        raise ValueError(f"No GPG key IDs found in {gpg_id_path}")
    return ids


def _import_gpg_pubkeys(database_path: FilePath) -> None:
    pubkeys_dir = _sibling_path(database_path, _GPG_PUBKEYS_DIRNAME)
    if not os.path.isdir(pubkeys_dir):
        return
    for entry in sorted(os.listdir(pubkeys_dir)):
        key_file = os.path.join(pubkeys_dir, entry)
        if os.path.isfile(key_file):
            logging.info(f"Importing GPG public key from {key_file}")
            result = subprocess.run(["gpg", "--batch", "--import", key_file])
            if result.returncode != 0:
                # Not everything that lands in this directory has to be a key
                # — a README, or a .DS_Store from an operator's machine — and
                # refusing to save the database over one would be absurd. A
                # recipient whose key is genuinely missing still fails, at
                # encryption time, where the diagnosis is clearer.
                logging.warning(f"Could not import {key_file}. Ignoring it.")


def _gpg_encrypt(data: bytes, recipient_ids: list[str]) -> bytes:
    # --trust-model always: the recipients are the ones the operator listed in
    # .gpg-id, which is the authority here. Under the default trust model gpg
    # refuses to encrypt to a key the local keyring has not signed, which would
    # make --batch operation fail on a keyring that has just imported a key
    # from .gpg-pubkeys/.
    cmd = ["gpg", "--batch", "--encrypt", "--trust-model", "always"]
    for rid in recipient_ids:
        cmd.extend(["--recipient", rid])
    result = subprocess.run(
        cmd,
        input=data,
        stdout=subprocess.PIPE,
        check=True,
    )
    return result.stdout


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
