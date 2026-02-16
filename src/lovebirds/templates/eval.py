# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""Template handling routines for message generation."""

from collections.abc import Mapping, Sequence, Set
import copy
from dataclasses import is_dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID
import inspect
from os import PathLike
from typing import Any, cast
from uuid import UUID

import jinja2


__all__ = [
    "evail_string",
    "eval_variables",
    "make_environemtn",
    "to_dict_recursive",
]


def to_dict_recursive(obj: Any) -> Any:
    """Convert an object recursively into a dict so that it is safe to use as a jinja2 template variable value."""
    match obj:
        case None | bool() | datetime() | float() | int() | str() | UUID():
            return obj
        case Enum():
            return obj.name
        case Mapping():
            return {
                to_dict_recursive(key): to_dict_recursive(value)
                for key, value in obj.items()
            }
        case Sequence():
            return [to_dict_recursive(elt) for elt in obj]
        case Set():
            return {to_dict_recursive(elt) for elt in obj}
        case _:
            # This should be a dataclass
            if not is_dataclass(obj):
                raise ValueError(
                    f"Cannot represent object as tempalte variable value: {obj}"
                )

            # Convert all attributes to a dict
            members = inspect.getmembers(
                obj,
                lambda m: not (
                    inspect.isclass(m) or inspect.isfunction(m) or inspect.ismethod(m)
                ),
            )
            return {
                to_dict_recursive(key): to_dict_recursive(value)
                for key, value in members
                if not key.startswith("_")
            }


def make_environment(dirs: list[str | PathLike[str]]) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(dirs),
        autoescape=jinja2.select_autoescape(default_for_string=False, default=False),
        undefined=jinja2.StrictUndefined,
        line_statement_prefix="%",
        line_comment_prefix="%#",
        trim_blocks=False,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        auto_reload=False,
        bytecode_cache=None,
    )


# This is a marker object stored in variable lists, when a given variable is
# completely evaluated. This prevents re-evaluation.
_evaluated = object()


def eval_variables(
    variables: dict[str, Any],
    root: dict[str, Any] | None = None,
    globals: dict[str, Any] = {},
) -> tuple[dict[str, Any], bool | None]:
    """Evaluate variables, and return the result values.

    Parameters:
        variables: dict[str, Any]
            All string values are evaluated as jinja2 templates. This is
            done recursively for all child lists and dicts.

        root: dict[str, Any]
            A dictionary where evaluated values are stored.
    Returns:
        tuple[dict[str, Any], bool]
            The first element is a data structure of the same form as
            the 'variables' parameter, except that all the values are
            evaluated as much as is possible.
            The second value is True if everything was evaluated,
            False if something was evaluated, and None if nothing was evaluated.
            This allows using eval_variables in succession (by passing the
            result data from a previous round as a 'root' parameter
            for the next round) to pre-evaluate all possible variables and
            later to evaluate all the rest.

    If the result parameter is given, variables are updated in place within
    it. This allows re-evaluating something that previously failed because of
    unresolved references.
    """

    if root is None:
        root = {}

    # Copy the variables so that we can freely modify them
    variables = copy.deepcopy(variables)

    # Evaluate the variables (supporting forward references).
    # Thus we evalute all variables until all evaluations either
    # succeed or fail.
    completion: bool | None = False
    while completion is False:
        completion = eval_container(
            variables=variables, root=root, container=root, globals=globals, path=""
        )

    return root, bool(completion)


def eval_element(
    variables: dict[str, Any] | list[Any],
    root: dict[str, Any],
    container: dict[str, Any] | list[Any],
    key: str | int,
    globals: dict[str, Any],
    path: str,
) -> bool | None:
    """Evaluate 'variables[key]' in an appropriate way. 'root' is the root of the variable
    evaluation results dictionary, 'container' is the list/dictionary where this
    object is to be stored at index defined by 'key'. 'prefix' is the string
    containing names of previous named/numbered mappings separated by dots. It
    is used for error messages only.

    Return True if evaluation was complete, False if incomplete, and None if
    no evaluation happened at all.
    """

    obj = variables[key]  # type: ignore
    if obj is _evaluated:
        return True

    key_defined = (
        isinstance(container, dict) and isinstance(key, str) and key in container
    ) or (isinstance(container, list) and isinstance(key, int) and len(container) > key)

    completion = None

    subcontainer: dict[str, Any] | list[Any]
    if isinstance(obj, (dict, list)):
        if not key_defined:
            if isinstance(obj, dict):
                subcontainer = {}
            else:
                subcontainer = []
            container[key] = subcontainer  # type: ignore
        else:
            subcontainer = container[key]  # type: ignore
        completion = eval_container(obj, root, subcontainer, globals, path)
    elif isinstance(obj, str):
        assert not key_defined
        result = eval_string(
            obj, {**globals, **root}, source=path, allow_undefined=True
        )
        if not isinstance(result, jinja2.runtime.Undefined):
            container[key] = result  # type: ignore
            completion = True
    else:
        # Nothing to evaluate, just store the value as it is
        container[key] = obj  # type: ignore
        completion = True

    if completion is True:
        variables[key] = _evaluated  # type: ignore

    return completion


def eval_container(
    variables: dict[str, Any] | list[Any],
    root: dict[str, Any],
    container: dict[str, Any] | list[Any],
    globals: dict[str, Any],
    path: str,
) -> bool | None:
    iter = variables.keys() if isinstance(variables, dict) else range(len(variables))
    results = []
    for key in iter:
        if isinstance(variables, dict):
            suffix = ("." if path != "" else "") + cast(str, key)
        else:
            suffix = f"[{key}]."
        results.append(
            eval_element(variables, root, container, key, globals, path + suffix)
        )

    if all(results):
        return True
    elif all(r is None for r in results):
        return None
    else:
        return False


_cached_env: jinja2.Environment


def eval_string(
    expr: str,
    vars: dict[str, Any],
    source: str | None = None,
    allow_undefined: bool = False,
) -> Any:
    global _cached_env

    if "_cached_env" not in globals():
        _cached_env = make_environment([])
    try:
        if expr.startswith("%") and "\n" not in expr:
            evaluator = _cached_env.compile_expression(
                expr[1:], undefined_to_none=False
            )
            result = evaluator(vars)
        else:
            tmplt = _cached_env.from_string(expr)
            result = tmplt.render(vars)
    except jinja2.exceptions.TemplateError as e:
        raise RuntimeError(
            f"{e.__class__.__name__}: {e.message} in expression {repr (expr)}{' from ' + source if source else ''}"
        )

    if not allow_undefined and isinstance(result, jinja2.runtime.Undefined):
        raise RuntimeError(
            f"Undefined reference in expression {repr (expr)}{' from ' + source if source else ''}"
        )
    else:
        return result
