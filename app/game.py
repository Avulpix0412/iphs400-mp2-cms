"""The game: Game Terms and Patches.

A Game Term is a named thing in the game, of one of seven kinds, with an
official Chinese and an official English name. A Hero is the kind of Game
Term every Guide is about. A Game Term may also have nicknames, the names
players use for it that the game doesn't (瓦姐 for 瓦妮莎), so the editor
preview can point them out. A Hero's URL slug is derived from the English Official name once, when the Hero
is added, and never changes after that.

A Patch is a game version such as `6.7`. Adding one makes it the Current
Patch, so the Current Patch is simply the Patch added most recently.

Anything the console should refuse raises `Refused` with a message to show.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import partial


class Refused(Exception):
    """A Hero or Patch change the console refuses, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# The seven kinds of Game Term, with the console's name for each.
KINDS = {"hero": "英雄", "item": "物品", "skill": "技能", "enchantment": "附魔",
         "monster": "怪物", "merchant": "商人", "event": "事件"}


@dataclass(frozen=True)
class Term:
    id: int
    kind: str
    name_zh: str
    name_en: str
    nicknames: tuple[str, ...]

    @property
    def kind_label(self) -> str:
        return KINDS[self.kind]


def _term_from_row(row: sqlite3.Row) -> Term:
    return Term(id=row["id"], kind=row["kind"], name_zh=row["name_zh"],
                name_en=row["name_en"], nicknames=_stored_nicknames(row))


def _stored_nicknames(row: sqlite3.Row) -> tuple[str, ...]:
    return tuple(row["nicknames"].splitlines())


def _to_store(nicknames: str) -> str:
    """Nicknames as parse_nicknames reads them, stored one per line."""
    return "\n".join(parse_nicknames(nicknames))


def nickname_notices(nicknames: Iterable[str]) -> list[str]:
    """A notice for each nickname that is a single Chinese character. It is
    allowed, but it matches that character anywhere, so the preview may warn
    about it often."""
    return [f"外号“{nickname}”只有一个汉字：预览会把正文里每一个“{nickname}”"
            "都当作这个外号，可能出现很多提醒。"
            for nickname in nicknames
            if re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", nickname)]


def parse_nicknames(text: str) -> tuple[str, ...]:
    """The nicknames in `text`, separated by 、 or | (or one per line),
    trimmed, without blanks or repeats."""
    names = (name.strip() for name in re.split(r"[、|\n]", text))
    return tuple(dict.fromkeys(name for name in names if name))


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
    nicknames: tuple[str, ...]


def _hero_from_row(row: sqlite3.Row) -> Hero:
    return Hero(id=row["id"], name_zh=row["name_zh"], name_en=row["name_en"],
                slug=row["slug"], nicknames=_stored_nicknames(row))


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


def _refuse_a_taken_english_name(conn: sqlite3.Connection, kind: str,
                                 name_en: str, term_id: int | None = None) -> None:
    """Raises Refused if another Game Term of this kind already has this
    English Official name, ignoring case. Compared in Python, as SQLite's
    lower() folds only ASCII."""
    rows = conn.execute("SELECT * FROM game_terms WHERE kind = ? AND id IS NOT ?",
                        (kind, term_id))
    for clash in rows:
        if clash["name_en"].casefold() == name_en.casefold():
            raise Refused(f"官方英文名 {clash['name_en']} 已被{KINDS[kind]}"
                          f" {clash['name_zh']} 使用。")


def _checked_names_and_slug(conn: sqlite3.Connection, name_zh: str,
                            name_en: str) -> tuple[str, str, str]:
    """Both Official names, trimmed, and the slug they give. Raises Refused if
    either name is missing or another Hero already has that English name or
    slug."""
    name_zh, name_en = _checked_names(name_zh, name_en)
    _refuse_a_taken_english_name(conn, "hero", name_en)
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


def add_hero(conn: sqlite3.Connection, *, name_zh: str, name_en: str,
             nicknames: str = "") -> Hero:
    """Raises Refused if either Official name is missing or the English name
    or slug is taken. `nicknames` is as parse_nicknames reads it."""
    name_zh, name_en, slug = _checked_names_and_slug(conn, name_zh, name_en)
    cur = conn.execute(
        "INSERT INTO game_terms (kind, name_zh, name_en, slug, nicknames)"
        " VALUES ('hero', ?, ?, ?, ?)",
        (name_zh, name_en, slug, _to_store(nicknames)))
    row = conn.execute("SELECT * FROM game_terms WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return _hero_from_row(row)


def hero(conn: sqlite3.Connection, hero_id: int) -> Hero | None:
    row = conn.execute("SELECT * FROM game_terms WHERE kind = 'hero' AND id = ?",
                       (hero_id,)).fetchone()
    return _hero_from_row(row) if row else None


def edit_hero(conn: sqlite3.Connection, hero_id: int, *, name_zh: str,
              name_en: str, nicknames: str) -> None:
    """Change a Hero's Official names and nicknames; its slug stays the one
    it was given when added, so its page and its Guides' links never move."""
    if hero(conn, hero_id) is None:
        raise Refused("找不到这个英雄。")
    edit_term(conn, hero_id, name_zh=name_zh, name_en=name_en, nicknames=nicknames)


def heroes(conn: sqlite3.Connection) -> list[Hero]:
    rows = conn.execute("SELECT * FROM game_terms WHERE kind = 'hero'"
                        " ORDER BY name_en COLLATE NOCASE").fetchall()
    return [_hero_from_row(row) for row in rows]


def add_term(conn: sqlite3.Connection, *, kind: str, name_zh: str,
             name_en: str, nicknames: str = "") -> Term:
    """Add a Game Term of a kind other than Hero (Heroes need a slug: see
    add_hero). Raises Refused if the kind is unknown, either Official name
    is missing, or another term of the kind has the English name."""
    if kind not in KINDS or kind == "hero":
        raise Refused("请选择术语种类。")
    name_zh, name_en = _checked_names(name_zh, name_en)
    _refuse_a_taken_english_name(conn, kind, name_en)
    cur = conn.execute(
        "INSERT INTO game_terms (kind, name_zh, name_en, nicknames)"
        " VALUES (?, ?, ?, ?)",
        (kind, name_zh, name_en, _to_store(nicknames)))
    row = conn.execute("SELECT * FROM game_terms WHERE id = ?",
                       (cur.lastrowid,)).fetchone()
    return _term_from_row(row)


def term(conn: sqlite3.Connection, term_id: int) -> Term | None:
    row = conn.execute("SELECT * FROM game_terms WHERE id = ?",
                       (term_id,)).fetchone()
    return _term_from_row(row) if row else None


def edit_term(conn: sqlite3.Connection, term_id: int, *, name_zh: str,
              name_en: str, nicknames: str) -> None:
    """Change a Game Term's Official names and nicknames (never its kind, nor
    a Hero's slug). Raises Refused if either name is missing or another term
    of its kind has the English name."""
    current = term(conn, term_id)
    if current is None:
        raise Refused("找不到这个游戏术语。")
    name_zh, name_en = _checked_names(name_zh, name_en)
    _refuse_a_taken_english_name(conn, current.kind, name_en, term_id)
    conn.execute("UPDATE game_terms SET name_zh = ?, name_en = ?, nicknames = ?"
                 " WHERE id = ?", (name_zh, name_en,
                                   _to_store(nicknames), term_id))


# Sorts Game Terms in KINDS order.
_BY_KIND = ("CASE kind " + " ".join(f"WHEN '{kind}' THEN {i}"
                                    for i, kind in enumerate(KINDS)) + " END")


class Glossary:
    """Every Game Term, Heroes included, looked up by either Official name
    (trimmed, ignoring case). Where several terms share a name, they come in
    KINDS order (Heroes first), then in the order they were added."""

    def __init__(self, terms: Iterable[Term]) -> None:
        self.terms = list(terms)
        self._by_name: dict[str, list[Term]] = {}
        for term in self.terms:
            for name in {term.name_zh.casefold(), term.name_en.casefold()}:
                self._by_name.setdefault(name, []).append(term)

    def matching(self, name: str) -> list[Term]:
        return self._by_name.get(name.strip().casefold(), [])

    def nicknames_in(self, text: str) -> list[tuple[str, Term, int]]:
        """Each known nickname found in `text`, with its Game Term and how
        many times it is there. Case is ignored, and a nickname starting or
        ending in a Latin letter or digit must be a whole word at that end
        (`Van` is not found in `Vanguard`), while Chinese has no spaces to
        mark words, so 瓦姐 is found anywhere (see nickname_notices)."""
        found = [(nickname, term,
                  len(re.findall(_whole_word(nickname), text, re.IGNORECASE)))
                 for term in self.terms for nickname in term.nicknames]
        return [(nickname, term, count) for nickname, term, count in found if count]


def _whole_word(nickname: str) -> str:
    pattern = re.escape(nickname)
    if re.match(r"[A-Za-z0-9]", nickname):
        pattern = r"(?<![A-Za-z0-9])" + pattern
    if re.search(r"[A-Za-z0-9]$", nickname):
        pattern += r"(?![A-Za-z0-9])"
    return pattern


def glossary(conn: sqlite3.Connection) -> Glossary:
    rows = conn.execute(f"SELECT * FROM game_terms ORDER BY {_BY_KIND}, id")
    return Glossary(_term_from_row(row) for row in rows)


def terms(conn: sqlite3.Connection) -> list[Term]:
    """Every Game Term but the Heroes, by kind, then English name."""
    rows = conn.execute("SELECT * FROM game_terms WHERE kind != 'hero'"
                        f" ORDER BY {_BY_KIND}, name_en COLLATE NOCASE").fetchall()
    return [_term_from_row(row) for row in rows]


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


# CSV import. The file's first row names its columns: kind, name_zh, name_en,
# and optionally nicknames. A row whose kind and English Official name
# (ignoring case) match an existing Game Term changes that term; any other
# row adds one. Bad rows are rejected one by one, so the good ones can still
# be imported.

CSV_COLUMNS = ("kind", "name_zh", "name_en")


@dataclass(frozen=True)
class CsvRow:
    number: int  # the row number a spreadsheet shows, the header being row 1
    kind: str
    name_zh: str
    name_en: str
    nicknames: tuple[str, ...]


@dataclass(frozen=True)
class ImportPlan:
    added: list[CsvRow]
    changed: list[tuple[Term, CsvRow]]  # the term as it is, and its row
    unchanged: int
    rejected: list[tuple[int, str]]  # (row number, reason)


def _kind_of(written: str) -> str | None:
    """The kind a CSV cell names, by its English key or its Chinese name."""
    written = written.strip()
    return next((kind for kind, label in KINDS.items()
                 if written.casefold() == kind or written == label), None)


def _csv_rows(csv_bytes: bytes) -> Iterator[tuple[int, dict[str, str]]]:
    """The file's rows after the header, numbered, with their cells trimmed;
    wholly blank rows are skipped. Raises Refused if the file isn't UTF-8 or
    lacks the header, or once a row can't be read as CSV."""
    try:
        text = csv_bytes.decode("utf-8-sig")  # Excel starts its UTF-8 with a BOM
    except UnicodeDecodeError:
        raise Refused("读不出这个文件。请把 CSV 存成 UTF-8 编码后再上传。") from None
    reader = csv.reader(io.StringIO(text))
    try:
        header = [cell.strip().lower() for cell in next(reader, [])]
    except csv.Error:
        header = []
    if not set(CSV_COLUMNS) <= set(header):
        raise Refused("CSV 第一行必须是表头：kind,name_zh,name_en,nicknames"
                      "（nicknames 一列可以省略）。")
    try:
        for number, cells in enumerate(reader, start=2):
            row = {column: cell.strip() for column, cell in zip(header, cells)}
            if any(row.values()):
                yield number, row
    except csv.Error as error:
        raise Refused(f"读不出这个 CSV 文件（第 {reader.line_num} 行附近：{error}）。"
                      "请检查引号是否成对。") from None


def plan_import(conn: sqlite3.Connection, csv_bytes: bytes) -> ImportPlan:
    """What importing the CSV file would add and change, and the rows it
    would reject with the reason for each. Nothing is saved. An empty
    nicknames cell keeps the nicknames a term already has."""
    existing = {(term.kind, term.name_en.casefold()): term
                for term in glossary(conn).terms}
    added: list[CsvRow] = []
    changed: list[tuple[Term, CsvRow]] = []
    rejected: list[tuple[int, str]] = []
    unchanged = 0
    row_of_term: dict[tuple[str, str], int] = {}  # each term's first row
    row_of_new_slug: dict[str, int] = {}
    for number, cells in _csv_rows(csv_bytes):
        kind = _kind_of(cells.get("kind", ""))
        name_zh, name_en = cells.get("name_zh", ""), cells.get("name_en", "")
        if kind is None:
            rejected.append((number, f"未知的种类“{cells.get('kind', '')}”。种类须是"
                             f"{'、'.join(KINDS.values())}之一，"
                             f"或其英文（{', '.join(KINDS)}）。"))
            continue
        if not name_zh or not name_en:
            rejected.append((number, f"缺少官方{'中' if not name_zh else '英'}文名。"))
            continue
        key = (kind, name_en.casefold())
        if key in row_of_term:
            rejected.append((number, f"和第 {row_of_term[key]} 行是同一个游戏术语"
                             "（种类和官方英文名都相同）。"))
            continue
        row_of_term[key] = number
        row = CsvRow(number, kind, name_zh, name_en,
                     parse_nicknames(cells.get("nicknames", "")))
        term = existing.get(key)
        if term is None and kind == "hero":
            try:
                slug = _checked_names_and_slug(conn, name_zh, name_en)[2]
            except Refused as refused:
                rejected.append((number, refused.message))
                continue
            if slug in row_of_new_slug:
                rejected.append((number, f"网址名 {slug} 已被第"
                                 f" {row_of_new_slug[slug]} 行的英雄使用。"))
                continue
            row_of_new_slug[slug] = number
        if term is None:
            added.append(row)
        elif (term.name_zh, term.name_en) != (name_zh, name_en) or (
                row.nicknames and row.nicknames != term.nicknames):
            changed.append((term, row))
        else:
            unchanged += 1
    return ImportPlan(added, changed, unchanged, rejected)


def import_terms(conn: sqlite3.Connection, csv_bytes: bytes, *,
                 only_new: bool = False) -> ImportPlan:
    """Import the CSV file's good rows, as plan_import plans, and say what
    was done. With `only_new`, Game Terms that already exist are left as
    they are, and the plan says nothing changed."""
    plan = plan_import(conn, csv_bytes)
    if only_new:
        plan = ImportPlan(plan.added, [], plan.unchanged + len(plan.changed),
                          plan.rejected)
    for row in plan.added:
        add = add_hero if row.kind == "hero" else partial(add_term, kind=row.kind)
        add(conn, name_zh=row.name_zh, name_en=row.name_en,
            nicknames="\n".join(row.nicknames))
    for term, row in plan.changed:
        edit_term(conn, term.id, name_zh=row.name_zh, name_en=row.name_en,
                  nicknames="\n".join(row.nicknames or term.nicknames))
    return plan
