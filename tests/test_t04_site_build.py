"""T04: the Site build puts Published Guides online in Chinese and English.

Content is set up through the console (Seam 1); what Readers get is checked in
the files `render_site` writes (Seam 2)."""
from __future__ import annotations

import posixpath
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import publish, settings
from app.publish import render_site
from conftest import csrf_token
from test_t02_heroes_patches import submit as fill_in
from test_t03_guides import (act, admin, editor, hero_id, new_guide,  # noqa: F401
                             patch_id, save, slug_of)


@pytest.fixture
def site(tmp_path) -> Path:
    return tmp_path / "site"


def published_guide(admin: TestClient, editor: TestClient | None = None,
                    **fields) -> str:
    """A Guide written by `editor` (or the Admin), Submitted and Published.
    Returns its slug."""
    author = editor or admin
    edit_page = new_guide(author, **fields)
    if editor:
        assert act(editor, edit_page, "submit").status_code == 303
    assert act(admin, edit_page, "publish").status_code == 303
    return slug_of(admin, edit_page)


def page(site: Path, path: str) -> str:
    """The text of the page Readers get at `path` (a folder such as
    `zh/guides/vanessa-1/`)."""
    file = site / path / "index.html"
    assert file.exists(), f"no page at {path}"
    return file.read_text()


def test_a_published_guide_gets_its_own_page(admin, site):
    slug = published_guide(admin, title_zh="瓦妮莎海盗流",
                           body_zh="## 终局阵容\n\n先拿船。")
    html = page(render_site(site), f"zh/guides/{slug}/")
    assert "瓦妮莎海盗流" in html
    assert "<h2>终局阵容</h2>" in html


def site_text(site: Path) -> str:
    """Every generated HTML file, run together."""
    return "\n".join(file.read_text() for file in sorted(site.rglob("*.html")))


def test_draft_and_submitted_guides_never_appear_anywhere(admin, editor, site):
    new_guide(editor, title_zh="还在写的草稿")
    act(editor, new_guide(editor, title_zh="等审核的攻略"), "submit")
    published_guide(admin, editor, title_zh="已发布的攻略")
    everything = site_text(render_site(site))
    assert "已发布的攻略" in everything
    assert "还在写的草稿" not in everything and "等审核的攻略" not in everything


def test_a_guide_without_english_text_stays_out_of_the_english_tree(admin, site):
    chinese_only = published_guide(admin, title_zh="只有中文")
    both = published_guide(admin, title_zh="中英都有", title_en="Both languages",
                           body_en="## Final lineup\n\nBoats first.")
    render_site(site)
    assert not (site / f"en/guides/{chinese_only}").exists()
    assert "只有中文" not in site_text(site / "en")
    english = page(site, f"en/guides/{both}/")
    assert "Both languages" in english and "<h2>Final lineup</h2>" in english
    assert "中英都有" in page(site, f"zh/guides/{both}/")


def test_the_root_sends_readers_to_the_chinese_site(site):
    html = (render_site(site) / "index.html").read_text()
    assert 'http-equiv="refresh" content="0; url=zh/"' in html
    assert 'href="zh/"' in html


def test_each_home_page_shows_the_current_patch_newest_guides_and_hero_grid(
        admin, site):
    published_guide(admin, title_zh="较早的攻略", title_en="Older guide",
                    body_en="Text.")
    published_guide(admin, title_zh="最新的攻略", title_en="Newest guide",
                    body_en="Text.")
    render_site(site)

    zh = page(site, "zh/")
    assert "当前版本：6.7" in zh
    assert zh.index("最新的攻略") < zh.index("较早的攻略")
    assert 'href="heroes/vanessa/">瓦妮莎</a>' in zh
    assert 'href="heroes/dooley/">杜利</a>' in zh

    en = page(site, "en/")
    assert "Current Patch: 6.7" in en
    assert en.index("Newest guide") < en.index("Older guide")
    assert 'href="heroes/vanessa/">Vanessa</a>' in en


def test_editing_a_published_guide_does_not_make_it_one_of_the_newest(admin, site):
    first = new_guide(admin, title_zh="先发布的攻略")
    act(admin, first, "publish")
    published_guide(admin, title_zh="后发布的攻略")
    save(admin, first, body_zh="管理员改了一个错别字。")
    zh = page(render_site(site), "zh/")
    assert zh.index("后发布的攻略") < zh.index("先发布的攻略")


def test_every_page_shows_the_current_patch_in_its_header(admin, site):
    slug = published_guide(admin)
    assert "当前版本：6.7" in page(render_site(site), f"zh/guides/{slug}/")


def test_a_hero_page_lists_its_guides_grouped_by_patch_newest_first(admin, site):
    for title, patch in [("6.6 船流", "6.6"), ("6.7 船流", "6.7（当前版本）"),
                         ("6.6 炮流", "6.6"), ("6.5 船流", "6.5")]:
        published_guide(admin, title_zh=title, patch_id=patch_id(admin, patch))
    published_guide(admin, title_zh="杜利的攻略",
                    hero_id=hero_id(admin, "杜利（Dooley）"))
    html = page(render_site(site), "zh/heroes/vanessa/")

    assert "<h1>瓦妮莎</h1>" in html and "杜利的攻略" not in html
    order = ["<h2>6.7</h2>", "6.7 船流", "<h2>6.6</h2>", "6.6 炮流", "6.6 船流",
             "<h2>6.5</h2>", "6.5 船流"]
    positions = [html.index(text) for text in order]
    assert positions == sorted(positions)


def test_hero_pages_exist_in_both_languages_with_a_notice_when_empty(admin, site):
    published_guide(admin, title_zh="只有中文")
    render_site(site)
    english = page(site, "en/heroes/vanessa/")
    assert "<h1>Vanessa</h1>" in english and "No English guides yet" in english
    assert "只有中文" in page(site, "zh/heroes/vanessa/")
    assert "还没有攻略" in page(site, "zh/heroes/dooley/")


def followed(site: Path, path: str, pattern: str) -> str:
    """Follow the first link on the page at `path` matching `pattern`, whose
    group is the href; returns the folder it leads to, from the site root."""
    match = re.search(pattern, page(site, path))
    assert match, f"no link matching {pattern} on {path}"
    href = match.group(1).partition("#")[0]
    return posixpath.normpath(posixpath.join(path, href)) + "/"


def test_a_guide_page_shows_its_hero_patch_author_and_date(admin, editor, site):
    slug = published_guide(admin, editor, patch_id=patch_id(admin, "6.6"))
    html = page(render_site(site), f"zh/guides/{slug}/")
    assert "6.6" in html and "演示编辑" in html and "更新于" in html
    assert followed(site, f"zh/guides/{slug}/", r'href="([./]*heroes/vanessa/)"') \
        == "zh/heroes/vanessa/"


def test_an_author_page_lists_their_guides_under_their_display_name_only(
        admin, editor, site):
    slug = published_guide(admin, editor, title_zh="编辑写的攻略")
    new_guide(admin, title_zh="管理员的草稿")
    render_site(site)

    author_page = followed(site, f"zh/guides/{slug}/", r'href="([./]*authors/\d+/)"')
    assert re.fullmatch(r"zh/authors/\d+/", author_page)
    html = page(site, author_page)
    assert "<h1>演示编辑</h1>" in html and "编辑写的攻略" in html
    assert [p.name for p in (site / "zh/authors").iterdir()] \
        == [author_page.split("/")[2]]  # the Admin has nothing Published
    assert "No English guides yet" in page(site, author_page.replace("zh/", "en/", 1))
    assert "@example.test" not in site_text(site)


SWITCH = r'<a class="language-switch" href="([^"]+)"'


def switch(site: Path, path: str) -> str:
    """Where the language switch on the page at `path` leads."""
    return followed(site, path, SWITCH)


def test_the_language_switch_links_to_the_same_page_in_the_other_language(
        admin, editor, site):
    slug = published_guide(admin, editor, title_en="Pirates", body_en="Boats.")
    render_site(site)
    author = followed(site, f"zh/guides/{slug}/", r'href="([./]*authors/\d+/)"')
    for zh, en in [("zh/", "en/"), (f"zh/guides/{slug}/", f"en/guides/{slug}/"),
                   ("zh/heroes/vanessa/", "en/heroes/vanessa/"),
                   (author, author.replace("zh/", "en/", 1))]:
        assert switch(site, zh) == en
        assert switch(site, en) == zh


def test_on_a_chinese_only_guide_the_switch_leads_to_its_heros_english_page(
        admin, site):
    slug = published_guide(admin, hero_id=hero_id(admin, "杜利（Dooley）"))
    render_site(site)
    assert switch(site, f"zh/guides/{slug}/") == "en/heroes/dooley/"
    link = re.search(SWITCH, page(site, f"zh/guides/{slug}/"))
    assert link
    fragment = link.group(1).partition("#")[2]
    notice = re.search(rf'id="{fragment}">(.*?)</p>', page(site, "en/heroes/dooley/"),
                       re.DOTALL)
    assert fragment and notice
    assert "has no English text yet" in " ".join(notice.group(1).split())


def test_no_generated_page_uses_a_root_absolute_path(admin, editor, site):
    published_guide(admin, editor, title_en="Pirates", body_en="Boats.")
    published_guide(admin, body_zh="[别的页面](/elsewhere) ![图](/boat.png)"
                                   " [外站](//evil.example/x)")
    render_site(site)
    files = sorted(site.rglob("*.html"))
    assert len(files) > 10
    for file in files:
        html = file.read_text()
        assert 'href="/' not in html and 'src="/' not in html, file


def test_script_in_a_guide_does_not_survive_the_site_build(admin, site):
    slug = published_guide(admin, body_zh='先拿船。<script>alert("x")</script>'
                                          '<img src="x.png" onerror="alert(1)">')
    html = page(render_site(site), f"zh/guides/{slug}/")
    assert "先拿船。" in html
    assert "<script" not in html and "onerror" not in html


def pending_changes(c: TestClient) -> str:
    match = re.search(r"\d+ 项更改尚未更新到网站|网站已是最新",
                      c.get("/admin/dashboard").text)
    assert match, "dashboard shows nothing about the site"
    return match.group(0)


def press_update_site(c: TestClient):
    return fill_in(c, "/admin/dashboard", "/admin/site-build")


def test_admin_puts_the_site_online_with_the_update_site_button(admin, deploys):
    assert pending_changes(admin) == "网站已是最新"
    slug = published_guide(admin)
    assert pending_changes(admin) == "1 项更改尚未更新到网站"

    response = press_update_site(admin)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"
    assert "网站已更新" in admin.get("/admin/dashboard").text
    assert deploys == [settings.SITE]
    assert (settings.SITE / f"zh/guides/{slug}/index.html").exists()
    assert pending_changes(admin) == "网站已是最新"

    published_guide(admin)
    assert pending_changes(admin) == "1 项更改尚未更新到网站"


def test_a_failed_deploy_is_reported_and_the_changes_stay_pending(
        admin, monkeypatch):
    def push_rejected(out, *_):
        raise publish.DeployFailed("! [rejected] gh-pages -> gh-pages (fetch first)")

    monkeypatch.setattr(publish, "deploy", push_rejected)
    published_guide(admin)
    assert press_update_site(admin).status_code == 303
    dashboard = admin.get("/admin/dashboard").text
    assert "更新网站失败" in dashboard and "[rejected] gh-pages" in dashboard
    assert pending_changes(admin) == "1 项更改尚未更新到网站"


def test_only_an_admin_can_update_the_site(admin, editor, deploys):
    assert "更新网站" not in editor.get("/admin/dashboard").text
    token = csrf_token(editor.get("/admin/dashboard").text)
    response = editor.post("/admin/site-build", data={"csrf_token": token},
                           follow_redirects=False)
    assert response.status_code == 403
    assert deploys == []
