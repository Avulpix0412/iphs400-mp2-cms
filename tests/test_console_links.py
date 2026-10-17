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
