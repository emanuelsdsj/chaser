from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from chaser.item.base import Item
from chaser.pipeline.base import Stage

if TYPE_CHECKING:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

_MISSING = (
    "DbStore requires sqlalchemy and an async driver — install with: pip install 'chaser[db]'"
)

_PY_TO_SA: dict[type, str] = {
    str: "String",
    int: "Integer",
    float: "Float",
    bool: "Boolean",
}


def _col_type(annotation: Any) -> Any:
    import sqlalchemy as sa  # noqa: PLC0415

    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        args = [a for a in getattr(annotation, "__args__", ()) if a is not type(None)]
        annotation = args[0] if args else str
    return {
        str: sa.String,
        int: sa.Integer,
        float: sa.Float,
        bool: sa.Boolean,
    }.get(annotation, sa.String)


def _build_table(item_cls: type[Item], metadata: sa.MetaData) -> sa.Table:
    import sqlalchemy as sa  # noqa: PLC0415

    cols: list[sa.Column[Any]] = [
        sa.Column("_id", sa.Integer, primary_key=True, autoincrement=True)
    ]
    for name, field_info in item_cls.model_fields.items():
        cols.append(sa.Column(name, _col_type(field_info.annotation), nullable=True))
    return sa.Table(item_cls.__name__.lower(), metadata, *cols, extend_existing=True)


class DbStore(Stage):
    """Persists items to a relational database via async SQLAlchemy.

    Tables are created automatically on first write, columns derived from the
    Item's Pydantic field definitions. Complex field types (list, dict) fall
    back to String. Requires the ``db`` extra::

        pip install 'chaser[db]'

    Usage::

        DbStore("sqlite+aiosqlite:///crawl.db")
        DbStore("postgresql+asyncpg://user:pass@host/dbname")
    """

    def __init__(self, url: str) -> None:
        try:
            import sqlalchemy as sa  # noqa: F401
            from sqlalchemy.ext.asyncio import create_async_engine  # noqa: F401
        except ImportError:
            raise ImportError(_MISSING) from None

        self._url = url
        self._engine: AsyncEngine | None = None
        self._tables: dict[str, Any] = {}

    async def open(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine  # noqa: PLC0415

        self._engine = create_async_engine(self._url, echo=False)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    async def process(self, item: Item) -> Item:
        if self._engine is None:
            return item

        import sqlalchemy as sa  # noqa: PLC0415
        from sqlalchemy.ext.asyncio import AsyncSession  # noqa: PLC0415

        item_cls = type(item)
        key = item_cls.__name__

        if key not in self._tables:
            metadata = sa.MetaData()
            table = _build_table(item_cls, metadata)
            self._tables[key] = (table, metadata)
            async with self._engine.begin() as conn:
                await conn.run_sync(metadata.create_all)

        table, _ = self._tables[key]
        async with AsyncSession(self._engine) as session, session.begin():
            await session.execute(table.insert().values(**item.model_dump()))

        return item
