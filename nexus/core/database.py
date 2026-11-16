"""Persistência local, com migração inicial e transações SQLite."""
import os
from contextlib import contextmanager
import sqlite3
from pathlib import Path


def default_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return root / "Nexus" / "nexus.sqlite3"


class Database:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from nexus.core.migrations import migrate
        try:
            migrate(self)
        except Exception:
            try:
                from nexus.core.logger import get_logger
                get_logger(self).exception('Falha ao inicializar ou migrar o banco')
            except OSError:
                pass  # Preserve the original database error if logs are unwritable too.
            raise

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def rows(self, sql, args=()):
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.connect() as conn:
            return conn.execute(sql, args).lastrowid
