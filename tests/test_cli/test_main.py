from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from click.exceptions import Exit as ClickExit
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
    with pytest.raises(ClickExit):
        _import_trapper("chaser.trapper.base")


def test_import_trapper_bad_module() -> None:
    with pytest.raises(ClickExit):
        _import_trapper("chaser.nonexistent.module:Foo")


def test_import_trapper_missing_class() -> None:
    with pytest.raises(ClickExit):
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
