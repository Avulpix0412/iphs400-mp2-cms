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


class _Highlighter(HTMLParser):
    """Copies sanitized HTML, wrapping each passage of its text that matches
    one of `patterns` in <mark>. Tags are copied as they came, so attributes
    are never touched."""

    def __init__(self, patterns: dict[str, re.Pattern[str]]) -> None:
        super().__init__(convert_charrefs=True)
        self.patterns = patterns
        self.out: list[str] = []
        self.found: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.out.append(self.get_starttag_text() or "")

    handle_startendtag = handle_starttag

    def handle_endtag(self, tag: str) -> None:
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        spans: list[tuple[int, int]] = []
        for quote, pattern in self.patterns.items():
            matches = [match.span() for match in pattern.finditer(data)]
            if matches:
                self.found.add(quote)
                spans += matches
        done = 0
        for start, end in _merged(spans):
            self.out += [escape(data[done:start], quote=False),
                         f"<mark>{escape(data[start:end], quote=False)}</mark>"]
            done = end
        self.out.append(escape(data[done:], quote=False))


def _merged(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The spans in order, with any that overlap or touch joined into one."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def highlight(html: str, quotes: Iterable[str]) -> tuple[str, set[str]]:
    """Mark each of `quotes` where it appears in `html` (the output of
    render_markdown), and say which ones appear. A quote is matched as
    Readers see the text, ignoring whitespace, but it must lie within one run
    of text: a passage that crosses formatting (part bold, part not) is not
    found. Quotes that overlap are marked together."""
    # Chinese text has no spaces between words, and a line break in the
    # Markdown may fall anywhere, so whitespace may come between any two
    # characters of a quote.
    patterns = {quote: re.compile(r"\s*".join(map(re.escape, "".join(quote.split()))))
                for quote in quotes if quote.split()}
    if not patterns:
        return html, set()
    highlighter = _Highlighter(patterns)
    highlighter.feed(html)
    highlighter.close()
    return "".join(highlighter.out), highlighter.found
