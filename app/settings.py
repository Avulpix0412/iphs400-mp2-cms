"""Configuration, read from the environment (never hard-code secrets)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"

# The settings below are read when called, not at import, so the entry points
# can load .env (app/envfile.py) after `settings` is already imported.


def secret_key() -> str:
    return os.environ.get("CMS_SECRET_KEY", "dev-only-not-for-production")


def site_title() -> str:
    return os.environ.get("CMS_SITE_TITLE", "My CMS")


def base_path() -> str:
    """Set this to your Pages URL once you deploy, e.g.
    https://yourname.github.io/iphs400-mp2-cms/"""
    return os.environ.get("CMS_BASE_PATH", "")


def database_path() -> Path:
    """Read on every connect, so tests can point CMS_DATABASE at a temp file."""
    return Path(os.environ.get("CMS_DATABASE", ROOT / "cms.db"))


def media_path() -> Path:
    """The folder of uploaded images (never committed). It sits next to the
    database unless CMS_MEDIA says otherwise, so a test's temporary database
    gets its own media folder too."""
    return Path(os.environ.get("CMS_MEDIA", database_path().parent / "media"))
