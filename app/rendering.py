"""Markdown rendering: the one function that turns a writer's Markdown into
the HTML Readers see. The editor preview uses it, and so will the Site build,
so the preview always shows exactly what will be published.

Writers may mix HTML into their Markdown, so the result is always sanitized
with nh3, which keeps formatting and images but drops scripts, event
handlers, iframes and `javascript:` links. It also drops links and image
sources that start with "/" (`/x` or `//host/x`): the public site is served
from a subfolder, so they would lead off the site.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from html import escape
from html.parser import HTMLParser
from itertools import groupby

import nh3
from markdown_it import MarkdownIt

_markdown = MarkdownIt("commonmark", {"html": True}).enable("table")


def _no_root_absolute_urls(tag: str, attribute: str, value: str) -> str | None:
    # Browsers ignore surrounding spaces in a URL and read a backslash as "/".
    if attribute in ("href", "src") and value.strip()[:1] in ("/", "\\"):
        return None
    return value


def render_markdown(text: str) -> str:
    """Markdown in, sanitized HTML out."""
    return nh3.clean(_markdown.render(text), attribute_filter=_no_root_absolute_urls)


class _Pieces(HTMLParser):
    """Splits sanitized HTML into its tags, copied as they came (so attributes
    are never touched), and its runs of text, with entities decoded."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pieces: list[tuple[bool, str]] = []  # (is_text, tag or text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.pieces.append((False, self.get_starttag_text() or ""))

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag: str) -> None:
        self.pieces.append((False, f"</{tag}>"))

    def handle_data(self, data: str) -> None:
        self.pieces.append((True, data))


# How strongly a character is highlighted: not at all, as part of a quote
# from an earlier review round, or from the latest one. The strongest wins.
_PLAIN, _EARLIER, _LATEST = 0, 1, 2
_MARKS = {_EARLIER: '<mark class="earlier">', _LATEST: "<mark>"}


def _marked(text: str, levels: bytearray) -> str:
    """`text`, escaped, with each run of highlighted characters (one level
    per character) in its <mark>. A run of whitespace only is left unmarked:
    it may sit between block elements, where <mark> doesn't belong."""
    out, done = [], 0
    for level, run in groupby(levels):
        end = done + len(list(run))
        piece = escape(text[done:end], quote=False)
        out.append(f"{_MARKS[level]}{piece}</mark>" if level and piece.strip()
                   else piece)
        done = end
    return "".join(out)


def highlight(html: str, quotes: Iterable[str],
              earlier: Iterable[str] = ()) -> tuple[str, set[str]]:
    """Mark each of `quotes` (the latest review round's) and `earlier` (those
    of rounds before it) where it appears in `html` (the output of
    render_markdown), and say which ones appear. Earlier quotes get
    <mark class="earlier">; where the two overlap, the latest round's mark
    wins. A quote is matched against the text as Readers see it, ignoring
    whitespace and formatting, so a passage copied from the preview is found
    even if it is part bold or runs through a link. Its <mark> is then split
    at the tags it crosses."""
    # Chinese text has no spaces between words, and a line break in the
    # Markdown may fall anywhere, so whitespace may come between any two
    # characters of a quote.
    patterns = [(quote, level,
                 re.compile(r"\s*".join(map(re.escape, "".join(quote.split())))))
                for quote_list, level in [(earlier, _EARLIER), (quotes, _LATEST)]
                for quote in quote_list if quote.split()]
    if not patterns:
        return html, set()
    parser = _Pieces()
    parser.feed(html)
    parser.close()
    text = "".join(piece for is_text, piece in parser.pieces if is_text)
    levels, found = bytearray(len(text)), set()
    for quote, level, pattern in patterns:
        for match in pattern.finditer(text):
            found.add(quote)
            for i in range(*match.span()):
                levels[i] = max(levels[i], level)
    out, offset = [], 0
    for is_text, piece in parser.pieces:
        if is_text:
            out.append(_marked(piece, levels[offset:offset + len(piece)]))
            offset += len(piece)
        else:
            out.append(piece)
    return "".join(out), found
