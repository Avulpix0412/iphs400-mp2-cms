"""The Guide workflow: every change to a Guide, and who may make it.

A Guide moves Draft -> Submitted -> Published. An Admin's Return (from
Submitted) or Unpublish (from Published) sends it back to its Author as a
Draft, recorded as a review round with Review notes. Routes never touch a
Guide's row themselves: they call a function here with the acting user, and it
either makes the change or raises `Refused` with the reason to show.

An Editor changes their Published Guide through a Revision: a pending copy of
its texts, Hero and Patch that goes Draft -> Submitted on its own while the
Guide stays on the site unchanged. Publishing the Revision copies it over the
Guide; Returning it leaves the Guide alone. Admins edit Published Guides
directly.

A Guide's slug is `<hero-slug>-<id>`, given when it is created. It never
changes on its own (not with the title, not with the Hero); only an Admin can
edit it.

Editors only ever see their own Guides. To them, anyone else's Guide does not
exist, so it is refused as not found rather than forbidden.

Deleting a Guide moves it to the Trash, which only Admins see. Outside the
Trash, a Guide in it does not exist for anyone, the Site build included.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, fields as fields_of
from typing import ClassVar
from itertools import groupby

from app import db, game
from app.accounts import SUBMISSION_BANNED, User
from app.rendering import highlight, render_markdown


class Refused(Exception):
    """A Guide change the console refuses, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotAllowed(Refused):
    """The acting user's role does not allow this change."""


class GuideNotFound(Refused):
    """No such Guide (or Revision), or none this user may see."""

    def __init__(self, message: str = "找不到这篇攻略。") -> None:
        super().__init__(message)


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
    trashed_at: str | None
    returned: bool  # a Draft that a Return or Unpublish sent back to its Author
    revision_status: str | None  # the open Revision's status, if there is one
    is_revision: ClassVar[bool] = False

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def console_path(self) -> str:
        """Where the Guide's console pages live, from the console root."""
        return f"admin/guides/{self.id}"

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
    def of(cls, guide: Guide | Revision) -> GuideFields:
        return cls(title_zh=guide.title_zh, body_zh=guide.body_zh,
                   title_en=guide.title_en, body_en=guide.body_en,
                   hero_id=guide.hero_id, patch_id=guide.patch_id, slug=guide.slug)


_SELECT = """
SELECT guides.*, heroes.name_zh AS hero_name_zh, heroes.name_en AS hero_name_en,
       heroes.slug AS hero_slug, patches.name AS patch_name, users.display_name AS author_name,
       (guides.status = 'draft' AND EXISTS (SELECT 1 FROM review_rounds
         WHERE review_rounds.guide_id = guides.id
           AND review_rounds.revision_id IS NULL)) AS returned,
       (SELECT status FROM revisions WHERE revisions.guide_id = guides.id)
         AS revision_status
FROM guides
JOIN game_terms AS heroes ON heroes.id = guides.hero_id
JOIN patches ON patches.id = guides.patch_id
JOIN users ON users.id = guides.author_id
"""


_NOT_TRASHED = "guides.trashed_at IS NULL"


def _guide_from_row(row: sqlite3.Row) -> Guide:
    fields = {field.name: row[field.name] for field in fields_of(Guide)}
    fields["returned"] = bool(fields["returned"])  # SQLite gives 0 or 1
    return Guide(**fields)


def _visible_to(actor: User) -> tuple[str, tuple[int, ...]]:
    """The WHERE clause limiting Guides to those `actor` may see (none in
    the Trash)."""
    if actor.can("manage_all_guides"):
        return _NOT_TRASHED, ()
    return f"guides.author_id = ? AND {_NOT_TRASHED}", (actor.id,)


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
    rows = conn.execute(f"{_SELECT} WHERE guides.status = 'published' AND {_NOT_TRASHED}"
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


def patch_choices(conn: sqlite3.Connection, guide: Guide | Revision | None = None
                  ) -> list[game.Patch]:
    """The Patches a Guide may be written for: the Current Patch and the two
    before it, plus the Guide's own Patch if that is older still."""
    patches = game.patches(conn)
    choices = patches[:3]
    if guide and all(patch.id != guide.patch_id for patch in choices):
        choices += [patch for patch in patches if patch.id == guide.patch_id]
    return choices


def _checked_hero_and_patch(conn: sqlite3.Connection, fields: GuideFields,
                            guide: Guide | Revision | None = None
                            ) -> tuple[game.Hero, int]:
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


def can_edit(actor: User, guide: Guide) -> bool:
    """Whether `actor` edits `guide` itself. Admins edit any Guide they see;
    an Editor's Published Guide changes only through a Revision."""
    return guide.status != "published" or actor.can("manage_all_guides")


def save(conn: sqlite3.Connection, actor: User, guide_id: int,
         fields: GuideFields) -> Guide:
    """Save changes to a Guide without changing its status."""
    current = _editable(conn, actor, guide_id)
    if not can_edit(actor, current):
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


def _check_text(fields: GuideFields | Guide | Revision) -> None:
    """The text a Guide needs before it can be reviewed or Published."""
    if not fields.title_zh.strip() or not fields.body_zh.strip():
        raise Refused("提交审核前请填写中文标题和正文。")
    if bool(fields.title_en.strip()) != bool(fields.body_en.strip()):
        raise Refused("英文版需要同时填写标题和正文；不写英文版就都留空。")


def _check_not_banned(actor: User) -> None:
    if actor.state == "submission_ban":
        raise NotAllowed(SUBMISSION_BANNED)


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
    _check_not_banned(actor)
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


@dataclass(frozen=True)
class ReviewNote:
    """A passage quoted from a Guide's text, with an Admin's advice on it."""
    quote: str
    advice: str


ROUND_LABELS = {"return": "退回", "unpublish": "撤下"}


@dataclass(frozen=True)
class ReviewRound:
    """One Return or Unpublish (of a Guide) or Return (of a Revision), with
    the Review notes the Admin gave."""
    kind: str
    of_revision: bool
    admin_name: str
    created_at: str
    notes: tuple[ReviewNote, ...]

    @property
    def label(self) -> str:
        return "退回修订" if self.of_revision else ROUND_LABELS[self.kind]


def review_rounds(conn: sqlite3.Connection, actor: User,
                  guide_id: int) -> list[ReviewRound]:
    """Every Return and Unpublish of a Guide `actor` may see, and the Returns
    of its Revisions that are no longer open, newest first."""
    _editable(conn, actor, guide_id)
    return _rounds(conn, "guide_id = ? AND (revision_id IS NULL"
                   " OR revision_id NOT IN (SELECT id FROM revisions))", (guide_id,))


def revision_rounds(conn: sqlite3.Connection, actor: User,
                    guide_id: int) -> list[ReviewRound]:
    """Every Return of the Guide's open Revision, newest first."""
    _open(conn, actor, guide_id)
    return _rounds(conn, "revision_id = (SELECT id FROM revisions WHERE guide_id = ?)",
                   (guide_id,))


def _rounds(conn: sqlite3.Connection, where: str,
            params: tuple[int, ...]) -> list[ReviewRound]:
    rows = conn.execute(
        "SELECT review_rounds.id, kind, revision_id, review_rounds.created_at,"
        " users.display_name AS admin_name, quote, advice FROM review_rounds"
        " JOIN users ON users.id = review_rounds.admin_id"
        " LEFT JOIN review_notes ON review_notes.round_id = review_rounds.id"
        f" WHERE {where} ORDER BY review_rounds.id DESC, review_notes.id",
        params).fetchall()
    rounds = []
    for _, group in groupby(rows, key=lambda row: row["id"]):
        group = list(group)
        # A round with no notes (an Unpublish may have none) has one row,
        # whose note columns are NULL.
        notes = tuple(ReviewNote(row["quote"], row["advice"])
                      for row in group if row["quote"] is not None)
        rounds.append(ReviewRound(kind=group[0]["kind"],
                                  of_revision=group[0]["revision_id"] is not None,
                                  admin_name=group[0]["admin_name"],
                                  created_at=group[0]["created_at"], notes=notes))
    return rounds


def can_review(actor: User, guide: Guide) -> bool:
    """Whether to offer `actor` the review screen for `guide`: Admins Return
    (or Publish) a Submitted Guide and Unpublish a Published one."""
    return actor.can("publish_guides") and guide.status in ("submitted", "published")


def quotes_to_highlight(conn: sqlite3.Connection, actor: User,
                        item: Guide | Revision) -> tuple[list[str], list[str]]:
    """The passages quoted by the latest review round's Review notes, and
    those quoted only by earlier rounds. The preview highlights both, set
    apart, wherever they are still in the text, until the Guide is Published
    again. A Revision has rounds of its own; a Guide's leave out those of its
    past Revisions, which quoted the Revision's text."""
    if isinstance(item, Revision):
        rounds = revision_rounds(conn, actor, item.id)
    elif item.status == "published":
        return [], []
    else:
        rounds = [round for round in review_rounds(conn, actor, item.id)
                  if not round.of_revision]
    if not rounds:
        return [], []
    latest = list(dict.fromkeys(note.quote for note in rounds[0].notes))
    earlier = [quote for quote in dict.fromkeys(
        note.quote for round in rounds[1:] for note in round.notes)
        if quote not in latest]
    return latest, earlier


def _checked_notes(conn: sqlite3.Connection, guide: Guide | Revision,
                   notes: list[ReviewNote]) -> list[ReviewNote]:
    """The notes, trimmed. Each quotes a passage of the Guide's text as the
    preview shows it, so the Author will see it highlighted there."""
    notes = [ReviewNote(note.quote.strip(), note.advice.strip()) for note in notes]
    if any(not note.quote or not note.advice for note in notes):
        raise Refused("每条审核意见都要有引用的段落和修改建议。")
    quotes = [note.quote for note in notes]
    glossary = game.glossary(conn)
    found = (highlight(render_markdown(guide.body_zh, "zh", glossary).html, quotes)[1]
             | highlight(render_markdown(guide.body_en, "en", glossary).html, quotes)[1])
    for quote in quotes:
        if quote not in found:
            raise Refused(f"在攻略正文中找不到引用的段落“{quote}”。"
                          "请从上面的正文中复制原文。")
    return notes


def _send_back(conn: sqlite3.Connection, actor: User, current: Guide, kind: str,
               notes: list[ReviewNote]) -> Guide:
    """Turn the Guide back into a Draft for its Author, recording the round.
    The status it was read in is checked again as it changes, so if another
    Admin got there first this is refused rather than undoing their step."""
    changed = conn.execute(
        f"UPDATE guides SET status = 'draft', updated_at = {db.NOW}"
        " WHERE id = ? AND status = ?", (current.id, current.status)).rowcount
    if not changed:
        raise Refused("这篇攻略刚被别人改过，请刷新页面后再试。")
    _record_round(conn, actor, current.id, kind, notes)
    return _editable(conn, actor, current.id)


def _record_round(conn: sqlite3.Connection, actor: User, guide_id: int, kind: str,
                  notes: list[ReviewNote], revision_id: int | None = None) -> None:
    cur = conn.execute("INSERT INTO review_rounds (guide_id, revision_id, admin_id,"
                       " kind) VALUES (?, ?, ?, ?)",
                       (guide_id, revision_id, actor.id, kind))
    conn.executemany("INSERT INTO review_notes (round_id, quote, advice)"
                     " VALUES (?, ?, ?)",
                     [(cur.lastrowid, note.quote, note.advice) for note in notes])


def return_guide(conn: sqlite3.Connection, actor: User, guide_id: int,
                 notes: list[ReviewNote]) -> Guide:
    """An Admin sends a Submitted Guide back to its Author as a Draft, with at
    least one Review note saying what to fix."""
    current = _editable(conn, actor, guide_id)
    if not actor.can("publish_guides"):
        raise NotAllowed("只有管理员可以退回攻略。")
    if current.status != "submitted":
        raise Refused("只能退回待审核的攻略。")
    notes = _checked_notes(conn, current, notes)
    if not notes:
        raise Refused("退回时请至少写一条审核意见。")
    return _send_back(conn, actor, current, "return", notes)


def unpublish(conn: sqlite3.Connection, actor: User, guide_id: int,
              notes: list[ReviewNote]) -> Guide:
    """An Admin takes a Published Guide off the site at the next Site build.
    It goes back to its Author as a Draft, with Review notes if any. An open
    Revision is kept, but back as a Draft: there is nothing for it to change
    until the Guide is Published again."""
    current = _editable(conn, actor, guide_id)
    if not actor.can("publish_guides"):
        raise NotAllowed("只有管理员可以撤下攻略。")
    if current.status != "published":
        raise Refused("只能撤下已发布的攻略。")
    unpublished = _send_back(conn, actor, current, "unpublish",
                             _checked_notes(conn, current, notes))
    conn.execute(f"UPDATE revisions SET status = 'draft', updated_at = {db.NOW}"
                 " WHERE guide_id = ? AND status = 'submitted'", (guide_id,))
    return unpublished


@dataclass(frozen=True)
class Revision:
    """A pending change to a Published Guide: its own copy of the texts, Hero
    and Patch, with its own status (Draft or Submitted). It has the Guide's
    slug and Author, and reads like a Guide wherever a page shows one."""
    guide: Guide
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
    status: str
    base_updated_at: str  # the Guide's updated_at when this was opened
    created_at: str
    updated_at: str
    returned: bool  # a Draft that an Admin Returned
    is_revision: ClassVar[bool] = True

    @property
    def guide_changed_since(self) -> bool:
        """Whether the Guide changed after this was opened (an Admin's edit,
        an Unpublish), so that Publishing this would undo that change."""
        return self.guide.updated_at != self.base_updated_at

    @property
    def id(self) -> int:
        return self.guide.id

    @property
    def slug(self) -> str:
        return self.guide.slug

    @property
    def author_id(self) -> int:
        return self.guide.author_id

    @property
    def author_name(self) -> str:
        return self.guide.author_name

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def console_path(self) -> str:
        return f"{self.guide.console_path}/revision"


_REVISION_SELECT = """
SELECT revisions.*, heroes.name_zh AS hero_name_zh, heroes.name_en AS hero_name_en,
       heroes.slug AS hero_slug, patches.name AS patch_name,
       (revisions.status = 'draft' AND EXISTS (SELECT 1 FROM review_rounds
         WHERE review_rounds.revision_id = revisions.id)) AS returned
FROM revisions
JOIN game_terms AS heroes ON heroes.id = revisions.hero_id
JOIN patches ON patches.id = revisions.patch_id
"""


def revision(conn: sqlite3.Connection, actor: User, guide_id: int) -> Revision | None:
    """The Guide's open Revision, or None if it has none or `actor` may not
    see the Guide."""
    found = guide(conn, actor, guide_id)
    if found is None:
        return None
    row = conn.execute(f"{_REVISION_SELECT} WHERE revisions.guide_id = ?",
                       (guide_id,)).fetchone()
    if row is None:
        return None
    fields = {field.name: row[field.name] for field in fields_of(Revision)
              if field.name != "guide"}
    fields["returned"] = bool(fields["returned"])
    return Revision(guide=found, **fields)


def _open(conn: sqlite3.Connection, actor: User, guide_id: int) -> Revision:
    found = revision(conn, actor, guide_id)
    if found is None:
        _editable(conn, actor, guide_id)  # not found at all, rather than no Revision
        raise GuideNotFound("这篇攻略没有打开的修订。")
    return found


def can_open_revision(actor: User, guide: Guide) -> bool:
    """Whether to offer `actor` the 修订 button on `guide`: an Editor revises
    their own Published Guide; an Admin edits it directly instead."""
    return (guide.author_id == actor.id and guide.status == "published"
            and guide.revision_status is None and not actor.can("manage_all_guides"))


def open_revision(conn: sqlite3.Connection, actor: User, guide_id: int) -> Revision:
    """The Author starts a Revision of their Published Guide, as a Draft copy
    of its texts, Hero and Patch."""
    current = _editable(conn, actor, guide_id)
    if actor.can("manage_all_guides"):
        raise Refused("管理员可以直接修改已发布的攻略，不需要修订。")
    if current.author_id != actor.id:
        raise NotAllowed("只有作者本人可以修订这篇攻略。")
    if current.status != "published":
        raise Refused("只有已发布的攻略需要修订；草稿和待审核的攻略可以直接修改。")
    _check_not_banned(actor)  # a Revision they could never Submit
    try:
        conn.execute(
            "INSERT INTO revisions (guide_id, base_updated_at, title_zh, body_zh,"
            " title_en, body_en, hero_id, patch_id) SELECT id, updated_at, title_zh,"
            " body_zh, title_en, body_en, hero_id, patch_id FROM guides WHERE id = ?",
            (guide_id,))
    except sqlite3.IntegrityError:  # the Guide already has one
        raise Refused("这篇攻略已经有一份修订了，请继续修改那一份。") from None
    return _open(conn, actor, guide_id)


def save_revision(conn: sqlite3.Connection, actor: User, guide_id: int,
                  fields: GuideFields) -> Revision:
    """Save changes to the open Revision without changing its status. The
    slug is the Guide's and stays as it is."""
    current = _open(conn, actor, guide_id)
    hero, patch_id = _checked_hero_and_patch(conn, fields, current)
    if current.status != "draft":
        _check_text(fields)
    conn.execute(
        "UPDATE revisions SET title_zh = ?, body_zh = ?, title_en = ?, body_en = ?,"
        f" hero_id = ?, patch_id = ?, updated_at = {db.NOW} WHERE guide_id = ?",
        (fields.title_zh.strip(), fields.body_zh, fields.title_en.strip(),
         fields.body_en, hero.id, patch_id, guide_id))
    return _open(conn, actor, guide_id)


def can_submit_revision(actor: User, revision: Revision) -> bool:
    return (revision.author_id == actor.id and revision.status == "draft"
            and revision.guide.status == "published")


def submit_revision(conn: sqlite3.Connection, actor: User, guide_id: int) -> Revision:
    """The Author marks their Revision finished, for an Admin to review."""
    current = _open(conn, actor, guide_id)
    if current.author_id != actor.id:
        raise NotAllowed("只有作者本人可以提交修订。")
    if current.status != "draft":
        raise Refused("这份修订已经提交审核了。")
    if current.guide.status != "published":
        raise Refused("这篇攻略已被撤下。修订只能在攻略重新发布后提交；"
                      "也可以直接修改攻略草稿。")
    _check_not_banned(actor)
    _check_text(current)
    conn.execute("UPDATE revisions SET status = 'submitted',"
                 f" updated_at = {db.NOW} WHERE guide_id = ?", (guide_id,))
    return _open(conn, actor, guide_id)


def can_discard_revision(actor: User, revision: Revision) -> bool:
    return revision.author_id == actor.id


def discard_revision(conn: sqlite3.Connection, actor: User, guide_id: int) -> None:
    """The Author throws their open Revision away, so they can open a new one
    later. The Published Guide is untouched; Returns of the Revision stay in
    its history."""
    current = _open(conn, actor, guide_id)
    if not can_discard_revision(actor, current):
        raise NotAllowed("只有作者本人可以放弃修订。")
    conn.execute("DELETE FROM revisions WHERE guide_id = ?", (guide_id,))


def can_publish_revision(actor: User, revision: Revision) -> bool:
    return actor.can("publish_guides") and revision.status == "submitted"


def publish_revision(conn: sqlite3.Connection, actor: User, guide_id: int) -> Guide:
    """An Admin approves a Revision: it replaces the Guide's texts, Hero and
    Patch (the old ones are not kept) and is gone. The slug stays, and the
    Guide's 更新于 date moves on. Readers see it at the next Site build."""
    current = _open(conn, actor, guide_id)
    if not actor.can("publish_guides"):
        raise NotAllowed("只有管理员可以发布修订。")
    if current.status != "submitted":
        raise Refused("这份修订还是草稿，要等作者提交审核后才能发布。")
    _check_text(current)
    # Checked again as it is deleted, so a Revision another Admin Returned
    # meanwhile is refused rather than Published.
    if not conn.execute("DELETE FROM revisions WHERE guide_id = ? AND status = 'submitted'",
                        (guide_id,)).rowcount:
        raise Refused("这份修订刚被别人改过，请刷新页面后再试。")
    conn.execute(
        "UPDATE guides SET title_zh = ?, body_zh = ?, title_en = ?, body_en = ?,"
        f" hero_id = ?, patch_id = ?, updated_at = {db.NOW} WHERE id = ?",
        (current.title_zh, current.body_zh, current.title_en, current.body_en,
         current.hero_id, current.patch_id, guide_id))
    return _editable(conn, actor, guide_id)


def return_revision(conn: sqlite3.Connection, actor: User, guide_id: int,
                    notes: list[ReviewNote]) -> Revision:
    """An Admin sends a Submitted Revision back to its Author as a Draft,
    with at least one Review note. The Published Guide stays as it is."""
    current = _open(conn, actor, guide_id)
    if not actor.can("publish_guides"):
        raise NotAllowed("只有管理员可以退回修订。")
    if current.status != "submitted":
        raise Refused("只能退回待审核的修订。")
    notes = _checked_notes(conn, current, notes)
    if not notes:
        raise Refused("退回时请至少写一条审核意见。")
    row = conn.execute(f"UPDATE revisions SET status = 'draft', updated_at = {db.NOW}"
                       " WHERE guide_id = ? AND status = 'submitted' RETURNING id",
                       (guide_id,)).fetchone()
    if row is None:  # another Admin got there first
        raise Refused("这份修订刚被别人改过，请刷新页面后再试。")
    _record_round(conn, actor, guide_id, "return", notes, revision_id=row["id"])
    return _open(conn, actor, guide_id)


def _revisions(conn: sqlite3.Connection, actor: User, where: str,
               params: tuple[int, ...]) -> list[Revision]:
    """The open Revisions matching `where`, of Guides `actor` may see."""
    rows = conn.execute(f"SELECT guide_id FROM revisions WHERE {where}", params)
    found = [revision(conn, actor, row["guide_id"]) for row in rows.fetchall()]
    return [item for item in found if item is not None]


def delete(conn: sqlite3.Connection, actor: User, guide_id: int) -> None:
    """Move a Guide, in whatever status and with any open Revision, to the
    Trash. Anyone who can see a Guide can delete it: an Editor their own, an
    Admin any. A Published one leaves the site at the next Site build."""
    _editable(conn, actor, guide_id)
    conn.execute(f"UPDATE guides SET trashed_at = {db.NOW} WHERE id = ?", (guide_id,))


def trashed(conn: sqlite3.Connection, actor: User) -> list[Guide]:
    """Every Guide in the Trash, most recently deleted first. Admins only."""
    if not actor.can("manage_trash"):
        raise NotAllowed("只有管理员可以查看回收站。")
    rows = conn.execute(f"{_SELECT} WHERE NOT {_NOT_TRASHED}"
                        " ORDER BY guides.trashed_at DESC, guides.id DESC").fetchall()
    return [_guide_from_row(row) for row in rows]


def in_trash(conn: sqlite3.Connection, actor: User, guide_id: int) -> Guide:
    """The Guide, if it is in the Trash. Admins only."""
    if not actor.can("manage_trash"):
        raise NotAllowed("只有管理员可以查看回收站。")
    row = conn.execute(f"{_SELECT} WHERE guides.id = ? AND NOT {_NOT_TRASHED}",
                       (guide_id,)).fetchone()
    if row is None:
        raise GuideNotFound("回收站里没有这篇攻略。")
    return _guide_from_row(row)


def restore(conn: sqlite3.Connection, actor: User, guide_id: int) -> None:
    """An Admin takes a Guide out of the Trash. Its status, texts, Review
    notes and open Revision never changed there, so it is back as it was."""
    if not actor.can("manage_trash"):
        raise NotAllowed("只有管理员可以从回收站恢复攻略。")
    if not conn.execute(f"UPDATE guides SET trashed_at = NULL, restored_at = {db.NOW}"
                        f" WHERE id = ? AND NOT {_NOT_TRASHED}", (guide_id,)).rowcount:
        raise GuideNotFound("回收站里没有这篇攻略。")


def delete_for_good(conn: sqlite3.Connection, actor: User, guide_id: int) -> None:
    """An Admin deletes a Guide in the Trash for good, with its Review notes
    and any open Revision. It cannot be restored."""
    if in_trash(conn, actor, guide_id).status == "published":
        conn.execute("INSERT INTO removed_guides (guide_id) VALUES (?)", (guide_id,))
    conn.execute(f"DELETE FROM guides WHERE id = ? AND NOT {_NOT_TRASHED}", (guide_id,))


def trash_changes_since(conn: sqlite3.Connection, since: str) -> set[int]:
    """The ids of Published Guides moved to the Trash, restored from it, or
    deleted from it for good after `since`: the next Site build drops or adds
    them. It may count one the site never had (or already lacks), such as a
    Guide deleted and restored in between, but never misses one."""
    rows = conn.execute(
        "SELECT id FROM guides WHERE status = 'published'"
        " AND (trashed_at > ? OR (trashed_at IS NULL AND restored_at > ?))"
        " UNION SELECT guide_id FROM removed_guides WHERE removed_at > ?",
        (since, since, since)).fetchall()
    return {row[0] for row in rows}


def unpublished_since(conn: sqlite3.Connection, since: str) -> set[int]:
    """The ids of Guides Unpublished after `since` and not Published again:
    the Site build reads Published Guides only, so they drop out of it."""
    rows = conn.execute(
        "SELECT DISTINCT guide_id FROM review_rounds JOIN guides"
        " ON guides.id = review_rounds.guide_id WHERE kind = 'unpublish'"
        " AND review_rounds.created_at > ? AND guides.status != 'published'",
        (since,)).fetchall()
    return {row["guide_id"] for row in rows}


def review_queue(conn: sqlite3.Connection, actor: User) -> list[Guide | Revision]:
    """Every Submitted Guide and Revision waiting for an Admin, longest
    waiting first (as far as the last change shows); nothing for anyone who
    can't review."""
    if not actor.can("publish_guides"):
        return []
    rows = conn.execute(f"{_SELECT} WHERE guides.status = 'submitted'"
                        f" AND {_NOT_TRASHED}").fetchall()
    queue = [_guide_from_row(row) for row in rows]
    queue += _revisions(conn, actor, "status = 'submitted'", ())
    return sorted(queue, key=lambda item: (item.updated_at, item.id))


def returned_to(conn: sqlite3.Connection, actor: User) -> list[Guide | Revision]:
    """`actor`'s own Guides and Revisions that an Admin sent back to them and
    that they have not Submitted again, most recently sent back first."""
    rows = conn.execute(f"{_SELECT} WHERE guides.author_id = ? AND returned"
                        f" AND {_NOT_TRASHED}", (actor.id,)).fetchall()
    returned = [_guide_from_row(row) for row in rows]
    returned += [item for item in _revisions(
        conn, actor, "status = 'draft' AND guide_id IN"
        " (SELECT id FROM guides WHERE author_id = ?)", (actor.id,)) if item.returned]
    return sorted(returned, key=lambda item: (item.updated_at, item.id), reverse=True)


def counts(conn: sqlite3.Connection, actor: User) -> dict[str, int]:
    """How many Guides `actor` may see are in each status."""
    where, params = _visible_to(actor)
    rows = conn.execute(f"SELECT status, COUNT(*) AS n FROM guides WHERE {where}"
                        " GROUP BY status", params).fetchall()
    found = {row["status"]: row["n"] for row in rows}
    return {status: found.get(status, 0) for status in STATUS_LABELS}


@dataclass(frozen=True)
class AuthorCounts:
    published: int = 0
    total: int = 0     # in any status, outside the Trash


def counts_by_author(conn: sqlite3.Connection, actor: User) -> dict[int, AuthorCounts]:
    """Each Author's Guides outside the Trash, for the Users page, keyed by
    user id; an Author with none is missing."""
    if not actor.can("manage_users"):
        raise NotAllowed("只有管理员可以查看所有人的攻略数量。")
    rows = conn.execute(
        "SELECT author_id, SUM(status = 'published') AS published,"
        f" COUNT(*) AS total FROM guides WHERE {_NOT_TRASHED} GROUP BY author_id"
    ).fetchall()
    return {row["author_id"]: AuthorCounts(row["published"], row["total"])
            for row in rows}
