"""The Site build: render everything Published into site/ as plain HTML.

The site has a Chinese tree (zh/) and an English tree (en/), and every page is
an index.html in its own folder, so its address is the folder (`zh/guides/
vanessa-12/`). Two rules the rubric checks:

  1. Only PUBLISHED content is read here. A Draft that reaches site/ is a bug.
  2. Every href and src is RELATIVE ("../../style.css"), never root-absolute
     ("/style.css"), because Pages serves this from a subfolder.

A Site build (the console's 更新网站 button) is render_site() followed by
deploy(), which pushes site/ to the gh-pages branch. Only a build whose deploy
succeeded is recorded, and the dashboard counts the changes since then.
"""
from __future__ import annotations

import itertools
import posixpath
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db, game, guides, settings
from app.rendering import render_markdown

CSS = """/* Minimal starter styles — make them yours. */
:root { color-scheme: light dark; }
body { font: 16px/1.6 system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 0 auto; max-width: 42rem; padding: 1rem; }
header { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: baseline; }
header .brand { font-weight: 700; text-decoration: none; margin-inline-end: auto; }
main { margin-block: 2rem; }
.fallback-notice { display: none; }
.fallback-notice:target { display: block; }
"""

LANGUAGES = ("zh", "en")

# The words on the public site, in each language.
LABELS = {
    "zh": {"site_name": "大巴扎攻略站", "current_patch": "当前版本：",
           "newest_guides": "最新攻略", "heroes": "英雄", "no_guides": "还没有攻略。",
           "updated": "更新于",
           "other_language": "English"},
    "en": {"site_name": "The Bazaar Guides", "current_patch": "Current Patch: ",
           "newest_guides": "Newest guides", "heroes": "Heroes",
           "no_guides": "No English guides yet.", "updated": "Updated",
           "other_language": "中文"},
}
NEWEST_ON_HOME = 10
NO_ENGLISH_TEXT = "no-english-text"  # the id of the fallback notice


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(settings.TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    # `guide|localized("title", lang)` is guide.title_zh or guide.title_en.
    env.filters["localized"] = lambda item, field, lang: getattr(item, f"{field}_{lang}")
    env.filters["markdown"] = render_markdown
    return env


def by_patch(listed: list[guides.Guide]) -> list[tuple[str, list[guides.Guide]]]:
    """Guides grouped by Patch, newest Patch first, keeping each group's order."""
    ordered = sorted(listed, key=lambda guide: guide.patch_id, reverse=True)
    return [(patch_name, list(group)) for patch_name, group
            in itertools.groupby(ordered, key=lambda guide: guide.patch_name)]


def relative(target: str, page: str) -> str:
    """The relative link from the page at folder `page` to `target`. Both are
    paths from the site root; a folder ends in "/" ("" is the root itself).
    `target` may end in a "#fragment"."""
    target, hash_mark, fragment = target.partition("#")
    link = posixpath.relpath(target or ".", page or ".")
    if target.endswith("/") or not target:
        link += "/"
    return f"{link}{hash_mark}{fragment}"


class _Writer:
    """Writes pages into `out`. Each page can make relative links with
    `site_link(path from the root)` and, inside a language tree, with
    `link(path inside the tree)`. A page in a language tree also gets
    `switch_link`, the language switch: the same page in the `other` tree
    unless `switch_to` names another path inside that tree."""

    def __init__(self, out: Path, current_patch: str | None) -> None:
        self.out = out
        self.env = environment()
        self.current_patch = current_patch

    def page(self, path: str, template: str, *, lang: str | None = None,
             switch_to: str | None = None, **context: Any) -> None:
        """Write the page Readers get at `path`: "" for the root, or a folder
        such as "zh/guides/vanessa-12/"."""
        def site_link(target: str) -> str:
            return relative(target, path)

        if lang:
            other = "en" if lang == "zh" else "zh"
            same_page = path.removeprefix(f"{lang}/")
            context |= {"lang": lang, "other": other, "t": LABELS[lang],
                        "link": lambda target: site_link(f"{lang}/{target}"),
                        "switch_link": site_link(f"{other}/{switch_to or same_page}")}
        file = self.out / path / "index.html"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(self.env.get_template(template).render(
            site_link=site_link, current_patch=self.current_patch, **context))


def render_site(out: Path | None = None) -> Path:
    out = out or settings.SITE
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with db.connect() as conn:
        published = guides.published(conn)
        heroes = game.heroes(conn)
        patches = game.patches(conn)
    (out / "style.css").write_text(CSS)
    # Every Author with a Published Guide gets a page in both trees, even if
    # none of their Guides has English text.
    authors = {guide.author_id: guide.author_name for guide in published}
    write = _Writer(out, current_patch=patches[0].name if patches else None)
    write.page("", "site/root.html")
    for lang in LANGUAGES:
        listed = [guide for guide in published if guide.has_text_in(lang)]
        newest = sorted(listed, key=lambda guide: guide.published_at or "",
                        reverse=True)[:NEWEST_ON_HOME]
        write.page(f"{lang}/", "site/home.html", lang=lang, guides=newest,
                   heroes=heroes)
        for hero in heroes:
            write.page(f"{lang}/heroes/{hero.slug}/", "site/hero.html", lang=lang,
                       hero=hero, patches=by_patch(
                           [guide for guide in listed if guide.hero_id == hero.id]))
        for author_id, author_name in authors.items():
            write.page(f"{lang}/authors/{author_id}/", "site/author.html", lang=lang,
                       author_name=author_name,
                       guides=[guide for guide in listed if guide.author_id == author_id])
        for guide in listed:
            # Only English can be missing, since Chinese text is required. The
            # switch then leads to the Hero's English page, whose notice shows
            # only when arrived at through this link.
            write.page(f"{lang}/guides/{guide.slug}/", "site/guide.html",
                       lang=lang, guide=guide,
                       switch_to=None if guide.has_text_in("en")
                       else f"heroes/{guide.hero_slug}/#{NO_ENGLISH_TEXT}")
    return out


class DeployFailed(Exception):
    """The push to gh-pages failed; the message says why."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def deploy(out: Path, message: str = "Publish site") -> None:
    """Push `out` to the gh-pages branch, which GitHub Pages serves.
    Raises DeployFailed with git's own explanation if the push fails."""
    result = subprocess.run(
        [sys.executable, "-m", "ghp_import", "-n", "-p", "-m", message, str(out)],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise DeployFailed(result.stderr.strip() or result.stdout.strip()
                           or f"ghp-import exited with {result.returncode}")


def build_site() -> Path:
    """Render the site and put it online. Raises DeployFailed if the push
    fails, in which case the build is not recorded."""
    with db.connect() as conn:
        started_at = conn.execute(f"SELECT {db.NOW}").fetchone()[0]
    out = render_site()
    deploy(out)
    with db.connect() as conn:
        conn.execute("INSERT INTO site_builds (started_at) VALUES (?)", (started_at,))
    return out


def changes_not_on_site(conn: sqlite3.Connection) -> int:
    """How many Guides changed since the last successful Site build started
    (all of them, if there has never been one): Published Guides edited
    since, Guides Unpublished since, which the next build leaves out, and
    Published Guides moved to or restored from the Trash since."""
    last = conn.execute("SELECT MAX(started_at) FROM site_builds").fetchone()[0] or ""
    changed = {guide.id for guide in guides.published(conn) if guide.updated_at > last}
    return len(changed | guides.unpublished_since(conn, last)
               | guides.trash_changes_since(conn, last))
