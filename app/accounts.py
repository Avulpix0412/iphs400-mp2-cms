"""Accounts: users, password hashing, login and logout, and sessions.

Passwords are only ever stored as argon2 hashes and never logged. A session is
a random id kept in the `sessions` table; the browser holds it inside a signed
cookie (see app/web.py), so logging out deletes the row and ends the session
even if someone kept a copy of the cookie.

Anything the console should refuse raises `Refused` with a message to show.
"""
from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

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


class AccountDeactivated(Refused):
    """The password was right, but the account is Deactivated."""

    def __init__(self) -> None:
        super().__init__("账号已停用，无法登录。如有疑问，请联系管理员。")


# A role is a bundle of capabilities. Code asks `user.can(...)`, never which
# role someone has, so a rule can move between roles without touching callers.
CAPABILITIES: dict[str, frozenset[str]] = {
    "admin": frozenset({
        "publish_guides",      # Publish Submitted Guides, and their own Drafts
        "manage_all_guides",   # see and edit everyone's Guides, any Hero
        "edit_guide_slugs",
        "manage_game",         # Heroes and Patches
    }),
    "editor": frozenset(),
}


@dataclass(frozen=True)
class User:
    id: int
    email: str
    role: str
    display_name: str | None
    state: str
    needs_setup: bool

    def can(self, capability: str) -> bool:
        return capability in CAPABILITIES[self.role]


def _user_from_row(row: sqlite3.Row) -> User:
    return User(id=row["id"], email=row["email"], role=row["role"],
                display_name=row["display_name"], state=row["state"],
                needs_setup=bool(row["needs_setup"]))


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


def set_state(conn: sqlite3.Connection, email: str, state: str) -> None:
    """Put an account into a state: active, submission_ban or deactivated.
    A Deactivated account's open sessions stop working at once."""
    conn.execute("UPDATE users SET state = ? WHERE email = ?",
                 (state, _normalise_email(email)))


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
