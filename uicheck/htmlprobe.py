"""Stdlib-only HTML probing: links, controls, ids, anchors, tabindex usage.

This is the heart of the offline path — everything here works on a saved
HTML string without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

VOID_TAGS = {"img", "input", "br", "hr", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    line: int
    text: str = ""

    def get(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)


@dataclass
class PageProbe:
    links: list[Element] = field(default_factory=list)          # <a> (with or without href)
    buttons: list[Element] = field(default_factory=list)        # <button>
    inputs: list[Element] = field(default_factory=list)         # <input> (non-hidden)
    images: list[Element] = field(default_factory=list)         # <img>
    ids: set[str] = field(default_factory=set)                  # all id attributes
    tabindex_elements: list[Element] = field(default_factory=list)

    def has_anchor(self, fragment: str) -> bool:
        return fragment in self.ids


class _ProbeParser(HTMLParser):
    INTERACTIVE = {"a", "button", "input", "select", "textarea"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.probe = PageProbe()
        self._stack: list[Element] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v if v is not None else "") for k, v in attrs}
        el = Element(tag=tag, attrs=attr, line=self.getpos()[0])

        if "id" in attr:
            self.probe.ids.add(attr["id"])
        if "tabindex" in attr:
            self.probe.tabindex_elements.append(el)
        if tag == "a":
            self.probe.links.append(el)
        elif tag == "button":
            self.probe.buttons.append(el)
        elif tag == "input" and attr.get("type", "text").lower() not in ("hidden", "submit", "button"):
            self.probe.inputs.append(el)
        elif tag == "img":
            self.probe.images.append(el)

        if tag not in VOID_TAGS:
            self._stack.append(el)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack and tag in {e.tag for e in self._stack}:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        # Pop to the matching open element; tolerate malformed nesting.
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text and self._stack:
            self._stack[-1].text += (" " if self._stack[-1].text else "") + text


def parse_html(html: str) -> PageProbe:
    """Parse HTML into a PageProbe. Never raises on malformed markup."""
    parser = _ProbeParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # HTMLParser is forgiving, but a broken page should still yield
        # whatever partial probe we collected instead of crashing the CLI.
        pass
    return parser.probe


def accessible_name(el: Element) -> str:
    """Best-effort accessible name for common controls (static approximation)."""
    aria = el.get("aria-label").strip()
    if aria:
        return aria
    if el.get("aria-labelledby").strip():
        return "(labelledby)"
    if el.tag == "img":
        return el.get("alt").strip()
    if el.tag == "input":
        typ = el.get("type", "text").lower()
        if typ in ("submit", "button", "reset"):
            return el.get("value").strip()
        return ""  # real name would come from an associated <label>; flagged separately
    return el.text.strip()


def is_internal_href(href: str) -> bool:
    href = href.strip()
    if not href:
        return False
    lowered = href.lower()
    for scheme in ("http://", "https://", "mailto:", "tel:", "javascript:", "data:"):
        if lowered.startswith(scheme):
            return False
    return True


def split_href(href: str) -> tuple[str, str]:
    """Return (path, fragment). Fragment is '' when absent."""
    if "#" in href:
        path, _, frag = href.partition("#")
        return path, frag
    return href, ""
