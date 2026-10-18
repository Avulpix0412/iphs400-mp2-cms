"""T08: the seed script adds an About Page and one Tournament item of each
kind (checked through the console and the Site build)."""
from __future__ import annotations

from app.publish import render_site
from test_t02_seed import seeded_admin
from test_t04_site_build import page
from test_t08_pages_tournaments import navigation, tournament_list


def test_seed_creates_an_about_page_and_a_published_announcement_and_recap(
        tmp_path, monkeypatch):
    seeded_admin(tmp_path, monkeypatch)
    site = render_site(tmp_path / "site")
    assert ("zh/about/", "关于") in navigation(site, "zh/")
    assert ("en/about/", "About") in navigation(site, "en/")
    for lang, badges in [("zh", {"预告", "回顾"}), ("en", {"Announcement", "Recap"})]:
        listed = tournament_list(site, lang)
        assert {badge for badge, _, _ in listed} == badges
    recap = next(folder for badge, _, folder in tournament_list(site, "zh")
                 if badge == "回顾")
    assert "对应的预告：" in page(site, recap)


def test_seeding_twice_adds_no_duplicate_pages_or_tournament_items(tmp_path, monkeypatch):
    admin = seeded_admin(tmp_path, monkeypatch, times=2)
    assert admin.get("/admin/pages").text.count("<code>about</code>") == 1
    site = render_site(tmp_path / "site")
    assert len(tournament_list(site, "zh")) == 2
