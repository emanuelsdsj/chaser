from __future__ import annotations

import asyncio
import code
import importlib
import json
import logging
import sys
from typing import Annotated, Any

import typer

from chaser import __version__


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _setup_logging(level: str, json_logs: bool) -> None:
    numeric = getattr(logging, level.upper(), logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    fmt: logging.Formatter = (
        _JsonFormatter() if json_logs else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    handler.setFormatter(fmt)
    logging.basicConfig(level=numeric, handlers=[handler], force=True)


app = typer.Typer(
    name="chaser",
    help="Chaser — async web crawling framework.",
    no_args_is_help=True,
    add_completion=False,
)


def _import_trapper(target: str) -> type[Any]:
    """Import a Trapper class from 'module.path:ClassName' notation."""
    if ":" not in target:
        typer.echo(
            f"Error: expected 'module.path:ClassName', got {target!r}",
            err=True,
        )
        raise typer.Exit(1)

    module_path, class_name = target.rsplit(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        typer.echo(f"Error: cannot import module {module_path!r}: {exc}", err=True)
        raise typer.Exit(1) from exc

    cls: type[Any] | None = getattr(module, class_name, None)
    if cls is None:
        typer.echo(
            f"Error: {class_name!r} not found in module {module_path!r}",
            err=True,
        )
        raise typer.Exit(1)

    return cls


@app.command()
def version() -> None:
    """Print the chaser version and exit."""
    typer.echo(f"chaser {__version__}")


@app.command()
def run(
    trapper: Annotated[
        str,
        typer.Argument(help="Trapper to run — 'module.path:ClassName'"),
    ],
    concurrency: Annotated[int, typer.Option(help="Number of concurrent workers")] = 16,
    strategy: Annotated[str, typer.Option(help="Frontier strategy: bfs | dfs | score")] = "bfs",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds")] = 30.0,
    proxy: Annotated[str | None, typer.Option(help="Proxy URL (http or socks5)")] = None,
    no_http2: Annotated[bool, typer.Option("--no-http2", help="Disable HTTP/2")] = False,
    log_level: Annotated[
        str, typer.Option("--log-level", help="Logging level: debug|info|warning|error")
    ] = "warning",
    json_logs: Annotated[
        bool, typer.Option("--json-logs", help="Emit logs as JSON objects")
    ] = False,
) -> None:
    """Run a Trapper and print collected items to stdout."""
    _setup_logging(log_level, json_logs)
    from chaser.engine.runner import Engine

    cls = _import_trapper(trapper)
    trapper_instance = cls()

    engine = Engine(
        concurrency=concurrency,
        strategy=strategy,
        http2=not no_http2,
        timeout=timeout,
        proxy=proxy,
    )

    items = asyncio.run(engine.run(trapper_instance))

    for item in items:
        typer.echo(item.model_dump_json())

    typer.echo(f"\n{len(items)} item(s) collected.", err=True)


@app.command()
def shell(
    url: Annotated[str, typer.Argument(help="URL to fetch")],
    proxy: Annotated[str | None, typer.Option(help="Proxy URL")] = None,
    no_http2: Annotated[bool, typer.Option("--no-http2", help="Disable HTTP/2")] = False,
) -> None:
    """Fetch a URL and open an interactive shell with the response.

    Available in the shell:

    \\b
        response  — the Response object
        sel       — response.selector (CSS + XPath)
        fetch(url) — helper to fetch another URL
    """
    from chaser.net.client import NetClient
    from chaser.net.request import Request

    async def _fetch(target_url: str) -> object:
        async with NetClient(http2=not no_http2, proxy=proxy) as client:
            return await client.fetch(Request(url=target_url))

    typer.echo(f"Fetching {url} …", err=True)
    response = asyncio.run(_fetch(url))

    def fetch(target_url: str) -> object:
        return asyncio.run(_fetch(target_url))

    banner = (
        f"\nChaser shell — {url}\n"
        "  response   → Response object\n"
        "  sel        → response.selector\n"
        "  fetch(url) → fetch another URL\n"
    )

    local_vars = {
        "response": response,
        "sel": getattr(response, "selector", None),
        "fetch": fetch,
    }

    try:
        import IPython

        IPython.start_ipython(argv=[], user_ns=local_vars, display_banner=False)
        typer.echo(banner, err=True)
    except ImportError:
        typer.echo(banner, err=True)
        code.interact(local=local_vars, banner="")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
