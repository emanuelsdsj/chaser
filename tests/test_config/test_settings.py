from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from chaser.config.settings import ChaserSettings, _read_chaser_table, load

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_defaults() -> None:
    cfg = ChaserSettings()
    assert cfg.concurrency == 16
    assert cfg.strategy == "bfs"
    assert cfg.http2 is True
    assert cfg.timeout == 30.0
    assert cfg.max_connections == 100
    assert cfg.proxy is None
    assert cfg.log_level == "WARNING"
    assert cfg.user_agent == "chaser/0.0.1"


# ---------------------------------------------------------------------------
# Explicit kwargs take highest priority
# ---------------------------------------------------------------------------


def test_explicit_overrides_defaults() -> None:
    cfg = ChaserSettings(concurrency=4, strategy="dfs", timeout=5.0)
    assert cfg.concurrency == 4
    assert cfg.strategy == "dfs"
    assert cfg.timeout == 5.0


def test_load_with_overrides() -> None:
    cfg = load(concurrency=8, proxy="socks5://127.0.0.1:1080")
    assert cfg.concurrency == 8
    assert cfg.proxy == "socks5://127.0.0.1:1080"


# ---------------------------------------------------------------------------
# Environment variables
# ---------------------------------------------------------------------------


def test_env_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHASER_CONCURRENCY", "64")
    cfg = ChaserSettings()
    assert cfg.concurrency == 64


def test_env_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHASER_STRATEGY", "score")
    cfg = ChaserSettings()
    assert cfg.strategy == "score"


def test_env_http2_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHASER_HTTP2", "false")
    cfg = ChaserSettings()
    assert cfg.http2 is False


def test_env_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHASER_PROXY", "http://proxy.example.com:8080")
    cfg = ChaserSettings()
    assert cfg.proxy == "http://proxy.example.com:8080"


def test_env_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHASER_LOG_LEVEL", "DEBUG")
    cfg = ChaserSettings()
    assert cfg.log_level == "DEBUG"


def test_explicit_kwarg_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHASER_CONCURRENCY", "100")
    cfg = ChaserSettings(concurrency=2)
    assert cfg.concurrency == 2


# ---------------------------------------------------------------------------
# pyproject.toml source
# ---------------------------------------------------------------------------


PYPROJECT_WITH_CHASER = """\
[tool.chaser]
concurrency = 24
strategy = "score"
timeout = 10.0
log_level = "INFO"
"""

PYPROJECT_WITHOUT_CHASER = """\
[tool.pytest.ini_options]
testpaths = ["tests"]
"""


def test_pyproject_values_are_loaded(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_WITH_CHASER)
    data = _read_chaser_table(tmp_path / "pyproject.toml")
    assert data["concurrency"] == 24
    assert data["strategy"] == "score"
    assert data["timeout"] == 10.0
    assert data["log_level"] == "INFO"


def test_missing_pyproject_returns_empty(tmp_path: Path) -> None:
    data = _read_chaser_table(tmp_path / "nonexistent.toml")
    assert data == {}


def test_pyproject_without_chaser_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_WITHOUT_CHASER)
    data = _read_chaser_table(tmp_path / "pyproject.toml")
    assert data == {}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_strategy_raises() -> None:
    with pytest.raises(ValidationError):
        ChaserSettings(strategy="random")


def test_invalid_log_level_raises() -> None:
    with pytest.raises(ValidationError):
        ChaserSettings(log_level="VERBOSE")


def test_concurrency_ge_1() -> None:
    with pytest.raises(ValidationError):
        ChaserSettings(concurrency=0)


def test_timeout_gt_0() -> None:
    with pytest.raises(ValidationError):
        ChaserSettings(timeout=0.0)


# ---------------------------------------------------------------------------
# configure_logging doesn't crash
# ---------------------------------------------------------------------------


def test_configure_logging_runs() -> None:
    cfg = ChaserSettings(log_level="ERROR")
    cfg.configure_logging()  # should not raise
