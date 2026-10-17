"""T02: Admins manage Heroes and Patches (Seam 1: the console over HTTP)."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient

from conftest import csrf_token


def submit(c: TestClient, form_page: str, action: str, **fields):
    """Fill in the form on `form_page` the way a browser does, token included."""
    token = csrf_token(c.get(form_page).text)
    return c.post(action, data={"csrf_token": token, **fields},
                  follow_redirects=False)


def add_hero(c: TestClient, name_zh: str, name_en: str):
    return submit(c, "/admin/heroes", "/admin/heroes",
                  name_zh=name_zh, name_en=name_en)


def test_admin_adds_a_hero_and_sees_it_listed_with_its_slug(client_as):
    admin = client_as("admin")
    response = add_hero(admin, "瓦妮莎", "Vanessa")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/heroes"

    page = admin.get("/admin/heroes")
    assert page.status_code == 200
    assert "瓦妮莎" in page.text and "Vanessa" in page.text
    assert "vanessa" in page.text


@pytest.mark.parametrize("name_zh, name_en, message", [
    ("", "Vanessa", "请填写官方中文名"),
    ("瓦妮莎", "   ", "请填写官方英文名"),
])
def test_a_hero_missing_either_official_name_is_refused(client_as, name_zh,
                                                        name_en, message):
    admin = client_as("admin")
    response = add_hero(admin, name_zh, name_en)
    assert response.status_code == 400
    assert message in response.text
    assert "还没有英雄" in admin.get("/admin/heroes").text


def test_a_two_word_english_name_gives_a_hyphenated_slug(client_as):
    admin = client_as("admin")
    add_hero(admin, "黑骑士", "Black  Knight")
    assert "<code>black-knight</code>" in admin.get("/admin/heroes").text


def test_a_hero_whose_slug_is_already_taken_is_refused(client_as):
    admin = client_as("admin")
    add_hero(admin, "瓦妮莎", "Vanessa")

    response = add_hero(admin, "另一个瓦妮莎", "Vanessa!")
    assert response.status_code == 400
    assert "网址名 vanessa 已被英雄 瓦妮莎（Vanessa）使用" in response.text
    assert "另一个瓦妮莎" not in admin.get("/admin/heroes").text


def test_a_new_hero_with_another_heros_english_name_is_refused(client_as):
    admin = client_as("admin")
    add_hero(admin, "瓦妮莎", "Vanessa")

    response = add_hero(admin, "另一个瓦妮莎", "vanessa ")
    assert response.status_code == 400
    assert "官方英文名 Vanessa 已被英雄 瓦妮莎 使用" in response.text
    assert "另一个瓦妮莎" not in admin.get("/admin/heroes").text


def test_english_names_clash_ignoring_non_ascii_case_too(client_as):
    admin = client_as("admin")
    add_hero(admin, "埃克莱尔", "Éclair")
    add_hero(admin, "杜利", "Dooley")

    clash = edit_hero(admin, "Dooley", name_zh="杜利", name_en="ÉCLAIR")
    assert clash.status_code == 400
    assert "官方英文名 Éclair 已被英雄 埃克莱尔 使用" in clash.text


def test_an_english_name_with_no_letters_or_digits_is_refused(client_as):
    response = add_hero(client_as("admin"), "问号", "???")
    assert response.status_code == 400
    assert "英文名需要包含字母或数字" in response.text


def edit_link(c: TestClient, listed_en: str) -> str:
    """The edit page linked from the Hero list row showing `listed_en`."""
    row = next(r for r in c.get("/admin/heroes").text.split("<tr>")
               if f"<td>{listed_en}</td>" in r)
    match = re.search(r'href="([./]*admin/heroes/\d+/edit)"', row)
    assert match, f"no edit link for {listed_en}"
    return urljoin("/admin/heroes", match.group(1))


def edit_hero(c: TestClient, listed_en: str, **fields):
    page = edit_link(c, listed_en)
    return submit(c, page, page.removesuffix("/edit"), **fields)


def test_admin_corrects_a_heros_official_names_and_the_slug_stays(client_as):
    admin = client_as("admin")
    add_hero(admin, "瓦妮沙", "Vanesa")
    add_hero(admin, "杜利", "Dooley")

    response = edit_hero(admin, "Vanesa", name_zh="瓦妮莎", name_en="Vanessa")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/heroes"
    page = admin.get("/admin/heroes").text
    assert "<td>瓦妮莎</td><td>Vanessa</td><td><code>vanesa</code></td>" in page
    assert "瓦妮沙" not in page and "Vanesa<" not in page
    assert "<td>杜利</td><td>Dooley</td><td><code>dooley</code></td>" in page


def test_editing_only_the_chinese_name_keeps_the_heros_own_slug(client_as):
    admin = client_as("admin")
    add_hero(admin, "瓦妮沙", "Vanessa")
    response = edit_hero(admin, "Vanessa", name_zh="瓦妮莎", name_en="Vanessa")
    assert response.status_code == 303
    assert "<td>瓦妮莎</td>" in admin.get("/admin/heroes").text


def test_an_edit_that_blanks_a_name_is_refused(client_as):
    admin = client_as("admin")
    add_hero(admin, "杜利", "Dooley")

    blank_zh = edit_hero(admin, "Dooley", name_zh="", name_en="Dooley")
    assert blank_zh.status_code == 400 and "请填写官方中文名" in blank_zh.text
    blank_en = edit_hero(admin, "Dooley", name_zh="杜利", name_en=" ")
    assert blank_en.status_code == 400 and "请填写官方英文名" in blank_en.text
    assert "<td>杜利</td><td>Dooley</td>" in admin.get("/admin/heroes").text


def test_an_edit_that_takes_another_heros_english_name_is_refused(client_as):
    admin = client_as("admin")
    add_hero(admin, "瓦妮莎", "Vanessa")
    add_hero(admin, "杜利", "Dooley")

    clash = edit_hero(admin, "Dooley", name_zh="杜利", name_en="VANESSA")
    assert clash.status_code == 400
    assert "官方英文名 Vanessa 已被英雄 瓦妮莎 使用" in clash.text
    assert "<td>杜利</td><td>Dooley</td>" in admin.get("/admin/heroes").text


def test_a_new_hero_cannot_take_a_corrected_heros_english_name(client_as):
    admin = client_as("admin")
    add_hero(admin, "瓦妮沙", "Vanesa")
    edit_hero(admin, "Vanesa", name_zh="瓦妮莎", name_en="Vanessa")

    response = add_hero(admin, "瓦妮莎", "Vanessa")
    assert response.status_code == 400
    assert "官方英文名 Vanessa 已被英雄 瓦妮莎 使用" in response.text


def test_editing_a_hero_that_does_not_exist_is_not_found(client_as):
    assert client_as("admin").get("/admin/heroes/999/edit").status_code == 404


def add_patch(c: TestClient, name: str):
    return submit(c, "/admin/patches", "/admin/patches", name=name)


def test_the_newest_patch_added_becomes_the_current_patch(client_as):
    admin = client_as("admin")
    assert add_patch(admin, "6.6").headers["location"] == "/admin/patches"
    assert "<td>6.6（当前版本）</td>" in admin.get("/admin/patches").text

    add_patch(admin, "6.7")
    page = admin.get("/admin/patches").text
    assert "<td>6.7（当前版本）</td>" in page
    assert "<td>6.6</td>" in page
    assert page.count("（当前版本）") == 1
    assert page.index("6.7") < page.index("6.6")  # newest first


@pytest.mark.parametrize("name, message", [
    ("6.7", "版本 6.7 已存在"),
    (" 6.7 ", "版本 6.7 已存在"),
    ("  ", "请填写版本号"),
])
def test_a_patch_that_already_exists_or_is_blank_is_refused(client_as, name,
                                                             message):
    admin = client_as("admin")
    add_patch(admin, "6.6")
    add_patch(admin, "6.7")

    response = add_patch(admin, name)
    assert response.status_code == 400
    assert message in response.text
    page = admin.get("/admin/patches").text
    assert page.count("<td>6.7") == 1
    assert "<td>6.7（当前版本）</td>" in page


def test_admin_console_navigation_links_to_heroes_and_patches(client_as):
    page = client_as("admin").get("/admin/dashboard").text
    assert 'href="../admin/heroes"' in page and 'href="../admin/patches"' in page


@pytest.mark.parametrize("method, path, fields", [
    ("GET", "/admin/heroes", {}),
    ("POST", "/admin/heroes", {"name_zh": "杜利", "name_en": "Dooley"}),
    ("GET", "/admin/heroes/{id}/edit", {}),
    ("POST", "/admin/heroes/{id}", {"name_zh": "改了", "name_en": "Changed"}),
    ("GET", "/admin/patches", {}),
    ("POST", "/admin/patches", {"name": "9.9"}),
])
def test_an_editor_is_refused_on_every_hero_and_patch_route(client_as, method,
                                                            path, fields):
    admin = client_as("admin")
    add_hero(admin, "瓦妮莎", "Vanessa")
    add_patch(admin, "6.7")
    path = path.format(id=edit_link(admin, "Vanessa").split("/")[3])

    editor = client_as("editor")
    dashboard = editor.get("/admin/dashboard").text
    assert 'admin/heroes"' not in dashboard
    # A real token, so the refusal is about the role and not about CSRF.
    data = {"csrf_token": csrf_token(dashboard), **fields}
    response = editor.request(method, path, data=data if method == "POST" else None,
                              follow_redirects=False)
    assert response.status_code == 403
    assert "只有管理员" in response.text

    heroes, patches = admin.get("/admin/heroes").text, admin.get("/admin/patches").text
    assert "Dooley" not in heroes and "Changed" not in heroes and "9.9" not in patches


@pytest.mark.parametrize("path", ["/admin/heroes", "/admin/patches"])
def test_signed_out_hero_and_patch_pages_redirect_to_login(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
