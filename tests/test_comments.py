"""#37: Comments with moderation, on Guides only (Seam 1: the console over
HTTP; Seam 2: the files the Site build writes). Each test is named after the
acceptance step it checks.

An Admin adds a Reader's Comment in the Moderation queue, in the Comment
language they pick (Chinese unless they choose English), and Accepts or
Rejects it there. Only Accepted Comments reach the site, under their Guide's
page in their own language tree. The issue's "approved" is Accepted here (see
CONTEXT.md: "approve" belongs to Publish).
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.publish import render_site
from conftest import csrf_token
from test_t03_guides import admin, editor  # noqa: F401
from test_t04_site_build import page, pending_changes, press_update_site, published_guide

QUEUE = "/admin/comments"


@pytest.fixture
def site(tmp_path) -> Path:
    return tmp_path / "site"


@pytest.fixture
def slug(admin, editor) -> str:
    """A Published Guide with Chinese and English text."""
    return published_guide(admin, editor, title_zh="瓦妮莎海盗流",
                           title_en="Vanessa pirates", body_en="Take the ship first.")


def guide_id(slug: str) -> str:
    return slug.rsplit("-", 1)[1]


def add_comment(c: TestClient, slug: str, **fields):
    """Fill in the queue's add form the way a browser does, token included.
    The language is left to the form's default unless `lang` is given."""
    queue = c.get(QUEUE).text
    data = {"guide_id": guide_id(slug), "reader_name": "路过的玩家",
            "body": "学到了，谢谢！", "lang": default_language(queue)} | fields
    token = csrf_token(queue)
    return c.post(QUEUE, data={"csrf_token": token, **data}, follow_redirects=False)


def default_language(queue: str) -> str:
    """The Comment language the add form starts with."""
    picker = re.search(r'<select name="lang"[^>]*>(.*?)</select>', queue, re.DOTALL)
    assert picker, "the add form has no language picker"
    selected = re.findall(r'<option value="(\w+)" selected', picker.group(1))
    assert len(selected) == 1
    return selected[0]


def decision_buttons(queue: str) -> dict[str, list[str]]:
    """The Comment ids each of the queue's buttons (accept, reject) is for."""
    found: dict[str, list[str]] = {"accept": [], "reject": []}
    for comment_id, decision in re.findall(
            r'<form method="post" action="(?:\.\./)*admin/comments/(\d+)/(accept|reject)"',
            queue):
        found[decision].append(comment_id)
    return found


def decide(c: TestClient, comment_id: str, decision: str):
    """Press a Comment's accept or reject button in the queue."""
    token = csrf_token(c.get(QUEUE).text)
    return c.post(f"{QUEUE}/{comment_id}/{decision}", data={"csrf_token": token},
                  follow_redirects=False)


def set_created_at(comment_id: str, stored: str) -> None:
    """Arrange a Comment's stored (UTC) time."""
    with closing(sqlite3.connect(settings.database_path())) as conn, conn:
        conn.execute("UPDATE comments SET created_at = ? WHERE id = ?",
                     (stored, comment_id))


def guide_page(slug: str, lang: str = "zh") -> str:
    """The Guide's page in the last Site build."""
    return page(settings.SITE, f"{lang}/guides/{slug}/")


def comment_rows() -> list[sqlite3.Row]:
    with closing(sqlite3.connect(settings.database_path())) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM comments ORDER BY id").fetchall()


def test_step1_the_comments_table_stores_reader_name_body_status_guide_and_time(
        admin, slug):
    response = add_comment(admin, slug, reader_name="阿强", body="船真的好用。")
    assert response.status_code == 303
    assert response.headers["location"] == QUEUE

    [row] = comment_rows()
    assert row["reader_name"] == "阿强"
    assert row["body"] == "船真的好用。"
    assert row["status"] == "pending"
    assert str(row["guide_id"]) == guide_id(slug)
    assert row["lang"] == "zh"  # the default Comment language
    assert row["created_at"]

    queue = admin.get(QUEUE).text
    assert "阿强" in queue and "船真的好用。" in queue and "瓦妮莎海盗流" in queue


def test_step2_the_queue_adds_pending_comments_and_accepts_or_rejects_each_one(
        admin, slug):
    assert add_comment(admin, slug, body="第一条").status_code == 303
    assert add_comment(admin, slug, body="第二条").status_code == 303
    queue = admin.get(QUEUE).text
    assert "第一条" in queue and "第二条" in queue
    first, second = (str(row["id"]) for row in comment_rows())
    assert decision_buttons(queue) == {"accept": [first, second],
                                       "reject": [first, second]}

    response = decide(admin, first, "accept")
    assert response.status_code == 303 and response.headers["location"] == QUEUE
    response = decide(admin, second, "reject")
    assert response.status_code == 303 and response.headers["location"] == QUEUE
    assert [row["status"] for row in comment_rows()] == ["accepted", "rejected"]

    queue = admin.get(QUEUE).text
    assert "第一条" not in queue and "第二条" not in queue
    assert decision_buttons(queue) == {"accept": [], "reject": []}
    # A Comment is decided once, and never edited.
    assert decide(admin, first, "reject").status_code == 400
    assert decide(admin, "999", "accept").status_code == 404
    assert admin.get(f"{QUEUE}/{first}/edit").status_code == 404
    assert decide(admin, first, "edit").status_code == 404


def test_step3_a_pending_comment_is_left_out_and_appears_once_accepted_and_built(
        admin, slug):
    add_comment(admin, slug, reader_name="阿强", body="船真的好用。")
    [row] = comment_rows()
    comment_id = str(row["id"])
    set_created_at(comment_id, "2026-10-17 13:05:42.123")

    assert press_update_site(admin).status_code == 303
    assert "船真的好用。" not in guide_page(slug)
    assert "阿强" not in guide_page(slug)

    decide(admin, comment_id, "accept")
    assert "船真的好用。" not in guide_page(slug)  # not until the next Site build
    assert press_update_site(admin).status_code == 303
    html = guide_page(slug)
    assert "船真的好用。" in html and "阿强" in html
    assert "2026-10-17 21:05" in html  # Beijing time
    assert html.index("船真的好用。") > html.index("先拿船。")  # under the Guide
    assert "船真的好用。" not in guide_page(slug, "en")  # a Chinese Comment


def test_step4_a_rejected_comment_is_left_out_of_the_site_build(admin, slug):
    add_comment(admin, slug, body="广告：加群领福利")
    add_comment(admin, slug, body="有用的评论", lang="en")
    rejected, accepted = (str(row["id"]) for row in comment_rows())
    decide(admin, rejected, "reject")
    decide(admin, accepted, "accept")
    assert press_update_site(admin).status_code == 303
    site = "\n".join(file.read_text() for file in settings.SITE.rglob("*.html"))
    assert "广告：加群领福利" not in site
    assert "有用的评论" in guide_page(slug, "en")


def test_step3_accepting_or_rejecting_counts_as_a_change_not_on_the_site(
        admin, slug):
    add_comment(admin, slug, body="第一条")
    add_comment(admin, slug, body="第二条")
    first, second = (str(row["id"]) for row in comment_rows())
    assert press_update_site(admin).status_code == 303
    assert pending_changes(admin) == "网站已是最新"  # adding one changes nothing yet

    decide(admin, first, "accept")
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    decide(admin, second, "reject")
    assert pending_changes(admin) == "2 项更改尚未更新到网站"
    assert press_update_site(admin).status_code == 303
    assert pending_changes(admin) == "网站已是最新"


def test_step2_the_comment_language_defaults_to_chinese_and_must_be_zh_or_en(
        admin, slug):
    assert default_language(admin.get(QUEUE).text) == "zh"
    for refused in ["fr", "", "zh-CN", "ZH"]:
        response = add_comment(admin, slug, lang=refused, body=f"语言 {refused!r}")
        assert response.status_code == 400, refused
        assert "评论语言只能是中文或英文" in response.text
    assert comment_rows() == []
    assert add_comment(admin, slug, lang="en", body="Nice build").status_code == 303
    assert [row["lang"] for row in comment_rows()] == ["en"]


def test_step2_an_english_comment_on_a_guide_without_english_text_is_refused(
        admin, editor):
    chinese_only = published_guide(admin, editor, title_zh="只有中文")
    response = add_comment(admin, chinese_only, lang="en", body="Nice build")
    assert response.status_code == 400
    assert "这篇攻略没有英文版" in response.text
    assert "Nice build" in response.text  # the form keeps what was typed
    assert comment_rows() == []
    assert add_comment(admin, chinese_only, body="不错").status_code == 303


def test_step2_english_picked_for_text_with_chinese_warns_and_keeps_the_choice(
        admin, slug):
    response = add_comment(admin, slug, lang="en", body="GG 瓦姐 yyds")
    assert response.status_code == 303
    queue = admin.get(QUEUE).text
    assert "选了英文，但内容里有汉字" in queue  # the flash after adding
    assert "选了英文，但内容里有汉字" in admin.get(QUEUE).text  # and on the comment
    [row] = comment_rows()
    assert row["lang"] == "en"

    add_comment(admin, slug, lang="en", body="GG well played")
    add_comment(admin, slug, lang="zh", body="666 xswl")
    assert admin.get(QUEUE).text.count("选了英文，但内容里有汉字") == 1

    for row in comment_rows():
        decide(admin, str(row["id"]), "accept")
    assert press_update_site(admin).status_code == 303
    assert "GG 瓦姐 yyds" in guide_page(slug, "en")
    assert "GG 瓦姐 yyds" not in guide_page(slug, "zh")
    assert "666 xswl" in guide_page(slug, "zh")
    assert "666 xswl" not in guide_page(slug, "en")


D4_PAYLOAD = ('**真香**<script>window.__xss=1</script>'
              '<img src=x onerror="window.__xss=2">')


def test_step5_a_comment_with_the_d4_payload_runs_neither_in_the_queue_nor_the_site_build(
        admin, slug):
    assert add_comment(admin, slug, body=D4_PAYLOAD).status_code == 303
    queue = admin.get(QUEUE).text
    # Rendered like a Guide's Markdown, through the same sanitizer.
    assert "<strong>真香</strong>" in queue
    assert "<script" not in queue and "onerror" not in queue
    assert "window.__xss" not in queue

    [row] = comment_rows()
    decide(admin, str(row["id"]), "accept")
    assert press_update_site(admin).status_code == 303
    html = guide_page(slug)
    assert "<strong>真香</strong>" in html
    assert "<script" not in html and "onerror" not in html
    assert "window.__xss" not in html


def test_step6_every_queue_form_carries_a_csrf_token_and_a_post_without_it_is_refused(
        admin, slug):
    add_comment(admin, slug, body="待处理的评论")
    [row] = comment_rows()
    queue = admin.get(QUEUE).text
    forms = re.findall(r'<form method="post" action="([^"]*admin/comments[^"]*)">(.*?)</form>',
                       queue, re.DOTALL)
    actions = sorted(action.removeprefix("../") for action, _ in forms)
    assert actions == ["admin/comments", f"admin/comments/{row['id']}/accept",
                       f"admin/comments/{row['id']}/reject"]
    for _, body in forms:
        assert re.search(r'<input type="hidden" name="csrf_token" value="[^"]+">', body)

    # Each POST replayed without its token, and with a forged one.
    add_fields = {"guide_id": guide_id(slug), "reader_name": "重放", "body": "重放的评论",
                  "lang": "zh"}
    for path, fields in [(QUEUE, add_fields), (f"{QUEUE}/{row['id']}/accept", {}),
                         (f"{QUEUE}/{row['id']}/reject", {})]:
        for token in [{}, {"csrf_token": "forged"}]:
            response = admin.post(path, data=fields | token, follow_redirects=False)
            assert response.status_code == 403, (path, token)
    assert [(r["body"], r["status"]) for r in comment_rows()] == [("待处理的评论", "pending")]


def test_step7_an_editor_who_requests_the_moderation_queue_is_refused(admin, editor, slug):
    assert "admin/comments" in admin.get("/admin/dashboard").text  # in the navigation
    assert "admin/comments" not in editor.get("/admin/dashboard").text
    response = editor.get(QUEUE, follow_redirects=False)
    assert response.status_code == 403
    assert "只有管理员" in response.text

    token = csrf_token(editor.get("/admin/dashboard").text)
    response = editor.post(QUEUE, data={"csrf_token": token, "guide_id": guide_id(slug),
                                        "reader_name": "编辑", "body": "偷偷加的",
                                        "lang": "zh"}, follow_redirects=False)
    assert response.status_code == 403
    assert comment_rows() == []


def test_step1_a_database_made_before_comments_keeps_working(tmp_path, monkeypatch,
                                                             client_as):
    """The comments table is only added, so an existing cms.db gains it on
    connect, with its Guides and accounts as they were."""
    from app import db
    from conftest import DEMO_USERS, add_user
    from test_t02_heroes_patches import add_hero, add_patch

    old = tmp_path / "before-37.db"
    with closing(sqlite3.connect(old)) as conn:
        conn.executescript(db.SCHEMA.split("-- A Reader's Comment on a Guide")[0])
        assert "comments" not in {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    monkeypatch.setenv("CMS_DATABASE", str(old))
    for role, user in DEMO_USERS.items():
        add_user(email=user["email"], password=user["password"], role=role,
                 display_name=user["display_name"])
    admin = client_as("admin")
    add_hero(admin, "瓦妮莎", "Vanessa")
    add_patch(admin, "6.7")
    slug = published_guide(admin)
    assert add_comment(admin, slug).status_code == 303
    assert [row["status"] for row in comment_rows()] == ["pending"]


def test_step2_the_queue_links_relatively_and_its_links_work(admin, slug):
    from test_console_links import check_page

    add_comment(admin, slug)
    check_page(admin, QUEUE, admin.get(QUEUE).text)
    response = add_comment(admin, slug, reader_name="")  # refused, shown at its POST URL
    assert response.status_code == 400 and "请填写读者的名字" in response.text
    check_page(admin, QUEUE, response.text)


def test_step1_a_guide_deleted_for_good_takes_its_comments_with_it(admin, editor):
    from test_t03_guides import new_guide, act
    from test_t06_revisions_trash import delete

    edit_page = new_guide(admin, title_zh="要删除的攻略")
    act(admin, edit_page, "publish")
    guide = edit_page.split("/")[3]
    token = csrf_token(admin.get(QUEUE).text)
    admin.post(QUEUE, data={"csrf_token": token, "guide_id": guide, "lang": "zh",
                            "reader_name": "读者", "body": "评论"})
    assert len(comment_rows()) == 1
    [row] = comment_rows()
    delete(admin, edit_page)
    # In the Trash, the Guide and its Comments are gone from the queue.
    assert "要删除的攻略" not in admin.get(QUEUE).text
    assert decide(admin, str(row["id"]), "accept").status_code == 404
    token = csrf_token(admin.get("/admin/trash").text)
    response = admin.post(f"/admin/trash/{guide}/delete", data={"csrf_token": token},
                          follow_redirects=False)
    assert response.status_code == 303
    assert comment_rows() == []
