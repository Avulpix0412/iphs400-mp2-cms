"""SQLite storage. The database lives at CMS_DATABASE and is never committed.

The schema is created on connect (every statement is IF NOT EXISTS), so a fresh
clone and a fresh test database need no separate setup step. A database made
before a table gained a column gets the column added on connect (see
ADDED_COLUMNS); a schema change that adding columns can't express needs a new
table instead.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from app import settings

# The time now, to the millisecond, for timestamps compared with the last Site
# build: a Guide Published in the same second as a Site build still counts.
NOW = "strftime('%Y-%m-%d %H:%M:%f', 'now')"

SCHEMA = f"""
-- last_login_at was added in T09 (see ADDED_COLUMNS).
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'editor')),
    display_name  TEXT UNIQUE COLLATE NOCASE,
    state         TEXT NOT NULL DEFAULT 'active'
                  CHECK (state IN ('active', 'submission_ban', 'deactivated')),
    needs_setup   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A Game Term's slug is set only for Heroes (NULLs never clash in UNIQUE).
-- nicknames, one per line, were added in T07 (see ADDED_COLUMNS).
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

-- A Guide's slug is filled in right after its row is created, since it ends
-- with the Guide's own id. Status changes only through app/guides.py.
-- A Guide is in the Trash while trashed_at is set (added in T06, as is
-- restored_at; see ADDED_COLUMNS). That is separate from its status, so a
-- restored Guide comes back exactly as it was; restored_at is when it last
-- came back.
CREATE TABLE IF NOT EXISTS guides (
    id           INTEGER PRIMARY KEY,
    slug         TEXT UNIQUE,
    title_zh     TEXT NOT NULL DEFAULT '',
    body_zh      TEXT NOT NULL DEFAULT '',
    title_en     TEXT NOT NULL DEFAULT '',
    body_en      TEXT NOT NULL DEFAULT '',
    hero_id      INTEGER NOT NULL REFERENCES game_terms (id),
    patch_id     INTEGER NOT NULL REFERENCES patches (id),
    author_id    INTEGER NOT NULL REFERENCES users (id),
    status       TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft', 'submitted', 'published')),
    created_at   TEXT NOT NULL DEFAULT ({NOW}),
    updated_at   TEXT NOT NULL DEFAULT ({NOW}),
    published_at TEXT
);

-- A Revision is a pending change to a Published Guide, at most one per Guide.
-- Publishing it copies it over the Guide and deletes it. base_updated_at is
-- the Guide's updated_at when the Revision was opened, to tell whether the
-- Guide changed since. Ids are never reused (AUTOINCREMENT), since review
-- rounds keep the id of the Revision they Returned after it is gone.
CREATE TABLE IF NOT EXISTS revisions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guide_id   INTEGER NOT NULL UNIQUE REFERENCES guides (id) ON DELETE CASCADE,
    base_updated_at TEXT NOT NULL,
    title_zh   TEXT NOT NULL DEFAULT '',
    body_zh    TEXT NOT NULL DEFAULT '',
    title_en   TEXT NOT NULL DEFAULT '',
    body_en    TEXT NOT NULL DEFAULT '',
    hero_id    INTEGER NOT NULL REFERENCES game_terms (id),
    patch_id   INTEGER NOT NULL REFERENCES patches (id),
    status     TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted')),
    created_at TEXT NOT NULL DEFAULT ({NOW}),
    updated_at TEXT NOT NULL DEFAULT ({NOW})
);

-- Each Return or Unpublish is a review round, kept for the Guide's history.
-- A Draft with a Return or Unpublish behind it came back to its Author: a
-- Guide only leaves Submitted or Published for Draft through one.
-- A Return of a Revision records the Revision's id (revision_id; added in T06,
-- see ADDED_COLUMNS). It belongs to that Revision while it is open and joins
-- the Guide's own history once it is gone.
CREATE TABLE IF NOT EXISTS review_rounds (
    id         INTEGER PRIMARY KEY,
    guide_id   INTEGER NOT NULL REFERENCES guides (id) ON DELETE CASCADE,
    admin_id   INTEGER NOT NULL REFERENCES users (id),
    kind       TEXT NOT NULL CHECK (kind IN ('return', 'unpublish')),
    created_at TEXT NOT NULL DEFAULT ({NOW})
);

CREATE TABLE IF NOT EXISTS review_notes (
    id       INTEGER PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES review_rounds (id) ON DELETE CASCADE,
    quote    TEXT NOT NULL CHECK (quote != ''),
    advice   TEXT NOT NULL CHECK (advice != '')
);

CREATE INDEX IF NOT EXISTS review_rounds_by_guide ON review_rounds (guide_id);
CREATE INDEX IF NOT EXISTS review_notes_by_round ON review_notes (round_id);

-- One row per successful Site build, at the time it started reading content.
CREATE TABLE IF NOT EXISTS site_builds (
    id         INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL
);

-- Pages and Tournament items are written by Admins with no review, so they are
-- only ever Draft or Published, and only app/content.py changes them.
-- site_changed_at is when the item last changed in a way the site shows (it
-- was Published, edited while Published, or Unpublished), for the dashboard's
-- count of changes not on the site.
CREATE TABLE IF NOT EXISTS pages (
    id              INTEGER PRIMARY KEY,
    slug            TEXT NOT NULL UNIQUE,
    title_zh        TEXT NOT NULL DEFAULT '',
    body_zh         TEXT NOT NULL DEFAULT '',
    title_en        TEXT NOT NULL DEFAULT '',
    body_en         TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'published')),
    created_at      TEXT NOT NULL DEFAULT ({NOW}),
    updated_at      TEXT NOT NULL DEFAULT ({NOW}),
    site_changed_at TEXT
);

-- A Tournament item is an announcement or a recap; a recap may link to the
-- announcement it follows (announcement_id), and loses the link if that is
-- deleted. tournament_date is YYYY-MM-DD. Ids are never reused
-- (AUTOINCREMENT), since an item's address on the site is its id.
CREATE TABLE IF NOT EXISTS tournament_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL CHECK (kind IN ('announcement', 'recap')),
    title_zh        TEXT NOT NULL DEFAULT '',
    body_zh         TEXT NOT NULL DEFAULT '',
    title_en        TEXT NOT NULL DEFAULT '',
    body_en         TEXT NOT NULL DEFAULT '',
    tournament_date TEXT NOT NULL,
    patch_id        INTEGER NOT NULL REFERENCES patches (id),
    announcement_id INTEGER REFERENCES tournament_items (id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'published')),
    created_at      TEXT NOT NULL DEFAULT ({NOW}),
    updated_at      TEXT NOT NULL DEFAULT ({NOW}),
    site_changed_at TEXT
);

-- Pages and Tournament items deleted for good after they were ever Published
-- (kind is 'page' or 'tournament_item'), with their status and
-- site_changed_at then, so the dashboard can tell whether the site still has
-- them.
CREATE TABLE IF NOT EXISTS removed_content (
    kind            TEXT NOT NULL,
    item_id         INTEGER NOT NULL,
    was_published   INTEGER NOT NULL,
    site_changed_at TEXT NOT NULL,
    removed_at      TEXT NOT NULL DEFAULT ({NOW})
);

-- An image uploaded into a Guide, its open Revision, or a Tournament item
-- (owner: "guide/12", "guide/12/revision" or "tournament/5"; see app/media.py).
-- filename is generated by the server and names the file in the media folder.
-- A Revision's images are copies of its Guide's rows sharing their files, so
-- a file goes only when no row names it any more.
CREATE TABLE IF NOT EXISTS images (
    id         INTEGER PRIMARY KEY,
    owner      TEXT NOT NULL,
    filename   TEXT NOT NULL,
    alt_zh     TEXT NOT NULL DEFAULT '',
    alt_en     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (owner, filename)
);

-- Published Guides deleted for good from the Trash. Their rows are gone, so
-- this is how the dashboard still counts them as a change not on the site.
CREATE TABLE IF NOT EXISTS removed_guides (
    guide_id   INTEGER NOT NULL,
    removed_at TEXT NOT NULL DEFAULT ({NOW})
);

-- A Reader's Comment on a Guide, added by an Admin in the Moderation queue
-- (added in #37; see app/comments.py). lang is the Comment language the Admin
-- picked. decided_at is when it was Accepted or Rejected, for the dashboard's
-- count of changes not on the site.
CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY,
    guide_id    INTEGER NOT NULL REFERENCES guides (id) ON DELETE CASCADE,
    reader_name TEXT NOT NULL CHECK (reader_name != ''),
    body        TEXT NOT NULL CHECK (body != ''),
    lang        TEXT NOT NULL DEFAULT 'zh' CHECK (lang IN ('zh', 'en')),
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at  TEXT NOT NULL DEFAULT ({NOW}),
    decided_at  TEXT
);

CREATE INDEX IF NOT EXISTS comments_by_guide ON comments (guide_id);
"""

# Columns added to a table after it was first created: (table, column, type).
# CREATE TABLE IF NOT EXISTS leaves an older table as it was, so connect()
# adds whichever of these it lacks.
ADDED_COLUMNS = [
    ("users", "last_login_at", "TEXT"),
    ("guides", "trashed_at", "TEXT"),
    ("guides", "restored_at", "TEXT"),
    ("review_rounds", "revision_id", "INTEGER"),
    ("game_terms", "nicknames", "TEXT NOT NULL DEFAULT ''"),
    # The cover's file name (added in S1): NULL for the first image, '' for
    # none (Tournament items only).
    ("guides", "cover", "TEXT"),
    ("revisions", "cover", "TEXT"),
    ("tournament_items", "cover", "TEXT"),
]

# Indexes on added columns, made once the columns are sure to exist.
INDEXES = """
CREATE INDEX IF NOT EXISTS review_rounds_by_revision ON review_rounds (revision_id);
"""


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    for table, column, type_ in ADDED_COLUMNS:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_}")


# What to do outside the database once an open connection's transaction
# commits or rolls back (see after_commit), by id(conn).
_after: dict[int, tuple[list[Callable[[], None]], list[Callable[[], None]]]] = {}


def after_commit(conn: sqlite3.Connection, committed: Callable[[], None] | None = None,
                 rolled_back: Callable[[], None] | None = None) -> None:
    """Run `committed` once the transaction on `conn` commits, or
    `rolled_back` if it doesn't, so a file kept beside the database (an
    uploaded image) changes only with the rows that name it."""
    on_commit, on_rollback = _after[id(conn)]
    if committed:
        on_commit.append(committed)
    if rolled_back:
        on_rollback.append(rolled_back)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database, commit if the block succeeds, and always close."""
    conn = sqlite3.connect(settings.database_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    on_commit, on_rollback = _after[id(conn)] = ([], [])
    try:
        conn.executescript(SCHEMA)
        _add_missing_columns(conn)
        conn.executescript(INDEXES)
        yield conn
        conn.commit()
    except BaseException:
        for action in on_rollback:
            action()
        raise
    else:
        for action in on_commit:
            action()
    finally:
        del _after[id(conn)]
        conn.close()
