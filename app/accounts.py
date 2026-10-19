"""Accounts: users, password hashing, login and logout, and sessions.

Passwords are only ever stored as argon2 hashes and never logged. A session is
a random id kept in the `sessions` table; the browser holds it inside a signed
cookie (see app/web.py), so logging out deletes the row and ends the session
even if someone kept a copy of the cookie.

Anything the console should refuse raises `Refused` with a message to show.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app import db

_hasher = PasswordHasher()
# Checked against when the email is unknown, so that a wrong email takes as
# long to refuse as a wrong password and timing doesn't reveal which exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

BAD_CREDENTIALS = "邮箱或密码错误。"
DISPLAY_NAME_TAKEN = "该昵称已被使用，请换一个。"


class Refused(Exception):
    """An account action the console refuses, with the reason to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotAllowed(Refused):
    """The acting user's role does not allow this action."""


class AccountDeactivated(Refused):
    """The password was right, but the account is Deactivated."""

    def __init__(self) -> None:
        super().__init__("账号已停用，无法登录。如有疑问，请联系管理员。")


# A role is a bundle of capabilities. Code asks `user.can(...)`, never which
# role someone has, so a rule can move between roles without touching callers.
CAPABILITIES: dict[str, frozenset[str]] = {
    "admin": frozenset({
        "publish_guides",      # Publish Submitted Guides, and their own Drafts;
                               # Return and Unpublish Guides
        "manage_all_guides",   # see and edit everyone's Guides, any Hero
        "edit_guide_slugs",
        "manage_trash",        # see the Trash, restore from it, delete for good
        "manage_game",         # Heroes and Patches
        "manage_pages",        # Pages and Tournament items
        "build_site",          # 更新网站: the Site build and deploy
        "manage_users",        # the Users page and everything on it
        "moderate_comments",   # the Moderation queue: add, Accept, Reject
    }),
    "editor": frozenset(),
}

# Shown on every console page to a banned Editor, and as the reason Submit and
# opening a Revision are refused.
SUBMISSION_BANNED = ("你的账号已被禁止投稿：可以继续编辑草稿，但不能提交审核，"
                     "也不能修订已发布的攻略。如有疑问，请联系管理员。")

ROLE_LABELS = {"admin": "管理员", "editor": "编辑"}
STATE_LABELS = {"active": "正常", "submission_ban": "禁止投稿",
                "deactivated": "已停用"}


@dataclass(frozen=True)
class User:
    id: int
    email: str
    role: str
    display_name: str | None
    state: str
    needs_setup: bool
    last_login_at: str | None = None

    def can(self, capability: str) -> bool:
        return capability in CAPABILITIES[self.role]


def _user_from_row(row: sqlite3.Row) -> User:
    return User(id=row["id"], email=row["email"], role=row["role"],
                display_name=row["display_name"], state=row["state"],
                needs_setup=bool(row["needs_setup"]),
                last_login_at=row["last_login_at"])


def _matches(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def create_user(conn: sqlite3.Connection, *, email: str, password: str,
                role: str, display_name: str | None = None,
                needs_setup: bool = False, state: str = "active") -> User:
    """Raises Refused if the email or Display name already belongs to someone."""
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, role, display_name,"
            " needs_setup, state) VALUES (?, ?, ?, ?, ?, ?)",
            (_normalise_email(email), _hasher.hash(password), role, display_name,
             int(needs_setup), state),
        )
    except sqlite3.IntegrityError as error:
        if "users.email" in str(error):
            raise Refused("该邮箱已有账号。") from None
        if "users.display_name" in str(error):
            raise Refused(DISPLAY_NAME_TAKEN) from None
        raise
    row = conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _user_from_row(row)


def user_with_email(conn: sqlite3.Connection, email: str) -> User | None:
    row = conn.execute("SELECT * FROM users WHERE email = ?",
                       (_normalise_email(email),)).fetchone()
    return _user_from_row(row) if row else None


def log_in(conn: sqlite3.Connection, email: str, password: str) -> tuple[str, User]:
    """Check the credentials and start a session.
    Returns the session id and the signed-in user."""
    row = conn.execute("SELECT * FROM users WHERE email = ?",
                       (_normalise_email(email),)).fetchone()
    # Hash-check first, even for an unknown email, so both take the same time.
    password_ok = _matches(row["password_hash"] if row else _DUMMY_HASH, password)
    if row is None or not password_ok:
        raise Refused(BAD_CREDENTIALS)
    # Only told after the right password, so the state reveals nothing either.
    if row["state"] == "deactivated":
        raise AccountDeactivated
    session_id = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions (id, user_id) VALUES (?, ?)",
                 (session_id, row["id"]))
    conn.execute(f"UPDATE users SET last_login_at = {db.NOW} WHERE id = ?",
                 (row["id"],))
    return session_id, _user_from_row(row)


def log_out(conn: sqlite3.Connection, session_id: str | None) -> None:
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


MIN_PASSWORD_LENGTH = 8
MAX_DISPLAY_NAME_LENGTH = 30


def complete_setup(conn: sqlite3.Connection, user: User, *, display_name: str,
                   password: str, password_confirm: str) -> None:
    """First-login setup: the user replaces their temporary password and
    chooses their Display name. Raises Refused if either is unacceptable."""
    display_name = display_name.strip()
    if not display_name:
        raise Refused("请填写昵称。")
    if len(display_name) > MAX_DISPLAY_NAME_LENGTH:
        raise Refused(f"昵称最多 {MAX_DISPLAY_NAME_LENGTH} 个字符。")
    if display_name.lower() == user.email.lower():
        raise Refused("昵称不能是登录邮箱，昵称会公开显示。")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise Refused(f"密码至少需要 {MIN_PASSWORD_LENGTH} 个字符。")
    if password != password_confirm:
        raise Refused("两次输入的密码不一致。")
    current = conn.execute("SELECT password_hash FROM users WHERE id = ?",
                           (user.id,)).fetchone()
    if _matches(current["password_hash"], password):
        raise Refused("新密码不能与临时密码相同。")
    try:
        conn.execute(
            "UPDATE users SET display_name = ?, password_hash = ?, needs_setup = 0"
            " WHERE id = ?", (display_name, _hasher.hash(password), user.id))
    except sqlite3.IntegrityError:
        raise Refused(DISPLAY_NAME_TAKEN) from None


def user_for_session(conn: sqlite3.Connection, session_id: str | None) -> User | None:
    """The user a session belongs to, or None if the session is gone or the
    account has been Deactivated since it was opened."""
    if not session_id:
        return None
    row = conn.execute(
        "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id"
        " WHERE sessions.id = ? AND users.state != 'deactivated'",
        (session_id,)).fetchone()
    return _user_from_row(row) if row else None


# User management (the Users page). Only users who can manage_users may call
# these; each refuses anyone else, whatever the route in front of it checked.

def _check_manages_users(actor: User) -> None:
    if not actor.can("manage_users"):
        raise NotAllowed("只有管理员可以管理用户。")


def users(conn: sqlite3.Connection, actor: User) -> list[User]:
    """Every account, Admins first, then by when it was created."""
    _check_manages_users(actor)
    rows = conn.execute("SELECT * FROM users ORDER BY role = 'editor', id").fetchall()
    return [_user_from_row(row) for row in rows]


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _check_temporary_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise Refused(f"临时密码至少需要 {MIN_PASSWORD_LENGTH} 个字符。")


def create_account(conn: sqlite3.Connection, actor: User, *, email: str,
                   role: str, temporary_password: str) -> User:
    """A new account with a temporary password. Its owner chooses their own
    password and Display name at first-login setup."""
    _check_manages_users(actor)
    if not _EMAIL.fullmatch(email.strip()):
        raise Refused("请填写正确的邮箱地址。")
    if role not in CAPABILITIES:
        raise Refused("请选择角色：管理员或编辑。")
    _check_temporary_password(temporary_password)
    return create_user(conn, email=email, password=temporary_password, role=role,
                       needs_setup=True)


# The site must always keep an active Admin. Part of the UPDATE that would
# remove one, so the check and the change happen at once: two Admins removing
# each other at the same moment can't both succeed.
_KEEPS_AN_ADMIN = """(users.role != 'admin' OR EXISTS (
    SELECT 1 FROM users AS other WHERE other.id != users.id
    AND other.role = 'admin' AND other.state != 'deactivated'))"""
LAST_ADMIN = "至少要保留一位正常状态的管理员，不能停用或降级最后一位管理员。"


class AccountNotFound(Refused):
    def __init__(self) -> None:
        super().__init__("找不到这个账号。")


def account(conn: sqlite3.Connection, actor: User, user_id: int) -> User:
    """The account with `user_id`. Raises AccountNotFound if there is none."""
    _check_manages_users(actor)
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise AccountNotFound
    return _user_from_row(row)


# Each change below repeats its precondition in its UPDATE, so a change
# another Admin made in between (say, a Deactivation) is never overwritten.
CHANGED_MEANWHILE = "这个账号刚被另一位管理员改过，请看看现在的状态再试。"


def _update(conn: sqlite3.Connection, sql: str, params: tuple[object, ...],
            refusal: str) -> None:
    if conn.execute(sql, params).rowcount == 0:
        raise Refused(refusal)


def change_role(conn: sqlite3.Connection, actor: User, user_id: int, role: str) -> None:
    """Make the account an Admin or an Editor. It takes effect on the user's
    next request, since every request reads the role afresh."""
    target = account(conn, actor, user_id)
    if role not in CAPABILITIES:
        raise Refused("请选择角色：管理员或编辑。")
    if target.id == actor.id and role != target.role:
        raise Refused("不能修改自己的角色，请让另一位管理员来改。")
    if role == "admin":
        if target.state == "submission_ban":
            raise Refused("这个账号被禁止投稿，请先解除禁止投稿，再改为管理员。")
        _update(conn, "UPDATE users SET role = 'admin' WHERE id = ?"
                " AND state != 'submission_ban'", (target.id,), CHANGED_MEANWHILE)
    else:
        _update(conn, f"UPDATE users SET role = ? WHERE id = ? AND {_KEEPS_AN_ADMIN}",
                (role, target.id), LAST_ADMIN)


def ban_submissions(conn: sqlite3.Connection, actor: User, user_id: int) -> None:
    """Submission ban (禁止投稿): the Editor can still log in and work on
    Drafts, but can't Submit or open a Revision. Their Published Guides stay."""
    target = account(conn, actor, user_id)
    if target.role != "editor":
        raise Refused("禁止投稿只适用于编辑；管理员发布攻略不需要投稿。")
    if target.state != "active":
        raise Refused("这个账号已经被禁止投稿了。" if target.state == "submission_ban"
                      else "这个账号已停用，请先重新启用。")
    _update(conn, "UPDATE users SET state = 'submission_ban' WHERE id = ?"
            " AND role = 'editor' AND state = 'active'", (target.id,), CHANGED_MEANWHILE)


def lift_submission_ban(conn: sqlite3.Connection, actor: User, user_id: int) -> None:
    target = account(conn, actor, user_id)
    if target.state != "submission_ban":
        raise Refused("这个账号没有被禁止投稿。")
    _update(conn, "UPDATE users SET state = 'active' WHERE id = ?"
            " AND state = 'submission_ban'", (target.id,), CHANGED_MEANWHILE)


def check_deactivatable(actor: User, target: User) -> None:
    """Refuse up front, before asking to confirm, what deactivate() would."""
    if target.id == actor.id:
        raise Refused("不能停用自己的账号，请让另一位管理员来停用。")
    if target.state == "deactivated":
        raise Refused("这个账号已经停用了。")


def deactivate(conn: sqlite3.Connection, actor: User, user_id: int) -> None:
    """The person can no longer log in, and their open sessions end at once.
    Their Published Guides stay on the site."""
    target = account(conn, actor, user_id)
    check_deactivatable(actor, target)
    _update(conn, "UPDATE users SET state = 'deactivated'"
            f" WHERE id = ? AND {_KEEPS_AN_ADMIN}", (target.id,), LAST_ADMIN)
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (target.id,))


def reactivate(conn: sqlite3.Connection, actor: User, user_id: int) -> None:
    """The person can log in again, in the normal state (a Submission ban
    from before the deactivation is not kept)."""
    target = account(conn, actor, user_id)
    if target.state != "deactivated":
        raise Refused("这个账号没有停用。")
    _update(conn, "UPDATE users SET state = 'active' WHERE id = ?"
            " AND state = 'deactivated'", (target.id,), CHANGED_MEANWHILE)


def reset_password(conn: sqlite3.Connection, actor: User, user_id: int,
                   temporary_password: str) -> None:
    """Replace the password with a temporary one. The old password stops
    working, the user's open sessions end, and they must complete first-login
    setup again."""
    target = account(conn, actor, user_id)
    if target.id == actor.id:
        raise Refused("不能重置自己的密码。")
    _check_temporary_password(temporary_password)
    conn.execute("UPDATE users SET password_hash = ?, needs_setup = 1 WHERE id = ?",
                 (_hasher.hash(temporary_password), target.id))
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (target.id,))
