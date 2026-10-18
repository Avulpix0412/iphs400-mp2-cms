"""Configuration, read from the environment (never hard-code secrets)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"

SECRET_KEY = os.environ.get("CMS_SECRET_KEY", "dev-only-not-for-production")
SITE_TITLE = os.environ.get("CMS_SITE_TITLE", "My CMS")
# Set this to your Pages URL once you deploy, e.g.
# https://yourname.github.io/iphs400-mp2-cms/
BASE_PATH = os.environ.get("CMS_BASE_PATH", "")


def database_path() -> Path:
    """Read on every connect, so tests can point CMS_DATABASE at a temp file."""
    return Path(os.environ.get("CMS_DATABASE", ROOT / "cms.db"))


def media_path() -> Path:
    """The folder of uploaded images (never committed). It sits next to the
    database unless CMS_MEDIA says otherwise, so a test's temporary database
    gets its own media folder too."""
    return Path(os.environ.get("CMS_MEDIA", database_path().parent / "media"))
