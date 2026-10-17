"""Console plumbing shared by every route: templates, the signed session
cookie, CSRF tokens, flash messages, and the signed-in guard.

The session cookie (Starlette's SessionMiddleware, signed with itsdangerous
using CMS_SECRET_KEY) holds only three things: the session id, the CSRF token,
and pending flash messages. Who is signed in is decided by the `sessions`
table, never by the cookie alone.
"""
from __future__ import annotations

import secrets

from fastapi import Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import accounts, db, settings

SESSION_COOKIE = "cms_session"
SESSION_MAX_AGE = 12 * 60 * 60  # seconds; sign in again after half a day

templates = Jinja2Templates(directory=str(settings.TEMPLATES))


def csrf_token(request: Request) -> str:
    """The token every console form carries as a hidden `csrf_token` field."""
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class CsrfRejected(Exception):
    """A state-changing request whose form lacks this session's token."""


async def verify_csrf(request: Request) -> None:
    """App-wide dependency: every POST (or other unsafe method) must carry the
    session's CSRF token in its form, or it is refused before the route runs."""
    if request.method in SAFE_METHODS:
        return
    expected = request.session.get("csrf")
    sent = (await request.form()).get("csrf_token")
    if not expected or not isinstance(sent, str) or not secrets.compare_digest(sent, expected):
        raise CsrfRejected


async def csrf_rejected_handler(request: Request, exc: Exception) -> PlainTextResponse:
    return PlainTextResponse("请求已过期或来源不明，请返回刷新页面后重试。",
                             status_code=403)


def flash(request: Request, message: str, kind: str = "success") -> None:
    """Queue a message for the next page shown. kind: success | error."""
    request.session.setdefault("flash", []).append([kind, message])


def pop_flashes(request: Request) -> list[list[str]]:
    return request.session.pop("flash", [])


def console_root(request: Request) -> str:
    """The relative path from this page back to the console root ("" at
    /login, "../" at /admin/guides, "../../../" at /admin/guides/5/edit).
    Templates put it in front of every console link, so no link is
    root-absolute and none depends on which route rendered the page. A
    mount prefix (root_path) is part of the console root, so it is not
    climbed out of."""
    path = request.url.path.removeprefix(request.scope.get("root_path", ""))
    return "../" * (path.count("/") - 1)


templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["pop_flashes"] = pop_flashes
templates.env.globals["console_root"] = console_root


def start_session(request: Request, session_id: str) -> None:
    """Replace the cookie's contents, so nothing from before login survives
    (the CSRF token is reissued on the next page)."""
    request.session.clear()
    request.session["sid"] = session_id


class LoginRequired(Exception):
    """Raised when nobody is signed in; answered with a redirect to /login."""


class SetupRequired(Exception):
    """Raised when the user still has first-login setup to do; answered with a
    redirect to /admin/setup."""


def signed_in_user_mid_setup(request: Request) -> accounts.User:
    """Dependency for the setup page only: the signed-in user, whether or not
    they have finished first-login setup."""
    with db.connect() as conn:
        user = accounts.user_for_session(conn, request.session.get("sid"))
    if user is None:
        raise LoginRequired
    return user


def signed_in_user(request: Request) -> accounts.User:
    """Dependency for every other console page: the signed-in user, who has
    finished first-login setup. Anyone else is redirected."""
    user = signed_in_user_mid_setup(request)
    if user.needs_setup:
        raise SetupRequired
    return user


class AdminRequired(Exception):
    """Raised when an Editor reaches an Admin-only page; answered with 403."""


def admin_user(request: Request) -> accounts.User:
    """Dependency for Admin-only pages: the signed-in Admin. Editors are
    refused, whether they followed a link or typed the URL."""
    user = signed_in_user(request)
    if not user.can("manage_game"):
        raise AdminRequired
    return user


def home_for(user: accounts.User) -> str:
    """Where a signed-in user belongs: setup first, then the dashboard."""
    return "/admin/setup" if user.needs_setup else "/admin/dashboard"


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


async def login_required_handler(request: Request, exc: Exception) -> RedirectResponse:
    return redirect("/login")


async def admin_required_handler(request: Request, exc: Exception) -> PlainTextResponse:
    return PlainTextResponse("只有管理员可以使用此页面。", status_code=403)


async def setup_required_handler(request: Request, exc: Exception) -> RedirectResponse:
    return redirect("/admin/setup")
