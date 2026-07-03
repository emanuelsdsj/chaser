# API Stability

Chaser follows [Semantic Versioning](https://semver.org/). Starting with `1.0.0`, the public API is everything importable directly from the `chaser` top-level package — i.e. every name listed in `chaser.__all__`.

## What's covered

```python
import chaser

chaser.__all__  # the full list of names covered by this guarantee
```

This includes `Engine`, `Request`, `Response`, `Item`, `ItemLoader`, all `Trapper` implementations, all pipeline stores (`JsonlStore`, `CsvStore`, `DbStore`, `ParquetStore`, `S3Store`, `GCSStore`), both frontier backends (`SqliteFrontier`, `RedisFrontier`), all hooks, `BrowserClient`/`BrowserPool`/`StealthConfig`, `HarWriter`, `ChaserSettings`, and `__version__`.

For any `1.x` release:

- These names will not be removed or renamed.
- Constructor parameters that exist today will keep working — new parameters are added with defaults, never by breaking an existing call.
- Return types and method signatures will not change in incompatible ways.

## What's not covered

- Anything under a private module path not re-exported from `chaser` (e.g. reaching into `chaser.pipeline.store.s3` internals beyond the `S3Store` class itself).
- Names prefixed with `_`.
- CLI output formatting and log message text.
- Behavior of features explicitly documented as experimental.

Importing a class from its submodule (e.g. `from chaser.pipeline.store.s3 import S3Store`) works and is used throughout these docs for optional-extra classes to make the required extra obvious at the import site — it carries the same stability guarantee as importing it from `chaser` directly, since the class itself doesn't move.

## Deprecation process

When a breaking change is unavoidable:

1. The old behavior keeps working for at least one minor release, emitting a `DeprecationWarning` that names the replacement.
2. The change is documented in the [Changelog](changelog.md) under a `Deprecated` heading.
3. The old behavior is only removed in a subsequent minor release (never a patch release), after the deprecation window has passed.

A major version bump (`2.0.0`) is reserved for changes that don't fit this process — for example, dropping a Python version or restructuring a subsystem's public shape.

## How this is enforced

`tests/test_public_api.py` pins the exact contents of `chaser.__all__`. Any accidental addition, removal, or rename shows up as a failing test, forcing a deliberate decision (and, if it's a removal, a deprecation cycle) rather than a silent break.
