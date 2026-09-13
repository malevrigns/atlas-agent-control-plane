"""SQLite engine must not share QueuePool connections across greenlets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy.pool import NullPool

from app.infrastructure.database.session import create_database_engine, is_sqlite_url


class DatabaseEngineConfigTest(unittest.TestCase):
    def test_sqlite_urls_are_detected(self) -> None:
        self.assertTrue(is_sqlite_url("sqlite+aiosqlite:///tmp/atlas.db"))
        self.assertFalse(is_sqlite_url("postgresql+asyncpg://localhost/atlas"))

    def test_sqlite_engine_uses_null_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            url = f"sqlite+aiosqlite:///{Path(tmp).as_posix()}/atlas.db"
            engine = create_database_engine(url)
            try:
                self.assertIs(engine.sync_engine.pool.__class__, NullPool)
            finally:
                engine.sync_engine.dispose()
