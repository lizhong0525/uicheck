import os

from uicheck.htmlprobe import accessible_name, is_internal_href, parse_html, split_href

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def test_parse_collects_elements():
    probe = parse_html(load("probe_page.html"))
    assert len(probe.links) == 4
    assert len(probe.images) == 2
    assert len(probe.buttons) == 4
    assert len(probe.inputs) == 2
    assert "real-anchor" in probe.ids
    assert probe.has_anchor("real-anchor")
    assert not probe.has_anchor("missing")
    assert len(probe.tabindex_elements) == 2


def test_accessible_names():
    probe = parse_html(load("probe_page.html"))
    assert accessible_name(probe.links[0]) == "About"
    assert accessible_name(probe.images[0]) == ""        # no alt
    assert accessible_name(probe.images[1]) == "fine"
    assert accessible_name(probe.buttons[0]) == ""       # empty button
    assert accessible_name(probe.buttons[1]) == "Save"
    assert accessible_name(probe.inputs[0]) == ""        # no label
    assert accessible_name(probe.inputs[1]) == "Email"


def test_malformed_html_does_not_crash():
    probe = parse_html("<div><a href='/x'>oops<span><button>never closed")
    assert len(probe.links) == 1
    assert len(probe.buttons) == 1


def test_empty_html():
    probe = parse_html("")
    assert probe.links == [] and probe.ids == set()


def test_is_internal_href():
    assert is_internal_href("/about")
    assert is_internal_href("about.html")
    assert is_internal_href("#faq")
    assert not is_internal_href("https://example.com/x")
    assert not is_internal_href("mailto:a@b.c")
    assert not is_internal_href("javascript:void(0)")
    assert not is_internal_href("")


def test_split_href():
    assert split_href("/page#frag") == ("/page", "frag")
    assert split_href("#frag") == ("", "frag")
    assert split_href("/page") == ("/page", "")
