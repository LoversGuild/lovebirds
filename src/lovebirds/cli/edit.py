# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Interactive data editing."""

import builtins
import logging
import os
from pydoc import pager
import readline
import tempfile
import subprocess
import sys
import traceback
from typing import Any, Callable, Type
import yaml

import mashumaro.codecs.basic as basic_codec
import mashumaro.codecs.yaml as yaml_codec

from lovebirds.models.email import is_valid_email_address
from lovebirds.utils import FilePath

__all__ = [
    "edit_as_yaml",
    "edit_file",
    "get_user_editor",
    "input",
    "input_choice",
    "input_email",
    "input_validated",
    "input_yes_no",
]


def edit_as_yaml[S, T](
    source_type: Type[S], target_type: Type[T], data: S, prefix: str
) -> T:
    try:
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, mode="w", encoding="UTF-8"
        )
        dict_data = basic_codec.encode(data, source_type)
        commented_prefix = (
            "\n".join(map(lambda line: f"# {line}", prefix.splitlines())) + "\n\n"
        )
        temp_file.write(commented_prefix)
        yaml.dump(
            dict_data,
            temp_file,
            yaml.CSafeDumper,
            allow_unicode=True,
            default_flow_style=None,
            indent=2,
            sort_keys=False,
        )
        temp_file.close()

        while True:
            edit_file(temp_file.name)
            try:
                with open(temp_file.name, "r", encoding="utf-8") as file:
                    content = file.read()
                return yaml_codec.decode(content, target_type)
            except BaseException as exc:
                pager(
                    f"Decoding YAML data failed:\n{format_exception(exc)}\n\nFix errors in editor."
                )
    finally:
        os.remove(temp_file.name)


def edit_file(filename: FilePath) -> None:
    editor = get_user_editor()
    subprocess.run([editor, filename])


def format_exception(exc: BaseException) -> str:
    return "".join(
        traceback.format_exception(type(exc), value=exc, tb=exc.__traceback__)
    )


def get_user_editor() -> str:
    return os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"


### Console input/output (including validation)


def input(prompt: str, default: str | None = None, init: str | None = None) -> str:
    return input_validated(
        prompt=prompt, predicate=lambda _: True, default=default, init=init
    )


def input_choice(
    prompt: str, choices: set[str], default: str | None = None, init: str | None = None
) -> str:
    """
    Prompts the user to enter one of the choices, providing completion options and default value.

    Args:
        prompt: The prompt message to display to the user.
        choices: A list of available choices for completion suggestions.
        default: The default choice to use if the user enters nothing or None for no default.
        init: Initial text in the input field

    Returns:
        str: The choice entered by the user, or the default value, if valid.
    """

    def completer(text: str, state: int) -> str | None:
        options = [choice for choice in choices if choice.startswith(text)]
        return options[state] if state < len(options) else None

    if default is not None and default not in choices:
        raise ValueError(
            f"input_choice: Default value `{default}' is not a valid choice"
        )

    # Prompt for input until valid choice is received
    return input_validated(
        prompt,
        predicate=lambda val: val in choices,
        completer=completer,
        default=default,
        init=init,
    )


def input_email(
    prompt: str, default: str | None = None, init: str | None = None
) -> str:
    return input_validated(
        prompt, predicate=is_valid_email_address, default=default, init=init
    )


def input_validated(
    prompt: str,
    predicate: Callable[[str], bool],
    completer: Callable[[str, int], str | None] | None = None,
    default: str | None = None,
    init: str | None = None,
) -> str:
    """
    Prompts the user to enter input accepted by the given predicate function.

    Args:
        prompt: The prompt message to display to the user.
        predicate: A function accepting a string and returning bool determining whether the input is valid.
    completer: Readline completer function or None.
        default: The default choice to use if the user enters nothing or None for no default.
        init: Initial text in the input field

    Returns:
        str: The choice entered by the user, or the default value, if valid.
    """

    # Set up tab completion
    readline.set_completer(completer)
    readline.set_completer_delims("")
    readline.parse_and_bind("tab: complete")

    # Set default in input value
    if init:
        readline.set_startup_hook(lambda: readline.insert_text(init))
    while True:
        try:
            line = builtins.input(prompt).strip()
            readline.set_startup_hook()
            if line == "" and default is not None:
                return default
            elif predicate(line) is True:
                return line
            else:
                logging.error(f"Invalid input, try again.")
                readline.set_startup_hook(lambda: readline.insert_text(line))
        except EOFError:
            logging.error("EOF, but I don't care! (Hit <CTRL-C> to abort.)")


def input_yes_no(prompt: str, default: bool | None = None) -> bool:
    trues = {"y", "yes"}
    falses = {"n", "no"}

    def is_valid(value: str) -> bool:
        value = value.lower()
        return value in trues or value in falses

    default_str: str | None
    if default is True:
        default_str = next(iter(trues))
    elif default is False:
        default_str = next(iter(falses))
    else:
        default_str = None
    reply = input_validated(
        prompt=prompt, predicate=is_valid, default=default_str
    ).lower()
    if reply in trues:
        return True
    elif reply in falses:
        return False
    else:
        raise RuntimeError(f"input_yes_no: Impossible input: `{reply}'")
