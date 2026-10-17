"""Markdown rendering: the one function that turns a writer's Markdown into
the HTML Readers see. The editor preview uses it, and so will the Site build,
so the preview always shows exactly what will be published.

Writers may mix HTML into their Markdown, so the result is always sanitized
with nh3, which keeps formatting and images but drops scripts, event
handlers, iframes and `javascript:` links.
"""
from __future__ import annotations

import nh3
from markdown_it import MarkdownIt

_markdown = MarkdownIt("commonmark", {"html": True}).enable("table")


def render_markdown(text: str) -> str:
    """Markdown in, sanitized HTML out."""
    return nh3.clean(_markdown.render(text))
