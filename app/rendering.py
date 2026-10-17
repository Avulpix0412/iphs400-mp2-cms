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
