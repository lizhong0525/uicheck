import json

from uicheck.checks import Finding, ScanResult, run_checks
from uicheck.report import render_report
from uicheck.snapshot import PageSnapshot, ViewportResult

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000c8357b79"
    "0000000d49444154789c626001000000ffff03000006000557bfabd400000000"
    "49454e44ae426082"
)


def make_result():
    s = PageSnapshot(
        route="/",
        url="http://localhost:8000/",
        html="<p>hi</p>",
        console_errors=["boom <script>alert(1)</script>"],
        failed_requests=["/x.js -> HTTP 404"],
        viewports=[
            ViewportResult(width=375, height=812, label="mobile",
                           horizontal_overflow=True, scroll_width=900,
                           client_width=375, screenshot_png=PNG_1PX)
        ],
    )
    return run_checks([s], base_url="http://localhost:8000")


def test_report_contains_findings_and_screenshots():
    html = render_report(make_result(), tool_version="0.1.0")
    assert "UICheck smoke-test report" in html
    assert "horizontal-overflow" in html
    assert "mobile" in html
    assert "data:image/png;base64," in html
    assert "not a complete accessibility or security audit" in html


def test_report_escapes_html():
    html = render_report(make_result())
    assert "<script>alert(1)</script>" not in html.replace("<script>", "")
    assert "&lt;script&gt;alert(1)" in html


def test_report_is_self_contained():
    html = render_report(make_result())
    assert "<link" not in html
    assert "src=\"http" not in html
    assert "href=\"http" not in html


def test_empty_result_report():
    result = ScanResult(base_url="http://x", snapshots=[])
    html = render_report(result)
    assert "No findings" in html


def test_severity_sorting():
    result = ScanResult(base_url="", snapshots=[])
    for sev in ("low", "critical", "medium", "high"):
        result.findings.append(Finding("t", sev, "/", sev, "d", "r"))
    order = [f.severity for f in result.sorted_findings()]
    assert order == ["critical", "high", "medium", "low"]


def test_snapshot_json_roundtrip():
    s = PageSnapshot(
        route="/about",
        url="http://x/about",
        html="<p>a</p>",
        console_errors=["e1"],
        link_statuses={"/gone": 404},
        viewports=[ViewportResult(100, 100, "tiny", True, 200, 100, PNG_1PX)],
    )
    s2 = PageSnapshot.from_json(s.to_json())
    assert s2.route == "/about"
    assert s2.link_statuses == {"/gone": 404}
    assert s2.viewports[0].screenshot_png == PNG_1PX
    assert s2.viewports[0].horizontal_overflow is True
    json.loads(s.to_json())  # must be valid JSON
