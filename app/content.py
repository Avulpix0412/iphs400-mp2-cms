"""Pages and Tournament items: the content only Admins write.

A Page (such as About 关于) appears in the public navigation once Published.
A Tournament item is an announcement (预告) of an upcoming Tournament or a
recap (回顾) of one that happened; the 锦标赛 section lists them.

Neither goes through review. An Admin saves a Draft and Publishes it, and can
Unpublish it or delete it for good. Every function takes the acting user and
refuses anyone who can't manage_pages, whatever the route in front of it
checked. Anything the console should refuse raises `Refused` with a message
to show.

A Tournament item can have images (app/media.py) and an optional cover,
changed with it; Pages have none.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, fields as fields_of, replace
from datetime import date
from pathlib import Path
from typing import Protocol

from app import db, media
from app.accounts import User
from app.guides import SLUG


class Refused(Exception):
    """A Page or Tournament item change the console refuses, with the reason
    to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotAllowed(Refused):
    """The acting user's role does not allow this change."""


class NotFound(Refused):
    """No such Page or Tournament item."""


STATUS_LABELS = {"draft": "草稿", "published": "已发布"}


class TextBearing(Protocol):
    """What Pages and Tournament items share: a Chinese and an English text,
    a status, and a place in the console. Read-only, as both are frozen."""
    @property
    def id(self) -> int: ...
    @property
    def title_zh(self) -> str: ...
    @property
    def body_zh(self) -> str: ...
    @property
    def title_en(self) -> str: ...
    @property
    def body_en(self) -> str: ...
    @property
    def status(self) -> str: ...
    @property
    def status_label(self) -> str: ...
    @property
    def console_path(self) -> str: ...
    def has_text_in(self, lang: str) -> bool: ...


def _check_manages_pages(actor: User) -> None:
    if not actor.can("manage_pages"):
        raise NotAllowed("只有管理员可以管理页面和锦标赛内容。")


@dataclass(frozen=True)
class Page:
    id: int
    slug: str
    title_zh: str
    body_zh: str
    title_en: str
    body_en: str
    status: str
    created_at: str
    updated_at: str

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def console_path(self) -> str:
        """Where the Page's console pages live, from the console root."""
        return f"admin/pages/{self.id}"

    def has_text_in(self, lang: str) -> bool:
        """Chinese text is required to Publish; English is optional."""
        return lang == "zh" or bool(self.title_en.strip() or self.body_en.strip())


@dataclass(frozen=True)
class PageFields:
    """What the Page form sends."""
    slug: str = ""
    title_zh: str = ""
    body_zh: str = ""
    title_en: str = ""
    body_en: str = ""

    @classmethod
    def of(cls, page: Page) -> PageFields:
        return cls(slug=page.slug, title_zh=page.title_zh, body_zh=page.body_zh,
                   title_en=page.title_en, body_en=page.body_en)


def _page_from_row(row: sqlite3.Row) -> Page:
    return Page(**{field.name: row[field.name] for field in fields_of(Page)})


# The folders the Site build already makes in each language tree.
RESERVED_SLUGS = {"guides", "heroes", "authors", "tournaments"}


def _checked_slug(conn: sqlite3.Connection, slug: str,
                  page_id: int | None = None) -> str:
    slug = slug.strip()
    if not slug:
        raise Refused("请填写网址名，例如 about。")
    if not SLUG.fullmatch(slug):
        raise Refused("网址名只能包含小写英文字母、数字和连字符，例如 about。")
    if slug in RESERVED_SLUGS:
        raise Refused(f"网址名 {slug} 是网站自己用的，请换一个。")
    if conn.execute("SELECT 1 FROM pages WHERE slug = ? AND id IS NOT ?",
                    (slug, page_id)).fetchone():
        raise Refused(f"网址名 {slug} 已被另一个页面使用。")
    return slug


def _trimmed[Fields: (PageFields, TournamentFields)](fields: Fields) -> Fields:
    """The fields with their titles trimmed, as Guides' are: a title is
    plain text, shown as written in the navigation and lists."""
    return replace(fields, title_zh=fields.title_zh.strip(),
                   title_en=fields.title_en.strip())


def _check_publishable(title_zh: str, body_zh: str, title_en: str, body_en: str) -> None:
    """What Readers get must have Chinese text, and English text either whole
    or not at all."""
    if not title_zh.strip() or not body_zh.strip():
        raise Refused("发布前请填写中文标题和中文正文。")
    if bool(title_en.strip()) != bool(body_en.strip()):
        raise Refused("英文版的标题和正文要么都填写，要么都留空。")


def create_page(conn: sqlite3.Connection, actor: User, fields: PageFields) -> Page:
    """A new Draft Page. Raises Refused if the slug is missing, not ASCII,
    reserved, or taken."""
    _check_manages_pages(actor)
    fields = _trimmed(fields)
    slug = _checked_slug(conn, fields.slug)
    cur = conn.execute(
        "INSERT INTO pages (slug, title_zh, body_zh, title_en, body_en)"
        " VALUES (?, ?, ?, ?, ?)",
        (slug, fields.title_zh, fields.body_zh, fields.title_en, fields.body_en))
    return _existing_page(conn, cur.lastrowid or 0)


def _existing_page(conn: sqlite3.Connection, page_id: int) -> Page:
    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page_id,)).fetchone()
    if row is None:
        raise NotFound("找不到这个页面。")
    return _page_from_row(row)


def page(conn: sqlite3.Connection, actor: User, page_id: int) -> Page:
    """Raises NotFound if there is no such Page."""
    _check_manages_pages(actor)
    return _existing_page(conn, page_id)


def pages(conn: sqlite3.Connection, actor: User) -> list[Page]:
    """Every Page, in the order they were added."""
    _check_manages_pages(actor)
    return [_page_from_row(row)
            for row in conn.execute("SELECT * FROM pages ORDER BY id")]


def save_page(conn: sqlite3.Connection, actor: User, page_id: int,
              fields: PageFields) -> Page:
    """Change a Page. A Published Page stays Published, so it must stay
    publishable; its change reaches the site at the next Site build."""
    current = page(conn, actor, page_id)
    fields = _trimmed(fields)
    slug = _checked_slug(conn, fields.slug, page_id)
    published = current.status == "published"
    if published:
        _check_publishable(fields.title_zh, fields.body_zh, fields.title_en,
                           fields.body_en)
    conn.execute(
        "UPDATE pages SET slug = ?, title_zh = ?, body_zh = ?, title_en = ?,"
        f" body_en = ?, updated_at = {db.NOW}"
        + (f", site_changed_at = {db.NOW}" if published else "") + " WHERE id = ?",
        (slug, fields.title_zh, fields.body_zh, fields.title_en, fields.body_en,
         page_id))
    return _existing_page(conn, page_id)


def _publish(conn: sqlite3.Connection, table: str, item: TextBearing,
             what: str) -> None:
    if item.status == "published":
        raise Refused(f"这个{what}已经发布了。")
    _check_publishable(item.title_zh, item.body_zh, item.title_en, item.body_en)
    conn.execute(f"UPDATE {table} SET status = 'published', site_changed_at = {db.NOW}"
                 " WHERE id = ?", (item.id,))


def _unpublish(conn: sqlite3.Connection, table: str, item: TextBearing,
               what: str) -> None:
    if item.status != "published":
        raise Refused(f"只有已发布的{what}才能撤下。")
    conn.execute(f"UPDATE {table} SET status = 'draft', site_changed_at = {db.NOW}"
                 " WHERE id = ?", (item.id,))


def _record_removal(conn: sqlite3.Connection, kind: str, table: str,
                    item: TextBearing) -> None:
    """Note an item about to be deleted for good, if it was ever Published,
    for changes_since."""
    conn.execute(
        "INSERT INTO removed_content (kind, item_id, was_published, site_changed_at)"
        f" SELECT ?, id, status = 'published', site_changed_at FROM {table}"
        " WHERE id = ? AND site_changed_at IS NOT NULL", (kind, item.id))


def changes_since(conn: sqlite3.Connection, since: str) -> int:
    """How many Pages and Tournament items changed on the site after `since`:
    Published, edited while Published, Unpublished, or deleted for good while
    the site had them. It may count one the site never had (such as one
    Published and Unpublished in between), but never misses one."""
    changed = sum(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE site_changed_at > ?",
                               (since,)).fetchone()[0]
                  for table in ("pages", "tournament_items"))
    removed = conn.execute(
        "SELECT COUNT(*) FROM removed_content WHERE removed_at > ?"
        " AND (was_published OR site_changed_at > ?)", (since, since)).fetchone()[0]
    return changed + removed


def publish_page(conn: sqlite3.Connection, actor: User, page_id: int) -> Page:
    """Publish a Draft Page; it appears in the navigation after the next Site
    build. Raises Refused if it lacks Chinese text."""
    _publish(conn, "pages", page(conn, actor, page_id), "页面")
    return _existing_page(conn, page_id)


def unpublish_page(conn: sqlite3.Connection, actor: User, page_id: int) -> Page:
    """Make a Published Page a Draft again; the next Site build leaves it out."""
    _unpublish(conn, "pages", page(conn, actor, page_id), "页面")
    return _existing_page(conn, page_id)


def delete_page(conn: sqlite3.Connection, actor: User, page_id: int) -> None:
    """Delete a Page for good. A Published one leaves the site at the next
    Site build."""
    _record_removal(conn, "page", "pages", page(conn, actor, page_id))
    conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))


def published_pages(conn: sqlite3.Connection) -> list[Page]:
    """Every Published Page, in the order they were added: all the Site build
    may read. It acts for no one, so it needs no user."""
    rows = conn.execute("SELECT * FROM pages WHERE status = 'published' ORDER BY id")
    return [_page_from_row(row) for row in rows]


# Tournament items. An announcement (预告) tells Readers about an upcoming
# Tournament; a recap (回顾) tells how one went, and may link to the
# announcement it follows. Each has the Tournament's date and Patch.

KIND_LABELS = {"announcement": "预告", "recap": "回顾"}


@dataclass(frozen=True)
class TournamentItem:
    id: int
    kind: str
    title_zh: str
    body_zh: str
    title_en: str
    body_en: str
    tournament_date: str  # YYYY-MM-DD
    patch_id: int
    patch_name: str
    announcement_id: int | None  # a recap's announcement, if it has one
    status: str
    created_at: str
    updated_at: str
    cover: str | None  # the chosen cover's file name; None: the first; '': none

    @property
    def media_owner(self) -> str:
        return f"tournament/{self.id}"

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def console_path(self) -> str:
        return f"admin/tournaments/{self.id}"

    def has_text_in(self, lang: str) -> bool:
        return lang == "zh" or bool(self.title_en.strip() or self.body_en.strip())


@dataclass(frozen=True)
class TournamentFields:
    """What the Tournament item form sends."""
    kind: str = "announcement"
    title_zh: str = ""
    body_zh: str = ""
    title_en: str = ""
    body_en: str = ""
    tournament_date: str = ""
    patch_id: int | None = None
    announcement_id: int | None = None
    images: media.ImageFields = media.ImageFields()

    @classmethod
    def of(cls, item: TournamentItem) -> TournamentFields:
        return cls(kind=item.kind, title_zh=item.title_zh, body_zh=item.body_zh,
                   title_en=item.title_en, body_en=item.body_en,
                   tournament_date=item.tournament_date, patch_id=item.patch_id,
                   announcement_id=item.announcement_id,
                   images=media.ImageFields(cover=item.cover))


_TOURNAMENT_SELECT = """
SELECT tournament_items.*, patches.name AS patch_name FROM tournament_items
JOIN patches ON patches.id = tournament_items.patch_id
"""
# Newest first: the latest Tournament date, and the one added last on a day.
_NEWEST_FIRST = "ORDER BY tournament_date DESC, tournament_items.id DESC"


def _item_from_row(row: sqlite3.Row) -> TournamentItem:
    return TournamentItem(**{field.name: row[field.name]
                             for field in fields_of(TournamentItem)})


def _checked_tournament_fields(conn: sqlite3.Connection, fields: TournamentFields,
                               item_id: int | None = None) -> TournamentFields:
    """The fields, with the date trimmed and an announcement's link dropped.
    Raises Refused if the kind, date or Patch is missing, or a recap links
    to anything but another announcement."""
    if fields.kind not in KIND_LABELS:
        raise Refused("请选择预告或回顾。")
    day = fields.tournament_date.strip()
    try:
        valid = date.fromisoformat(day).isoformat() == day
    except ValueError:
        valid = False
    if not valid:
        raise Refused("请填写比赛日期，例如 2026-10-24。")
    if fields.patch_id is None or not conn.execute(
            "SELECT 1 FROM patches WHERE id = ?", (fields.patch_id,)).fetchone():
        raise Refused("请选择版本。")
    announcement_id = fields.announcement_id if fields.kind == "recap" else None
    if announcement_id is not None and (announcement_id == item_id or not conn.execute(
            "SELECT 1 FROM tournament_items WHERE id = ? AND kind = 'announcement'",
            (announcement_id,)).fetchone()):
        raise Refused("回顾只能关联一条锦标赛预告。")
    return replace(_trimmed(fields), tournament_date=day,
                   announcement_id=announcement_id)


def _existing_item(conn: sqlite3.Connection, item_id: int) -> TournamentItem:
    row = conn.execute(f"{_TOURNAMENT_SELECT} WHERE tournament_items.id = ?",
                       (item_id,)).fetchone()
    if row is None:
        raise NotFound("找不到这条锦标赛内容。")
    return _item_from_row(row)


def tournament_item(conn: sqlite3.Connection, actor: User,
                    item_id: int) -> TournamentItem:
    """Raises NotFound if there is no such Tournament item."""
    _check_manages_pages(actor)
    return _existing_item(conn, item_id)


def tournament_items(conn: sqlite3.Connection, actor: User) -> list[TournamentItem]:
    """Every Tournament item, newest first."""
    _check_manages_pages(actor)
    return [_item_from_row(row)
            for row in conn.execute(f"{_TOURNAMENT_SELECT} {_NEWEST_FIRST}")]


def create_tournament_item(conn: sqlite3.Connection, actor: User,
                           fields: TournamentFields) -> TournamentItem:
    """A new Draft Tournament item."""
    _check_manages_pages(actor)
    fields = _checked_tournament_fields(conn, fields)
    cur = conn.execute(
        "INSERT INTO tournament_items (kind, title_zh, body_zh, title_en, body_en,"
        " tournament_date, patch_id, announcement_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (fields.kind, fields.title_zh, fields.body_zh, fields.title_en,
         fields.body_en, fields.tournament_date, fields.patch_id,
         fields.announcement_id))
    return _existing_item(conn, cur.lastrowid or 0)


def save_tournament_item(conn: sqlite3.Connection, actor: User, item_id: int,
                         fields: TournamentFields) -> TournamentItem:
    """Change a Tournament item. A Published one must stay publishable. An
    announcement made a recap is no longer one, so recaps stop linking to it."""
    current = tournament_item(conn, actor, item_id)
    fields = _checked_tournament_fields(conn, fields, item_id)
    published = current.status == "published"
    if published:
        _check_publishable(fields.title_zh, fields.body_zh, fields.title_en,
                           fields.body_en)
    cover = current.cover if fields.images.cover is None else media.checked_cover(
        conn, current.media_owner, fields.images.cover, optional=True)
    conn.execute(
        "UPDATE tournament_items SET kind = ?, title_zh = ?, body_zh = ?,"
        " title_en = ?, body_en = ?, tournament_date = ?, patch_id = ?,"
        f" announcement_id = ?, cover = ?, updated_at = {db.NOW}"
        + (f", site_changed_at = {db.NOW}" if published else "") + " WHERE id = ?",
        (fields.kind, fields.title_zh, fields.body_zh, fields.title_en,
         fields.body_en, fields.tournament_date, fields.patch_id,
         fields.announcement_id, cover, item_id))
    media.save_alts(conn, current.media_owner, fields.images)
    if published:
        _recaps_change_with(conn, current)
    if fields.kind != "announcement":
        _unlink_recaps_of(conn, current)
    return _existing_item(conn, item_id)


def _touch_item(conn: sqlite3.Connection, item: TournamentItem) -> None:
    """Mark the item as changed now, as a save does."""
    conn.execute(f"UPDATE tournament_items SET updated_at = {db.NOW}"
                 + (f", site_changed_at = {db.NOW}" if item.status == "published" else "")
                 + " WHERE id = ?", (item.id,))


def tournament_images(conn: sqlite3.Connection, actor: User,
                      item_id: int) -> list[media.Image]:
    return media.images(conn, tournament_item(conn, actor, item_id).media_owner)


def add_tournament_image(conn: sqlite3.Connection, actor: User, item_id: int,
                         upload: media.Upload) -> media.Image:
    item = tournament_item(conn, actor, item_id)
    try:
        added = media.add(conn, item.media_owner, upload)
    except media.BadImage as bad:
        raise Refused(bad.message) from None
    _touch_item(conn, item)
    return added


def remove_tournament_image(conn: sqlite3.Connection, actor: User, item_id: int,
                            image_id: int) -> None:
    """Delete one of the item's images, unless its text still uses it."""
    item = tournament_item(conn, actor, item_id)
    try:
        removed = media.remove_unused(conn, item.media_owner, image_id,
                                      item.body_zh, item.body_en)
    except media.BadImage as bad:
        raise Refused(bad.message) from None
    if not removed:
        raise NotFound("找不到这张图片，它可能已经被删除了。")
    _touch_item(conn, item)


def tournament_image_file(conn: sqlite3.Connection, actor: User, item_id: int,
                          filename: str) -> Path | None:
    return media.file(conn, tournament_item(conn, actor, item_id).media_owner, filename)


def _recaps_change_with(conn: sqlite3.Connection, item: TournamentItem) -> None:
    """When an announcement is Published, Unpublished, edited while Published
    or deleted, each Published recap linking to it changes on the site too:
    its link appears, goes, or shows the new title."""
    if item.kind == "announcement":
        conn.execute(f"UPDATE tournament_items SET site_changed_at = {db.NOW}"
                     " WHERE announcement_id = ? AND status = 'published'",
                     (item.id,))


def _unlink_recaps_of(conn: sqlite3.Connection, announcement: TournamentItem) -> None:
    """Recaps that linked to the announcement stop doing so."""
    conn.execute("UPDATE tournament_items SET announcement_id = NULL"
                 " WHERE announcement_id = ?", (announcement.id,))


def publish_tournament_item(conn: sqlite3.Connection, actor: User,
                            item_id: int) -> TournamentItem:
    item = tournament_item(conn, actor, item_id)
    _publish(conn, "tournament_items", item, "锦标赛内容")
    _recaps_change_with(conn, item)
    return _existing_item(conn, item_id)


def unpublish_tournament_item(conn: sqlite3.Connection, actor: User,
                              item_id: int) -> TournamentItem:
    item = tournament_item(conn, actor, item_id)
    _unpublish(conn, "tournament_items", item, "锦标赛内容")
    _recaps_change_with(conn, item)
    return _existing_item(conn, item_id)


def delete_tournament_item(conn: sqlite3.Connection, actor: User, item_id: int) -> None:
    """Delete a Tournament item for good, with its images; recaps that linked
    to it stay, with no link."""
    item = tournament_item(conn, actor, item_id)
    media.remove_all(conn, item.media_owner)
    if item.status == "published":
        _recaps_change_with(conn, item)
    _unlink_recaps_of(conn, item)
    _record_removal(conn, "tournament_item", "tournament_items", item)
    conn.execute("DELETE FROM tournament_items WHERE id = ?", (item_id,))


def published_tournament_items(conn: sqlite3.Connection) -> list[TournamentItem]:
    """Every Published Tournament item, newest first: all the Site build may
    read."""
    rows = conn.execute(f"{_TOURNAMENT_SELECT} WHERE status = 'published' {_NEWEST_FIRST}")
    return [_item_from_row(row) for row in rows]
