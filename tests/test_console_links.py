"""#18: console pages link with relative paths only, and every link still
reaches its page from whatever URL depth the page is served at."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import web
from conftest import login
from test_t01_login import new_editor_needing_setup
from test_t02_heroes_patches import add_hero, add_patch, edit_link, submit
from test_t03_guides import new_guide

LINK = re.compile(r'\b(href|src|action|formaction)="([^"]*)"')
GET_FORM = re.compile(r'<form method="get" action="([^"]*)"')


def links(page: str) -> list[tuple[str, str]]:
    return LINK.findall(page)


@pytest.mark.parametrize("root_path", ["", "/cms"])
@pytest.mark.parametrize("path, prefix", [
    ("/", ""),
    ("/login", ""),
    ("/admin/guides", "../"),
    ("/admin/guides/5/edit", "../../../"),
])
def test_the_link_prefix_leads_back_to_the_console_root(path, prefix, root_path):
    # Starlette puts a mount prefix (root_path) in front of the path itself.
    full = root_path + path
    request = Request({"type": "http", "method": "GET", "path": full,
                       "root_path": root_path, "headers": [], "query_string": b""})
    assert web.console_root(request) == prefix
    assert urljoin(f"http://testserver{full}", f"{prefix}login") \
        == f"http://testserver{root_path}/login"


def check_page(c: TestClient, page_url: str, page: str) -> None:
    """No root-absolute path on the page, and each link, resolved against the
    page's own URL, reaches a console route that answers it."""
    found = links(page)
    assert found, f"{page_url} has no links"
    get_forms = GET_FORM.findall(page)
    for attribute, target in found:
        assert not target.startswith("/"), f"{page_url}: {attribute}={target!r}"
        resolved = urljoin(f"http://testserver{page_url}", target)
        if attribute == "href" or (attribute == "action" and target in get_forms):
            assert c.get(resolved).status_code == 200, f"{page_url}: {target}"
        else:
            # POST targets: an empty form is refused for its CSRF token (403),
            # which only happens on a route that exists and accepts POST.
            response = c.post(resolved, follow_redirects=False)
            assert response.status_code == 403, f"{page_url}: {target}"


@pytest.fixture
def admin(client_as) -> TestClient:
    admin = client_as("admin")
    add_hero(admin, "瓦妮莎", "Vanessa")
    add_patch(admin, "6.7")
    return admin


def test_every_admin_console_page_links_relatively_and_its_links_work(admin):
    hero_edit = edit_link(admin, "Vanessa")
    guide_edit = new_guide(admin)
    pages = ["/admin/dashboard", "/admin/guides", "/admin/guides/new",
             guide_edit, guide_edit.removesuffix("/edit") + "/preview",
             "/admin/heroes", hero_edit, "/admin/patches"]
    for page_url in pages:
        response = admin.get(page_url)
        assert response.status_code == 200, page_url
        check_page(admin, page_url, response.text)


def test_a_refused_form_reshown_at_a_deeper_url_still_links_correctly(admin):
    hero_edit = edit_link(admin, "Vanessa")
    action = hero_edit.removesuffix("/edit")
    response = submit(admin, hero_edit, action, name_zh="", name_en="")
    assert response.status_code == 400
    check_page(admin, action, response.text)


def test_the_login_and_setup_pages_link_relatively_and_their_links_work(client):
    check_page(client, "/login", client.get("/login").text)

    # The T00 hello page borrows the public base template, whose stylesheet
    # and home links only exist on the Site; its link into the console works.
    hello = client.get("/admin").text
    assert not [t for _, t in links(hello) if t.startswith("/")]
    assert ("href", "login") in links(hello)

    new_editor_needing_setup()
    login(client, "new@example.test", "temporary-pw")
    check_page(client, "/admin/setup", client.get("/admin/setup").text)


def test_revision_and_trash_pages_link_relatively_and_their_links_work(
        admin, client_as):
    from test_t03_guides import act
    from test_t06_revisions_trash import delete, open_revision, revision_page

    editor = client_as("editor")
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")
    open_revision(editor, edit_page)
    revision = revision_page(edit_page)
    act(editor, revision, "submit")
    guide = edit_page.removesuffix("/edit")
    for c, page_url in [(editor, revision), (editor, f"{guide}/revision/preview"),
                        (editor, f"{guide}/delete"),
                        (editor, f"{guide}/revision/delete"), (admin, revision),
                        (admin, f"{guide}/revision/review")]:
        response = c.get(page_url)
        assert response.status_code == 200, page_url
        check_page(c, page_url, response.text)

    delete(editor, new_guide(editor))
    for page_url in ["/admin/trash", "/admin/trash/2/delete"]:
        response = admin.get(page_url)
        assert response.status_code == 200, page_url
        check_page(admin, page_url, response.text)


def test_users_pages_and_the_refusal_page_link_relatively_and_their_links_work(
        admin, client_as):
    from test_t09_users import EDITOR, account_page, create_account

    create_account(admin, "writer@example.test")
    editor_page = account_page(admin, EDITOR)
    for page_url in ["/admin/users", editor_page, f"{editor_page}/deactivate",
                     account_page(admin, "writer@example.test")]:
        response = admin.get(page_url)
        assert response.status_code == 200, page_url
        check_page(admin, page_url, response.text)

    editor = client_as("editor")
    refused = editor.get(editor_page)
    assert refused.status_code == 403
    check_page(editor, editor_page, refused.text)


def test_game_term_pages_link_relatively_and_their_links_work(admin):
    from test_t07_game_terms import CSV_HEADER, add_term, term_edit_link, upload_csv

    add_term(admin, "item", "船锚", "Anchor")
    for page_url in ["/admin/terms", term_edit_link(admin, "Anchor"),
                     "/admin/terms/import"]:
        response = admin.get(page_url)
        assert response.status_code == 200, page_url
        check_page(admin, page_url, response.text)

    preview = upload_csv(admin, CSV_HEADER + "物品,火药桶,Powder Keg,\n")
    assert preview.status_code == 200
    check_page(admin, "/admin/terms/import", preview.text)
