import pytest

from mashumaro.codecs import BasicDecoder, BasicEncoder

from lovebirds.models.people import Person
from lovebirds.models.email import EmailAddress


class TestForbidExtraKeys:
    def test_unknown_key_raises(self) -> None:
        decoder = BasicDecoder(Person)
        data = {
            "email": "test@example.com",
            "languages": ["en"],
            "totally_unknown_field": "oops",
        }
        with pytest.raises(Exception):
            decoder.decode(data)


class TestOmitDefault:
    def test_defaults_omitted_in_serialization(self) -> None:
        person = Person(
            email=EmailAddress("test@example.com"),
            languages=["en"],
        )
        encoder = BasicEncoder(Person)
        encoded = encoder.encode(person)
        # Fields at their default value should be omitted
        assert "locked" not in encoded
        assert "aliases" not in encoded
        assert "comment" not in encoded

    def test_non_default_values_present(self) -> None:
        person = Person(
            email=EmailAddress("test@example.com"),
            languages=["en"],
            locked=True,
        )
        encoder = BasicEncoder(Person)
        encoded = encoder.encode(person)
        assert encoded["locked"] is True


class TestMissingRequiredField:
    def test_missing_email_raises(self) -> None:
        decoder = BasicDecoder(Person)
        data = {"languages": ["en"]}
        with pytest.raises(Exception):
            decoder.decode(data)

    def test_missing_languages_raises(self) -> None:
        decoder = BasicDecoder(Person)
        data = {"email": "test@example.com"}
        with pytest.raises(Exception):
            decoder.decode(data)
