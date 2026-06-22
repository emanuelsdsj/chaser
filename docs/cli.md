# CLI Reference

The `chaser` command-line tool lets you scaffold projects, run Trappers, start the API server, and open an interactive shell.

## chaser new

Scaffold a new project directory:

```bash
chaser new myproject
```

Creates:

```
myproject/
├── pyproject.toml
├── myproject/
│   ├── __init__.py
│   └── trappers.py      # starter Trapper
└── tests/
    └── test_trappers.py
```

## chaser run

Run a Trapper by dotted import path:

```bash
chaser run myproject.trappers.MyTrapper
```

Options:

| Flag | Description |
|------|-------------|
| `--concurrency N` | Number of parallel workers (default: 16) |
| `--log-level LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO) |
| `--json-logs` | Emit structured JSON log lines instead of plain text |
| `--output FILE` | Write items to a JSONL file |
| `--no-http2` | Disable HTTP/2 |

```bash
chaser run myproject.trappers.BlogTrapper \
  --concurrency 32 \
  --output articles.jsonl \
  --log-level DEBUG
```

## chaser serve

Start the REST API server:

```bash
chaser serve
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--host HOST` | `0.0.0.0` | Interface to bind |
| `--port PORT` | `8000` | Port to listen on |
| `--reload` | off | Auto-reload on code changes (development) |

```bash
chaser serve --port 9000 --reload
```

Requires `pip install "chaser[api]"`.

## chaser shell

Open an interactive Python shell with a live `Engine` and convenience imports pre-loaded. Useful for experimenting with selectors against real pages.

```bash
chaser shell
```

Inside the shell:

```python
>>> response = await fetch("https://example.com")
>>> response.selector.css("title::text").get()
'Example Domain'
>>> response.status
200
```

## chaser version

Print the installed version:

```bash
chaser version
# chaser 0.4.0
```
