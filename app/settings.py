"""Configuration, read from the environment (never hard-code secrets)."""
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"

# The settings below are read when called, not at import, so the entry points
# can load .env (app/envfile.py) after `settings` is already imported.


DEV_SECRET_KEY = "dev-only-not-for-production"
# The placeholders in .env.example, which production must not run with.
EXAMPLE_SECRET_KEY = "change-me-to-a-long-random-string"
EXAMPLE_ADMIN_PASSWORD = "change-me-admin"


def secret_key() -> str:
    return os.environ.get("CMS_SECRET_KEY", DEV_SECRET_KEY)


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


class BadConfiguration(Exception):
    """The environment is not fit to start in; the message names each
    variable to fix, one per line."""


def environment(env: Mapping[str, str]) -> str:
    """CMS_ENV: development (also when unset or empty) or production."""
    return env.get("CMS_ENV", "") or "development"


def check_configuration(env: Mapping[str, str]) -> None:
    """Refuse a production environment that would run with a known secret or
    without its first Admin's login. Called by create_app() and `cms serve`.
    Development is never refused."""
    mode = environment(env)
    if mode == "development":
        return
    if mode != "production":
        raise BadConfiguration(
            f"CMS_ENV is {mode!r}; set it to development or production.")
    problems = []
    key = env.get("CMS_SECRET_KEY", "").strip()
    if not key:
        problems.append("CMS_SECRET_KEY is not set.")
    elif key in (DEV_SECRET_KEY, EXAMPLE_SECRET_KEY):
        problems.append("CMS_SECRET_KEY is still a published default; set a "
                        "long random value.")
    if not env.get("CMS_ADMIN_EMAIL", "").strip():
        problems.append("CMS_ADMIN_EMAIL is not set; it is the first Admin's login.")
    password = env.get("CMS_ADMIN_PASSWORD", "").strip()
    if not password:
        problems.append("CMS_ADMIN_PASSWORD is not set; it is the first Admin's "
                        "temporary password.")
    elif password == EXAMPLE_ADMIN_PASSWORD:
        problems.append("CMS_ADMIN_PASSWORD is still the .env.example value.")
    if problems:
        raise BadConfiguration("\n".join(problems))
