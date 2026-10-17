"""T03: Editors write and Submit Guides; Admins Publish them (Seam 1: the
console over HTTP)."""
from __future__ import annotations

import html
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import add_user, csrf_token, login
from test_t02_heroes_patches import submit as fill_in


@pytest.fixture
def admin(client_as) -> TestClient:
    """An Admin, with Heroes and Patches 6.4 to 6.7 (6.7 current) in place."""
    admin = client_as("admin")
    for name_zh, name_en in [("瓦妮莎", "Vanessa"), ("杜利", "Dooley")]:
        fill_in(admin, "/admin/heroes", "/admin/heroes",
               name_zh=name_zh, name_en=name_en)
    for name in ["6.4", "6.5", "6.6", "6.7"]:
        fill_in(admin, "/admin/patches", "/admin/patches", name=name)
    return admin


@pytest.fixture
def editor(admin, client_as) -> TestClient:
    return client_as("editor")


def option_value(page: str, label: str) -> str:
    """The value of the <option> showing `label` on a rendered form."""
    match = re.search(rf'<option value="(\d+)"[^>]*>{re.escape(label)}</option>', page)
    assert match, f"no option labelled {label}"
    return match.group(1)


def choice(c: TestClient, label: str) -> str:
    """The value of the Hero or Patch picker option showing `label`."""
    return option_value(c.get("/admin/guides/new").text, label)


hero_id = patch_id = choice


def guide_fields(c: TestClient, **fields) -> dict[str, str]:
    """A complete Guide form: Chinese text, Vanessa, the Current Patch."""
    defaults = {"title_zh": "瓦妮莎海盗流", "body_zh": "## 终局阵容\n\n先拿船。",
                "title_en": "", "body_en": "",
                "hero_id": hero_id(c, "瓦妮莎（Vanessa）"),
                "patch_id": patch_id(c, "6.7（当前版本）")}
    return defaults | fields


def new_guide(c: TestClient, **fields) -> str:
    """Save a new Guide as a Draft; returns its edit page."""
    response = fill_in(c, "/admin/guides/new", "/admin/guides",
                      **guide_fields(c, **fields))
    assert response.status_code == 303, response.text
    edit_page = response.headers["location"]
    assert re.fullmatch(r"/admin/guides/\d+/edit", edit_page)
    return edit_page


def form_values(page: str) -> dict[str, str]:
    """What the Guide form on `page` would send unchanged: its text inputs,
    textareas and selected options."""
    values = dict(re.findall(r'<input type="text" name="(\w+)" value="([^"]*)"', page))
    values |= dict(re.findall(r'<textarea name="(\w+)"[^>]*>(.*?)</textarea>', page,
                              re.DOTALL))
    for name, options in re.findall(r'<select name="(\w+)"[^>]*>(.*?)</select>', page,
                                    re.DOTALL):
        selected = re.search(r'<option value="(\d*)" selected', options)
        values[name] = selected.group(1) if selected else ""
    return {name: html.unescape(value) for name, value in values.items()}


def save(c: TestClient, edit_page: str, **fields):
    """Change some fields of a saved Guide, keeping the rest as they are."""
    current = form_values(c.get(edit_page).text)
    return fill_in(c, edit_page, edit_page.removesuffix("/edit"),
                  **(current | fields))


def test_editor_saves_a_draft_and_edits_it_later(editor):
    edit_page = new_guide(editor, title_zh="瓦妮莎海盗流",
                          body_zh="先拿船，再拿炮。")
    page = editor.get(edit_page)
    assert page.status_code == 200
    assert "草稿已保存" in page.text
    assert 'value="瓦妮莎海盗流"' in page.text and "先拿船，再拿炮。" in page.text

    response = save(editor, edit_page, title_zh="瓦妮莎海盗流（修改版）")
    assert response.status_code == 303
    assert 'value="瓦妮莎海盗流（修改版）"' in editor.get(edit_page).text

    listing = editor.get("/admin/guides").text
    assert "瓦妮莎海盗流（修改版）" in listing and "草稿" in listing


def options(page: str, select: str) -> list[str]:
    """The labels of the options in the <select> called `select`."""
    match = re.search(rf'<select name="{select}"[^>]*>(.*?)</select>', page, re.DOTALL)
    assert match, f"no {select} picker"
    return re.findall(r"<option[^>]*>([^<]*)</option>", match.group(1))


def test_hero_picker_lists_official_names_only(editor):
    page = editor.get("/admin/guides/new").text
    assert options(page, "hero_id") == ["请选择英雄", "杜利（Dooley）", "瓦妮莎（Vanessa）"]


def test_patch_picker_offers_the_current_patch_preselected_and_the_two_before(editor):
    page = editor.get("/admin/guides/new").text
    assert options(page, "patch_id") == ["6.7（当前版本）", "6.6", "6.5"]
    assert form_values(page)["patch_id"] == patch_id(editor, "6.7（当前版本）")


def test_a_patch_older_than_the_choices_is_refused_for_a_new_guide(admin, editor):
    too_old = filter_value(admin, "patch", "6.4")  # listed, but never offered
    response = fill_in(editor, "/admin/guides/new", "/admin/guides",
                      **guide_fields(editor, patch_id=too_old))
    assert response.status_code == 400
    assert "请选择版本" in response.text


def test_a_guide_keeps_its_older_patch_after_new_patches_arrive(editor, admin):
    edit_page = new_guide(editor, patch_id=patch_id(editor, "6.5"))
    for name in ["6.8", "6.9"]:
        fill_in(admin, "/admin/patches", "/admin/patches", name=name)

    page = editor.get(edit_page).text
    assert options(page, "patch_id") == ["6.9（当前版本）", "6.8", "6.7", "6.5"]
    assert save(editor, edit_page, title_zh="改个标题").status_code == 303
    assert options(editor.get(edit_page).text, "patch_id")[-1] == "6.5"


def test_a_guide_must_have_a_hero(editor):
    response = fill_in(editor, "/admin/guides/new", "/admin/guides",
                      **guide_fields(editor, hero_id=""))
    assert response.status_code == 400
    assert "请选择英雄" in response.text
    assert "没有攻略" in editor.get("/admin/guides").text


def slug_of(c: TestClient, edit_page: str) -> str:
    match = re.search(r"网址名：<code>([^<]+)</code>", c.get(edit_page).text)
    assert match, "edit page shows no slug"
    return match.group(1)


def test_a_new_guide_gets_the_slug_hero_slug_dash_id(editor):
    edit_page = new_guide(editor)
    guide_number = edit_page.split("/")[3]
    assert slug_of(editor, edit_page) == f"vanessa-{guide_number}"

    second = new_guide(editor, hero_id=hero_id(editor, "杜利（Dooley）"))
    assert slug_of(editor, second) == f"dooley-{second.split('/')[3]}"


def test_editing_the_title_or_hero_never_changes_the_slug(editor):
    edit_page = new_guide(editor)
    slug = slug_of(editor, edit_page)
    save(editor, edit_page, title_zh="全新的标题",
         hero_id=hero_id(editor, "杜利（Dooley）"))
    assert slug_of(editor, edit_page) == slug


def test_admin_changes_a_guides_slug_and_a_duplicate_is_refused(editor, admin):
    first = new_guide(editor)
    second = new_guide(editor)
    response = save(admin, first, slug="vanessa-pirates")
    assert response.status_code == 303
    assert slug_of(editor, first) == "vanessa-pirates"

    clash = save(admin, second, slug="vanessa-pirates")
    assert clash.status_code == 400
    assert "网址名 vanessa-pirates 已被另一篇攻略使用" in clash.text
    assert slug_of(admin, second) != "vanessa-pirates"


@pytest.mark.parametrize("slug", ["", "Vanessa Pirates", "瓦妮莎", "-x-"])
def test_a_slug_that_is_not_lowercase_letters_digits_and_hyphens_is_refused(
        editor, admin, slug):
    edit_page = new_guide(editor)
    response = save(admin, edit_page, slug=slug)
    assert response.status_code == 400
    assert "网址名只能包含小写英文字母、数字和连字符" in response.text


def test_an_editor_cannot_change_a_slug(editor):
    edit_page = new_guide(editor)
    assert 'name="slug"' not in editor.get(edit_page).text
    slug = slug_of(editor, edit_page)
    response = save(editor, edit_page, slug="my-own-slug")
    assert response.status_code == 403
    assert "只有管理员可以修改网址名" in response.text
    assert slug_of(editor, edit_page) == slug


def test_a_new_guide_whose_usual_slug_is_taken_still_gets_a_unique_one(editor, admin):
    first = new_guide(editor)
    next_number = int(first.split("/")[3]) + 1
    save(admin, first, slug=f"vanessa-{next_number}")

    second = new_guide(editor)
    assert second == f"/admin/guides/{next_number}/edit"
    assert slug_of(editor, second).startswith(f"vanessa-{next_number}-")


def act(c: TestClient, edit_page: str, action: str, **fields):
    """Press a workflow button (submit, publish). With no fields this is a bare
    post, as if typed by hand; with fields, the editor form is sent along."""
    if fields:
        fields = form_values(c.get(edit_page).text) | fields
    return fill_in(c, edit_page, f"{edit_page.removesuffix('/edit')}/{action}",
                  **fields)


def status_of(c: TestClient, edit_page: str) -> str:
    match = re.search(r"状态：(\S+)", c.get(edit_page).text)
    assert match, "edit page shows no status"
    return match.group(1)


def test_editor_submits_a_draft_for_review(editor):
    edit_page = new_guide(editor)
    response = act(editor, edit_page, "submit")
    assert response.status_code == 303
    page = editor.get(edit_page).text
    assert "已提交审核" in page
    assert status_of(editor, edit_page) == "待审核"
    assert "待审核" in editor.get("/admin/guides").text


def test_submitting_from_the_editor_saves_the_latest_edits_too(editor):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit", title_zh="提交前最后一改")
    assert status_of(editor, edit_page) == "待审核"
    assert 'value="提交前最后一改"' in editor.get(edit_page).text


@pytest.mark.parametrize("missing", [{"title_zh": ""}, {"body_zh": "   "}])
def test_a_guide_without_chinese_text_cannot_be_submitted_and_the_console_says_why(
        editor, missing):
    edit_page = new_guide(editor, **missing)
    response = act(editor, edit_page, "submit")
    assert response.status_code == 400
    assert "提交审核前请填写中文标题和正文" in response.text
    assert status_of(editor, edit_page) == "草稿"


def test_a_failed_submit_keeps_what_was_typed_on_screen(editor):
    edit_page = new_guide(editor)
    response = act(editor, edit_page, "submit", title_zh="", body_en="typed")
    assert response.status_code == 400
    assert "typed</textarea>" in response.text
    assert "typed</textarea>" not in editor.get(edit_page).text  # not saved


def test_english_text_needs_both_a_title_and_a_body_to_submit(editor):
    edit_page = new_guide(editor, title_en="Vanessa pirates")
    response = act(editor, edit_page, "submit")
    assert response.status_code == 400
    assert "英文版需要同时填写标题和正文" in response.text


def test_a_guide_can_only_be_submitted_once(editor):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    response = act(editor, edit_page, "submit")
    assert response.status_code == 400
    assert "这篇攻略已经提交审核了" in response.text


def offers_publish(page: str) -> bool:
    return re.search(r"<button[^>]*>[^<]*发布[^<]*</button>", page) is not None


def test_the_editors_submit_control_reads_提交审核_and_nothing_offers_发布(editor):
    edit_page = new_guide(editor)
    draft_page = editor.get(edit_page).text
    assert re.search(r"<button[^>]*>提交审核</button>", draft_page)
    act(editor, edit_page, "submit")
    for page in ["/admin/dashboard", "/admin/guides", "/admin/guides/new", edit_page]:
        assert not offers_publish(editor.get(page).text), page
    assert not offers_publish(draft_page)


def test_an_editor_cannot_publish_even_by_posting_to_the_publish_route(editor):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    response = act(editor, edit_page, "publish")
    assert response.status_code == 403
    assert "只有管理员可以发布攻略" in response.text
    assert status_of(editor, edit_page) == "待审核"

    draft = new_guide(editor)
    assert act(editor, draft, "publish").status_code == 403
    assert status_of(editor, draft) == "草稿"


def test_admin_publishes_a_submitted_guide(editor, admin):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    assert offers_publish(admin.get(edit_page).text)

    response = act(admin, edit_page, "publish")
    assert response.status_code == 303
    page = admin.get(edit_page).text
    assert "已发布" in page
    assert "更新网站" in page  # not on the site until then
    assert status_of(editor, edit_page) == "已发布"


def test_admin_creates_and_publishes_their_own_guide_without_submitting(admin):
    edit_page = new_guide(admin)
    page = admin.get(edit_page).text
    assert offers_publish(page) and "提交审核</button>" not in page
    act(admin, edit_page, "publish", title_zh="管理员直接发布")
    assert status_of(admin, edit_page) == "已发布"
    assert 'value="管理员直接发布"' in admin.get(edit_page).text


def test_admin_cannot_publish_an_editors_draft_before_it_is_submitted(editor, admin):
    edit_page = new_guide(editor)
    assert not offers_publish(admin.get(edit_page).text)
    response = act(admin, edit_page, "publish")
    assert response.status_code == 400
    assert "要等作者提交审核后才能发布" in response.text
    assert status_of(admin, edit_page) == "草稿"


def test_a_guide_without_chinese_text_cannot_be_published(admin):
    edit_page = new_guide(admin, body_zh="")
    response = act(admin, edit_page, "publish")
    assert response.status_code == 400
    assert "请填写中文标题和正文" in response.text
    assert status_of(admin, edit_page) == "草稿"


def test_admin_edits_a_published_guide_and_it_stays_published(editor, admin):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")
    assert save(admin, edit_page, title_zh="管理员修了个错字").status_code == 303
    assert status_of(admin, edit_page) == "已发布"

    blanked = save(admin, edit_page, title_zh="")
    assert blanked.status_code == 400
    assert "请填写中文标题和正文" in blanked.text


def test_an_editor_cannot_edit_their_published_guide_directly(editor, admin):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")
    response = save(editor, edit_page, title_zh="偷偷改掉")
    assert response.status_code == 403
    assert "已发布的攻略要通过修订来修改" in response.text
    assert 'value="偷偷改掉"' not in editor.get(edit_page).text


def test_editor_edits_their_submitted_guide_and_it_stays_submitted(editor):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    assert save(editor, edit_page, body_zh="提交后又补了一段。").status_code == 303
    assert status_of(editor, edit_page) == "待审核"
    assert "提交后又补了一段。" in editor.get(edit_page).text


def test_admin_changes_the_hero_of_any_guide(editor, admin):
    edit_page = new_guide(editor)
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")

    response = save(admin, edit_page, hero_id=hero_id(admin, "杜利（Dooley）"))
    assert response.status_code == 303
    assert form_values(admin.get(edit_page).text)["hero_id"] == hero_id(admin, "杜利（Dooley）")
    assert status_of(admin, edit_page) == "已发布"
    assert "<td>杜利</td>" in editor.get("/admin/guides").text


@pytest.fixture
def someone_elses_guide(admin) -> str:
    """A Guide Submitted by a second Editor; returns its edit page."""
    add_user(email="other@example.test", password="other-pw-123", role="editor",
             display_name="另一位编辑")
    other = TestClient(create_app())
    login(other, "other@example.test", "other-pw-123")
    edit_page = new_guide(other, title_zh="别人的草稿")
    act(other, edit_page, "submit")
    return edit_page


def test_an_editor_cannot_see_or_open_another_persons_guides(editor,
                                                             someone_elses_guide):
    assert "别人的草稿" not in editor.get("/admin/guides").text
    guide = someone_elses_guide.removesuffix("/edit")
    token = csrf_token(editor.get("/admin/guides").text)
    for method, path in [("GET", f"{guide}/edit"), ("POST", guide),
                         ("POST", f"{guide}/submit"), ("POST", f"{guide}/publish")]:
        response = editor.request(method, path, data={"csrf_token": token,
                                                      "title_zh": "改掉"},
                                  follow_redirects=False)
        assert response.status_code == 404, (method, path)


def test_an_admin_sees_everyones_guides(admin, someone_elses_guide):
    listing = admin.get("/admin/guides").text
    assert "别人的草稿" in listing and "另一位编辑" in listing
    assert admin.get(someone_elses_guide).status_code == 200


def test_a_guide_that_does_not_exist_is_not_found(admin):
    assert admin.get("/admin/guides/999/edit").status_code == 404


def test_signed_out_guide_pages_redirect_to_login(client):
    response = client.get("/admin/guides", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


UNSAFE_BODY = """## 终局阵容

先拿**船**。

<script>alert("x")</script>
<img src="x.png" onerror="alert(1)">
[点我](javascript:alert(1))
<iframe src="https://example.com"></iframe>
"""


def test_preview_renders_markdown_and_strips_unsafe_html(editor):
    edit_page = new_guide(editor, body_zh=UNSAFE_BODY)
    assert f'href="../../..{edit_page.removesuffix("/edit")}/preview"' in editor.get(edit_page).text

    preview = editor.get(f"{edit_page.removesuffix('/edit')}/preview")
    assert preview.status_code == 200
    assert "<h2>终局阵容</h2>" in preview.text
    assert "<strong>船</strong>" in preview.text
    assert "<script>alert" not in preview.text
    for unsafe in ["onerror=", 'href="javascript:', "<iframe"]:
        assert unsafe not in preview.text
    assert '<img src="x.png"' in preview.text  # the safe part stays


def test_preview_shows_the_english_text_when_there_is_one(editor):
    edit_page = new_guide(editor, title_en="Vanessa pirates", body_en="Take the *ship*.")
    preview = editor.get(f"{edit_page.removesuffix('/edit')}/preview").text
    assert "Vanessa pirates" in preview and "<em>ship</em>" in preview

    chinese_only = new_guide(editor)
    preview = editor.get(f"{chinese_only.removesuffix('/edit')}/preview").text
    assert "没有英文版" in preview


def test_an_editor_cannot_preview_another_persons_guide(editor, someone_elses_guide):
    guide = someone_elses_guide.removesuffix("/edit")
    assert editor.get(f"{guide}/preview").status_code == 404


@pytest.fixture
def three_guides(editor, admin) -> None:
    """Editor: a Chinese-only Vanessa Draft on 6.7 and a bilingual Dooley
    Guide on 6.6, Submitted. Admin: a Vanessa Guide on 6.5, Published."""
    new_guide(editor, title_zh="甲：瓦妮莎草稿")
    submitted = new_guide(editor, title_zh="乙：杜利双语", title_en="Dooley",
                          body_en="Bilingual.", hero_id=hero_id(editor, "杜利（Dooley）"),
                          patch_id=patch_id(editor, "6.6"))
    act(editor, submitted, "submit")
    published = new_guide(admin, title_zh="丙：管理员的瓦妮莎",
                          patch_id=patch_id(admin, "6.5"))
    act(admin, published, "publish")


def listed(c: TestClient, query: str = "") -> set[str]:
    page = c.get(f"/admin/guides{query}").text
    return {title[0] for title in re.findall(r'/edit">([甲乙丙])：', page)}


def filter_value(c: TestClient, select: str, label: str) -> str:
    page = c.get("/admin/guides").text
    match = re.search(rf'<select name="{select}"[^>]*>(.*?)</select>', page, re.DOTALL)
    assert match, f"no {select} filter"
    return option_value(match.group(1), label)


def test_the_content_list_filters_by_status_hero_author_patch_and_language(
        admin, three_guides):
    assert listed(admin) == {"甲", "乙", "丙"}
    assert listed(admin, "?status=submitted") == {"乙"}
    assert listed(admin, "?status=published") == {"丙"}
    vanessa = filter_value(admin, "hero", "瓦妮莎（Vanessa）")
    assert listed(admin, f"?hero={vanessa}") == {"甲", "丙"}
    editor_id = filter_value(admin, "author", "演示编辑")
    assert listed(admin, f"?author={editor_id}") == {"甲", "乙"}
    assert listed(admin, f"?patch={filter_value(admin, 'patch', '6.6')}") == {"乙"}
    assert listed(admin, "?lang=en") == {"乙"}
    assert listed(admin, "?lang=zh") == {"甲", "丙"}
    assert listed(admin, f"?status=draft&hero={vanessa}") == {"甲"}


def test_the_filters_show_what_is_chosen_and_an_empty_result_says_so(admin, three_guides):
    page = admin.get("/admin/guides?status=published&lang=en").text
    assert re.search(r'<option value="published" selected>', page)
    assert "没有符合条件的攻略" in page


def test_an_editors_filtered_list_still_holds_only_their_own_guides(
        editor, admin, three_guides):
    assert listed(editor) == {"甲", "乙"}
    assert listed(editor, "?status=published") == set()
    assert listed(editor, f"?author={filter_value(admin, 'author', '演示管理员')}") == set()


def dashboard_counts(c: TestClient) -> dict[str, int]:
    page = c.get("/admin/dashboard").text
    return {label: int(n) for label, n in
            re.findall(r'<a href="\.\./admin/guides\?status=\w+">(\S+?)：(\d+)</a>', page)}


def test_the_dashboard_counts_guides_by_status_an_editor_their_own(
        editor, admin, three_guides, someone_elses_guide):
    assert dashboard_counts(editor) == {"草稿": 1, "待审核": 1, "已发布": 0}
    assert dashboard_counts(admin) == {"草稿": 1, "待审核": 2, "已发布": 1}


def test_an_editor_under_a_submission_ban_keeps_drafting_but_cannot_submit(admin):
    add_user(email="banned@example.test", password="banned-pw-123", role="editor",
             display_name="禁投编辑", state="submission_ban")
    banned = TestClient(create_app())
    login(banned, "banned@example.test", "banned-pw-123")

    edit_page = new_guide(banned)
    assert save(banned, edit_page, title_zh="还能继续写").status_code == 303
    response = act(banned, edit_page, "submit")
    assert response.status_code == 403
    assert "禁止投稿" in response.text
    assert status_of(banned, edit_page) == "草稿"
