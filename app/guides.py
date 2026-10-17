"""The Guide workflow: every change to a Guide, and who may make it.

A Guide moves Draft -> Submitted -> Published. Routes never touch a Guide's
row themselves: they call a function here with the acting user, and it either
makes the change or raises `Refused` with the reason to show.

A Guide's slug is `<hero-slug>-<id>`, given when it is created. It never
changes on its own (not with the title, not with the Hero); only an Admin can
edit it.

Editors only ever see their own Guides. To them, anyone else's Guide does not
exist, so it is refused as not found rather than forbidden.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from app import db, game
from app.accounts import User


class Refused(Exception):
    """A Guide change the console refuses, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotAllowed(Refused):
    """The acting user's role does not allow this change."""


class GuideNotFound(Refused):
    """No such Guide, or none this user may see."""

    def __init__(self) -> None:
        super().__init__("找不到这篇攻略。")


STATUS_LABELS = {"draft": "草稿", "submitted": "待审核", "published": "已发布"}


@dataclass(frozen=True)
class Guide:
    id: int
    slug: str
    title_zh: str
    body_zh: str
    title_en: str
    body_en: str
    hero_id: int
    hero_name_zh: str
    hero_name_en: str
    hero_slug: str
    patch_id: int
    patch_name: str
    author_id: int
    author_name: str
    status: str
    created_at: str
    updated_at: str
    published_at: str | None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    def has_text_in(self, lang: str) -> bool:
        """Chinese text is required, so every Guide has it; English is optional."""
        return lang == "zh" or bool(self.title_en.strip() or self.body_en.strip())


@dataclass(frozen=True)
class GuideFields:
    """What the Guide form sends. `slug` is None when the form has no slug
    field (only Admins see one)."""
    title_zh: str = ""
    body_zh: str = ""
    title_en: str = ""
    body_en: str = ""
    hero_id: int | None = None
    patch_id: int | None = None
    slug: str | None = None

    @classmethod
    def of(cls, guide: Guide) -> GuideFields:
        return cls(title_zh=guide.title_zh, body_zh=guide.body_zh,
                   title_en=guide.title_en, body_en=guide.body_en,
                   hero_id=guide.hero_id, patch_id=guide.patch_id, slug=guide.slug)


_SELECT = """
SELECT guides.*, heroes.name_zh AS hero_name_zh, heroes.name_en AS hero_name_en,
       heroes.slug AS hero_slug, patches.name AS patch_name, users.display_name AS author_name
FROM guides
JOIN game_terms AS heroes ON heroes.id = guides.hero_id
JOIN patches ON patches.id = guides.patch_id
JOIN users ON users.id = guides.author_id
"""


def _guide_from_row(row: sqlite3.Row) -> Guide:
    return Guide(**{field: row[field] for field in Guide.__dataclass_fields__})


def _visible_to(actor: User) -> tuple[str, tuple[int, ...]]:
    """The WHERE clause limiting Guides to those `actor` may see."""
    if actor.can("manage_all_guides"):
        return "1", ()
    return "guides.author_id = ?", (actor.id,)


def guide(conn: sqlite3.Connection, actor: User, guide_id: int) -> Guide | None:
    """The Guide, or None if it doesn't exist or `actor` may not see it."""
    where, params = _visible_to(actor)
    row = conn.execute(f"{_SELECT} WHERE guides.id = ? AND {where}",
                       (guide_id, *params)).fetchone()
    return _guide_from_row(row) if row else None


LANGUAGE_LABELS = {"en": "有英文版", "zh": "只有中文版"}


@dataclass(frozen=True)
class GuideFilter:
    """What the content list is narrowed to; None (or "") means any."""
    status: str = ""
    hero_id: int | None = None
    author_id: int | None = None
    patch_id: int | None = None
    language: str = ""   # "en": has English text; "zh": Chinese text only


def guides(conn: sqlite3.Connection, actor: User,
           filters: GuideFilter = GuideFilter()) -> list[Guide]:
    """The Guides `actor` may see that match `filters`, most recently updated
    first."""
    where, params = _visible_to(actor)
    clauses, values = [where], list(params)
    for column, value in [("guides.status", filters.status or None),
                          ("guides.hero_id", filters.hero_id),
                          ("guides.author_id", filters.author_id),
                          ("guides.patch_id", filters.patch_id)]:
        if value is not None:
            clauses.append(f"{column} = ?")
            values.append(value)
    has_english = "(guides.title_en != '' OR guides.body_en != '')"
    if filters.language == "en":
        clauses.append(has_english)
    elif filters.language == "zh":
        clauses.append(f"NOT {has_english}")
    rows = conn.execute(f"{_SELECT} WHERE {' AND '.join(clauses)}"
                        " ORDER BY guides.updated_at DESC, guides.id DESC",
                        values).fetchall()
    return [_guide_from_row(row) for row in rows]


def published(conn: sqlite3.Connection) -> list[Guide]:
    """Every Published Guide, most recently updated first: all the Site build
    may read. It acts for no one, so it needs no user."""
    rows = conn.execute(f"{_SELECT} WHERE guides.status = 'published'"
                        " ORDER BY guides.updated_at DESC, guides.id DESC").fetchall()
    return [_guide_from_row(row) for row in rows]


def authors(conn: sqlite3.Connection, actor: User) -> list[tuple[int, str]]:
    """(id, Display name) of everyone who wrote a Guide `actor` may see."""
    where, params = _visible_to(actor)
    rows = conn.execute(
        "SELECT DISTINCT users.id, users.display_name FROM guides"
        f" JOIN users ON users.id = guides.author_id WHERE {where}"
        " ORDER BY users.display_name", params).fetchall()
    return [(row["id"], row["display_name"]) for row in rows]


def patch_choices(conn: sqlite3.Connection, guide: Guide | None = None
                  ) -> list[game.Patch]:
    """The Patches a Guide may be written for: the Current Patch and the two
    before it, plus the Guide's own Patch if that is older still."""
    patches = game.patches(conn)
    choices = patches[:3]
    if guide and all(patch.id != guide.patch_id for patch in choices):
        choices += [patch for patch in patches if patch.id == guide.patch_id]
    return choices


def _checked_hero_and_patch(conn: sqlite3.Connection, fields: GuideFields,
                            guide: Guide | None = None) -> tuple[game.Hero, int]:
    hero = game.hero(conn, fields.hero_id) if fields.hero_id else None
    if hero is None:
        raise Refused("请选择英雄。")
    patch_id = fields.patch_id
    if patch_id is None or all(patch.id != patch_id
                               for patch in patch_choices(conn, guide)):
        raise Refused("请选择版本。")
    return hero, patch_id


def create(conn: sqlite3.Connection, actor: User, fields: GuideFields) -> Guide:
    """Save a new Guide as a Draft by `actor`, who becomes its Author."""
    hero, patch_id = _checked_hero_and_patch(conn, fields)
    cur = conn.execute(
        "INSERT INTO guides (title_zh, body_zh, title_en, body_en, hero_id,"
        " patch_id, author_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fields.title_zh.strip(), fields.body_zh, fields.title_en.strip(),
         fields.body_en, hero.id, patch_id, actor.id))
    guide_id = cur.lastrowid
    assert guide_id is not None
    slug, n = f"{hero.slug}-{guide_id}", 1
    # Only if an Admin already gave that slug to another Guide.
    while conn.execute("SELECT 1 FROM guides WHERE slug = ?", (slug,)).fetchone():
        n += 1
        slug = f"{hero.slug}-{guide_id}-{n}"
    conn.execute("UPDATE guides SET slug = ? WHERE id = ?", (slug, guide_id))
    new = guide(conn, actor, guide_id)
    assert new is not None
    return new


def _editable(conn: sqlite3.Connection, actor: User, guide_id: int) -> Guide:
    found = guide(conn, actor, guide_id)
    if found is None:
        raise GuideNotFound
    return found


_SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def _checked_slug(conn: sqlite3.Connection, actor: User, current: Guide,
                  slug: str | None) -> str:
    """The slug to keep: the current one unless an Admin typed another."""
    if slug is None or slug.strip() == current.slug:
        return current.slug
    if not actor.can("edit_guide_slugs"):
        raise NotAllowed("只有管理员可以修改网址名。")
    slug = slug.strip()
    if not _SLUG.fullmatch(slug):
        raise Refused("网址名只能包含小写英文字母、数字和连字符，例如 vanessa-12。")
    if conn.execute("SELECT 1 FROM guides WHERE slug = ? AND id != ?",
                    (slug, current.id)).fetchone():
        raise Refused(f"网址名 {slug} 已被另一篇攻略使用。")
    return slug


def save(conn: sqlite3.Connection, actor: User, guide_id: int,
         fields: GuideFields) -> Guide:
    """Save changes to a Guide without changing its status."""
    current = _editable(conn, actor, guide_id)
    if current.status == "published" and not actor.can("manage_all_guides"):
        raise NotAllowed("已发布的攻略要通过修订来修改。")
    hero, patch_id = _checked_hero_and_patch(conn, fields, current)
    slug = _checked_slug(conn, actor, current, fields.slug)
    if current.status != "draft":
        _check_text(fields)
    conn.execute(
        "UPDATE guides SET title_zh = ?, body_zh = ?, title_en = ?, body_en = ?,"
        f" hero_id = ?, patch_id = ?, slug = ?, updated_at = {db.NOW}"
        " WHERE id = ?",
        (fields.title_zh.strip(), fields.body_zh, fields.title_en.strip(),
         fields.body_en, hero.id, patch_id, slug, guide_id))
    return _editable(conn, actor, guide_id)


def _check_text(fields: GuideFields | Guide) -> None:
    """The text a Guide needs before it can be reviewed or Published."""
    if not fields.title_zh.strip() or not fields.body_zh.strip():
        raise Refused("提交审核前请填写中文标题和正文。")
    if bool(fields.title_en.strip()) != bool(fields.body_en.strip()):
        raise Refused("英文版需要同时填写标题和正文；不写英文版就都留空。")


def can_submit(actor: User, guide: Guide) -> bool:
    """Whether to offer `actor` the Submit button (提交审核) on `guide`. Admins
    are offered Publish instead, since they need no review."""
    return (guide.author_id == actor.id and guide.status == "draft"
            and not can_publish(actor, guide))


def submit(conn: sqlite3.Connection, actor: User, guide_id: int) -> Guide:
    """The Author marks their Draft finished, for an Admin to review."""
    current = _editable(conn, actor, guide_id)
    if current.author_id != actor.id:
        raise NotAllowed("只有作者本人可以提交审核。")
    if current.status != "draft":
        raise Refused("这篇攻略已经提交审核了。" if current.status == "submitted"
                      else "这篇攻略已经发布了。")
    if actor.state == "submission_ban":
        raise NotAllowed("你的账号已被禁止投稿：可以继续编辑草稿，但不能提交审核。"
                         "如有疑问，请联系管理员。")
    _check_text(current)
    conn.execute("UPDATE guides SET status = 'submitted',"
                 f" updated_at = {db.NOW} WHERE id = ?", (guide_id,))
    return _editable(conn, actor, guide_id)


def can_publish(actor: User, guide: Guide) -> bool:
    """Whether to offer `actor` the Publish button (发布) on `guide`: Admins
    Publish Submitted Guides, and their own Drafts without Submitting."""
    return actor.can("publish_guides") and (
        guide.status == "submitted"
        or (guide.status == "draft" and guide.author_id == actor.id))


def publish(conn: sqlite3.Connection, actor: User, guide_id: int) -> Guide:
    """An Admin approves a Guide. It reaches Readers at the next Site build."""
    current = _editable(conn, actor, guide_id)
    if not actor.can("publish_guides"):
        raise NotAllowed("只有管理员可以发布攻略。")
    if current.status == "published":
        raise Refused("这篇攻略已经发布了。")
    if not can_publish(actor, current):
        raise Refused("这篇攻略还是草稿，要等作者提交审核后才能发布。")
    _check_text(current)
    conn.execute("UPDATE guides SET status = 'published',"
                 f" published_at = {db.NOW}, updated_at = {db.NOW}"
                 " WHERE id = ?", (guide_id,))
    return _editable(conn, actor, guide_id)


def counts(conn: sqlite3.Connection, actor: User) -> dict[str, int]:
    """How many Guides `actor` may see are in each status."""
    where, params = _visible_to(actor)
    rows = conn.execute(f"SELECT status, COUNT(*) AS n FROM guides WHERE {where}"
                        " GROUP BY status", params).fetchall()
    found = {row["status"]: row["n"] for row in rows}
    return {status: found.get(status, 0) for status in STATUS_LABELS}
