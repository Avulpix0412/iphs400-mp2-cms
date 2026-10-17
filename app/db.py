"""SQLite storage. The database lives at CMS_DATABASE and is never committed.

The schema is created on connect (every statement is IF NOT EXISTS), so a fresh
clone and a fresh test database need no separate setup step.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'editor')),
    display_name  TEXT UNIQUE COLLATE NOCASE,
    state         TEXT NOT NULL DEFAULT 'active'
                  CHECK (state IN ('active', 'submission_ban', 'deactivated')),
    needs_setup   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A Game Term's slug is set only for Heroes (NULLs never clash in UNIQUE).
CREATE TABLE IF NOT EXISTS game_terms (
    id      INTEGER PRIMARY KEY,
    kind    TEXT NOT NULL CHECK (kind IN ('hero', 'item', 'skill', 'enchantment',
                                          'monster', 'merchant', 'event')),
    name_zh TEXT NOT NULL CHECK (name_zh != ''),
    name_en TEXT NOT NULL CHECK (name_en != ''),
    slug    TEXT,
    UNIQUE (kind, slug)
);

-- The Current Patch is the one added most recently (the highest id).
CREATE TABLE IF NOT EXISTS patches (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE CHECK (name != ''),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database, commit if the block succeeds, and always close."""
    conn = sqlite3.connect(settings.database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()
