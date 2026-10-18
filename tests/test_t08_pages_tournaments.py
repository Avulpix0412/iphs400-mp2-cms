"""T08: Admins write Pages and Tournament items, and the public navigation is
built from them.

Content is set up through the console (Seam 1); what Readers get is checked in
the files `render_site` writes (Seam 2)."""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.publish import render_site
from conftest import csrf_token
from test_t02_heroes_patches import submit as fill_in
from test_t03_guides import admin, editor, form_values, new_guide, option_value  # noqa: F401
from test_t04_site_build import (SWITCH, page, pending_changes, press_update_site,  # noqa: F401
                                 published_guide, site,
                                 site_text, switch)

PAGE = {"slug": "about", "title_zh": "关于", "body_zh": "我们是几位主播。",
        "title_en": "", "body_en": ""}


def new_page(admin: TestClient, **fields) -> str:
    """Save a new Page as a Draft; returns its edit page."""
    response = fill_in(admin, "/admin/pages/new", "/admin/pages", **(PAGE | fields))
    assert response.status_code == 303, response.text
    edit_page = response.headers["location"]
    assert re.fullmatch(r"/admin/pages/\d+/edit", edit_page)
    return edit_page


def save_page(admin: TestClient, edit_page: str, **fields):
    """Change some fields of a saved Page, keeping the rest as they are."""
    current = form_values(admin.get(edit_page).text)
    return fill_in(admin, edit_page, edit_page.removesuffix("/edit"),
                   **(current | fields))


def page_act(admin: TestClient, edit_page: str, action: str):
    """Press a Page's button (publish, unpublish) as a bare post."""
    return fill_in(admin, edit_page, f"{edit_page.removesuffix('/edit')}/{action}")


def published_page(admin: TestClient, **fields) -> str:
    edit_page = new_page(admin, **fields)
    assert page_act(admin, edit_page, "publish").status_code == 303
    return edit_page


NAV = re.compile(r'<nav class="site-nav"[^>]*>(.*?)</nav>', re.DOTALL)
NAV_LINK = re.compile(r'<a href="([^"]+)"[^>]*>([^<]+)</a>')


def navigation(site: Path, path: str) -> list[tuple[str, str]]:
    """The public navigation on the page at `path`: (the folder each link
    leads to, from the site root; its text)."""
    match = NAV.search(page(site, path))
    assert match, f"no navigation on {path}"
    return [(posixpath.normpath(posixpath.join(path, href)) + "/", text.strip())
            for href, text in NAV_LINK.findall(match.group(1))]


def assert_fallback_notice(site: Path, path: str, lands_on: str) -> None:
    """The language switch on the page at `path` leads to `lands_on` with a
    notice, shown only when arrived at through that link, saying the page
    has no English text."""
    link = re.search(SWITCH, page(site, path))
    assert link
    fragment = link.group(1).partition("#")[2]
    notice = re.search(rf'id="{fragment}">(.*?)</p>', page(site, lands_on), re.DOTALL)
    assert fragment and notice, f"no notice on {lands_on}"
    assert "has no English text yet" in " ".join(notice.group(1).split())


def generated_pages(site: Path, lang: str) -> list[str]:
    """The path of every page in one language tree."""
    return sorted(f"{file.parent.relative_to(site)}/"
                  for file in (site / lang).rglob("index.html"))


def test_a_published_page_appears_in_the_navigation_of_every_page_after_guides_and_tournaments(
        admin, site):
    published_page(admin, slug="about", title_zh="关于")
    published_guide(admin)
    render_site(site)

    paths = generated_pages(site, "zh")
    assert len(paths) > 5
    for path in paths:
        assert navigation(site, path) == [
            ("zh/guides/", "攻略"), ("zh/tournaments/", "锦标赛"), ("zh/about/", "关于")], path
    assert "我们是几位主播。" in page(site, "zh/about/")


def test_a_draft_page_appears_nowhere_on_the_site(admin, site):
    new_page(admin, slug="draft-page", title_zh="还在写的页面", body_zh="草稿正文")
    render_site(site)
    assert not (site / "zh/draft-page").exists()
    assert "还在写的页面" not in site_text(site) and "草稿正文" not in site_text(site)


def test_a_page_without_english_text_stays_out_of_the_english_tree(admin, site):
    published_page(admin, slug="about", title_zh="关于")
    published_page(admin, slug="rules", title_zh="规则", title_en="Rules",
                   body_en="Be kind.")
    render_site(site)

    assert not (site / "en/about").exists()
    assert navigation(site, "en/") == [("en/guides/", "Guides"),
                                       ("en/tournaments/", "Tournaments"),
                                       ("en/rules/", "Rules")]
    assert "Be kind." in page(site, "en/rules/")
    assert switch(site, "zh/rules/") == "en/rules/"
    # The switch on a Chinese-only Page leads to the English home page, with
    # a notice saying why.
    assert switch(site, "zh/about/") == "en/"
    assert_fallback_notice(site, "zh/about/", "en/")


def test_the_admin_sees_a_saved_page_in_the_page_list(admin):
    edit_page = new_page(admin, slug="about", title_zh="关于我们")
    listed = admin.get("/admin/pages").text
    assert "关于我们" in listed and "<code>about</code>" in listed and "草稿" in listed
    assert f'href="../{edit_page.removeprefix("/")}"' in listed


@pytest.mark.parametrize("slug, message", [
    ("", "请填写网址名"),
    ("关于", "只能包含小写英文字母、数字和连字符"),
    ("About Us", "只能包含小写英文字母、数字和连字符"),
    ("café", "只能包含小写英文字母、数字和连字符"),
    ("tournaments", "是网站自己用的"),
    ("guides", "是网站自己用的"),
])
def test_a_page_slug_must_be_ascii_and_not_one_the_site_uses(admin, slug, message):
    response = fill_in(admin, "/admin/pages/new", "/admin/pages", **(PAGE | {"slug": slug}))
    assert response.status_code == 400
    assert message in response.text
    assert "还没有页面" in admin.get("/admin/pages").text


def test_two_pages_cannot_share_a_slug(admin):
    new_page(admin, slug="about")
    response = fill_in(admin, "/admin/pages/new", "/admin/pages",
                       **(PAGE | {"slug": "about", "title_zh": "另一个关于"}))
    assert response.status_code == 400 and "已被另一个页面使用" in response.text

    rules = new_page(admin, slug="rules", title_zh="规则")
    response = save_page(admin, rules, slug="about")
    assert response.status_code == 400 and "已被另一个页面使用" in response.text
    assert "<code>rules</code>" in admin.get("/admin/pages").text


def test_an_edit_to_a_published_page_reaches_the_site_at_the_next_build(admin, site):
    about = published_page(admin, slug="about", body_zh="旧的介绍。")
    assert save_page(admin, about, body_zh="新的介绍。").status_code == 303
    html = page(render_site(site), "zh/about/")
    assert "新的介绍。" in html and "旧的介绍。" not in html


def test_an_unpublished_page_goes_back_to_draft_and_leaves_the_site(admin, site):
    about = published_page(admin, slug="about")
    assert page_act(admin, about, "unpublish").status_code == 303
    assert "状态：草稿" in admin.get(about).text
    render_site(site)
    assert not (site / "zh/about").exists()
    assert ("zh/about/", "关于") not in navigation(site, "zh/")


def test_deleting_a_page_asks_first_then_removes_it_for_good(admin, site):
    about = published_page(admin, slug="about", title_zh="关于")
    confirm = admin.get(about.replace("/edit", "/delete"))
    assert confirm.status_code == 200
    assert "确定要彻底删除页面《关于》吗？" in confirm.text and "无法恢复" in confirm.text
    # Nothing is deleted until the confirmation is sent.
    assert "关于" in admin.get("/admin/pages").text

    response = fill_in(admin, about.replace("/edit", "/delete"),
                       about.replace("/edit", "/delete"))
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/pages"
    assert "还没有页面" in admin.get("/admin/pages").text
    assert admin.get(about).status_code == 404
    render_site(site)
    assert not (site / "zh/about").exists()


@pytest.mark.parametrize("fields, message", [
    ({"title_zh": ""}, "发布前请填写中文标题和中文正文"),
    ({"body_zh": "  "}, "发布前请填写中文标题和中文正文"),
    ({"title_en": "About"}, "英文版的标题和正文要么都填写，要么都留空"),
])
def test_a_page_needs_chinese_text_and_whole_english_text_to_be_published(
        admin, fields, message):
    edit_page = new_page(admin, **fields)
    response = page_act(admin, edit_page, "publish")
    assert response.status_code == 400 and message in response.text
    assert "状态：草稿" in admin.get(edit_page).text


def test_a_published_page_cannot_be_saved_without_its_chinese_text(admin):
    about = published_page(admin)
    response = save_page(admin, about, body_zh="")
    assert response.status_code == 400 and "发布前请填写中文标题和中文正文" in response.text
    assert "我们是几位主播。" in admin.get(about).text


def test_page_markdown_is_sanitized_and_shows_game_terms_in_each_language(admin, site):
    published_page(admin, slug="about",
                   body_zh='我们只玩 [[Vanessa]]。<script>alert("x")</script>'
                           '<img src="x.png" onerror="alert(1)">',
                   title_en="About", body_en="We only play [[瓦妮莎]].")
    render_site(site)
    zh, en = page(site, "zh/about/"), page(site, "en/about/")
    assert '我们只玩 <span class="term">瓦妮莎</span>。' in zh
    assert "<script" not in zh and "onerror" not in zh
    assert 'We only play <span class="term">Vanessa</span>.' in en


def test_the_page_preview_shows_it_as_readers_will_with_game_term_warnings(admin):
    about = new_page(admin, body_zh="**加粗** [[瓦姐]] 和 [[没有这个]]<script>x</script>")
    preview = admin.get(about.replace("/edit", "/preview"))
    assert preview.status_code == 200
    assert "<strong>加粗</strong>" in preview.text and "<script>x" not in preview.text
    assert "[[没有这个]] 没有对应的游戏术语" in preview.text
    assert "没有英文版，不会出现在英文网站上" in preview.text


TOURNAMENT_ITEM = {"kind": "announcement", "title_zh": "十月锦标赛",
                   "body_zh": "周六晚上八点开始。", "title_en": "", "body_en": "",
                   "tournament_date": "2026-10-24", "announcement_id": ""}


def add_tournament_item(admin: TestClient, **fields):
    """Send the new Tournament item form: an announcement on the Current
    Patch unless `fields` say otherwise."""
    form = admin.get("/admin/tournaments/new").text
    return fill_in(admin, "/admin/tournaments/new", "/admin/tournaments",
                   **(TOURNAMENT_ITEM | {"patch_id": option_value(form, "6.7（当前版本）")}
                      | fields))


def new_tournament_item(admin: TestClient, **fields) -> str:
    """Save a new Tournament item as a Draft; returns its edit page."""
    response = add_tournament_item(admin, **fields)
    assert response.status_code == 303, response.text
    edit_page = response.headers["location"]
    assert re.fullmatch(r"/admin/tournaments/\d+/edit", edit_page)
    return edit_page


def published_tournament_item(admin: TestClient, **fields) -> str:
    edit_page = new_tournament_item(admin, **fields)
    assert page_act(admin, edit_page, "publish").status_code == 303
    return edit_page


TOURNAMENT_LIST_ITEM = re.compile(
    r'<li>\s*(?:<img [^>]*>\s*)?<span class="badge">([^<]+)</span>\s*'
    r'<a href="([^"]+)">([^<]+)</a>')  # after the item's cover, if it has one


def tournament_list(site: Path, lang: str) -> list[tuple[str, str, str]]:
    """The 锦标赛 list of one language tree: (badge, title, the folder its
    link leads to, from the site root), in order."""
    path = f"{lang}/tournaments/"
    return [(badge, title, posixpath.normpath(posixpath.join(path, href)) + "/")
            for badge, href, title in TOURNAMENT_LIST_ITEM.findall(page(site, path))]


def test_a_published_announcement_is_listed_with_its_badge_and_has_its_own_page(
        admin, site):
    published_tournament_item(admin, title_zh="十月锦标赛", tournament_date="2026-10-24")
    render_site(site)

    [(badge, title, item_page)] = tournament_list(site, "zh")
    assert (badge, title) == ("预告", "十月锦标赛")
    html = page(site, item_page)
    assert "<h1>十月锦标赛</h1>" in html and "周六晚上八点开始。" in html
    assert "2026-10-24" in html and "6.7" in html and "预告" in html


def test_the_tournament_list_is_newest_first_by_tournament_date_with_badges(admin, site):
    published_tournament_item(admin, title_zh="九月锦标赛", tournament_date="2026-09-12")
    published_tournament_item(admin, kind="recap", title_zh="九月锦标赛回顾",
                              tournament_date="2026-09-12")
    published_tournament_item(admin, title_zh="十月锦标赛", tournament_date="2026-10-24")
    # Added last, but its Tournament was the earliest.
    published_tournament_item(admin, kind="recap", title_zh="八月锦标赛回顾",
                              tournament_date="2026-08-01")
    render_site(site)
    assert [(badge, title) for badge, title, _ in tournament_list(site, "zh")] == [
        ("预告", "十月锦标赛"), ("回顾", "九月锦标赛回顾"), ("预告", "九月锦标赛"),
        ("回顾", "八月锦标赛回顾")]


def announcement_option(admin: TestClient, title_zh: str) -> str:
    """The value of the recap form's option for the announcement `title_zh`."""
    form = admin.get("/admin/tournaments/new").text
    match = re.search(rf'<option value="(\d+)"[^>]*>[\d-]+ {re.escape(title_zh)}（', form)
    assert match, f"no announcement {title_zh} to link to"
    return match.group(1)


def test_a_recap_links_to_its_announcement_on_its_public_page(admin, site):
    published_tournament_item(admin, title_zh="十月锦标赛", title_en="October Tournament",
                              body_en="Saturday at 8pm.")
    published_tournament_item(admin, kind="recap", title_zh="十月锦标赛回顾",
                              title_en="October recap", body_en="A close final.",
                              announcement_id=announcement_option(admin, "十月锦标赛"))
    render_site(site)

    for lang, recap, announcement, follows in [
            ("zh", "十月锦标赛回顾", "十月锦标赛", "对应的预告："),
            ("en", "October recap", "October Tournament", "Announcement: ")]:
        items = {title: folder for _, title, folder in tournament_list(site, lang)}
        html = page(site, items[recap])
        link = re.search(rf'{follows}<a href="([^"]+)">{announcement}</a>', html)
        assert link, f"{lang}: no link to the announcement"
        assert posixpath.normpath(posixpath.join(items[recap], link.group(1))) + "/" \
            == items[announcement]


def test_a_recap_shows_no_link_to_an_announcement_readers_cannot_see(admin, site):
    new_tournament_item(admin, title_zh="还没发布的预告")
    published_tournament_item(admin, kind="recap", title_zh="回顾",
                              announcement_id=announcement_option(admin, "还没发布的预告"))
    render_site(site)
    [(_, _, recap)] = tournament_list(site, "zh")
    html = page(site, recap)
    assert "对应的预告" not in html and "还没发布的预告" not in site_text(site)


def test_draft_tournament_items_and_chinese_only_ones_stay_off_the_trees(admin, site):
    new_tournament_item(admin, title_zh="草稿预告", body_zh="草稿正文")
    published_tournament_item(admin, title_zh="只有中文的预告")
    published_tournament_item(admin, kind="recap", title_zh="中英都有的回顾",
                              title_en="Recap in English", body_en="Final day.")
    render_site(site)

    assert "草稿预告" not in site_text(site) and "草稿正文" not in site_text(site)
    assert [title for _, title, _ in tournament_list(site, "zh")] == [
        "中英都有的回顾", "只有中文的预告"]
    assert [(badge, title) for badge, title, _ in tournament_list(site, "en")] == [
        ("Recap", "Recap in English")]
    assert "只有中文的预告" not in site_text(site / "en")
    chinese_only = dict((title, folder) for _, title, folder
                        in tournament_list(site, "zh"))["只有中文的预告"]
    assert switch(site, chinese_only) == "en/tournaments/"
    assert_fallback_notice(site, chinese_only, "en/tournaments/")


def test_the_english_tournament_list_says_so_when_empty(admin, site):
    published_tournament_item(admin)
    render_site(site)
    assert "No English tournament posts yet." in page(site, "en/tournaments/")


def tournament_form_values(admin: TestClient, edit_page: str) -> dict[str, str]:
    """What the Tournament item form on `edit_page` would send unchanged."""
    form = admin.get(edit_page).text
    kind = re.search(r'name="kind" value="(\w+)" checked', form)
    day = re.search(r'name="tournament_date" value="([^"]*)"', form)
    assert kind and day
    return form_values(form) | {"kind": kind.group(1), "tournament_date": day.group(1)}


def save_tournament_item(admin: TestClient, edit_page: str, **fields):
    """Change some fields of a saved Tournament item, keeping the rest."""
    return fill_in(admin, edit_page, edit_page.removesuffix("/edit"),
                   **(tournament_form_values(admin, edit_page) | fields))


@pytest.mark.parametrize("fields, message", [
    ({"tournament_date": ""}, "请填写比赛日期"),
    ({"tournament_date": "10/24/2026"}, "请填写比赛日期"),
    ({"tournament_date": "2026-02-30"}, "请填写比赛日期"),
    ({"patch_id": ""}, "请选择版本"),
    ({"kind": "news"}, "请选择预告或回顾"),
])
def test_a_tournament_item_needs_a_kind_a_date_and_a_patch(admin, fields, message):
    response = add_tournament_item(admin, **fields)
    assert response.status_code == 400 and message in response.text
    assert "还没有锦标赛内容" in admin.get("/admin/tournaments").text


def test_a_recap_can_only_link_to_an_announcement(admin):
    recap = new_tournament_item(admin, kind="recap", title_zh="一篇回顾")
    response = add_tournament_item(admin, kind="recap",
                                   announcement_id=recap.split("/")[3])
    assert response.status_code == 400 and "回顾只能关联一条锦标赛预告" in response.text


def test_an_admin_edits_a_published_tournament_item_and_the_site_follows(admin, site):
    item = published_tournament_item(admin, title_zh="十月锦标赛", tournament_date="2026-10-24")
    assert save_tournament_item(admin, item, tournament_date="2026-10-31",
                                body_zh="改到了月底。").status_code == 303
    render_site(site)
    [(_, _, folder)] = tournament_list(site, "zh")
    html = page(site, folder)
    assert "2026-10-31" in html and "改到了月底。" in html


def test_an_unpublished_tournament_item_leaves_the_site(admin, site):
    item = published_tournament_item(admin, title_zh="十月锦标赛")
    assert page_act(admin, item, "unpublish").status_code == 303
    assert "状态：草稿" in admin.get(item).text
    render_site(site)
    assert tournament_list(site, "zh") == [] and "十月锦标赛" not in site_text(site)


def test_deleting_an_announcement_for_good_keeps_its_recap_without_the_link(admin, site):
    announcement = published_tournament_item(admin, title_zh="十月锦标赛")
    recap = published_tournament_item(admin, kind="recap", title_zh="十月锦标赛回顾",
                                      announcement_id=announcement_option(admin, "十月锦标赛"))
    delete_page_url = announcement.replace("/edit", "/delete")
    confirm = admin.get(delete_page_url).text
    assert "确定要彻底删除锦标赛预告《十月锦标赛》吗？" in confirm
    assert "回顾会保留" in confirm
    response = fill_in(admin, delete_page_url, delete_page_url)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/tournaments"
    assert admin.get(announcement).status_code == 404
    assert tournament_form_values(admin, recap)["announcement_id"] == ""

    render_site(site)
    [(badge, title, folder)] = tournament_list(site, "zh")
    assert (badge, title) == ("回顾", "十月锦标赛回顾")
    assert "对应的预告" not in page(site, folder)


def test_tournament_markdown_is_sanitized_and_shows_game_terms(admin, site):
    published_tournament_item(admin, body_zh='冠军用了 [[Vanessa]]。<script>alert(1)</script>'
                                             '<a href="javascript:alert(1)">链接</a>')
    render_site(site)
    [(_, _, folder)] = tournament_list(site, "zh")
    html = page(site, folder)
    assert '冠军用了 <span class="term">瓦妮莎</span>。' in html
    assert "<script" not in html and "javascript:" not in html


def test_the_tournament_preview_shows_the_item_with_game_term_warnings(admin):
    item = new_tournament_item(admin, kind="recap", body_zh="[[不存在的术语]] 夺冠。")
    preview = admin.get(item.replace("/edit", "/preview")).text
    assert "锦标赛回顾" in preview and "比赛日期 2026-10-24" in preview
    assert "[[不存在的术语]] 没有对应的游戏术语" in preview


def test_the_guides_link_leads_to_an_index_of_every_published_guide_newest_first(
        admin, site):
    published_guide(admin, title_zh="较早的攻略", title_en="Older guide", body_en="Text.")
    published_guide(admin, title_zh="只有中文的攻略")
    published_guide(admin, title_zh="最新的攻略", title_en="Newest guide", body_en="Text.")
    new_guide(admin, title_zh="草稿攻略")
    render_site(site)

    zh = page(site, "zh/guides/")
    assert "<h1>攻略</h1>" in zh and "草稿攻略" not in zh
    assert zh.index("最新的攻略") < zh.index("只有中文的攻略") < zh.index("较早的攻略")
    en = page(site, "en/guides/")
    assert en.index("Newest guide") < en.index("Older guide")
    assert "只有中文的攻略" not in en
    assert switch(site, "zh/guides/") == "en/guides/"


def test_every_navigation_link_leads_to_a_generated_page(admin, site):
    published_page(admin, slug="about", title_en="About", body_en="Us.")
    published_tournament_item(admin)
    render_site(site)
    for lang in ("zh", "en"):
        for folder, _ in navigation(site, f"{lang}/"):
            assert (site / folder / "index.html").exists(), folder


def test_every_page_and_tournament_route_is_behind_an_admin_only_guard():
    from fastapi.routing import APIRoute

    from app.routes import pages, tournaments
    from test_t09_users import admin_only_routes

    routes = {(method, route.path) for module in (pages, tournaments)
              for route in module.router.routes if isinstance(route, APIRoute)
              for method in route.methods or ()}
    assert len(routes) == 23
    assert routes <= set(admin_only_routes())


def test_an_editor_never_sees_or_reaches_pages_and_tournament_items(admin, editor):
    about = published_page(admin, slug="about")
    item = published_tournament_item(admin)
    dashboard = editor.get("/admin/dashboard").text
    assert 'admin/pages"' not in dashboard and 'admin/tournaments"' not in dashboard
    token = csrf_token(dashboard)
    for path in [about.removesuffix("/edit"), about.replace("/edit", "/unpublish"),
                 item.replace("/edit", "/delete")]:
        response = editor.post(path, data={"csrf_token": token, **PAGE},
                               follow_redirects=False)
        assert response.status_code == 403 and "只有管理员" in response.text, path
    assert editor.get(about).status_code == 403
    assert "我们是几位主播。" in admin.get(about).text
    assert "十月锦标赛" in admin.get("/admin/tournaments").text


def test_page_changes_count_as_not_on_the_site_until_the_next_site_build(admin):
    about = new_page(admin, slug="about")
    assert pending_changes(admin) == "网站已是最新"  # a Draft is not on the site
    page_act(admin, about, "publish")
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    press_update_site(admin)
    assert pending_changes(admin) == "网站已是最新"

    save_page(admin, about, body_zh="改过的介绍。")
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    press_update_site(admin)
    page_act(admin, about, "unpublish")
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    press_update_site(admin)
    save_page(admin, about, body_zh="草稿里改的。")  # a Draft again, not on the site
    assert pending_changes(admin) == "网站已是最新"

    rules = published_page(admin, slug="rules", title_zh="规则")
    press_update_site(admin)
    fill_in(admin, rules.replace("/edit", "/delete"), rules.replace("/edit", "/delete"))
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    press_update_site(admin)
    # Deleting a Page the site no longer has changes nothing on the site.
    fill_in(admin, about.replace("/edit", "/delete"), about.replace("/edit", "/delete"))
    assert pending_changes(admin) == "网站已是最新"


def test_tournament_changes_count_as_not_on_the_site_until_the_next_site_build(admin):
    announcement = published_tournament_item(admin, title_zh="十月锦标赛")
    recap = published_tournament_item(admin, kind="recap", title_zh="回顾",
                                      announcement_id=announcement_option(admin, "十月锦标赛"))
    assert pending_changes(admin) == "2 项更改尚未更新到网站"
    press_update_site(admin)
    save_tournament_item(admin, recap, body_zh="补充了决赛。")
    assert pending_changes(admin) == "1 项更改尚未更新到网站"
    press_update_site(admin)
    # The announcement goes, and the recap loses its link to it: two changes.
    fill_in(admin, announcement.replace("/edit", "/delete"),
            announcement.replace("/edit", "/delete"))
    assert pending_changes(admin) == "2 项更改尚未更新到网站"


def test_publishing_or_unpublishing_an_announcement_also_counts_its_recaps(admin):
    recap = published_tournament_item(admin, kind="recap", title_zh="回顾")
    announcement = new_tournament_item(admin, title_zh="十月锦标赛")
    save_tournament_item(admin, recap,
                         announcement_id=announcement_option(admin, "十月锦标赛"))
    press_update_site(admin)
    # The recap's page gains its link to the announcement.
    page_act(admin, announcement, "publish")
    assert pending_changes(admin) == "2 项更改尚未更新到网站"
    press_update_site(admin)
    # A new title shows in the recap's link too.
    save_tournament_item(admin, announcement, title_zh="十月锦标赛（改期）")
    assert pending_changes(admin) == "2 项更改尚未更新到网站"
    press_update_site(admin)
    page_act(admin, announcement, "unpublish")
    assert pending_changes(admin) == "2 项更改尚未更新到网站"


@pytest.mark.parametrize("field", ["patch_id", "announcement_id"])
@pytest.mark.parametrize("value", ["²", "99999999999999999999999"])
def test_a_tampered_id_in_the_tournament_form_gets_a_message_not_an_error(
        admin, field, value):
    response = add_tournament_item(admin, kind="recap", **{field: value})
    if field == "patch_id":
        assert response.status_code == 400 and "请选择版本" in response.text
    else:  # an unknown announcement is simply not linked
        assert response.status_code == 303


def test_deleting_an_item_already_deleted_is_not_found(admin):
    about = new_page(admin)
    item = new_tournament_item(admin)
    for edit_page in (about, item):
        delete_url = edit_page.replace("/edit", "/delete")
        token = csrf_token(admin.get(delete_url).text)
        assert admin.post(delete_url, data={"csrf_token": token},
                          follow_redirects=False).status_code == 303
        assert admin.post(delete_url, data={"csrf_token": token},
                          follow_redirects=False).status_code == 404


def test_page_and_tournament_titles_are_saved_without_surrounding_spaces(admin, site):
    published_page(admin, slug="about", title_zh="  关于 ")
    item = published_tournament_item(admin, title_zh=" 十月锦标赛  ")
    render_site(site)
    assert ("zh/about/", "关于") in navigation(site, "zh/")
    assert "<h1>关于</h1>" in page(site, "zh/about/")
    assert tournament_form_values(admin, item)["title_zh"] == "十月锦标赛"


def test_every_folder_the_site_build_makes_is_a_slug_no_page_can_take(admin, editor, site):
    from app.content import RESERVED_SLUGS

    published_guide(admin, editor, title_en="Pirates", body_en="Boats.")
    published_tournament_item(admin, title_en="Tournament", body_en="Soon.")
    published_page(admin, slug="about", title_en="About", body_en="Us.")
    render_site(site)
    for lang in ("zh", "en"):
        folders = {path.name for path in (site / lang).iterdir() if path.is_dir()}
        assert folders - {"about"} == RESERVED_SLUGS, lang
