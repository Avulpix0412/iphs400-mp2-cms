"""The game: Game Terms (so far only Heroes) and Patches.

A Hero is a Game Term with an official Chinese and an official English name.
Its URL slug is derived from the English Official name once, when the Hero
is added, and never changes after that.

A Patch is a game version such as `6.7`. Adding one makes it the Current
Patch, so the Current Patch is simply the Patch added most recently.

Anything the console should refuse raises `Refused` with a message to show.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass


class Refused(Exception):
    """A Hero or Patch change the console refuses, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Patch:
    id: int
    name: str
    is_current: bool


@dataclass(frozen=True)
class Hero:
    id: int
    name_zh: str
    name_en: str
    slug: str


def _hero_from_row(row: sqlite3.Row) -> Hero:
    return Hero(id=row["id"], name_zh=row["name_zh"], name_en=row["name_en"],
                slug=row["slug"])


def slugify(name_en: str) -> str:
    """`Vanessa` -> `vanessa`, `Black Knight` -> `black-knight`."""
    return re.sub(r"[^a-z0-9]+", "-", name_en.lower()).strip("-")


def _checked_names(name_zh: str, name_en: str) -> tuple[str, str]:
    """Both Official names, trimmed. Raises Refused if either is missing."""
    name_zh, name_en = name_zh.strip(), name_en.strip()
    if not name_zh:
        raise Refused("请填写官方中文名。")
    if not name_en:
        raise Refused("请填写官方英文名。")
    return name_zh, name_en


def _refuse_a_taken_english_name(conn: sqlite3.Connection, name_en: str,
                                 hero_id: int | None = None) -> None:
    """Raises Refused if another Hero already has this English Official name,
    ignoring case. Compared in Python, as SQLite's lower() folds only ASCII."""
    rows = conn.execute("SELECT * FROM game_terms WHERE kind = 'hero'"
                        " AND id IS NOT ?", (hero_id,))
    for clash in rows:
        if clash["name_en"].casefold() == name_en.casefold():
            raise Refused(f"官方英文名 {clash['name_en']} 已被英雄"
                          f" {clash['name_zh']} 使用。")


def _checked_names_and_slug(conn: sqlite3.Connection, name_zh: str,
                            name_en: str) -> tuple[str, str, str]:
    """Both Official names, trimmed, and the slug they give. Raises Refused if
    either name is missing or another Hero already has that English name or
    slug."""
    name_zh, name_en = _checked_names(name_zh, name_en)
    _refuse_a_taken_english_name(conn, name_en)
    slug = slugify(name_en)
    if not slug:
        raise Refused("官方英文名需要包含字母或数字，用来生成网址名。")
    clash = conn.execute(
        "SELECT * FROM game_terms WHERE kind = 'hero' AND slug = ?",
        (slug,)).fetchone()
    if clash:
        raise Refused(f"网址名 {slug} 已被英雄"
                      f" {clash['name_zh']}（{clash['name_en']}）使用。")
    return name_zh, name_en, slug


def add_hero(conn: sqlite3.Connection, *, name_zh: str, name_en: str) -> Hero:
    """Raises Refused if either Official name is missing or the English name
    or slug is taken."""
    name_zh, name_en, slug = _checked_names_and_slug(conn, name_zh, name_en)
    cur = conn.execute(
        "INSERT INTO game_terms (kind, name_zh, name_en, slug)"
        " VALUES ('hero', ?, ?, ?)", (name_zh, name_en, slug))
    row = conn.execute("SELECT * FROM game_terms WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return _hero_from_row(row)


def hero(conn: sqlite3.Connection, hero_id: int) -> Hero | None:
    row = conn.execute("SELECT * FROM game_terms WHERE kind = 'hero' AND id = ?",
                       (hero_id,)).fetchone()
    return _hero_from_row(row) if row else None


def edit_hero(conn: sqlite3.Connection, hero_id: int, *, name_zh: str,
              name_en: str) -> None:
    """Change a Hero's Official names; its slug stays the one it was given
    when added, so its page and its Guides' links never move. Raises Refused
    if either name is missing or another Hero has that English name."""
    name_zh, name_en = _checked_names(name_zh, name_en)
    _refuse_a_taken_english_name(conn, name_en, hero_id)
    conn.execute("UPDATE game_terms SET name_zh = ?, name_en = ?"
                 " WHERE kind = 'hero' AND id = ?", (name_zh, name_en, hero_id))


def heroes(conn: sqlite3.Connection) -> list[Hero]:
    rows = conn.execute("SELECT * FROM game_terms WHERE kind = 'hero'"
                        " ORDER BY name_en COLLATE NOCASE").fetchall()
    return [_hero_from_row(row) for row in rows]


def add_patch(conn: sqlite3.Connection, name: str) -> Patch:
    """Add a Patch, which becomes the Current Patch.
    Raises Refused if the name is blank or the Patch already exists."""
    name = name.strip()
    if not name:
        raise Refused("请填写版本号，例如 6.7。")
    try:
        cur = conn.execute("INSERT INTO patches (name) VALUES (?)", (name,))
    except sqlite3.IntegrityError:
        raise Refused(f"版本 {name} 已存在。") from None
    row = conn.execute("SELECT * FROM patches WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return Patch(id=row["id"], name=row["name"], is_current=True)


def patches(conn: sqlite3.Connection) -> list[Patch]:
    """Every Patch, newest first; the first is the Current Patch."""
    rows = conn.execute("SELECT * FROM patches ORDER BY id DESC").fetchall()
    return [Patch(id=row["id"], name=row["name"], is_current=(i == 0))
            for i, row in enumerate(rows)]
