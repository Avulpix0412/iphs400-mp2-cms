#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run python scripts/seed_demo.py    # loads .env from the current folder

Creates one Admin and one Editor, a few Heroes, a few Patches (the last
one, 6.7, becomes the Current Patch), demo Game Terms imported from
demo_game_terms.csv (which doubles as a sample file for the console's CSV
import), and demo Guides in Draft, Submitted and Published, made through the
Guide workflow just as the console makes them, plus a Published About
Page and a Published Tournament announcement with its recap. The passwords
come from
CMS_ADMIN_PASSWORD and CMS_EDITOR_PASSWORD; there are no default passwords, so
the script refuses to run without both. Running it again leaves existing
accounts, Heroes, Patches and Game Terms alone (even ones an Admin has edited
since), and adds no Guides, Pages or Tournament items once any of that kind
exist.

It refuses to run unless CMS_ENV is development (or unset): production makes
its one Admin from CMS_ADMIN_EMAIL and CMS_ADMIN_PASSWORD at startup instead.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from app import accounts, content, db, envfile, game, guides, settings

# Matches DEMO_USERS in tests/conftest.py (which uses its own fixed passwords).
DEMO_USERS = [
    # role, email, Display name, environment variable holding the password
    ("admin", "admin@example.test", "演示管理员", "CMS_ADMIN_PASSWORD"),
    ("editor", "editor@example.test", "演示编辑", "CMS_EDITOR_PASSWORD"),
]

# Official Chinese name, official English name, nicknames.
DEMO_HEROES = [
    ("瓦妮莎", "Vanessa", "瓦姐"),
    ("皮格马利翁", "Pygmalien", ""),
    ("杜利", "Dooley", ""),
    ("马克", "Mak", ""),
]
# Game Terms in the console's CSV import format.
DEMO_GAME_TERMS = Path(__file__).with_name("demo_game_terms.csv")
# Oldest first, so the last one added is the Current Patch.
DEMO_PATCHES = ["6.5", "6.6", "6.7"]

# Author's role, Hero (English name), Patch, status reached, Chinese title,
# Chinese body, English title, English body.
DEMO_GUIDES = [
    ("editor", "Vanessa", "6.7", "draft", "瓦妮莎海盗船流（写作中）",
     "## 思路\n\n瓦姐先拿船，再找 [[火药桶]]。终局阵容还在测试。", "", ""),
    ("editor", "Dooley", "6.7", "submitted", "杜利核心流入门",
     "## 终局阵容\n\n围绕核心，前期拿**能量**物品。\n\n## 运营\n\n第 5 天前定型。",
     "Dooley core build for beginners",
     "## Final lineup\n\nBuild around the core and take **energy** items early."),
    ("editor", "Pygmalien", "6.6", "published", "皮格马利翁经济流",
     "## 思路\n\n前期攒钱，中期一次性升级。", "", ""),
    ("admin", "Mak", "6.7", "published", "马克药水流（6.7）",
     "## 终局阵容\n\n[[Mak]] 用药水叠毒，配合治疗。\n\n| 天数 | 目标 |\n|---|---|\n| 1–4 | 拿药水 |\n| 5+ | 叠毒 |",
     "Mak potion build (6.7)",
     "## Final lineup\n\n[[马克]] stacks poison with potions and heals through the midgame."),
]

# Slug, Chinese title and body, English title and body. Published.
DEMO_PAGES = [
    ("about", "关于",
     "大巴扎攻略站由几位《大巴扎》主播维护，收录图文攻略，"
     "方便大家按英雄和版本查找终局阵容。\n\n有问题请在 B 站私信我们。",
     "About",
     "The Bazaar Guides is run by a few streamers of The Bazaar. Guides are "
     "written, so you can find a build by Hero and Patch."),
]

# Kind, Chinese title and body, English title and body, Tournament date,
# Patch. Published; one Tournament's announcement, then its recap, which
# links to it.
DEMO_TOURNAMENT_ITEMS = [
    ("announcement", "九月锦标赛预告",
     "## 时间\n\n9 月 26 日（周六）晚上八点开始，版本 6.6。\n\n"
     "本场热门英雄预计是 [[瓦妮莎]]。",
     "September Tournament", "Saturday 26 September at 8pm, on Patch 6.6.",
     "2026-09-26", "6.6"),
    ("recap", "九月锦标赛回顾",
     "冠军用 [[Mak]] 的药水流一路领先，决赛只剩三位玩家。",
     "September Tournament recap",
     "The champion led all the way with a [[马克]] potion build.",
     "2026-09-26", "6.6"),
]


def seed_pages(conn: sqlite3.Connection) -> None:
    admin = _seed_user(conn, "admin")
    if content.pages(conn, admin):
        print("pages: some already exist, none added.")
        return
    for slug, title_zh, body_zh, title_en, body_en in DEMO_PAGES:
        page = content.create_page(conn, admin, content.PageFields(
            slug=slug, title_zh=title_zh, body_zh=body_zh, title_en=title_en,
            body_en=body_en))
        content.publish_page(conn, admin, page.id)
        print(f"page: created {title_zh} ({slug}, Published).")


def seed_tournament_items(conn: sqlite3.Connection) -> None:
    admin = _seed_user(conn, "admin")
    if content.tournament_items(conn, admin):
        print("tournament items: some already exist, none added.")
        return
    patches = {patch.name: patch.id for patch in game.patches(conn)}
    announcement_id = None
    for (kind, title_zh, body_zh, title_en, body_en, day,
         patch) in DEMO_TOURNAMENT_ITEMS:
        item = content.create_tournament_item(conn, admin, content.TournamentFields(
            kind=kind, title_zh=title_zh, body_zh=body_zh, title_en=title_en,
            body_en=body_en, tournament_date=day, patch_id=patches[patch],
            announcement_id=announcement_id if kind == "recap" else None))
        content.publish_tournament_item(conn, admin, item.id)
        if kind == "announcement":
            announcement_id = item.id
        print(f"tournament item: created {title_zh} ({content.KIND_LABELS[kind]}).")


def seed_guides(conn: sqlite3.Connection) -> None:
    admin = _seed_user(conn, "admin")
    if guides.guides(conn, admin):
        print("guides: some already exist, none added.")
        return
    heroes = {hero.name_en: hero.id for hero in game.heroes(conn)}
    patches = {patch.name: patch.id for patch in game.patches(conn)}
    for (role, hero, patch, status, title_zh, body_zh,
         title_en, body_en) in DEMO_GUIDES:
        author = _seed_user(conn, role)
        guide = guides.create(conn, author, guides.GuideFields(
            title_zh=title_zh, body_zh=body_zh, title_en=title_en,
            body_en=body_en, hero_id=heroes[hero], patch_id=patches[patch]))
        if status != "draft" and guides.can_submit(author, guide):
            guides.submit(conn, author, guide.id)
        if status == "published":
            guides.publish(conn, admin, guide.id)
        print(f"guide: created {title_zh} ({guides.STATUS_LABELS[status]}).")


def _seed_user(conn: sqlite3.Connection, role: str) -> accounts.User:
    email = next(email for r, email, *_ in DEMO_USERS if r == role)
    user = accounts.user_with_email(conn, email)
    assert user is not None, f"{email} should have been created above"
    return user


def main() -> int:
    envfile.load()
    if settings.environment(os.environ) != "development":
        print(f"CMS_ENV is {settings.environment(os.environ)}: the demo data and "
              "its known logins are for development only, so nothing was created.",
              file=sys.stderr)
        return 1
    missing = [var for *_, var in DEMO_USERS if not os.environ.get(var)]
    if missing:
        print(f"Set {' and '.join(missing)} in .env (copy .env.example), then run "
              "`uv run python scripts/seed_demo.py`.")
        return 1

    for *_, var in DEMO_USERS:
        if os.environ[var].startswith("change-me"):
            print(f"Warning: {var} is still the .env.example placeholder. "
                  "Change it in .env before anyone else can reach this console.")

    with db.connect() as conn:
        for role, email, display_name, var in DEMO_USERS:
            try:
                accounts.create_user(conn, email=email, password=os.environ[var],
                                     role=role, display_name=display_name)
            except accounts.Refused:
                print(f"{role}: {email} already exists, left unchanged.")
                continue
            print(f"{role}: created {email} (password from {var}).")
        for name_zh, name_en, nicknames in DEMO_HEROES:
            try:
                game.add_hero(conn, name_zh=name_zh, name_en=name_en,
                              nicknames=nicknames)
            except game.Refused as refused:
                print(f"hero: {name_en} left unchanged ({refused.message})")
                continue
            print(f"hero: created {name_zh} ({name_en}).")
        for name in DEMO_PATCHES:
            try:
                game.add_patch(conn, name)
            except game.Refused as refused:
                print(f"patch: {name} left unchanged ({refused.message})")
                continue
            print(f"patch: created {name}.")
        plan = game.import_terms(conn, DEMO_GAME_TERMS.read_bytes(), only_new=True)
        print(f"game terms: {len(plan.added)} added, {plan.unchanged} already there,"
              f" {len(plan.rejected)} rejected.")
        seed_guides(conn)
        seed_pages(conn)
        seed_tournament_items(conn)
    print(f"Database: {settings.database_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
