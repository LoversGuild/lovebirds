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

import contextlib
import logging
import os
import subprocess
import tempfile

from mashumaro.codecs.yaml import YAMLDecoder
from mashumaro.codecs import BasicEncoder
import yaml

import lovebirds.models.events as e
import lovebirds.models.people as p
from lovebirds.utils import FilePath


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
    """Write data to a temporary file beside the destination and rename it
    into place.

    This is the database's only protection against a failed write: the
    destination holds either its old contents or the new ones, never a
    half-written mixture. Durability beyond that point comes from the git
    commit.

    The temporary file inherits NamedTemporaryFile's 0600 mode, which then
    becomes the mode of the database. That suits a file holding personal
    data, and it is deliberate rather than incidental.
    """

    temp_file = tempfile.NamedTemporaryFile(
        delete=False, dir=os.path.dirname(filename), mode="wb"
    )
    try:
        with temp_file:
            temp_file.write(data)
        os.replace(temp_file.name, filename)
    except BaseException:
        # Cleaning up must not replace the failure being reported: that
        # exception is what the caller prints before offering a retry.
        with contextlib.suppress(OSError):
            os.remove(temp_file.name)
        raise
