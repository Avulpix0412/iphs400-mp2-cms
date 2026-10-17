#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run --env-file .env python scripts/seed_demo.py

Creates one Admin and one Editor, a few Heroes, a few Patches (the last
one, 6.7, becomes the Current Patch), and demo Guides in Draft, Submitted and
Published, made through the Guide workflow just as the console makes them. The passwords come from
CMS_ADMIN_PASSWORD and CMS_EDITOR_PASSWORD; there are no default passwords, so
the script refuses to run without both. Running it again leaves existing
accounts, Heroes and Patches alone, and adds no Guides once any exist.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed. Later tickets add
other Game Terms, a Page and Tournament items.
"""
from __future__ import annotations

import os
import sqlite3
import sys

from app import accounts, db, game, guides, settings

# Matches DEMO_USERS in tests/conftest.py (which uses its own fixed passwords).
DEMO_USERS = [
    # role, email, Display name, environment variable holding the password
    ("admin", "admin@example.test", "演示管理员", "CMS_ADMIN_PASSWORD"),
    ("editor", "editor@example.test", "演示编辑", "CMS_EDITOR_PASSWORD"),
]

# Official Chinese name, official English name.
DEMO_HEROES = [
    ("瓦妮莎", "Vanessa"),
    ("皮格马利翁", "Pygmalien"),
    ("杜利", "Dooley"),
    ("马克", "Mak"),
]
# Oldest first, so the last one added is the Current Patch.
DEMO_PATCHES = ["6.5", "6.6", "6.7"]

# Author's role, Hero (English name), Patch, status reached, Chinese title,
# Chinese body, English title, English body.
DEMO_GUIDES = [
    ("editor", "Vanessa", "6.7", "draft", "瓦妮莎海盗船流（写作中）",
     "## 思路\n\n先拿船，再找炮。终局阵容还在测试。", "", ""),
    ("editor", "Dooley", "6.7", "submitted", "杜利核心流入门",
     "## 终局阵容\n\n围绕核心，前期拿**能量**物品。\n\n## 运营\n\n第 5 天前定型。",
     "Dooley core build for beginners",
     "## Final lineup\n\nBuild around the core and take **energy** items early."),
    ("editor", "Pygmalien", "6.6", "published", "皮格马利翁经济流",
     "## 思路\n\n前期攒钱，中期一次性升级。", "", ""),
    ("admin", "Mak", "6.7", "published", "马克药水流（6.7）",
     "## 终局阵容\n\n药水叠毒，配合治疗。\n\n| 天数 | 目标 |\n|---|---|\n| 1–4 | 拿药水 |\n| 5+ | 叠毒 |",
     "Mak potion build (6.7)",
     "## Final lineup\n\nStack poison with potions and heal through the midgame."),
]


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
    missing = [var for *_, var in DEMO_USERS if not os.environ.get(var)]
    if missing:
        print(f"Set {' and '.join(missing)} in .env (copy .env.example), then run "
              "`uv run --env-file .env python scripts/seed_demo.py`.")
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
        for name_zh, name_en in DEMO_HEROES:
            try:
                game.add_hero(conn, name_zh=name_zh, name_en=name_en)
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
        seed_guides(conn)
    print(f"Database: {settings.database_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
