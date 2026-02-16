import os
import pathlib
from unittest.mock import MagicMock, patch

import pytest

from lovebirds.io import (
    _safe_write_file,
    backup_file,
    load_people,
    save_people,
)
from lovebirds.models.email import EmailAddress
from lovebirds.models.people import People


class TestSaveLoadRoundTrip:
    def test_round_trip(self, tmp_path: pathlib.Path, sample_people: People) -> None:
        filepath = tmp_path / "people.yaml"
        save_people(filepath, sample_people)
        loaded = load_people(filepath)

        assert set(loaded.keys()) == set(sample_people.keys())
        for key in sample_people:
            assert loaded[key].email == sample_people[key].email
            assert loaded[key].first_name == sample_people[key].first_name
            assert loaded[key].last_name == sample_people[key].last_name

    def test_output_is_sorted(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        filepath = tmp_path / "people.yaml"
        save_people(filepath, sample_people)
        loaded = load_people(filepath)
        named_emails = [p.named_email for p in loaded.values()]
        assert named_emails == sorted(named_emails, key=str.lower)


class TestBackupFile:
    def test_creates_timestamped_copy(self, tmp_path: pathlib.Path) -> None:
        original = tmp_path / "data.yaml"
        original.write_text("original content")
        backup_file(original)
        backups = [f for f in tmp_path.iterdir() if f.name.startswith("data.yaml.")]
        assert len(backups) == 1
        assert backups[0].read_text() == "original content"

    def test_nonexistent_file_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError, match="does not exist"):
            backup_file(tmp_path / "nonexistent.yaml")


class TestSafeWriteFile:
    def test_creates_file(self, tmp_path: pathlib.Path) -> None:
        filepath = tmp_path / "output.txt"
        _safe_write_file(filepath, b"hello world")
        assert filepath.read_bytes() == b"hello world"

    def test_overwrites_existing(self, tmp_path: pathlib.Path) -> None:
        filepath = tmp_path / "output.txt"
        filepath.write_bytes(b"old content")
        _safe_write_file(filepath, b"new content")
        assert filepath.read_bytes() == b"new content"

    def test_temp_file_removed_when_the_rename_fails(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Writes go to a temp file and are renamed into place. If the rename
        fails the temp file must not be left behind next to the database."""
        filepath = tmp_path / "output.txt"
        with patch("lovebirds.io.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                _safe_write_file(filepath, b"data")
        assert list(tmp_path.iterdir()) == []

    def test_existing_file_survives_a_failed_write(
        self, tmp_path: pathlib.Path
    ) -> None:
        filepath = tmp_path / "output.txt"
        filepath.write_bytes(b"original")
        with patch("lovebirds.io.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                _safe_write_file(filepath, b"replacement")
        assert filepath.read_bytes() == b"original"


class TestLoadPeopleErrors:
    def test_invalid_yaml(self, tmp_path: pathlib.Path) -> None:
        filepath = tmp_path / "bad.yaml"
        filepath.write_text(": : : not valid yaml [[[")
        with pytest.raises(Exception):
            load_people(filepath)

    def test_extra_keys_rejected(self, tmp_path: pathlib.Path) -> None:
        filepath = tmp_path / "extra.yaml"
        filepath.write_text(
            "alice@example.com:\n"
            "  email: alice@example.com\n"
            "  languages: [en]\n"
            "  unknown_field: oops\n"
        )
        with pytest.raises(Exception):
            load_people(filepath)


class TestLoadEvent:
    def test_valid_event(self, tmp_path: pathlib.Path) -> None:
        from lovebirds.io import load_event

        filepath = tmp_path / "event.yaml"
        filepath.write_text(
            "event_id: test_event\n"
            "mail:\n"
            "  message_filter:\n"
            "    html: '*.html'\n"
            "    plain: '*.txt'\n"
            "  headers:\n"
            "    From: test@example.com\n"
            "  smtp:\n"
            "    server: smtp.example.com\n"
            "variables:\n"
            "  foo: bar\n"
            "messages:\n"
            "  welcome:\n"
            "    condition: 'true'\n"
            "    translations: [en]\n"
            "    filename: welcome.txt\n"
            "    variables:\n"
            "      key: value\n"
        )
        event = load_event(filepath)
        assert event.event_id == "test_event"
        assert event.mail.smtp.server == "smtp.example.com"
        assert event.mail.smtp.tls is True
