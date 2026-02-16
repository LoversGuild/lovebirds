import pytest
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from typeguard import TypeCheckError, check_type

from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    People,
    Person,
    PersonRef,
    PersonRefById,
    PersonRefByName,
)
from lovebirds.models.typecheck import dataclass_typechecker_lookup


class TestTypecheckPerson:
    def test_valid_person(self, make_person: Callable[..., Person]) -> None:
        person = make_person()
        check_type(person, Person)

    def test_invalid_field_type(self) -> None:
        # Create an object that claims to be Person but has wrong field types
        person = Person.__new__(Person)
        object.__setattr__(person, "email", 12345)  # not an EmailAddress
        object.__setattr__(person, "languages", ["en"])
        object.__setattr__(person, "first_name", None)
        object.__setattr__(person, "last_name", None)
        object.__setattr__(person, "aliases", [])
        object.__setattr__(person, "locked", False)
        object.__setattr__(person, "comment", None)
        object.__setattr__(person, "birth_year", None)
        object.__setattr__(person, "phone", None)
        object.__setattr__(person, "participation", {})
        from lovebirds.models.people import Consent

        object.__setattr__(person, "consent", Consent())
        with pytest.raises(TypeCheckError):
            check_type(person, Person)


class TestTypecheckPeople:
    def test_valid_people(self, sample_people: People) -> None:
        check_type(sample_people, People)

    def test_invalid_people(self) -> None:
        bad_dict = {"not-an-email": "not-a-person"}
        with pytest.raises(TypeCheckError):
            check_type(bad_dict, People)


class TestTypecheckPersonRef:
    def test_ref_by_id(self) -> None:
        ref = PersonRefById(id=uuid4())
        check_type(ref, PersonRef)

    def test_ref_by_name(self) -> None:
        ref = PersonRefByName(name="Alice Smith")
        check_type(ref, PersonRef)

    def test_invalid_ref(self) -> None:
        with pytest.raises(TypeCheckError):
            check_type("not a ref", PersonRef)


class TestCheckerLookup:
    def test_returns_checker_for_people(self) -> None:
        checker = dataclass_typechecker_lookup(People, (), ())
        assert checker is not None

    def test_returns_checker_for_person_ref(self) -> None:
        checker = dataclass_typechecker_lookup(PersonRef, (), ())
        assert checker is not None

    def test_returns_checker_for_dataclass(self) -> None:
        checker = dataclass_typechecker_lookup(Person, (), ())
        assert checker is not None

    def test_returns_none_for_non_dataclass(self) -> None:
        checker = dataclass_typechecker_lookup(str, (), ())
        assert checker is None
