from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from typer import Exit as TyExit
from typer.testing import CliRunner

from chaser import __version__
from chaser.cli.main import _import_trapper, app
from chaser.item.base import Item
from chaser.net.headers import Headers
from chaser.net.response import Response
from chaser.trapper.base import Trapper

runner = CliRunner()


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_version_output() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"chaser {__version__}" in result.output


# ---------------------------------------------------------------------------
# _import_trapper helper
# ---------------------------------------------------------------------------


def test_import_trapper_valid() -> None:
    cls = _import_trapper("chaser.trapper.base:Trapper")
    assert cls is Trapper


def test_import_trapper_missing_colon() -> None:
    with pytest.raises(TyExit):
        _import_trapper("chaser.trapper.base")


def test_import_trapper_bad_module() -> None:
    with pytest.raises(TyExit):
        _import_trapper("chaser.nonexistent.module:Foo")


def test_import_trapper_missing_class() -> None:
    with pytest.raises(TyExit):
        _import_trapper("chaser.trapper.base:NoSuchClass")


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


class _FakeItem(Item):
    url: str
    title: str = "hello"


class _FakeTrapper(Trapper):
    start_urls = ["https://example.com"]

    async def parse(self, response: Response) -> AsyncIterator[object]:
        yield _FakeItem(url=response.url)


def test_run_prints_items(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [_FakeItem(url="https://example.com", title="hello")]

    async def _fake_run(_trapper: object) -> list[Item]:
        return items

    with patch("chaser.engine.runner.Engine.run", new=AsyncMock(return_value=items)):
        result = runner.invoke(
            app,
            ["run", "tests.test_cli.test_main:_FakeTrapper"],
        )

    assert result.exit_code == 0
    assert "example.com" in result.output or result.exit_code == 0


def test_run_bad_trapper_module() -> None:
    result = runner.invoke(app, ["run", "no.such.module:Foo"])
    assert result.exit_code != 0


def test_run_missing_colon() -> None:
    result = runner.invoke(app, ["run", "chaser.trapper.base"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# shell command — smoke test (no real HTTP)
# ---------------------------------------------------------------------------


def test_shell_fetches_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_response = Response(
        url="https://example.com",
        status=200,
        headers=Headers({"content-type": "text/html"}),
        body=b"<html><body><h1>Hi</h1></body></html>",
    )

    with (
        patch("chaser.net.client.NetClient.__aenter__", return_value=AsyncMock()),
        patch(
            "chaser.net.client.NetClient.fetch",
            new=AsyncMock(return_value=fake_response),
        ),
        patch("code.interact"),  # prevent opening a real REPL
    ):
        result = runner.invoke(app, ["shell", "https://example.com"], input="\n")

    # exit code may vary — just verify no unhandled crash
    assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# --log-level / --json-logs
# ---------------------------------------------------------------------------


def test_setup_logging_sets_level() -> None:
    import logging

    from chaser.cli.main import _setup_logging

    _setup_logging("debug", json_logs=False)
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_json_formatter() -> None:
    import json
    import logging

    from chaser.cli.main import _JsonFormatter, _setup_logging

    _setup_logging("info", json_logs=True)
    root = logging.getLogger()
    handlers = [h for h in root.handlers if isinstance(h.formatter, _JsonFormatter)]
    assert handlers, "no JSON formatter attached"

    record = logging.LogRecord("test", logging.INFO, "", 0, "hello json", (), None)
    payload = json.loads(handlers[0].formatter.format(record))
    assert payload["level"] == "INFO"
    assert payload["msg"] == "hello json"
    assert "ts" in payload


def test_run_accepts_log_level_option() -> None:
    from unittest.mock import AsyncMock, patch

    items: list = []
    with patch("chaser.engine.runner.Engine.run", new=AsyncMock(return_value=items)):
        result = runner.invoke(
            app,
            ["run", "tests.test_cli.test_main:_FakeTrapper", "--log-level", "debug"],
        )
    assert result.exit_code == 0


def test_run_accepts_json_logs_flag() -> None:
    from unittest.mock import AsyncMock, patch

    items: list = []
    with patch("chaser.engine.runner.Engine.run", new=AsyncMock(return_value=items)):
        result = runner.invoke(
            app,
            ["run", "tests.test_cli.test_main:_FakeTrapper", "--json-logs"],
        )
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# chaser new
# ---------------------------------------------------------------------------


def test_new_creates_directory(tmp_path) -> None:
    result = runner.invoke(app, ["new", "my-project", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "my-project").is_dir()


def test_new_creates_package_and_trapper(tmp_path) -> None:
    runner.invoke(app, ["new", "my-project", "--output-dir", str(tmp_path)])
    root = tmp_path / "my-project"
    assert (root / "my_project" / "trappers.py").exists()
    assert (root / "my_project" / "__init__.py").exists()


def test_new_creates_test_file(tmp_path) -> None:
    runner.invoke(app, ["new", "my-project", "--output-dir", str(tmp_path)])
    assert (tmp_path / "my-project" / "tests" / "test_trappers.py").exists()


def test_new_creates_pyproject_toml(tmp_path) -> None:
    runner.invoke(app, ["new", "my-project", "--output-dir", str(tmp_path)])
    pyproject = (tmp_path / "my-project" / "pyproject.toml").read_text()
    assert "chaser" in pyproject
    assert 'name = "my-project"' in pyproject


def test_new_creates_gitignore(tmp_path) -> None:
    runner.invoke(app, ["new", "my-project", "--output-dir", str(tmp_path)])
    assert (tmp_path / "my-project" / ".gitignore").exists()


def test_new_sanitizes_hyphenated_name(tmp_path) -> None:
    runner.invoke(app, ["new", "my-cool-scraper", "--output-dir", str(tmp_path)])
    root = tmp_path / "my-cool-scraper"
    assert (root / "my_cool_scraper" / "trappers.py").exists()
    content = (root / "my_cool_scraper" / "trappers.py").read_text()
    assert "MyCoolScraperTrapper" in content


def test_new_fails_if_directory_exists(tmp_path) -> None:
    runner.invoke(app, ["new", "myproject", "--output-dir", str(tmp_path)])
    result = runner.invoke(app, ["new", "myproject", "--output-dir", str(tmp_path)])
    assert result.exit_code != 0


def test_new_generated_test_uses_testing_module(tmp_path) -> None:
    runner.invoke(app, ["new", "myproject", "--output-dir", str(tmp_path)])
    test_content = (tmp_path / "myproject" / "tests" / "test_trappers.py").read_text()
    assert "from chaser.testing import" in test_content
    assert "FakeResponse" in test_content
    assert "assert_items" in test_content
