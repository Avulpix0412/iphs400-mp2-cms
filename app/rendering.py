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


def _merged(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The spans in order, with any that overlap or touch joined into one."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _marked(text: str, spans: list[tuple[int, int]]) -> str:
    """`text`, escaped, with each span (offsets into `text`) in <mark>. A
    span of whitespace only is left unmarked: it may sit between block
    elements, where <mark> doesn't belong."""
    out, done = [], 0
    for start, end in spans:
        out.append(escape(text[done:start], quote=False))
        piece = escape(text[start:end], quote=False)
        out.append(f"<mark>{piece}</mark>" if piece.strip() else piece)
        done = end
    out.append(escape(text[done:], quote=False))
    return "".join(out)


def highlight(html: str, quotes: Iterable[str]) -> tuple[str, set[str]]:
    """Mark each of `quotes` where it appears in `html` (the output of
    render_markdown), and say which ones appear. A quote is matched against
    the text as Readers see it, ignoring whitespace and formatting, so a
    passage copied from the preview is found even if it is part bold or runs
    through a link. Its <mark> is then split at the tags it crosses. Quotes
    that overlap are marked together."""
    # Chinese text has no spaces between words, and a line break in the
    # Markdown may fall anywhere, so whitespace may come between any two
    # characters of a quote.
    patterns = {quote: re.compile(r"\s*".join(map(re.escape, "".join(quote.split()))))
                for quote in quotes if quote.split()}
    if not patterns:
        return html, set()
    parser = _Pieces()
    parser.feed(html)
    parser.close()
    text = "".join(piece for is_text, piece in parser.pieces if is_text)
    found, spans = set(), []
    for quote, pattern in patterns.items():
        matches = [match.span() for match in pattern.finditer(text)]
        if matches:
            found.add(quote)
            spans += matches
    spans = _merged(spans)
    out, offset = [], 0
    for is_text, piece in parser.pieces:
        if not is_text:
            out.append(piece)
            continue
        end = offset + len(piece)
        inside = [(max(start, offset) - offset, min(stop, end) - offset)
                  for start, stop in spans if start < end and stop > offset]
        out.append(_marked(piece, inside))
        offset = end
    return "".join(out), found
