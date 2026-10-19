"""Comments (评论): what Readers said about a Published Guide.

There is no public comment form. Readers comment elsewhere, and an Admin adds
a Comment in the Moderation queue as Pending, then Approves or Rejects it
there. A Comment is never edited. Only Approved Comments reach the site, at
the next Site build, under their Guide's page.

Each Comment has a Comment language, Chinese or English, which the Admin
picks when adding it (Chinese unless they choose otherwise); it shows only on
its Guide's page in that language. Nothing guesses it from the text: Chinese
commenters often write with no Chinese characters at all (666, yyds, GG).
A Comment picked as English that does contain Chinese characters only gets a
warning, never a different language. An English Comment needs a Guide with
English text, since only those have an English page.

Every function takes the acting user and refuses anyone who can't
moderate_comments, whatever the route in front of it checked. Anything the
console should refuse raises `Refused` with a message to show.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from app import db, guides
from app.accounts import User


class Refused(Exception):
    """A Comment change the console refuses, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotAllowed(Refused):
    """The acting user's role does not allow this change."""


class NotFound(Refused):
    """No such Comment, or no such Published Guide to add one to."""


STATUS_LABELS = {"pending": "待处理", "approved": "已通过", "rejected": "已拒绝"}
LANGUAGES = {"zh": "中文", "en": "英文"}  # the first is the default

# CJK Unified Ideographs and Extension A, as tried in the P2 prototype
# (branch prototype-comment-language, commit c335771).
_CHINESE = re.compile("[\u3400-\u4dbf\u4e00-\u9fff]")

MAX_READER_NAME_LENGTH = 30
MAX_BODY_LENGTH = 2000


@dataclass(frozen=True)
class Comment:
    id: int
    guide_id: int
    guide_title_zh: str
    reader_name: str
    body: str
    lang: str
    status: str
    created_at: str
    decided_at: str | None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def language_label(self) -> str:
        return LANGUAGES[self.lang]

    @property
    def language_warning(self) -> str | None:
        """Why the Admin may want to check the Comment language they picked."""
        if self.lang == "en" and _CHINESE.search(self.body):
            return ("这条评论选了英文，但内容里有汉字。它只会出现在攻略的英文页面上；"
                    "评论添加后不能修改，如果选错了，请拒绝后重新添加。")
        return None


# Like its Guide, a Comment on a Guide in the Trash does not exist for anyone
# until the Guide is restored.
_SELECT = """
SELECT comments.*, guides.title_zh AS guide_title_zh
FROM comments JOIN guides ON guides.id = comments.guide_id
WHERE guides.trashed_at IS NULL
"""


def _comment_from_row(row: sqlite3.Row) -> Comment:
    return Comment(**{name: row[name] for name in Comment.__dataclass_fields__})


def _check_moderates(actor: User) -> None:
    if not actor.can("moderate_comments"):
        raise NotAllowed("只有管理员可以管理评论。")


def guide_choices(conn: sqlite3.Connection, actor: User) -> list[guides.Guide]:
    """The Guides a Comment can be added to: every Published one."""
    _check_moderates(actor)
    return guides.published(conn)


def add(conn: sqlite3.Connection, actor: User, *, guide_id: int | None,
        reader_name: str, body: str, lang: str) -> Comment:
    """Add a Reader's Comment in Comment language `lang` to a Published Guide,
    Pending. Raises Refused if it lacks a name or text, the language isn't
    zh or en, the Guide isn't Published, or the Comment is English and the
    Guide has no English text."""
    _check_moderates(actor)
    reader_name, body = reader_name.strip(), body.strip()
    if not reader_name:
        raise Refused("请填写读者的名字。")
    if len(reader_name) > MAX_READER_NAME_LENGTH:
        raise Refused(f"读者的名字最多 {MAX_READER_NAME_LENGTH} 个字符。")
    if not body:
        raise Refused("请填写评论内容。")
    if len(body) > MAX_BODY_LENGTH:
        raise Refused(f"评论最多 {MAX_BODY_LENGTH} 个字符。")
    if lang not in LANGUAGES:
        raise Refused("评论语言只能是中文或英文。")
    guide = guides.guide(conn, actor, guide_id) if guide_id is not None else None
    if guide is None or guide.status != "published":
        raise NotFound("找不到这篇已发布的攻略，评论只能加在已发布的攻略下面。")
    if not guide.has_text_in(lang):
        raise Refused("这篇攻略没有英文版，英文评论无处显示。"
                      "请改选中文，或等攻略有了英文版再添加。")
    cur = conn.execute("INSERT INTO comments (guide_id, reader_name, body, lang)"
                       " VALUES (?, ?, ?, ?)", (guide_id, reader_name, body, lang))
    return _existing(conn, cur.lastrowid or 0)


def _existing(conn: sqlite3.Connection, comment_id: int) -> Comment:
    row = conn.execute(f"{_SELECT} AND comments.id = ?", (comment_id,)).fetchone()
    if row is None:
        raise NotFound("找不到这条评论。")
    return _comment_from_row(row)


def pending(conn: sqlite3.Connection, actor: User) -> list[Comment]:
    """The Moderation queue: every Pending Comment, oldest first."""
    _check_moderates(actor)
    rows = conn.execute(f"{_SELECT} AND comments.status = 'pending'"
                        " ORDER BY comments.created_at, comments.id")
    return [_comment_from_row(row) for row in rows]


def _decide(conn: sqlite3.Connection, actor: User, comment_id: int,
            status: str) -> Comment:
    _check_moderates(actor)
    if _existing(conn, comment_id).status != "pending":
        raise Refused("这条评论已经处理过了。评论通过或拒绝后不能再改。")
    conn.execute(f"UPDATE comments SET status = ?, decided_at = {db.NOW} WHERE id = ?",
                 (status, comment_id))
    return _existing(conn, comment_id)


def approve(conn: sqlite3.Connection, actor: User, comment_id: int) -> Comment:
    """Approve a Pending Comment: it appears under its Guide after the next
    Site build."""
    return _decide(conn, actor, comment_id, "approved")


def reject(conn: sqlite3.Connection, actor: User, comment_id: int) -> Comment:
    """Reject a Pending Comment: it never reaches the site."""
    return _decide(conn, actor, comment_id, "rejected")


def approved(conn: sqlite3.Connection) -> dict[tuple[int, str], list[Comment]]:
    """Every Approved Comment, by (Guide id, Comment language), oldest first:
    all the Site build may read. It acts for no one, so it needs no user."""
    rows = conn.execute(f"{_SELECT} AND comments.status = 'approved'"
                        " ORDER BY comments.created_at, comments.id")
    found: dict[tuple[int, str], list[Comment]] = {}
    for row in rows:
        comment = _comment_from_row(row)
        found.setdefault((comment.guide_id, comment.lang), []).append(comment)
    return found


def changes_since(conn: sqlite3.Connection, since: str) -> int:
    """How many Comments were Approved or Rejected after `since`. A Rejected
    one changes nothing on the site, but still counts, as does one whose
    Guide has since gone to the Trash: it may count one the site never had,
    but never misses one."""
    return conn.execute("SELECT COUNT(*) FROM comments WHERE decided_at > ?",
                        (since,)).fetchone()[0]
