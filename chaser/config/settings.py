from __future__ import annotations

import logging
import tomllib  # stdlib on Python 3.11+
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


def _find_pyproject() -> Path | None:
    """Walk up from cwd looking for pyproject.toml."""
    path = Path.cwd()
    for _ in range(8):
        candidate = path / "pyproject.toml"
        if candidate.exists():
            return candidate
        parent = path.parent
        if parent == path:
            break
        path = parent
    return None


def _read_chaser_table(pyproject_path: Path | None = None) -> dict[str, Any]:
    """Extract [tool.chaser] from pyproject.toml, or return empty dict."""
    target = pyproject_path or _find_pyproject()
    if target is None or not target.exists():
        return {}
    try:
        with target.open("rb") as fh:
            raw = tomllib.load(fh)
        return raw.get("tool", {}).get("chaser", {})
    except Exception:
        return {}


class _PyprojectSource(PydanticBaseSettingsSource):
    """Reads [tool.chaser] from the nearest pyproject.toml."""

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        *,
        pyproject_path: Path | None = None,
    ) -> None:
        super().__init__(settings_cls)
        self._data = _read_chaser_table(pyproject_path)

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def field_is_complex(self, field: Any) -> bool:
        return False

    def __call__(self) -> dict[str, Any]:
        return {k: v for k, v in self._data.items() if v is not None}


class ChaserSettings(BaseSettings):
    """Runtime configuration for Chaser.

    Sources in priority order (highest first):

    1. Explicit constructor kwargs
    2. ``CHASER_*`` environment variables
    3. ``[tool.chaser]`` section in ``pyproject.toml``
    4. Built-in defaults

    Usage in pyproject.toml::

        [tool.chaser]
        concurrency = 32
        strategy = "bfs"
        timeout = 15.0
        log_level = "INFO"

    Or via environment::

        CHASER_CONCURRENCY=32 CHASER_TIMEOUT=15 chaser run my_trapper
    """

    model_config = SettingsConfigDict(env_prefix="CHASER_", extra="ignore")

    concurrency: int = Field(default=16, ge=1, le=512)
    strategy: str = Field(default="bfs", pattern="^(bfs|dfs|score)$")
    http2: bool = True
    timeout: float = Field(default=30.0, gt=0)
    max_connections: int = Field(default=100, ge=1)
    proxy: str | None = None
    log_level: str = Field(default="WARNING", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    user_agent: str = "chaser/0.0.1"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, _PyprojectSource(settings_cls))

    def configure_logging(self) -> None:
        logging.basicConfig(level=self.log_level)


def load(**overrides: Any) -> ChaserSettings:
    """Load settings from pyproject.toml + env vars, apply any explicit overrides."""
    return ChaserSettings(**overrides)
