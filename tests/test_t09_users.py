"""T09: Admins manage users (Seam 1: the console over HTTP; Seam 2 for the
Site build)."""
from __future__ import annotations

import importlib
import pkgutil
import re
import sqlite3
from contextlib import closing

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import create_app
from app.publish import render_site
from app.web import ADMIN_GUARDS
from conftest import DEMO_USERS, csrf_token, login
from test_t01_login import submit_setup
from test_t02_heroes_patches import submit
from test_t03_guides import (act, admin, editor, new_guide, save,  # noqa: F401
                             status_of)
from test_t05_review import published_guide
from test_t06_revisions_trash import delete, open_revision, revision_page


def user_row(c: TestClient, email: str) -> str:
    """The Users page's table row for the account with `email`."""
    page = c.get("/admin/users")
    assert page.status_code == 200
    for row in re.findall(r"<tr>(.*?)</tr>", page.text, re.DOTALL):
        if email in row:
            return row
    raise AssertionError(f"no row for {email}")


def test_the_users_page_lists_every_account_with_role_state_guide_counts_and_last_login(
        admin, editor):
    published_guide(editor, admin)
    new_guide(editor)
    delete(editor, new_guide(editor))  # a Guide in the Trash isn't counted

    admin_row = user_row(admin, DEMO_USERS["admin"]["email"])
    assert "演示管理员" in admin_row and "管理员" in admin_row
    assert "正常" in admin_row
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", admin_row)  # last login

    editor_row = user_row(admin, DEMO_USERS["editor"]["email"])
    assert "演示编辑" in editor_row and "编辑" in editor_row
    assert "已发布 1 · 共 2" in editor_row

    assert 'href="../admin/users">用户</a>' in admin.get("/admin/dashboard").text


def create_account(admin: TestClient, email: str, role: str = "editor",
                   temporary_password: str = "temporary-pw-1"):
    return submit(admin, "/admin/users", "/admin/users", email=email, role=role,
                  temporary_password=temporary_password)


def test_an_admin_creates_an_account_whose_owner_must_complete_first_login_setup(
        admin, client):
    response = create_account(admin, "writer@example.test")
    assert response.status_code == 303
    assert "已创建账号" in admin.get(response.headers["location"]).text
    assert "待首次登录设置" in user_row(admin, "writer@example.test")

    response = login(client, "writer@example.test", "temporary-pw-1")
    assert response.headers["location"] == "/admin/setup"
    assert client.get("/admin/guides", follow_redirects=False).headers["location"] \
        == "/admin/setup"
    assert submit_setup(client, "新作者", "my-own-password").status_code == 303
    assert client.get("/admin/guides/new").status_code == 200
    assert "新作者" in user_row(admin, "writer@example.test")


@pytest.mark.parametrize("email, role, temporary_password, message", [
    ("editor@example.test", "editor", "temporary-pw-1", "该邮箱已有账号"),
    ("EDITOR@example.test", "editor", "temporary-pw-1", "该邮箱已有账号"),
    ("not-an-email", "editor", "temporary-pw-1", "邮箱"),
    ("writer@example.test", "owner", "temporary-pw-1", "角色"),
    ("writer@example.test", "editor", "short", "至少需要 8 个字符"),
])
def test_creating_an_account_with_bad_input_is_refused_with_a_message(
        admin, email, role, temporary_password, message):
    response = create_account(admin, email, role, temporary_password)
    assert response.status_code == 400
    assert message in response.text
    assert "writer@example.test" not in admin.get("/admin/users").text


def account_page(admin: TestClient, email: str) -> str:
    """The URL of the account's own page, linked from its row's Display name."""
    match = re.search(r'href="\.\./(admin/users/\d+)"', user_row(admin, email))
    assert match, f"no link to the page of {email}"
    return "/" + match.group(1)


def manage(admin: TestClient, email: str, action: str, **fields):
    """Press a button (role, ban, unban, deactivate, reactivate, password) on
    the account's page."""
    page = account_page(admin, email)
    return submit(admin, page, f"{page}/{action}", **fields)


EDITOR = DEMO_USERS["editor"]["email"]
ADMIN = DEMO_USERS["admin"]["email"]


def test_a_role_change_takes_effect_on_the_users_next_request(admin, editor):
    assert editor.get("/admin/heroes").status_code == 403

    response = manage(admin, EDITOR, "role", role="admin")
    assert response.status_code == 303
    assert "管理员" in user_row(admin, EDITOR)
    assert editor.get("/admin/heroes").status_code == 200

    assert manage(admin, EDITOR, "role", role="editor").status_code == 303
    assert editor.get("/admin/heroes").status_code == 403


def test_an_admin_cannot_demote_themselves(admin):
    response = manage(admin, ADMIN, "role", role="editor")
    assert response.status_code == 400
    assert "不能修改自己的角色" in response.text
    assert admin.get("/admin/heroes").status_code == 200


def test_a_banned_editor_keeps_drafting_but_submit_and_revisions_are_refused_with_the_reason(
        admin, editor):
    published = published_guide(editor, admin)
    response = manage(admin, EDITOR, "ban")
    assert response.status_code == 303
    assert "禁止投稿" in user_row(admin, EDITOR)

    assert editor.get("/admin/dashboard").status_code == 200  # still signed in
    edit_page = new_guide(editor)
    assert "禁止投稿" in editor.get(edit_page).text  # told before pressing Submit
    assert "禁止投稿" in editor.get(published).text
    assert save(editor, edit_page, title_zh="还能继续写").status_code == 303
    response = act(editor, edit_page, "submit")
    assert response.status_code == 403 and "禁止投稿" in response.text
    assert status_of(editor, edit_page) == "草稿"

    response = open_revision(editor, published)
    assert response.status_code == 403 and "禁止投稿" in response.text
    assert editor.get(revision_page(published)).status_code == 404


def test_lifting_the_ban_restores_submit(admin, editor):
    edit_page = new_guide(editor)
    manage(admin, EDITOR, "ban")
    assert act(editor, edit_page, "submit").status_code == 403

    response = manage(admin, EDITOR, "unban")
    assert response.status_code == 303
    assert "正常" in user_row(admin, EDITOR)
    assert act(editor, edit_page, "submit").status_code == 303
    assert status_of(editor, edit_page) == "待审核"


def test_a_submission_ban_applies_only_to_editors(admin, editor):
    manage(admin, EDITOR, "role", role="admin")
    response = manage(admin, EDITOR, "ban")
    assert response.status_code == 400 and "只适用于编辑" in response.text

    manage(admin, EDITOR, "role", role="editor")
    manage(admin, EDITOR, "ban")
    response = manage(admin, EDITOR, "role", role="admin")
    assert response.status_code == 400 and "先解除禁止投稿" in response.text
    assert editor.get("/admin/heroes").status_code == 403


def test_a_deactivated_user_cannot_log_in_and_reactivating_restores_login(
        admin, editor, client):
    page = account_page(admin, EDITOR)
    confirm = admin.get(f"{page}/deactivate")
    assert confirm.status_code == 200 and "停用" in confirm.text
    response = manage(admin, EDITOR, "deactivate")
    assert response.status_code == 303
    assert "已停用" in user_row(admin, EDITOR)

    # The open session ends at once, and logging in again is refused.
    after = editor.get("/admin/dashboard", follow_redirects=False)
    assert after.headers["location"] == "/login"
    password = DEMO_USERS["editor"]["password"]
    response = login(client, EDITOR, password)
    assert response.status_code == 403 and "账号已停用" in response.text

    assert manage(admin, EDITOR, "reactivate").status_code == 303
    assert "正常" in user_row(admin, EDITOR)
    assert login(client, EDITOR, password).headers["location"] == "/admin/dashboard"


def test_an_admin_cannot_deactivate_themselves(admin):
    page = account_page(admin, ADMIN)
    confirm = admin.get(f"{page}/deactivate")
    assert confirm.status_code == 400 and "不能停用自己的账号" in confirm.text
    assert "确定要停用" not in confirm.text
    response = manage(admin, ADMIN, "deactivate")
    assert response.status_code == 400
    assert "不能停用自己的账号" in response.text
    assert admin.get("/admin/users").status_code == 200


def second_admin(admin: TestClient) -> TestClient:
    """Another Admin, made on the Users page, signed in and set up."""
    create_account(admin, "admin2@example.test", role="admin")
    c = TestClient(create_app())
    login(c, "admin2@example.test", "temporary-pw-1")
    assert submit_setup(c, "第二位管理员", "admin2-own-pw").status_code == 303
    return c


def test_an_admin_whose_account_was_just_removed_cannot_remove_the_other(admin):
    other = second_admin(admin)
    token = csrf_token(other.get("/admin/users").text)  # page loaded earlier
    assert manage(admin, "admin2@example.test", "deactivate").status_code == 303

    response = other.post(account_page(admin, ADMIN) + "/deactivate",
                          data={"csrf_token": token}, follow_redirects=False)
    assert response.headers["location"] == "/login"
    assert "正常" in user_row(admin, ADMIN)


def test_the_last_active_admin_can_never_be_deactivated_or_demoted(admin):
    """No console request can reach this: an Admin able to act is active, so
    the target is never the last one. It guards against a stale Admin, as in
    two Admins removing each other at the same moment."""
    from app import accounts, db

    second_admin(admin)
    with db.connect() as conn:
        stale = accounts.user_with_email(conn, "admin2@example.test")
        last = accounts.user_with_email(conn, ADMIN)
    assert stale and last
    manage(admin, "admin2@example.test", "deactivate")

    with db.connect() as conn:
        for remove in [lambda: accounts.deactivate(conn, stale, last.id),
                       lambda: accounts.change_role(conn, stale, last.id, "editor")]:
            with pytest.raises(accounts.Refused, match="至少要保留一位"):
                remove()
    assert admin.get("/admin/heroes").status_code == 200


def test_a_password_reset_ends_the_old_password_and_requires_setup_again(
        admin, editor, client):
    response = manage(admin, EDITOR, "password", temporary_password="reset-temp-pw")
    assert response.status_code == 303
    assert "待首次登录设置" in user_row(admin, EDITOR)
    assert editor.get("/admin/dashboard", follow_redirects=False) \
        .headers["location"] == "/login"

    old = login(client, EDITOR, DEMO_USERS["editor"]["password"])
    assert old.status_code == 401
    response = login(client, EDITOR, "reset-temp-pw")
    assert response.headers["location"] == "/admin/setup"
    setup_page = client.get("/admin/setup").text
    assert 'value="演示编辑"' in setup_page  # their Display name, kept as offered
    assert submit_setup(client, "演示编辑", "my-new-password").status_code == 303
    assert client.get("/admin/guides/new").status_code == 200


@pytest.mark.parametrize("email, password, message", [
    (EDITOR, "short", "至少需要 8 个字符"),
    (ADMIN, "reset-temp-pw", "不能重置自己的密码"),
])
def test_a_password_reset_with_bad_input_is_refused(admin, email, password, message):
    response = manage(admin, email, "password", temporary_password=password)
    assert response.status_code == 400 and message in response.text
    assert "待首次登录设置" not in user_row(admin, email)


@pytest.mark.parametrize("action", ["ban", "deactivate"])
def test_published_guides_of_a_banned_or_deactivated_editor_stay_in_the_site_build(
        admin, editor, tmp_path, action):
    from test_t04_site_build import page, published_guide as published_slug

    slug = published_slug(admin, editor, title_zh="被停用前写的攻略")
    assert manage(admin, EDITOR, action).status_code == 303

    site = render_site(tmp_path / "site")
    assert "被停用前写的攻略" in page(site, f"zh/guides/{slug}/")
    authors = [path for path in site.glob("zh/authors/*/index.html")
               if "演示编辑" in path.read_text()]
    assert authors and "被停用前写的攻略" in authors[0].read_text()


def console_routes() -> list[APIRoute]:
    """Every route of every router module under app/routes/."""
    import app.routes

    modules = [importlib.import_module(f"app.routes.{module.name}")
               for module in pkgutil.iter_modules(app.routes.__path__)]
    return [route for module in modules for route in module.router.routes
            if isinstance(route, APIRoute)]


def admin_only_routes() -> list[tuple[str, str]]:
    """(method, path) of every console route behind an Admin-only guard,
    read from the routers themselves, so a new Admin route is covered unasked."""
    def guarded(dependant) -> bool:
        return any(d.call in ADMIN_GUARDS or guarded(d)
                   for d in dependant.dependencies)
    return sorted((method, route.path) for route in console_routes()
                  if guarded(route.dependant) for method in route.methods or ())


def test_every_users_route_is_behind_an_admin_only_guard():
    from app.routes import users

    users_routes = {(method, route.path) for route in users.router.routes
                    if isinstance(route, APIRoute) for method in route.methods or ()}
    assert len(users_routes) == 10
    assert users_routes <= set(admin_only_routes())


@pytest.mark.parametrize("method, path", admin_only_routes())
def test_an_editor_is_refused_on_every_admin_only_route(admin, editor, method, path):
    path = re.sub(r"\{\w+\}", "1", path)  # account 1 is the Admin
    dashboard = editor.get("/admin/dashboard").text
    assert 'admin/users"' not in dashboard
    # A real token and real fields, so the refusal is about the role alone.
    data = {"csrf_token": csrf_token(dashboard), "role": "editor",
            "email": "sneaky@example.test", "temporary_password": "sneaky-pw-1"}
    response = editor.request(method, path, data=data if method == "POST" else None,
                              follow_redirects=False)
    assert response.status_code == 403
    assert "只有管理员" in response.text
    assert "退出登录" in response.text  # a console page, not a dead end

    admin_row = user_row(admin, ADMIN)
    assert "管理员" in admin_row and "正常" in admin_row
    assert "待首次登录设置" not in admin_row
    assert "sneaky@example.test" not in admin.get("/admin/users").text


@pytest.mark.parametrize("method, path", admin_only_routes())
def test_a_signed_out_visitor_is_sent_to_login_on_every_admin_only_route(
        client, method, path):
    path = re.sub(r"\{\w+\}", "1", path)
    token = csrf_token(client.get("/login").text)
    response = client.request(method, path,
                              data={"csrf_token": token} if method == "POST" else None,
                              follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


USERS_BEFORE_T09 = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'editor')),
    display_name  TEXT UNIQUE COLLATE NOCASE,
    state         TEXT NOT NULL DEFAULT 'active'
                  CHECK (state IN ('active', 'submission_ban', 'deactivated')),
    needs_setup   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def test_a_database_made_before_the_users_page_still_works(tmp_path, monkeypatch,
                                                            client_as):
    from conftest import add_user

    old = tmp_path / "before-t09.db"
    with closing(sqlite3.connect(old)) as conn:
        conn.executescript(USERS_BEFORE_T09)
    monkeypatch.setenv("CMS_DATABASE", str(old))
    for role, user in DEMO_USERS.items():
        add_user(email=user["email"], password=user["password"], role=role,
                 display_name=user["display_name"])

    admin = client_as("admin")
    assert "从未登录" in user_row(admin, EDITOR)
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", user_row(admin, ADMIN))
