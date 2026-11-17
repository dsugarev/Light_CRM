"""Helpers for comparing the database schema revision with the migration scripts."""

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    if database_url is not None:
        # Percent signs must be escaped for ConfigParser interpolation.
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@lru_cache
def head_revisions() -> frozenset[str]:
    return frozenset(ScriptDirectory.from_config(alembic_config()).get_heads())


async def current_revisions(connection: AsyncConnection) -> frozenset[str]:
    result = await connection.execute(text("SELECT version_num FROM alembic_version"))
    return frozenset(result.scalars().all())
