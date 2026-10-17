"""T06: Editors revise or delete their Published Guides (Seam 1: the console
over HTTP; Seam 2: what the Site build writes)."""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from app.publish import render_site
from conftest import csrf_token
from test_t02_heroes_patches import submit as fill_in
from test_t03_guides import (act, admin, editor, hero_id, new_guide,  # noqa: F401
                             patch_id, save, slug_of, someone_elses_guide, status_of)
from test_t04_site_build import (page, pending_changes, press_update_site,  # noqa: F401
                                 site, site_text)
from test_t05_review import (notes_section, preview_of, published_guide, submitted_guide,
                             returned_badge, review)


def open_revision(c: TestClient, edit_page: str):
    """Press 修订 on a Published Guide's edit page."""
    return fill_in(c, edit_page, f"{edit_page.removesuffix('/edit')}/revisions")


def revision_page(edit_page: str) -> str:
    """The edit page of the Guide's open Revision."""
    return f"{edit_page.removesuffix('/edit')}/revision/edit"


def test_editor_opens_a_revision_saves_it_as_a_draft_and_submits_it(editor, admin):
    edit_page = published_guide(editor, admin, title_zh="瓦妮莎海盗流")
    response = open_revision(editor, edit_page)
    assert response.status_code == 303
    revision = response.headers["location"]
    assert revision == revision_page(edit_page)
    page = editor.get(revision).text
    assert 'value="瓦妮莎海盗流"' in page  # a copy of the Published texts
    assert status_of(editor, revision) == "草稿"

    assert save(editor, revision, title_zh="瓦妮莎海盗流（6.8）").status_code == 303
    assert 'value="瓦妮莎海盗流（6.8）"' in editor.get(revision).text
    assert act(editor, revision, "submit").status_code == 303
    assert status_of(editor, revision) == "待审核"

    # The Published Guide itself is untouched.
    assert status_of(editor, edit_page) == "已发布"
    assert "<h1>瓦妮莎海盗流</h1>" in preview_of(editor, edit_page)


def test_a_second_revision_is_refused_while_one_is_open(editor, admin):
    edit_page = published_guide(editor, admin)
    assert open_revision(editor, edit_page).status_code == 303
    page = editor.get(edit_page).text
    assert "修订这篇攻略" not in page and "打开修订" in page

    token = csrf_token(page)
    response = editor.post(f"{edit_page.removesuffix('/edit')}/revisions",
                           data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 400
    assert "已经有一份修订" in response.text


def test_only_the_author_opens_a_revision_and_only_on_a_published_guide(
        editor, admin, someone_elses_guide):
    draft = new_guide(editor)
    assert "修订这篇攻略" not in editor.get(draft).text
    response = open_revision(editor, draft)
    assert response.status_code == 400 and "只有已发布的攻略需要修订" in response.text

    token = csrf_token(editor.get("/admin/guides").text)
    elsewhere = someone_elses_guide.removesuffix("/edit")
    assert editor.post(f"{elsewhere}/revisions", data={"csrf_token": token},
                       follow_redirects=False).status_code == 404
    assert editor.get(f"{elsewhere}/revision/edit").status_code == 404

    # An Admin edits a Published Guide directly instead.
    published = published_guide(editor, admin)
    assert "修订这篇攻略" not in admin.get(published).text
    assert open_revision(admin, published).status_code == 400


def test_while_a_revision_is_open_the_site_build_shows_the_published_content(
        editor, admin, site):
    edit_page = published_guide(editor, admin, title_zh="旧标题", body_zh="旧的正文。")
    slug = slug_of(admin, edit_page)
    open_revision(editor, edit_page)
    revision = revision_page(edit_page)
    save(editor, revision, title_zh="新标题", body_zh="新的正文。")
    act(editor, revision, "submit")

    html = site_text(render_site(site))
    assert "旧标题" in page(site, f"zh/guides/{slug}/")
    assert "新标题" not in html and "新的正文" not in html


def updated_at(c: TestClient, edit_page: str) -> str:
    match = re.search(r"更新于 ([\d:. -]+)", c.get(edit_page).text)
    assert match, "edit page shows no update time"
    return match.group(1).strip()


def test_publishing_a_revision_replaces_the_guides_content_and_keeps_its_url(
        editor, admin, site):
    edit_page = published_guide(editor, admin, title_zh="旧标题", body_zh="旧的正文。")
    slug, before = slug_of(admin, edit_page), updated_at(admin, edit_page)
    open_revision(editor, edit_page)
    revision = revision_page(edit_page)
    save(editor, revision, title_zh="新标题", body_zh="新的正文。",
         title_en="New title", body_en="New text.",
         hero_id=hero_id(editor, "杜利（Dooley）"),
         patch_id=patch_id(editor, "6.6"))
    act(editor, revision, "submit")

    response = act(admin, revision, "publish")
    assert response.status_code == 303
    assert response.headers["location"] == edit_page
    assert "修订已发布" in admin.get(edit_page).text
    assert admin.get(revision).status_code == 404  # the Revision is gone
    assert status_of(admin, edit_page) == "已发布"
    assert slug_of(admin, edit_page) == slug
    after = updated_at(admin, edit_page)
    assert after > before

    render_site(site)
    zh = page(site, f"zh/guides/{slug}/")
    assert "新标题" in zh and "新的正文" in zh and "旧标题" not in zh
    assert "杜利" in zh and "6.6" in zh and f"更新于 {after[:10]}" in zh
    assert "New title" in page(site, f"en/guides/{slug}/")
    assert "旧标题" not in site_text(site)


def published_revision(editor: TestClient, admin: TestClient, edit_page: str,
                       **fields) -> None:
    """The Editor revises their Published Guide and an Admin Publishes it."""
    assert open_revision(editor, edit_page).status_code == 303
    revision = revision_page(edit_page)
    assert save(editor, revision, **fields).status_code == 303
    assert act(editor, revision, "submit").status_code == 303
    assert act(admin, revision, "publish").status_code == 303


def test_a_revision_that_changes_the_patch_moves_the_guide_to_that_patch_group(
        editor, admin, site):
    published_guide(editor, admin, title_zh="一直是6.7的攻略")
    edit_page = published_guide(editor, admin, title_zh="要改版本的攻略")
    hero = page(render_site(site), "zh/heroes/vanessa/")
    assert hero.index("<h2>6.7</h2>") < hero.index("要改版本的攻略")
    assert "<h2>6.6</h2>" not in hero

    published_revision(editor, admin, edit_page, patch_id=patch_id(editor, "6.6"))
    hero = page(render_site(site), "zh/heroes/vanessa/")
    assert (hero.index("<h2>6.7</h2>") < hero.index("一直是6.7的攻略")
            < hero.index("<h2>6.6</h2>") < hero.index("要改版本的攻略"))


def submitted_revision(editor: TestClient, edit_page: str, **fields) -> str:
    """The Editor revises their Published Guide and Submits the Revision;
    returns the Revision's edit page."""
    assert open_revision(editor, edit_page).status_code == 303
    revision = revision_page(edit_page)
    assert save(editor, revision, **fields).status_code == 303
    assert act(editor, revision, "submit").status_code == 303
    return revision


def test_returning_a_revision_with_review_notes_leaves_the_live_guide_unchanged(
        editor, admin, site):
    edit_page = published_guide(editor, admin, title_zh="旧标题", body_zh="先拿船。")
    slug = slug_of(admin, edit_page)
    revision = submitted_revision(editor, edit_page, body_zh="改成先拿炮。")
    press_update_site(admin)

    screen = admin.get(f"{revision.removesuffix('/edit')}/review")
    assert screen.status_code == 200 and "改成先拿炮。" in screen.text
    response = review(admin, revision, "return", [("先拿炮", "炮在 6.8 被削弱了。")])
    assert response.status_code == 303
    assert response.headers["location"] == revision

    assert status_of(editor, revision) == "草稿"
    top = notes_section(editor.get(revision).text)
    assert "先拿炮" in top and "炮在 6.8 被削弱了。" in top
    assert "<mark>先拿炮</mark>" in preview_of(editor, revision)

    assert status_of(editor, edit_page) == "已发布"
    assert "先拿船。" in preview_of(editor, edit_page)
    assert "炮在 6.8" not in editor.get(edit_page).text
    assert pending_changes(admin) == "网站已是最新"
    assert "先拿船" in page(render_site(site), f"zh/guides/{slug}/")


def test_a_returned_revision_is_badged_on_the_authors_dashboard_and_resubmitted(
        editor, admin):
    edit_page = published_guide(editor, admin)
    revision = submitted_revision(editor, edit_page, body_zh="改成先拿炮。")
    review(admin, revision, "return", [("先拿炮", "炮被削弱了。")])
    dashboard = editor.get("/admin/dashboard").text
    assert returned_badge(editor) == 1
    assert 'href="../admin/guides/' in dashboard and '/revision/edit"' in dashboard

    assert act(editor, revision, "submit", body_zh="改成先拿锚。").status_code == 303
    assert returned_badge(editor) is None
    assert status_of(editor, revision) == "待审核"


def test_a_submitted_revision_waits_in_the_admins_review_queue(editor, admin):
    edit_page = published_guide(editor, admin, title_zh="旧标题")
    revision = submitted_revision(editor, edit_page, title_zh="修订后的标题")
    dashboard = admin.get("/admin/dashboard").text
    review_screen = revision.removesuffix("/edit").removeprefix("/") + "/review"
    assert f'href="../{review_screen}">修订后的标题</a>（修订）' in dashboard

    act(admin, revision, "publish")
    assert "修订后的标题</a>（修订）" not in admin.get("/admin/dashboard").text


def test_an_admins_edit_to_a_published_guide_applies_with_no_revision(
        editor, admin, site):
    edit_page = published_guide(editor, admin, title_zh="有错字的标题")
    slug = slug_of(admin, edit_page)
    assert save(admin, edit_page, title_zh="改好的标题").status_code == 303
    assert "打开修订" not in admin.get(edit_page).text
    assert "打开修订" not in editor.get(edit_page).text
    assert "改好的标题" in page(render_site(site), f"zh/guides/{slug}/")


def test_unpublishing_a_guide_holds_its_revision_until_it_is_published_again(
        editor, admin):
    edit_page = published_guide(editor, admin, title_zh="旧标题")
    revision = submitted_revision(editor, edit_page, title_zh="修订后的标题")
    review(admin, edit_page, "unpublish", [])

    assert status_of(editor, edit_page) == "草稿"
    assert status_of(editor, revision) == "草稿"  # out of the review queue
    assert "修订后的标题" not in admin.get("/admin/dashboard").text
    assert "打开修订" in editor.get(edit_page).text  # the work is kept
    response = act(editor, revision, "submit")
    assert response.status_code == 400 and "重新发布" in response.text

    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")
    assert act(editor, revision, "submit").status_code == 303


def delete_page(edit_page: str) -> str:
    return f"{edit_page.removesuffix('/edit')}/delete"


def delete(c: TestClient, edit_page: str):
    """Follow the edit page's 删除 link and confirm on the page it leads to."""
    page = c.get(edit_page).text
    assert f'href="../../../{delete_page(edit_page).removeprefix("/")}"' in page
    confirm = c.get(delete_page(edit_page))
    assert confirm.status_code == 200 and "确定要删除" in confirm.text
    return fill_in(c, delete_page(edit_page), delete_page(edit_page))


def test_an_editor_deletes_their_own_guide_in_any_status_after_confirming(
        editor, admin):
    draft = new_guide(editor, title_zh="草稿攻略")
    submitted = new_guide(editor, title_zh="待审核攻略")
    act(editor, submitted, "submit")
    published = published_guide(editor, admin, title_zh="已发布攻略")
    for edit_page in (draft, submitted, published):
        response = delete(editor, edit_page)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/guides"
        assert "已移到回收站" in editor.get("/admin/guides").text
        assert editor.get(edit_page).status_code == 404
    listing = editor.get("/admin/guides").text
    for title in ("草稿攻略", "待审核攻略", "已发布攻略"):
        assert title not in listing


def test_an_editor_cannot_delete_someone_elses_guide(editor, someone_elses_guide):
    page = delete_page(someone_elses_guide)
    assert editor.get(page).status_code == 404
    token = csrf_token(editor.get("/admin/guides").text)
    assert editor.post(page, data={"csrf_token": token},
                       follow_redirects=False).status_code == 404


def test_a_deleted_guide_is_in_the_trash_for_admins_only_and_off_the_site(
        editor, admin, site):
    edit_page = published_guide(editor, admin, title_zh="要删除的攻略")
    slug = slug_of(admin, edit_page)
    press_update_site(admin)
    delete(editor, edit_page)

    trash = admin.get("/admin/trash")
    assert trash.status_code == 200 and "要删除的攻略" in trash.text
    assert 'href="../admin/trash"' in admin.get("/admin/dashboard").text
    assert editor.get("/admin/trash").status_code == 403
    assert 'href="../admin/trash"' not in editor.get("/admin/dashboard").text
    assert "要删除的攻略" not in admin.get("/admin/guides").text

    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    html = site_text(render_site(site))
    assert "要删除的攻略" not in html
    assert not (site / "zh" / "guides" / slug).exists()


def restore(c: TestClient, title: str):
    """Press 恢复 beside the Guide called `title` in the Trash."""
    trash = c.get("/admin/trash").text
    match = re.search(rf"{re.escape(title)}.*?action=\"\.\./(admin/trash/\d+/restore)\"",
                      trash, re.DOTALL)
    assert match, f"no 恢复 button for {title}"
    return fill_in(c, "/admin/trash", f"/{match.group(1)}")


def test_an_admin_restores_a_guide_from_the_trash_exactly_as_it_was(
        editor, admin, site):
    published = published_guide(editor, admin, title_zh="已发布的攻略")
    slug = slug_of(admin, published)
    open_revision(editor, published)
    save(editor, revision_page(published), title_zh="修订中的标题")
    returned = submitted_guide(editor, title_zh="被退回的攻略")
    review(admin, returned, "return", [("先拿船", "先说明经济。")])
    press_update_site(admin)
    for edit_page in (published, returned):
        delete(editor, edit_page)
    assert returned_badge(editor) is None

    for title in ("已发布的攻略", "被退回的攻略"):
        response = restore(admin, title)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/trash"
        assert "已恢复" in admin.get("/admin/trash").text
    assert "已发布的攻略" not in admin.get("/admin/trash").text

    assert status_of(editor, published) == "已发布"
    assert slug_of(editor, published) == slug
    assert 'value="修订中的标题"' in editor.get(revision_page(published)).text
    assert status_of(editor, returned) == "草稿"
    assert returned_badge(editor) == 1
    assert "先说明经济。" in notes_section(editor.get(returned).text)

    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    assert "已发布的攻略" in page(render_site(site), f"zh/guides/{slug}/")


def test_an_editor_cannot_restore_from_the_trash(editor, admin):
    edit_page = new_guide(editor, title_zh="删掉的草稿")
    delete(editor, edit_page)
    guide = edit_page.split("/")[3]
    token = csrf_token(editor.get("/admin/guides").text)
    assert editor.post(f"/admin/trash/{guide}/restore", data={"csrf_token": token},
                       follow_redirects=False).status_code == 403
    assert "删掉的草稿" in admin.get("/admin/trash").text


def test_an_admin_deletes_a_guide_from_the_trash_for_good(editor, admin):
    edit_page = published_guide(editor, admin, title_zh="要彻底删除的攻略")
    revision = submitted_revision(editor, edit_page, body_zh="改成先拿炮。")
    review(admin, revision, "return", [("先拿炮", "炮被削弱了。")])
    delete(editor, edit_page)
    guide = edit_page.split("/")[3]
    forever = f"/admin/trash/{guide}/delete"
    assert f'href="../{forever.removeprefix("/")}"' in admin.get("/admin/trash").text
    confirm = admin.get(forever)
    assert confirm.status_code == 200 and "无法恢复" in confirm.text

    response = fill_in(admin, forever, forever)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/trash"
    trash = admin.get("/admin/trash").text
    assert "已彻底删除" in trash and "要彻底删除的攻略</td>" not in trash
    assert admin.get(edit_page).status_code == 404
    token = csrf_token(trash)
    assert admin.post(f"/admin/trash/{guide}/restore", data={"csrf_token": token},
                      follow_redirects=False).status_code == 404


def test_only_a_guide_in_the_trash_is_deleted_for_good_and_only_by_an_admin(
        editor, admin):
    edit_page = new_guide(editor, title_zh="还在用的草稿")
    guide = edit_page.split("/")[3]
    token = csrf_token(admin.get("/admin/trash").text)
    assert admin.post(f"/admin/trash/{guide}/delete", data={"csrf_token": token},
                      follow_redirects=False).status_code == 404
    assert admin.get(f"/admin/trash/{guide}/delete").status_code == 404

    delete(editor, edit_page)
    token = csrf_token(editor.get("/admin/guides").text)
    assert editor.post(f"/admin/trash/{guide}/delete", data={"csrf_token": token},
                       follow_redirects=False).status_code == 403
    assert "还在用的草稿" in admin.get("/admin/trash").text


# The Guide tables as T05 left them, before T06 added to them.
TABLES_BEFORE_T06 = """
CREATE TABLE guides (
    id           INTEGER PRIMARY KEY,
    slug         TEXT UNIQUE,
    title_zh     TEXT NOT NULL DEFAULT '',
    body_zh      TEXT NOT NULL DEFAULT '',
    title_en     TEXT NOT NULL DEFAULT '',
    body_en      TEXT NOT NULL DEFAULT '',
    hero_id      INTEGER NOT NULL REFERENCES game_terms (id),
    patch_id     INTEGER NOT NULL REFERENCES patches (id),
    author_id    INTEGER NOT NULL REFERENCES users (id),
    status       TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft', 'submitted', 'published')),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    published_at TEXT
);
CREATE TABLE review_rounds (
    id         INTEGER PRIMARY KEY,
    guide_id   INTEGER NOT NULL REFERENCES guides (id) ON DELETE CASCADE,
    admin_id   INTEGER NOT NULL REFERENCES users (id),
    kind       TEXT NOT NULL CHECK (kind IN ('return', 'unpublish')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
);
"""


@pytest.fixture
def database_from_before_t06(tmp_path, monkeypatch) -> None:
    """Point the console at a database made before T06, holding the demo
    users. Listed before `admin` and `editor`, so they use it too."""
    from conftest import DEMO_USERS, add_user

    old = tmp_path / "before-t06.db"
    with closing(sqlite3.connect(old)) as conn:
        conn.executescript(TABLES_BEFORE_T06)
    monkeypatch.setenv("CMS_DATABASE", str(old))
    for role, user in DEMO_USERS.items():
        add_user(email=user["email"], password=user["password"], role=role,
                 display_name=user["display_name"])


def test_a_database_made_before_revisions_and_the_trash_still_works(
        database_from_before_t06, editor, admin):
    edit_page = published_guide(editor, admin)
    revision = submitted_revision(editor, edit_page, body_zh="改成先拿炮。")
    assert review(admin, revision, "return", [("先拿炮", "炮被削弱了。")]).status_code == 303
    assert returned_badge(editor) == 1
    assert delete(editor, edit_page).status_code == 303
    assert restore(admin, "瓦妮莎海盗流").status_code == 303
    assert status_of(editor, edit_page) == "已发布"


def delete_for_good(c: TestClient, edit_page: str):
    forever = f"/admin/trash/{edit_page.split('/')[3]}/delete"
    return fill_in(c, forever, forever)


def test_deleting_a_published_guide_for_good_stays_a_change_not_on_the_site(
        editor, admin):
    edit_page = published_guide(editor, admin)
    press_update_site(admin)
    delete(editor, edit_page)
    assert delete_for_good(admin, edit_page).status_code == 303
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    press_update_site(admin)
    assert pending_changes(admin) == "网站已是最新"


def test_an_editors_published_guide_offers_a_revision_not_a_form_that_fails(
        editor, admin):
    edit_page = published_guide(editor, admin)
    page = editor.get(edit_page).text
    assert "修订这篇攻略" in page
    assert 'name="body_zh"' not in page and ">保存<" not in page
    assert 'name="body_zh"' in admin.get(edit_page).text


def test_the_review_screen_warns_when_the_guide_changed_after_the_revision_opened(
        editor, admin):
    edit_page = published_guide(editor, admin, title_zh="旧标题")
    revision = submitted_revision(editor, edit_page, title_zh="修订后的标题")
    review_screen = f"{revision.removesuffix('/edit')}/review"
    assert "修订打开之后" not in admin.get(review_screen).text

    save(admin, edit_page, title_zh="管理员改过的标题")
    assert "修订打开之后" in admin.get(review_screen).text
    assert "修订打开之后" in editor.get(revision).text


def test_the_author_discards_their_revision_and_can_open_a_new_one(editor, admin):
    edit_page = published_guide(editor, admin, title_zh="旧标题")
    revision = submitted_revision(editor, edit_page, title_zh="不要了的修订")
    discard = f"{revision.removesuffix('/edit')}/delete"
    assert f'href="../../../../{discard.removeprefix("/")}"' in editor.get(revision).text
    confirm = editor.get(discard)
    assert confirm.status_code == 200 and "放弃" in confirm.text

    response = fill_in(editor, discard, discard)
    assert response.status_code == 303
    assert response.headers["location"] == edit_page
    assert "修订已放弃" in editor.get(edit_page).text
    assert editor.get(revision).status_code == 404
    assert "不要了的修订" not in admin.get("/admin/dashboard").text
    assert status_of(editor, edit_page) == "已发布"
    assert open_revision(editor, edit_page).status_code == 303
