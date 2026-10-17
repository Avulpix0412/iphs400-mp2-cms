#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run --env-file .env python scripts/seed_demo.py

Creates one Admin and one Editor. Their passwords come from CMS_ADMIN_PASSWORD
and CMS_EDITOR_PASSWORD; there are no default passwords, so the script refuses
to run without both. Running it again leaves existing accounts alone.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed. Later tickets add
demo Heroes, Patches, Game Terms, Guides, a Page and Tournament items.
"""
from __future__ import annotations

import os
import sys

from app import accounts, db, settings

# Matches DEMO_USERS in tests/conftest.py (which uses its own fixed passwords).
DEMO_USERS = [
    # role, email, Display name, environment variable holding the password
    ("admin", "admin@example.test", "演示管理员", "CMS_ADMIN_PASSWORD"),
    ("editor", "editor@example.test", "演示编辑", "CMS_EDITOR_PASSWORD"),
]


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
    print(f"Database: {settings.database_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
