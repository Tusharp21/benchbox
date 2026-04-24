import logging
from pathlib import Path

import pytest

from benchbox_core import logs


@pytest.fixture(autouse=True)
def _reset_logs() -> None:
    logs.reset_for_testing()
    yield
    logs.reset_for_testing()


def test_init_session_creates_timestamped_dir(tmp_path: Path) -> None:
    session = logs.init_session(log_root=tmp_path)
    assert session.exists()
    assert session.parent == tmp_path
    assert (session / "session.log").parent.exists()


def test_init_session_is_idempotent(tmp_path: Path) -> None:
    first = logs.init_session(log_root=tmp_path)
    second = logs.init_session(log_root=tmp_path)
    assert first == second
    assert logs.current_session_dir() == first


def test_current_session_dir_starts_none() -> None:
    assert logs.current_session_dir() is None


def test_log_lines_land_in_session_log(tmp_path: Path) -> None:
    session = logs.init_session(log_root=tmp_path)
    log = logs.get_logger("benchbox.test")
    log.warning("hello-from-test")

    for handler in logging.getLogger().handlers:
        handler.flush()

    session_log = (session / "session.log").read_text()
    assert "hello-from-test" in session_log
    assert "WARNING" in session_log
    assert "benchbox.test" in session_log


def test_env_var_overrides_default_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(logs.ENV_LOG_DIR, str(tmp_path / "custom"))
    session = logs.init_session()
    assert session.parent == tmp_path / "custom"


def test_get_logger_auto_inits_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(logs.ENV_LOG_DIR, str(tmp_path))
    assert logs.current_session_dir() is None
    logs.get_logger("benchbox.auto")
    assert logs.current_session_dir() is not None


def test_reset_clears_handlers_and_dir(tmp_path: Path) -> None:
    logs.init_session(log_root=tmp_path)
    assert logs.current_session_dir() is not None
    assert logging.getLogger().handlers

    logs.reset_for_testing()

    assert logs.current_session_dir() is None
    assert not logging.getLogger().handlers
