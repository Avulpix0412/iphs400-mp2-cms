"""T05: Admins Return or Unpublish Guides with Review notes (Seam 1: the
console over HTTP; Seam 2: what the Site build writes)."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.publish import render_site
from conftest import csrf_token
from test_t03_guides import (act, admin, editor, new_guide,  # noqa: F401
                             save, slug_of, someone_elses_guide, status_of)
from test_t04_site_build import press_update_site, site, site_text  # noqa: F401

BODY = "## 终局阵容\n\n先拿船，再拿炮。\n\n别忘了买**锚**。"


def submitted_guide(editor: TestClient, **fields) -> str:
    """A Guide the Editor wrote and Submitted; returns its edit page."""
    edit_page = new_guide(editor, **({"body_zh": BODY} | fields))
    assert act(editor, edit_page, "submit").status_code == 303
    return edit_page


def review(c: TestClient, edit_page: str, action: str,
           notes: list[tuple[str, str]]):
    """Fill in the review screen's Review notes and press Return (return) or
    Unpublish (unpublish)."""
    guide = edit_page.removesuffix("/edit")
    page = c.get(f"{guide}/review")
    token = csrf_token(page.text) if page.status_code == 200 else (
        csrf_token(c.get("/admin/guides").text))
    data: dict[str, str | list[str]] = {
        "csrf_token": token, "quote": [quote for quote, _ in notes],
        "advice": [advice for _, advice in notes]}
    return c.post(f"{guide}/{action}", data=data, follow_redirects=False)


def test_admin_returns_a_submitted_guide_with_review_notes(editor, admin):
    edit_page = submitted_guide(editor)
    response = review(admin, edit_page, "return",
                      [("先拿船", "开局拿船太慢，先说明经济。"),
                       ("锚", "锚在 6.7 被削弱了。")])
    assert response.status_code == 303
    assert status_of(editor, edit_page) == "草稿"
    assert "已退回" in admin.get(response.headers["location"]).text


def test_a_return_needs_at_least_one_review_note(editor, admin):
    edit_page = submitted_guide(editor)
    response = review(admin, edit_page, "return", [])
    assert response.status_code == 400
    assert "请至少写一条审核意见" in response.text
    assert status_of(admin, edit_page) == "待审核"


def test_each_review_note_needs_a_quoted_passage_and_advice(editor, admin):
    edit_page = submitted_guide(editor)
    response = review(admin, edit_page, "return",
                      [("先拿船", "说明经济。"), ("锚", "")])
    assert response.status_code == 400
    assert "每条审核意见都要有引用的段落和修改建议" in response.text
    assert "说明经济。</textarea>" in response.text  # what was typed stays
    assert status_of(admin, edit_page) == "待审核"


def test_an_editor_cannot_open_the_review_screen_or_return_a_guide(editor):
    edit_page = submitted_guide(editor)
    guide = edit_page.removesuffix("/edit")
    assert editor.get(f"{guide}/review").status_code == 403
    response = review(editor, edit_page, "return", [("先拿船", "自己退回自己。")])
    assert response.status_code == 403
    assert "只有管理员可以退回攻略" in response.text
    assert status_of(editor, edit_page) == "待审核"


def notes_section(page: str) -> str:
    """The part of the edit page between the heading and the Guide form."""
    top = page.split("<main>", 1)[1].split("<form", 1)[0]
    assert "审核意见" in top, "no Review notes above the form"
    return top


def test_review_notes_appear_at_the_top_of_the_returned_draft(editor, admin):
    edit_page = submitted_guide(editor)
    review(admin, edit_page, "return", [("先拿船", "开局拿船太慢，先说明经济。")])
    top = notes_section(editor.get(edit_page).text)
    assert "先拿船" in top and "开局拿船太慢，先说明经济。" in top
    assert "演示管理员" in top and "退回" in top


def test_review_notes_from_earlier_rounds_stay_after_a_second_return(editor, admin):
    edit_page = submitted_guide(editor)
    review(admin, edit_page, "return", [("先拿船", "第一轮：先说明经济。")])
    assert act(editor, edit_page, "submit").status_code == 303
    review(admin, edit_page, "return", [("锚", "第二轮：锚被削弱了。")])
    for c in (editor, admin):
        top = notes_section(c.get(edit_page).text)
        assert top.index("第二轮") < top.index("第一轮")  # newest round first


def returned_badge(c: TestClient) -> int | None:
    """The number on the dashboard's Returned badge, or None if it isn't shown."""
    match = re.search(r'class="badge"[^>]*>被退回\D*(\d+)', c.get("/admin/dashboard").text)
    return int(match.group(1)) if match else None


def test_the_authors_dashboard_shows_a_badge_counting_returned_guides(editor, admin):
    assert returned_badge(editor) is None
    first, second = submitted_guide(editor), submitted_guide(editor)
    submitted_guide(editor)
    for edit_page in (first, second):
        review(admin, edit_page, "return", [("先拿船", "先说明经济。")])
    assert returned_badge(editor) == 2
    assert returned_badge(admin) is None  # they wrote none of them


def test_the_editor_fixes_a_returned_guide_and_submits_it_again(editor, admin):
    edit_page = submitted_guide(editor)
    review(admin, edit_page, "return", [("先拿船", "先说明经济。")])
    assert save(editor, edit_page, body_zh="先攒钱，再拿船。").status_code == 303
    assert act(editor, edit_page, "submit").status_code == 303
    assert status_of(editor, edit_page) == "待审核"
    assert returned_badge(editor) is None
    assert act(admin, edit_page, "publish").status_code == 303


def preview_of(c: TestClient, edit_page: str) -> str:
    return c.get(f"{edit_page.removesuffix('/edit')}/preview").text


def test_the_preview_highlights_quoted_passages_still_in_the_text(editor, admin):
    edit_page = submitted_guide(editor)
    review(admin, edit_page, "return", [("先拿船，再拿炮", "先说明经济。"),
                                        ("别忘了买", "锚被削弱了。")])
    preview = preview_of(editor, edit_page)
    assert "<mark>先拿船，再拿炮</mark>" in preview
    assert "<mark>别忘了买</mark><strong>锚</strong>" in preview

    save(editor, edit_page, body_zh="## 终局阵容\n\n先拿船，再拿炮。")
    preview = preview_of(editor, edit_page)
    assert "<mark>先拿船，再拿炮</mark>" in preview
    assert "<mark>别忘了买" not in preview
    assert preview.count("<mark>") == 1


def test_a_quoted_passage_must_be_in_the_guides_text(editor, admin):
    edit_page = submitted_guide(editor)
    response = review(admin, edit_page, "return", [("先拿锚", "不存在的段落。")])
    assert response.status_code == 400
    assert "找不到引用的段落" in response.text
    assert status_of(admin, edit_page) == "待审核"


def test_highlighting_keeps_markup_and_unsafe_html_out(editor, admin):
    edit_page = submitted_guide(
        editor, body_zh='<img src="x.png" alt="船>炮"> 船 & 炮 <script>alert(1)</script>')
    review(admin, edit_page, "return", [("船 & 炮", "说清楚。"), ("炮", "哪门炮？")])
    preview = preview_of(editor, edit_page)
    assert "<mark>船 &amp; 炮</mark>" in preview  # overlapping quotes marked as one
    assert 'alt="船>炮"' in preview or 'alt="船&gt;炮"' in preview
    assert "<script>" not in preview


def published_guide(editor: TestClient, admin: TestClient, **fields) -> str:
    edit_page = submitted_guide(editor, **fields)
    assert act(admin, edit_page, "publish").status_code == 303
    return edit_page


def test_admin_unpublishes_a_guide_and_the_next_site_build_leaves_it_out(
        editor, admin, site):
    edit_page = published_guide(editor, admin, title_zh="要撤下的攻略")
    slug = slug_of(admin, edit_page)
    assert press_update_site(admin).status_code == 303
    assert "网站已是最新" in admin.get("/admin/dashboard").text

    response = review(admin, edit_page, "unpublish", [])
    assert response.status_code == 303
    assert "已撤下" in admin.get(response.headers["location"]).text
    assert status_of(editor, edit_page) == "草稿"
    assert returned_badge(editor) == 1
    assert "1 项更改尚未更新到网站" in admin.get("/admin/dashboard").text

    render_site(site)
    assert not (site / "zh" / "guides" / slug).exists()
    assert "要撤下的攻略" not in site_text(site)


def test_admin_unpublishes_with_a_review_note_for_the_author(editor, admin):
    edit_page = published_guide(editor, admin)
    response = review(admin, edit_page, "unpublish", [("锚", "锚已被削弱，这套打法不成立了。")])
    assert response.status_code == 303
    top = notes_section(editor.get(edit_page).text)
    assert "撤下" in top and "锚已被削弱，这套打法不成立了。" in top


def test_only_a_published_guide_can_be_unpublished(editor, admin):
    edit_page = submitted_guide(editor)
    response = review(admin, edit_page, "unpublish", [])
    assert response.status_code == 400
    assert "只能撤下已发布的攻略" in response.text
    assert status_of(admin, edit_page) == "待审核"


def test_an_editor_cannot_unpublish_even_their_own_guide(editor, admin):
    edit_page = published_guide(editor, admin)
    response = review(editor, edit_page, "unpublish", [])
    assert response.status_code == 403
    assert "只有管理员可以撤下攻略" in response.text
    assert status_of(editor, edit_page) == "已发布"


def review_queue(c: TestClient) -> list[str]:
    """The titles in the dashboard's 待审核 queue, which links each to its
    review screen."""
    page = c.get("/admin/dashboard").text
    return re.findall(r'<a href="\.\./admin/guides/\d+/review">([^<]+)</a>', page)


def test_admins_see_a_review_queue_listing_every_submitted_guide(
        editor, admin, someone_elses_guide):
    submitted_guide(editor, title_zh="等待审核的攻略")
    new_guide(editor, title_zh="还在写的草稿")
    published_guide(editor, admin, title_zh="已经发布的攻略")
    returned = submitted_guide(editor, title_zh="被退回的攻略")
    review(admin, returned, "return", [("先拿船", "先说明经济。")])

    assert sorted(review_queue(admin)) == sorted(["等待审核的攻略", "别人的草稿"])
    assert re.search(r"待审核\D{0,40}2", admin.get("/admin/dashboard").text)
    assert review_queue(editor) == []


def test_review_notes_and_highlights_never_reach_the_public_site(editor, admin, site):
    edit_page = submitted_guide(editor, title_en="Vanessa pirates",
                                body_en="Take the ship first.")
    review(admin, edit_page, "return", [("先拿船", "退回意见：先说明经济。"),
                                        ("Take the ship", "Explain the economy.")])
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")
    review(admin, edit_page, "unpublish", [("锚", "撤下意见：锚被削弱了。")])
    act(editor, edit_page, "submit")
    act(admin, edit_page, "publish")

    html = site_text(render_site(site))
    assert "先拿船" in html and "Take the ship first." in html
    for console_only in ["退回意见", "撤下意见", "Explain the economy", "审核意见",
                         "<mark"]:
        assert console_only not in html, console_only


def test_to_an_editor_the_review_routes_of_someone_elses_guide_do_not_exist(
        editor, someone_elses_guide):
    guide = someone_elses_guide.removesuffix("/edit")
    assert editor.get(f"{guide}/review").status_code == 404
    for action in ["return", "unpublish"]:
        assert review(editor, someone_elses_guide, action,
                      [("先拿船", "改掉。")]).status_code == 404, action


def test_overlapping_quoted_passages_are_both_highlighted(editor, admin):
    edit_page = submitted_guide(editor)
    review(admin, edit_page, "return", [("先拿船", "一"), ("船，再拿炮", "二")])
    assert "<mark>先拿船，再拿炮</mark>" in preview_of(editor, edit_page)


def test_a_review_note_sent_as_a_file_is_refused_not_dropped(editor, admin):
    edit_page = published_guide(editor, admin)
    guide = edit_page.removesuffix("/edit")
    token = csrf_token(admin.get(f"{guide}/review").text)
    response = admin.post(f"{guide}/unpublish", data={"csrf_token": token,
                                                      "advice": "说明一下。"},
                          files={"quote": ("q.txt", b"x")}, follow_redirects=False)
    assert response.status_code == 400
    assert status_of(admin, edit_page) == "已发布"
