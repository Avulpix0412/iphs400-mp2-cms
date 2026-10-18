"""Markdown rendering: the one function that turns a writer's Markdown into
the HTML Readers see. The editor preview and the Site build both use it, so
the preview always shows exactly what will be published.

A Game Term marker, `[[瓦妮莎]]` or `[[Vanessa]]`, names a Game Term by either
Official name and shows as its Official name in the language being rendered,
in a <span class="term">. A marker that names no Game Term shows its text as
written, without the brackets. The same pass returns warnings for the
preview: such unknown markers, markers naming several terms with different
names, and known nicknames written without a marker. Warnings never block
anything.

Writers may mix HTML into their Markdown, so the result is always sanitized
with nh3, which keeps formatting and images but drops scripts, event
handlers, iframes and `javascript:` links. It also drops links and image
sources that start with "/" (`/x` or `//host/x`): the public site is served
from a subfolder, so they would lead off the site.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from itertools import groupby

import nh3
from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict

from app.game import KINDS, Glossary

_MARKER = re.compile(r"\[\[([^\[\]\n]+)\]\]")


def _shown_name(written: str, env: EnvType) -> str | None:
    """The Official name the marker `[[written]]` shows in env's language,
    or None if it names no Game Term. Notes any warning in env."""
    matches = env["glossary"].matching(written)
    if not matches:
        env["warnings"].append(f"[[{written}]] 没有对应的游戏术语，"
                               "网站上会显示为不带括号的原文。")
        return None
    name = getattr(matches[0], f"name_{env['lang']}")
    if len({getattr(term, f"name_{env['lang']}") for term in matches}) > 1:
        listed = "、".join(f"{KINDS[term.kind]} {term.name_zh}（{term.name_en}）"
                          for term in matches)
        env["warnings"].append(f"[[{written}]] 对应多个游戏术语：{listed}。"
                               f"网站上会显示为“{name}”。")
    return name


def _game_term(state: StateInline, silent: bool) -> bool:
    """Inline rule: `[[name]]` becomes a game_term token holding the name it
    shows, and whether it names a Game Term (meta["known"]). Silent mode only
    skips over text, as when a link label is scanned for its closing "]"; a
    token found there would end the link, so the marker is left to be
    skipped as plain brackets, which balance out."""
    match = None if silent else _MARKER.match(state.src, state.pos)
    if not match:
        return False
    name = _shown_name(match.group(1), state.env)
    token = state.push("game_term", "", 0)
    token.content = name or match.group(1)
    token.meta["known"] = name is not None
    state.pos = match.end()
    return True


class _Renderer(RendererHTML):
    def game_term(self, tokens: Sequence[Token], idx: int, options: OptionsDict,
                  env: EnvType) -> str:
        token = tokens[idx]
        if not token.meta["known"]:
            return escape(token.content)
        return f'<span class="term">{escape(token.content)}</span>'

    def renderInlineAsText(self, tokens: Sequence[Token] | None,
                           options: OptionsDict, env: EnvType) -> str:
        """Text for an image's alt, where a marker shows as its name too."""
        return super().renderInlineAsText(
            [Token("text", "", 0, content=token.content)
             if token.type == "game_term" else token for token in tokens or []],
            options, env)


_markdown = MarkdownIt("commonmark", {"html": True},
                       renderer_cls=_Renderer).enable("table")
_markdown.inline.ruler.before("link", "game_term", _game_term)


def _no_root_absolute_urls(tag: str, attribute: str, value: str) -> str | None:
    # Browsers ignore surrounding spaces in a URL and read a backslash as "/".
    if attribute in ("href", "src") and value.strip()[:1] in ("/", "\\"):
        return None
    return value


@dataclass(frozen=True)
class Rendered:
    html: str
    warnings: list[str]


def render_markdown(text: str, lang: str, glossary: Glossary) -> Rendered:
    """Markdown in, sanitized HTML out, with Game Term markers showing the
    Official name in `lang` ("zh" or "en"), and the preview's warnings."""
    env = {"lang": lang, "glossary": glossary, "warnings": []}
    html = nh3.clean(_markdown.render(text, env),
                     attribute_filter=_no_root_absolute_urls,
                     allowed_classes={"span": {"term"}})
    warnings = env["warnings"] + nickname_warnings(_unmarked_text(html), lang, glossary)
    return Rendered(html, list(dict.fromkeys(warnings)))


def nickname_warnings(text: str, lang: str, glossary: Glossary) -> list[str]:
    """One warning for each known nickname in `text`, plain text in `lang`,
    saying how many times it is there."""
    return [f"外号“{nickname}”没有标记（{count} 处），官方名称是"
            f" {term.name_zh}（{term.name_en}），"
            f"可以写成 [[{getattr(term, f'name_{lang}')}]]。"
            for nickname, term, count in glossary.nicknames_in(text)]


def title_warnings(title: str, lang: str, glossary: Glossary) -> list[str]:
    """Warnings for a title in `lang`. A title is plain text, shown as written
    (markers are not rendered there), so it needs the Official name itself."""
    return [f"标题里的 [[{written}]] 会原样显示，请直接写官方名称。"
            for written in _MARKER.findall(title)] + [
        f"外号“{nickname}”没有标记（{count} 处），官方名称是"
        f" {term.name_zh}（{term.name_en}），"
        f"标题里请直接写 {getattr(term, f'name_{lang}')}。"
        for nickname, term, count in glossary.nicknames_in(title)]


def preview_warnings(title_zh: str, title_en: str, rendered_zh: Rendered,
                     rendered_en: Rendered, glossary: Glossary) -> list[str]:
    """Every warning the preview shows for a text in both languages (titles
    and rendered bodies), each labelled with where it is."""
    return [f"{where}：{warning}" for where, warnings in [
                ("中文标题", title_warnings(title_zh, "zh", glossary)),
                ("中文正文", rendered_zh.warnings),
                ("英文标题", title_warnings(title_en, "en", glossary)),
                ("英文正文", rendered_en.warnings)]
            for warning in warnings]


def _unmarked_text(html: str) -> str:
    """The text Readers see in `html` (the output of render_markdown), less
    Game Term markers and code, where a nickname may stand as written. Each
    left-out stretch becomes a line break, so no nickname is found across it."""
    parser = _Pieces()
    parser.feed(html)
    parser.close()
    out, code, spans = [], 0, []  # spans: whether each open <span> is a term
    for is_text, piece in parser.pieces:
        if is_text:
            out.append("\n" if code or any(spans) else piece)
        elif re.match(r"<(code|pre)\b", piece):
            code += 1
        elif piece in ("</code>", "</pre>"):
            code -= 1
        elif piece.startswith("<span"):
            spans.append('class="term"' in piece)
        elif piece == "</span>" and spans:
            spans.pop()
    return "".join(out)


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
