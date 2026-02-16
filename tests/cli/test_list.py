from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest

from lovebirds.cli.config import Config
from lovebirds.cli.list import list_people, table_to_html, table_to_text
from lovebirds.models.email import EmailAddress
from lovebirds.models.people import (
    Participation,
    ParticipationRole,
    ParticipationStatus,
    People,
    Person,
)


class TestTableToHtml:
    def test_basic_output(self) -> None:
        headers = ["Name", "Age"]
        rows = [["Alice", 30], ["Bob", 25]]
        result = table_to_html(headers, rows)
        assert "<th>Name</th>" in result
        assert "<th>Age</th>" in result
        assert "<td>Alice</td>" in result
        assert "<td>30</td>" in result

    def test_html_escaping(self) -> None:
        headers = ["Data"]
        rows = [["<script>alert('xss')</script>"]]
        result = table_to_html(headers, rows)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_none_value(self) -> None:
        headers = ["Data"]
        rows = [[None]]
        result = table_to_html(headers, rows)
        # None values are rendered as a cross mark
        assert "\u274c" in result

    def test_empty_string_value(self) -> None:
        headers = ["Data"]
        rows = [[""]]
        result = table_to_html(headers, rows)
        # Empty strings are rendered as em-dash
        assert "\u2014" in result


class TestTableToText:
    def test_basic_output(self) -> None:
        headers = ["Name", "Age"]
        rows = [["Alice", 30], ["Bob", 25]]
        result = table_to_text(headers, rows)
        assert "Name" in result
        assert "Age" in result
        assert "Alice" in result
        assert "Bob" in result


def list_config(
    make_config: Callable[..., Config],
    people: People,
    columns: list[str],
    **kwargs: Any,
) -> Config:
    defaults: dict[str, Any] = dict(
        columns=columns,
        filter_expr="True",
        sort_key=None,
        html=False,
        enumerate=False,
    )
    defaults.update(kwargs)
    return make_config(people=people, event_id="event1", **defaults)


class TestListPeople:
    def _people(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
    ) -> People:
        alice = make_person(
            email=EmailAddress("alice@example.com"),
            first_name="Alice",
            last_name="Ahonen",
            birth_year=1990,
            participation={
                "event1": make_participation(status=ParticipationStatus.accepted)
            },
        )
        bob = make_person(
            email=EmailAddress("bob@example.com"),
            first_name="Bob",
            last_name="Berg",
            birth_year=1985,
            participation={
                "event1": make_participation(status=ParticipationStatus.queued)
            },
        )
        return {uuid4(): alice, uuid4(): bob}

    def test_prints_a_column_per_expression(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        people = self._people(make_person, make_participation)
        list_people(list_config(make_config, people, ["full_name", "status"]))
        out = capsys.readouterr().out
        assert "Alice Ahonen" in out and "accepted" in out
        assert "Bob Berg" in out and "queued" in out

    def test_underscores_become_spaces_in_headers(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        people = self._people(make_person, make_participation)
        list_people(list_config(make_config, people, ["full_name"]))
        assert "full name" in capsys.readouterr().out

    def test_filter_expression_selects_rows(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        people = self._people(make_person, make_participation)
        config = list_config(
            make_config, people, ["full_name"], filter_expr="status == 'accepted'"
        )
        list_people(config)
        out = capsys.readouterr().out
        assert "Alice Ahonen" in out
        assert "Bob Berg" not in out

    def test_sort_key_orders_rows(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        people = self._people(make_person, make_participation)
        config = list_config(make_config, people, ["last_name"], sort_key="birth_year")
        list_people(config)
        out = capsys.readouterr().out
        assert out.index("Berg") < out.index("Ahonen"), "Bob is older, so first"

    def test_enumerate_adds_a_row_number_column(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        people = self._people(make_person, make_participation)
        config = list_config(make_config, people, ["full_name"], enumerate=True)
        list_people(config)
        out = capsys.readouterr().out
        assert "#" in out
        assert "1" in out and "2" in out

    def test_html_output_is_a_table(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        people = self._people(make_person, make_participation)
        config = list_config(make_config, people, ["full_name"], html=True)
        list_people(config)
        out = capsys.readouterr().out
        assert "<table>" in out and "<td>Alice Ahonen</td>" in out

    def test_statistics_column_counts_each_status(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The compact per-person history: first letter of each status plus a
        count, e.g. `a1` for one `accepted` phase."""
        people = self._people(make_person, make_participation)
        config = list_config(
            make_config, people, ["statistics"], filter_expr="status == 'accepted'"
        )
        list_people(config)
        assert "a1" in capsys.readouterr().out

    def test_expression_touching_participation_aborts_on_an_outsider(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
    ) -> None:
        """An organiser with no participation has no `status`, and the whole
        listing dies on them.

        list_people looks like it guards against this -- it catches
        jinja2.TemplateRuntimeError and skips people outside the event -- but
        eval_string wraps every jinja2 error in a plain RuntimeError, so that
        except clause never matches and the handler is unreachable.
        """
        people = self._people(make_person, make_participation)
        people[uuid4()] = make_person(
            email=EmailAddress("olive@example.com"),
            first_name="Olive",
            last_name="Organizer",
        )
        config = list_config(
            make_config, people, ["full_name"], filter_expr="status == 'accepted'"
        )
        with pytest.raises(RuntimeError, match="'status' is undefined"):
            list_people(config)

    def test_guarding_the_expression_leaves_outsiders_out(
        self,
        make_person: Callable[..., Person],
        make_participation: Callable[..., Participation],
        make_config: Callable[..., Config],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The working way to write such a filter."""
        people = self._people(make_person, make_participation)
        people[uuid4()] = make_person(
            email=EmailAddress("olive@example.com"),
            first_name="Olive",
            last_name="Organizer",
        )
        config = list_config(
            make_config,
            people,
            ["full_name"],
            filter_expr="status is defined and status == 'accepted'",
        )
        list_people(config)
        out = capsys.readouterr().out
        assert "Alice Ahonen" in out
        assert "Olive Organizer" not in out
