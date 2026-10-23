"""Optional Playwright runtime path.

Imported lazily by the CLI so that `uicheck` works (and its tests pass) on
machines without Playwright or browsers installed.
"""

from __future__ import annotations

from .htmlprobe import is_internal_href, parse_html, split_href
from .snapshot import PageSnapshot, ViewportResult


class BrowserUnavailable(RuntimeError):
    pass


def load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable(
            "Playwright is not installed. Browser scanning needs it:\n"
            "  pip install playwright && playwright install chromium\n"
            "The offline `audit` command works without it."
        ) from exc
    return sync_playwright


def scan_routes(
    base_url: str,
    routes: list[str],
    viewports: list[tuple[int, int, str]],
    timeout_ms: int = 15000,
    settle_ms: int = 400,
) -> list[PageSnapshot]:
    """Visit every route x viewport with Chromium and collect snapshots."""
    sync_playwright = load_playwright()
    snapshots: list[PageSnapshot] = []
    base = base_url.rstrip("/")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:
            raise BrowserUnavailable(
                "Playwright is installed but no browser binary was found.\n"
                "Run: playwright install chromium\n"
                f"(original error: {exc})"
            ) from exc
        try:
            for route in routes:
                url = base + (route if route.startswith("/") else "/" + route)
                snap = PageSnapshot(route=route, url=url)
                # One context per route at the first viewport for signal collection;
                # other viewports reuse the same page resized.
                context = browser.new_context(
                    viewport={"width": viewports[0][0], "height": viewports[0][1]}
                )
                page = context.new_page()

                page.on(
                    "console",
                    lambda msg: snap.console_errors.append(msg.text)
                    if msg.type == "error"
                    else None,
                )
                page.on("pageerror", lambda err: snap.page_errors.append(str(err)))
                page.on(
                    "requestfailed",
                    lambda req: snap.failed_requests.append(f"{req.url} ({req.failure})"),
                )
                page.on(
                    "response",
                    lambda resp: snap.failed_requests.append(f"{resp.url} -> HTTP {resp.status}")
                    if resp.status >= 400
                    else None,
                )

                page.goto(url, timeout=timeout_ms, wait_until="load")
                page.wait_for_timeout(settle_ms)
                snap.html = page.content()

                for width, height, label in viewports:
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(settle_ms // 2)
                    metrics = page.evaluate(
                        "() => ({sw: document.documentElement.scrollWidth, "
                        "cw: document.documentElement.clientWidth})"
                    )
                    snap.viewports.append(
                        ViewportResult(
                            width=width,
                            height=height,
                            label=label or f"{width}x{height}",
                            horizontal_overflow=metrics["sw"] > metrics["cw"] + 1,
                            scroll_width=metrics["sw"],
                            client_width=metrics["cw"],
                            screenshot_png=page.screenshot(full_page=False),
                        )
                    )

                # Follow internal links and record their HTTP status.
                probe = parse_html(snap.html)
                targets: set[str] = set()
                for link in probe.links:
                    href = link.get("href").strip()
                    if href and is_internal_href(href):
                        path, _frag = split_href(href)
                        if path:
                            targets.add(path)
                for path in sorted(targets):
                    target_url = base + (path if path.startswith("/") else "/" + path)
                    try:
                        resp = context.request.get(target_url, timeout=timeout_ms)
                        snap.link_statuses[path] = resp.status
                    except Exception:
                        snap.link_statuses[path] = None

                context.close()
                snapshots.append(snap)
        finally:
            browser.close()
    return snapshots
