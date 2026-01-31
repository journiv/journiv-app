from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import uuid
from unittest.mock import MagicMock, patch

import pytest
from click.exceptions import Exit as ClickExit

from app.cli.commands.migrate import migrate_content


class FakeResult:
    def __init__(self, one_value=None, all_value=None):
        self._one_value = one_value
        self._all_value = all_value

    def one(self):
        return self._one_value

    def all(self):
        return self._all_value


def _mock_session():
    session = MagicMock()
    session.commit.return_value = None
    return session


def test_migrate_content_dry_run(tmp_path):
    session = _mock_session()
    session.exec.return_value = FakeResult(one_value=(2,))

    migrator = tmp_path / "migrator"
    migrator.write_text("#!/bin/sh\nexit 0\n")

    with patch("app.cli.commands.migrate.Session") as mock_session, \
         patch("app.cli.commands.migrate.confirm_action", return_value=True), \
         patch("app.cli.commands.migrate._resolve_migrator_path", return_value=migrator), \
         patch("app.cli.commands.migrate.setup_cli_logging"), \
         patch("app.cli.commands.migrate.engine") as mock_engine:
        mock_engine.url.get_backend_name.return_value = "sqlite"
        mock_session.return_value.__enter__.return_value = session

        # Expect click.Exit to be raised with exit_code 0 (dry run completes successfully)
        with pytest.raises(ClickExit) as exc_info:
            migrate_content(batch_size=10, limit=2, dry_run=True, force=True, verbose=False, error_log=tmp_path / "errors.log")

        assert exc_info.value.exit_code == 0

    # Should have made 1 exec call (count query only, no preview since verbose=False)
    session.exec.assert_called_once()


def test_migrate_content_success(tmp_path):
    session = _mock_session()
    entry_id = uuid.uuid4()
    entry = SimpleNamespace(id=entry_id, content_delta=None, content_plain_text=None, word_count=0)
    session.exec.side_effect = [
        FakeResult(one_value=(1,)),  # Total count query
        FakeResult(
            all_value=[
                SimpleNamespace(id=entry_id, content="**Bold**", entry_datetime_utc=datetime(2026, 1, 1))
            ]
        ),  # First batch of rows
        FakeResult(all_value=[]),  # Media items query
        FakeResult(all_value=[entry]),  # Entries for update
        FakeResult(all_value=[]),  # Second iteration - no more rows
    ]

    migrator = tmp_path / "migrator"
    migrator.write_text("#!/bin/sh\nexit 0\n")

    subprocess_result = SimpleNamespace(returncode=0, stdout='{"ops":[{"insert":"Bold"}]}', stderr="")

    with patch("app.cli.commands.migrate.Session") as mock_session, \
         patch("app.cli.commands.migrate.confirm_action", return_value=True), \
         patch("app.cli.commands.migrate._resolve_migrator_path", return_value=migrator), \
         patch("app.cli.commands.migrate.subprocess.run", return_value=subprocess_result) as mock_run, \
         patch("app.cli.commands.migrate.setup_cli_logging"), \
         patch("app.cli.commands.migrate.engine") as mock_engine:
        mock_engine.url.get_backend_name.return_value = "sqlite"
        mock_session.return_value.__enter__.return_value = session

        migrate_content(batch_size=10, limit=1, dry_run=False, force=True, verbose=False, cleanup=False, error_log=tmp_path / "errors.log")

    assert entry.content_delta is not None
    assert entry.content_plain_text is not None
    assert entry.word_count >= 0
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("input") == "**Bold**"


def test_migrate_content_uses_stdin_input(tmp_path):
    session = _mock_session()
    entry_id = uuid.uuid4()
    session.exec.side_effect = [
        FakeResult(one_value=(1,)),  # Total count query
        FakeResult(
            all_value=[
                SimpleNamespace(id=entry_id, content="Hello", entry_datetime_utc=datetime(2026, 1, 1))
            ]
        ),  # First batch of rows
        FakeResult(all_value=[]),  # Media items query
        FakeResult(all_value=[SimpleNamespace(id=entry_id, content_delta=None, content_plain_text=None, word_count=0)]),  # Entries for update
        FakeResult(all_value=[]),  # Second iteration - no more rows
    ]

    migrator = tmp_path / "migrator"
    migrator.write_text("#!/bin/sh\nexit 0\n")

    subprocess_result = SimpleNamespace(returncode=0, stdout='{"ops":[{"insert":"Hello"}]}', stderr="")

    with patch("app.cli.commands.migrate.Session") as mock_session, \
         patch("app.cli.commands.migrate.confirm_action", return_value=True), \
         patch("app.cli.commands.migrate._resolve_migrator_path", return_value=migrator), \
         patch("app.cli.commands.migrate.subprocess.run", return_value=subprocess_result) as mock_run, \
         patch("app.cli.commands.migrate.setup_cli_logging"), \
         patch("app.cli.commands.migrate.engine") as mock_engine:
        mock_engine.url.get_backend_name.return_value = "sqlite"
        mock_session.return_value.__enter__.return_value = session

        migrate_content(batch_size=10, limit=1, dry_run=False, force=True, verbose=False, cleanup=False, error_log=tmp_path / "errors.log")

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    assert args[0] == [str(migrator)]
    assert kwargs.get("input") == "Hello"
