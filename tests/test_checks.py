import os

from uicheck.checks import run_checks
from uicheck.snapshot import PageSnapshot, ViewportResult

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SITE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "site")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return fh.read()


def snap(**kw):
    kw.setdefault("route", "/")
    kw.setdefault("url", "http://localhost:8000/")
    return PageSnapshot(**kw)


def findings_by_id(result, check_id):
    return [f for f in result.findings if f.check_id == check_id]


def test_console_and_page_errors():
    s = snap(console_errors=["boom"], page_errors=["ReferenceError: x"])
    result = run_checks([s])
    assert len(findings_by_id(result, "console-error")) == 1
    crit = findings_by_id(result, "uncaught-exception")
    assert crit and crit[0].severity == "critical"
    assert not result.ok


def test_failed_requests():
    s = snap(failed_requests=["/app.js -> HTTP 404"])
    result = run_checks([s])
    assert findings_by_id(result, "failed-request")


def test_broken_anchor_detected():
    s = snap(html=load("probe_page.html"))
    result = run_checks([s])
    anchors = findings_by_id(result, "broken-anchor")
    assert len(anchors) == 1
    assert "#missing" in anchors[0].detail


def test_external_links_ignored():
    s = snap(html=load("probe_page.html"))
    result = run_checks([s])
    assert all("example.com" not in f.detail for f in result.findings)


def test_link_statuses_from_browser():
    html = '<a href="/ok">ok</a><a href="/gone">gone</a><a href="/dead">dead</a>'
    s = snap(html=html, link_statuses={"/ok": 200, "/gone": 404, "/dead": None})
    result = run_checks([s])
    broken = findings_by_id(result, "broken-link")
    assert len(broken) == 2
    titles = " ".join(f.title for f in broken)
    assert "404" in titles and "never completed" in titles


def test_local_root_resolution(tmp_path):
    (tmp_path / "about.html").write_text("<p>hi</p>", encoding="utf-8")
    html = '<a href="/about.html">ok</a><a href="/nope.html">nope</a>'
    s = snap(html=html)
    result = run_checks([s], local_root=str(tmp_path))
    broken = findings_by_id(result, "broken-link")
    assert len(broken) == 1
    assert "/nope.html" in broken[0].detail


def test_known_routes_resolution():
    html = '<a href="/about">ok</a><a href="/ghost">ghost</a>'
    s = snap(html=html)
    result = run_checks([s], known_routes=["/", "/about"])
    broken = findings_by_id(result, "broken-link")
    assert len(broken) == 1
    assert "/ghost" in broken[0].detail


def test_missing_accessible_names():
    s = snap(html=load("probe_page.html"))
    result = run_checks([s])
    missing = findings_by_id(result, "missing-accessible-name")
    # 1 img without alt + 1 empty button + 1 unlabeled input
    assert len(missing) == 3
    assert all(f.severity == "medium" for f in missing)


def test_keyboard_focus():
    s = snap(html=load("probe_page.html"))
    result = run_checks([s])
    kb = findings_by_id(result, "keyboard-focus")
    # <a> without href + positive tabindex + tabindex=-1 on a button
    assert len(kb) == 3


def test_horizontal_overflow_measured():
    s = snap(viewports=[
        ViewportResult(width=375, height=812, label="mobile",
                       horizontal_overflow=True, scroll_width=900, client_width=375),
        ViewportResult(width=1280, height=800, label="desktop",
                       horizontal_overflow=False, scroll_width=1200, client_width=1280),
    ])
    result = run_checks([s])
    overflow = findings_by_id(result, "horizontal-overflow")
    assert len(overflow) == 1
    assert "mobile" in overflow[0].title
    assert not result.skipped


def test_overflow_skipped_offline():
    s = snap(html="<p>hello</p>")
    result = run_checks([s])
    assert any("horizontal-overflow" in x for x in result.skipped)


def test_clean_page_passes():
    html = """
    <html><body>
      <a href="/about">About</a>
      <img src="logo.png" alt="logo">
      <button>Go</button>
      <div id="top"></div><a href="#top">Top</a>
    </body></html>
    """
    s = snap(html=html)
    result = run_checks([s], known_routes=["/", "/about"])
    assert result.findings == []
    assert result.ok


def test_real_fixture_site_flags_bugs():
    with open(os.path.join(SITE, "index.html"), encoding="utf-8") as fh:
        html = fh.read()
    s = snap(html=html)
    result = run_checks([s], local_root=SITE)
    ids = {f.check_id for f in result.findings}
    assert "broken-link" in ids        # pricing.html missing
    assert "broken-anchor" in ids      # #faq missing
    assert "missing-accessible-name" in ids
    assert "keyboard-focus" in ids
    assert not result.ok
