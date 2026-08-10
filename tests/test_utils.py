import datetime

import pytest

from lovebirds.utils import (
    calculate_age,
    is_valid_iso_datetime,
    local_now,
    parse_datetime,
    show_datetime,
    utc_now,
)


class TestCalculateAge:
    def test_birthday_passed(self) -> None:
        birth = datetime.datetime(2000, 1, 15)
        current = datetime.datetime(2025, 6, 1)
        assert calculate_age(birth, current) == 25

    def test_birthday_not_passed(self) -> None:
        birth = datetime.datetime(2000, 12, 25)
        current = datetime.datetime(2025, 6, 1)
        assert calculate_age(birth, current) == 24

    def test_on_birthday(self) -> None:
        birth = datetime.datetime(2000, 6, 1)
        current = datetime.datetime(2025, 6, 1)
        assert calculate_age(birth, current) == 25

    def test_day_before_birthday(self) -> None:
        birth = datetime.datetime(2000, 6, 2)
        current = datetime.datetime(2025, 6, 1)
        assert calculate_age(birth, current) == 24

    def test_leap_year_birth(self) -> None:
        birth = datetime.datetime(2000, 2, 29)
        current = datetime.datetime(2025, 3, 1)
        assert calculate_age(birth, current) == 25


class TestIsValidIsoDatetime:
    @pytest.mark.parametrize(
        "value",
        ["2025-01-15", "2025-01-15T10:30:00", "2025-01-15T10:30:00+02:00"],
    )
    def test_valid(self, value: str) -> None:
        assert is_valid_iso_datetime(value) is True

    @pytest.mark.parametrize(
        "value",
        ["not-a-date", "", "2025-13-01", "yesterday"],
    )
    def test_invalid(self, value: str) -> None:
        assert is_valid_iso_datetime(value) is False


class TestParseDatetime:
    def test_iso_format(self) -> None:
        result = parse_datetime("2025-01-15T10:30:00")
        assert result == datetime.datetime(2025, 1, 15, 10, 30, 0)

    def test_rfc5322_format(self) -> None:
        result = parse_datetime("Tue, 15 Jan 2025 10:30:00 +0000")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Not an ISO or RFC5322"):
            parse_datetime("not-a-date")


class TestShowDatetime:
    def test_with_value(self) -> None:
        dt = datetime.datetime(2025, 1, 15, 10, 30, 0)
        assert show_datetime(dt) == dt.isoformat()

    def test_with_none(self) -> None:
        assert show_datetime(None) == "None"


class TestTimezoneAware:
    def test_local_now(self) -> None:
        result = local_now()
        assert result.tzinfo is not None

    def test_utc_now(self) -> None:
        result = utc_now()
        assert result.tzinfo is not None
        assert result.tzinfo == datetime.timezone.utc
