"""Load a .env file into the environment, standard library only.

The entry points (the `cms` command and scripts/seed_demo.py) call `load()`
first thing, so `uv run cms serve` works without `--env-file .env`. Importing
`app` never loads it, so tests never see the developer's real .env.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def load(path: Path = Path(".env")) -> None:
    """Copy each KEY=value line of `path` (relative to the working folder)
    into the environment. A variable already set there wins, so the tests'
    CMS_DATABASE and `uv run --env-file .env` keep working.

    Blank lines and lines starting with # are skipped, and so is a leading
    `export `. A value in single or double quotes is what lies between them; an
    unquoted value runs to a ` #` comment or the end of the line, spaces and
    all (uv's --env-file would reject the file instead).
    """
    if not path.exists():
        return
    # utf-8-sig: a byte order mark (Windows Notepad) would hide the first key.
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, equals, value = line.removeprefix("export ").partition("=")
        if not equals or not key.strip():
            # Not the line itself: it may hold a secret.
            print(f"Skipped {path} line {number}: not KEY=value.", file=sys.stderr)
            continue
        value = value.strip()
        quote = value[:1]
        if quote in ("\"", "'") and quote in value[1:]:
            value = value[1:value.index(quote, 1)]
        else:
            value = re.sub(r"(^|\s)#.*", "", value).strip()
        os.environ.setdefault(key.strip(), value)
