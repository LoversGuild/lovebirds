# ©2025 The Lovers’ Guild
# This file is licensed under the GNU General Public License version 3.0.

"""
Simple dataclass typechecker extension for `typeguard`
"""

from dataclasses import is_dataclass
from inspect import isclass
from typing import Any, get_type_hints

from typeguard import (
    CollectionCheckStrategy,
    ForwardRefPolicy,
    TypeCheckError,
    TypeCheckMemo,
    TypeCheckerCallable,
    check_type,
)

from lovebirds.models.people import *


def typecheck_dataclass(
    value: Any, origin_type: Any, args: tuple[Any, ...], memo: TypeCheckMemo
) -> None:
    if not (is_dataclass(value) and is_dataclass(type(value))):
        raise TypeCheckError("is not an instance of a dataclass")
    if not isinstance(value, origin_type):
        raise TypeCheckError(f"is not an instance of {origin_type.__qualname__}")

    for name, hint in get_type_hints(origin_type).items():
        check_type(
            getattr(value, name),
            hint,
            forward_ref_policy=ForwardRefPolicy.ERROR,
            collection_check_strategy=CollectionCheckStrategy.ALL_ITEMS,
        )


def typecheck_people(
    value: Any, origin_type: Any, args: tuple[Any, ...], memo: TypeCheckMemo
) -> None:
    for id, person in value.items():
        check_type(id, PersonId)
        check_type(person, Person)


def typecheck_person_ref(
    value: Any, origin_type: Any, args: tuple[Any, ...], memo: TypeCheckMemo
) -> None:
    if isinstance(value, PersonRefById):
        check_type(value, PersonRefById)
    elif isinstance(value, PersonRefByName):
        check_type(value, PersonRefByName)
    else:
        raise TypeCheckError(f"Invalid person reference: {value}")


def dataclass_typechecker_lookup(
    origin_type: Any, args: tuple[Any, ...], extras: tuple[Any, ...]
) -> TypeCheckerCallable | None:
    if origin_type == People:
        return typecheck_people
    elif origin_type == PersonRef:
        return typecheck_person_ref
    elif isclass(origin_type) and is_dataclass(origin_type):
        if len(args) != 0:
            raise TypeCheckError(
                "dataclasses with generic parameters are not supported"
            )
        return typecheck_dataclass
    return None
