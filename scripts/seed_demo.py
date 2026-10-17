#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run --env-file .env python scripts/seed_demo.py

Creates one Admin and one Editor, a few Heroes, and a few Patches (the last
one, 6.7, becomes the Current Patch). The passwords come from
CMS_ADMIN_PASSWORD and CMS_EDITOR_PASSWORD; there are no default passwords, so
the script refuses to run without both. Running it again leaves existing
accounts, Heroes and Patches alone.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed. Later tickets add
other Game Terms, Guides, a Page and Tournament items.
"""
from __future__ import annotations

import os
import sys

from app import accounts, db, game, settings

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
    print(f"Database: {settings.database_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
