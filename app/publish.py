"""The Site build: render everything Published into site/ as plain HTML.

The site has a Chinese tree (zh/) and an English tree (en/), and every page is
an index.html in its own folder, so its address is the folder (`zh/guides/
vanessa-12/`). Two rules the rubric checks:

  1. Only PUBLISHED content is read here. A Draft that reaches site/ is a bug.
  2. Every href and src is RELATIVE ("../../style.css"), never root-absolute
     ("/style.css"), because Pages serves this from a subfolder.

The images of what is written are copied into media/, which both trees share.

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

from app import content, db, game, guides, media, settings, times
from app.rendering import render_markdown

CSS = """/* Minimal starter styles — make them yours. */
:root { color-scheme: light dark; }
body { font: 16px/1.6 system-ui, "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 0 auto; max-width: 42rem; padding: 1rem; }
header { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: baseline; }
header .brand { font-weight: 700; text-decoration: none; margin-inline-end: auto; }
.site-nav { display: flex; flex-wrap: wrap; gap: .25rem 1rem; flex-basis: 100%; }
main { margin-block: 2rem; }
.badge { display: inline-block; padding: 0 .5rem; border-radius: 1rem;
         border: 1px solid; font-size: .85em; }
.term { font-weight: 600; }
img { max-width: 100%; height: auto; }
/* A Cover in a list: a small image above the item's title. */
.guides, .tournament-items { list-style: none; padding: 0; }
.guides li, .tournament-items li { margin-block: .75rem; }
.guides img, .tournament-items img { display: block; width: 12rem; }
.fallback-notice { display: none; }
.fallback-notice:target { display: block; }
"""

LANGUAGES = ("zh", "en")

# The words on the public site, in each language.
LABELS = {
    "zh": {"site_name": "大巴扎攻略站", "current_patch": "当前版本：",
           "newest_guides": "最新攻略", "heroes": "英雄", "no_guides": "还没有攻略。",
           "updated": "更新于", "guides": "攻略", "tournaments": "锦标赛",
           "announcement": "预告", "recap": "回顾", "tournament_date": "比赛日期",
           "no_tournament_items": "还没有锦标赛内容。", "follows": "对应的预告：",
           "other_language": "English"},
    "en": {"site_name": "The Bazaar Guides", "current_patch": "Current Patch: ",
           "newest_guides": "Newest guides", "heroes": "Heroes",
           "no_guides": "No English guides yet.", "updated": "Updated",
           "guides": "Guides", "tournaments": "Tournaments",
           "announcement": "Announcement", "recap": "Recap",
           "tournament_date": "Tournament date",
           "no_tournament_items": "No English tournament posts yet.",
           "follows": "Announcement: ",
           "other_language": "中文"},
}
NEWEST_ON_HOME = 10
NO_ENGLISH_TEXT = "no-english-text"  # the id of the fallback notice


def environment(glossary: game.Glossary) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(settings.TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    # `guide|localized("title", lang)` is guide.title_zh or guide.title_en.
    env.filters["localized"] = lambda item, field, lang: getattr(item, f"{field}_{lang}")
    # `text|markdown(lang, images(item))`: sanitized HTML, with Game Terms in
    # `lang` and the item's images.
    env.filters["markdown"] = lambda text, lang, images=None: render_markdown(
        text, lang, glossary, images).html
    env.filters.update(times.FILTERS)
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
    unless `switch_to` names another path inside that tree, and `nav_pages`,
    the Published Pages in the navigation of that tree. `images(item)` is
    what the item's text needs to show its images there, and `cover(item)`
    is its cover, with `media_link(image)` leading to an image's file."""

    def __init__(self, out: Path, current_patch: str | None,
                 glossary: game.Glossary, nav_pages: list[content.Page],
                 images: dict[str, list[media.Image]]) -> None:
        self.out = out
        self.images = images  # by owner
        self.env = environment(glossary)
        self.current_patch = current_patch
        self.nav_pages = {lang: [page for page in nav_pages if page.has_text_in(lang)]
                          for lang in LANGUAGES}

    def page(self, path: str, template: str, *, lang: str | None = None,
             switch_to: str | None = None, **context: Any) -> None:
        """Write the page Readers get at `path`: "" for the root, or a folder
        such as "zh/guides/vanessa-12/"."""
        def site_link(target: str) -> str:
            return relative(target, path)

        def owned(item: guides.Guide | content.TournamentItem) -> list[media.Image]:
            return self.images.get(item.media_owner, [])

        context |= {
            "media_link": lambda image: site_link(f"media/{image.filename}"),
            "cover": lambda item: media.cover(owned(item), item.cover)}
        if lang:
            context["images"] = lambda item: media.sources(
                owned(item), lang, site_link("media/{}"))
            other = "en" if lang == "zh" else "zh"
            same_page = path.removeprefix(f"{lang}/")
            context |= {"lang": lang, "other": other, "t": LABELS[lang],
                        "link": lambda target: site_link(f"{lang}/{target}"),
                        "switch_link": site_link(f"{other}/{switch_to or same_page}"),
                        "nav_pages": self.nav_pages[lang]}
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
        glossary = game.glossary(conn)
        pages = content.published_pages(conn)
        tournament_items = content.published_tournament_items(conn)
        owners = [item.media_owner for item in [*published, *tournament_items]]
        images = {owner: media.images(conn, owner) for owner in owners}
    media.copy_files(itertools.chain(*images.values()), out / "media")
    (out / "style.css").write_text(CSS)
    # Every Author with a Published Guide gets a page in both trees, even if
    # none of their Guides has English text.
    authors = {guide.author_id: guide.author_name for guide in published}
    write = _Writer(out, current_patch=patches[0].name if patches else None,
                    glossary=glossary, nav_pages=pages, images=images)
    write.page("", "site/root.html")
    for lang in LANGUAGES:
        listed = [guide for guide in published if guide.has_text_in(lang)]
        newest = sorted(listed, key=lambda guide: guide.published_at or "",
                        reverse=True)
        write.page(f"{lang}/", "site/home.html", lang=lang,
                   guides=newest[:NEWEST_ON_HOME], heroes=heroes)
        write.page(f"{lang}/guides/", "site/guides.html", lang=lang, guides=newest)
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
        write_tournaments(write, lang, tournament_items)
        for page in pages:
            # A Chinese-only Page's switch leads to the English home page.
            if page.has_text_in(lang):
                write.page(f"{lang}/{page.slug}/", "site/page.html", lang=lang,
                           page=page, switch_to=None if page.has_text_in("en")
                           else f"#{NO_ENGLISH_TEXT}")
    return out


def write_tournaments(write: _Writer, lang: str,
                      items: list[content.TournamentItem]) -> None:
    """The 锦标赛 list and each item's page, in one language tree. A recap
    links to its announcement where that is on the same tree; a Chinese-only
    item's switch leads to the English list."""
    listed = [item for item in items if item.has_text_in(lang)]
    on_tree = {item.id: item for item in listed}
    write.page(f"{lang}/tournaments/", "site/tournaments.html", lang=lang,
               items=listed)
    for item in listed:
        write.page(f"{lang}/tournaments/{item.id}/", "site/tournament_item.html",
                   lang=lang, item=item,
                   announcement=on_tree.get(item.announcement_id or 0),
                   switch_to=None if item.has_text_in("en")
                   else f"tournaments/#{NO_ENGLISH_TEXT}")


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
    """How many Guides, Pages and Tournament items changed since the last
    successful Site build started (all of them, if there has never been
    one): Published Guides edited since, Guides Unpublished since, which the
    next build leaves out, Published Guides moved to or restored from the
    Trash since, and the Page and Tournament changes content.changes_since
    counts."""
    last = conn.execute("SELECT MAX(started_at) FROM site_builds").fetchone()[0] or ""
    changed = {guide.id for guide in guides.published(conn) if guide.updated_at > last}
    return (len(changed | guides.unpublished_since(conn, last)
                | guides.trash_changes_since(conn, last))
            + content.changes_since(conn, last))
