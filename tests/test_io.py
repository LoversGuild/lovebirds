import os
import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from lovebirds.io import (
    gpg_decrypt,
    _gpg_encrypt,
    _import_gpg_pubkeys,
    _is_gpg_file,
    _read_gpg_ids,
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


class TestIsGpgFile:
    def test_gpg_extension(self) -> None:
        assert _is_gpg_file("people.yaml.gpg") is True

    def test_yaml_extension(self) -> None:
        assert _is_gpg_file("people.yaml") is False

    def test_pathlike(self, tmp_path: pathlib.Path) -> None:
        assert _is_gpg_file(tmp_path / "db.yaml.gpg") is True

    def test_no_extension(self) -> None:
        assert _is_gpg_file("people") is False


class TestReadGpgIds:
    def test_single_id(self, tmp_path: pathlib.Path) -> None:
        gpg_id_file = tmp_path / ".gpg-id"
        gpg_id_file.write_text("ABCD1234\n")
        db_path = tmp_path / "people.yaml.gpg"
        assert _read_gpg_ids(db_path) == ["ABCD1234"]

    def test_multiple_ids(self, tmp_path: pathlib.Path) -> None:
        gpg_id_file = tmp_path / ".gpg-id"
        gpg_id_file.write_text("ABCD1234\nEFGH5678\n")
        db_path = tmp_path / "people.yaml.gpg"
        assert _read_gpg_ids(db_path) == ["ABCD1234", "EFGH5678"]

    def test_ignores_comments_and_blank_lines(self, tmp_path: pathlib.Path) -> None:
        gpg_id_file = tmp_path / ".gpg-id"
        gpg_id_file.write_text("# A comment\n\nABCD1234\n  \n# Another\nEFGH5678\n")
        db_path = tmp_path / "people.yaml.gpg"
        assert _read_gpg_ids(db_path) == ["ABCD1234", "EFGH5678"]

    def test_strips_whitespace(self, tmp_path: pathlib.Path) -> None:
        gpg_id_file = tmp_path / ".gpg-id"
        gpg_id_file.write_text("  ABCD1234  \n")
        db_path = tmp_path / "people.yaml.gpg"
        assert _read_gpg_ids(db_path) == ["ABCD1234"]

    def test_missing_file_raises(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "people.yaml.gpg"
        with pytest.raises(FileNotFoundError, match=".gpg-id"):
            _read_gpg_ids(db_path)

    def test_empty_file_raises(self, tmp_path: pathlib.Path) -> None:
        gpg_id_file = tmp_path / ".gpg-id"
        gpg_id_file.write_text("# only comments\n\n")
        db_path = tmp_path / "people.yaml.gpg"
        with pytest.raises(ValueError, match="No GPG key IDs"):
            _read_gpg_ids(db_path)


class TestGpgDecrypt:
    def test_calls_gpg_decrypt(self, tmp_path: pathlib.Path) -> None:
        gpg_file = tmp_path / "data.gpg"
        gpg_file.write_bytes(b"encrypted")
        with patch("lovebirds.io.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=b"decrypted yaml"
            )
            result = gpg_decrypt(gpg_file)
        mock_run.assert_called_once_with(
            ["gpg", "--batch", "--decrypt", str(gpg_file)],
            stdout=subprocess.PIPE,
            check=True,
        )
        assert result == b"decrypted yaml"

    def test_gpg_failure_raises(self, tmp_path: pathlib.Path) -> None:
        gpg_file = tmp_path / "data.gpg"
        gpg_file.write_bytes(b"encrypted")
        with patch("lovebirds.io.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(2, "gpg")
            with pytest.raises(subprocess.CalledProcessError):
                gpg_decrypt(gpg_file)


class TestGpgEncrypt:
    @pytest.mark.parametrize(
        "recipient_ids", [["ABCD1234"], ["ABCD1234", "EFGH5678"]], ids=["one", "two"]
    )
    def test_encrypts_to_every_recipient(self, recipient_ids: list[str]) -> None:
        with patch("lovebirds.io.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=b"encrypted data"
            )
            result = _gpg_encrypt(b"plain yaml", recipient_ids)

        expected_cmd = ["gpg", "--batch", "--encrypt", "--trust-model", "always"]
        for recipient_id in recipient_ids:
            expected_cmd += ["--recipient", recipient_id]
        mock_run.assert_called_once_with(
            expected_cmd,
            input=b"plain yaml",
            stdout=subprocess.PIPE,
            check=True,
        )
        assert result == b"encrypted data"

    def test_gpg_failure_raises(self) -> None:
        with patch("lovebirds.io.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(2, "gpg")
            with pytest.raises(subprocess.CalledProcessError):
                _gpg_encrypt(b"plain yaml", ["ABCD1234"])


class TestImportGpgPubkeys:
    def test_imports_keys(self, tmp_path: pathlib.Path) -> None:
        pubkeys_dir = tmp_path / ".gpg-pubkeys"
        pubkeys_dir.mkdir()
        (pubkeys_dir / "alice.asc").write_text("key-data-alice")
        (pubkeys_dir / "bob.asc").write_text("key-data-bob")
        db_path = tmp_path / "people.yaml.gpg"

        with patch("lovebirds.io.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            _import_gpg_pubkeys(db_path)

        assert [c.args[0] for c in mock_run.call_args_list] == [
            ["gpg", "--batch", "--import", str(pubkeys_dir / "alice.asc")],
            ["gpg", "--batch", "--import", str(pubkeys_dir / "bob.asc")],
        ]

    def test_no_pubkeys_dir_is_noop(self, tmp_path: pathlib.Path) -> None:
        db_path = tmp_path / "people.yaml.gpg"
        with patch("lovebirds.io.subprocess.run") as mock_run:
            _import_gpg_pubkeys(db_path)
        mock_run.assert_not_called()

    def test_skips_subdirectories(self, tmp_path: pathlib.Path) -> None:
        pubkeys_dir = tmp_path / ".gpg-pubkeys"
        pubkeys_dir.mkdir()
        (pubkeys_dir / "subdir").mkdir()
        (pubkeys_dir / "alice.asc").write_text("key-data")
        db_path = tmp_path / "people.yaml.gpg"

        with patch("lovebirds.io.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)
            _import_gpg_pubkeys(db_path)

        assert [c.args[0] for c in mock_run.call_args_list] == [
            ["gpg", "--batch", "--import", str(pubkeys_dir / "alice.asc")],
        ]

    def test_a_file_that_is_not_a_key_does_not_stop_the_save(
        self, tmp_path: pathlib.Path
    ) -> None:
        """gpg rejects anything that is not a key, and this directory sits in
        the operator's git repository — a README or a .DS_Store is bound to
        turn up there eventually. Neither may cost them their save.

        The keys are imported in name order, so the rejected file here sorts
        first: giving up at the first refusal would skip a real co-organizer's
        key and fail later, at encryption, with a much worse message.
        """
        pubkeys_dir = tmp_path / ".gpg-pubkeys"
        pubkeys_dir.mkdir()
        (pubkeys_dir / "README").write_text("Put co-organizers' keys here.")
        (pubkeys_dir / "alice.asc").write_text("key-data")
        db_path = tmp_path / "people.yaml.gpg"

        def refuse_the_readme(
            cmd: list[str], check: bool = False, **kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            # `check` has to be honoured here: a mock ignores it, so a stub
            # that did too would pass whether or not the code asks gpg's exit
            # status to be fatal — which is the whole point of the test.
            if not cmd[-1].endswith("README"):
                return subprocess.CompletedProcess(args=cmd, returncode=0)
            if check:
                raise subprocess.CalledProcessError(2, cmd)
            return subprocess.CompletedProcess(args=cmd, returncode=2)

        with patch(
            "lovebirds.io.subprocess.run", side_effect=refuse_the_readme
        ) as mock_run:
            _import_gpg_pubkeys(db_path)

        assert [c.args[0] for c in mock_run.call_args_list] == [
            ["gpg", "--batch", "--import", str(pubkeys_dir / "README")],
            ["gpg", "--batch", "--import", str(pubkeys_dir / "alice.asc")],
        ]


class TestLoadPeopleGpg:
    def test_load_gpg_file_decrypts(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        # First, save plain YAML so we know what the decrypted content looks like
        plain_path = tmp_path / "people.yaml"
        save_people(plain_path, sample_people)
        yaml_bytes = plain_path.read_bytes()

        gpg_path = tmp_path / "people.yaml.gpg"
        gpg_path.write_bytes(b"encrypted")

        with patch("lovebirds.io.gpg_decrypt") as mock_decrypt:
            mock_decrypt.return_value = yaml_bytes
            loaded = load_people(gpg_path)

        mock_decrypt.assert_called_once_with(gpg_path)
        assert set(loaded.keys()) == set(sample_people.keys())

    def test_load_plain_file_unchanged(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        plain_path = tmp_path / "people.yaml"
        save_people(plain_path, sample_people)

        with patch("lovebirds.io.gpg_decrypt") as mock_decrypt:
            loaded = load_people(plain_path)

        mock_decrypt.assert_not_called()
        assert set(loaded.keys()) == set(sample_people.keys())


class TestSavePeopleGpg:
    def test_save_gpg_file_encrypts(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        gpg_id_file = tmp_path / ".gpg-id"
        gpg_id_file.write_text("ABCD1234\nEFGH5678\n")
        gpg_path = tmp_path / "people.yaml.gpg"

        with patch("lovebirds.io._gpg_encrypt") as mock_encrypt:
            mock_encrypt.return_value = b"encrypted output"
            save_people(gpg_path, sample_people)

        mock_encrypt.assert_called_once()
        yaml_data, recipient_ids = mock_encrypt.call_args.args
        assert isinstance(yaml_data, bytes)
        assert recipient_ids == ["ABCD1234", "EFGH5678"]
        # The file should contain the encrypted output
        assert gpg_path.read_bytes() == b"encrypted output"

    def test_save_gpg_file_imports_pubkeys_before_encrypting(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        """A recipient added to .gpg-id along with their key in .gpg-pubkeys/
        is unknown to the keyring until the key is imported, so the import has
        to happen before gpg is asked to encrypt to them.
        """
        (tmp_path / ".gpg-id").write_text("ABCD1234\n")
        gpg_path = tmp_path / "people.yaml.gpg"

        steps = MagicMock()
        with (
            patch("lovebirds.io._import_gpg_pubkeys") as mock_import,
            patch("lovebirds.io._gpg_encrypt") as mock_encrypt,
        ):
            mock_encrypt.return_value = b"encrypted output"
            steps.attach_mock(mock_import, "import_pubkeys")
            steps.attach_mock(mock_encrypt, "encrypt")
            save_people(gpg_path, sample_people)

        mock_import.assert_called_once_with(gpg_path)
        assert [name for name, _, _ in steps.mock_calls] == [
            "import_pubkeys",
            "encrypt",
        ]

    def test_save_plain_file_unchanged(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        plain_path = tmp_path / "people.yaml"

        with patch("lovebirds.io._gpg_encrypt") as mock_encrypt:
            save_people(plain_path, sample_people)

        mock_encrypt.assert_not_called()
        # File should be readable YAML
        loaded = load_people(plain_path)
        assert set(loaded.keys()) == set(sample_people.keys())

    def test_save_gpg_missing_gpg_id_raises(
        self, tmp_path: pathlib.Path, sample_people: People
    ) -> None:
        gpg_path = tmp_path / "people.yaml.gpg"
        with pytest.raises(FileNotFoundError, match=".gpg-id"):
            save_people(gpg_path, sample_people)
