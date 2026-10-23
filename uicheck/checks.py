"""Checks: turn PageSnapshots (plus optional local files) into Findings.

Every check is pure Python over a PageSnapshot — the browser is only one way
of producing a snapshot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .htmlprobe import accessible_name, is_internal_href, parse_html, split_href
from .snapshot import PageSnapshot

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class Finding:
    check_id: str
    severity: str  # critical | high | medium | low
    route: str
    title: str
    detail: str
    repro: str


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    snapshots: list[PageSnapshot] = field(default_factory=list)
    base_url: str = ""
    skipped: list[str] = field(default_factory=list)  # checks that could not run (e.g. overflow offline)

    def sorted_findings(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.route, f.check_id))

    @property
    def ok(self) -> bool:
        return not any(f.severity in ("critical", "high") for f in self.findings)


def _describe_element(tag: str, line: int, extra: str = "") -> str:
    base = f"<{tag}> on line {line}"
    return f"{base} ({extra})" if extra else base


def run_checks(
    snapshots: list[PageSnapshot],
    base_url: str = "",
    local_root: str | None = None,
    known_routes: list[str] | None = None,
) -> ScanResult:
    result = ScanResult(snapshots=snapshots, base_url=base_url)
    for snap in snapshots:
        probe = parse_html(snap.html) if snap.html else None
        _check_console(snap, result)
        _check_failed_requests(snap, result)
        _check_links(snap, probe, result, local_root, known_routes)
        if probe is not None:
            _check_accessible_names(snap, probe, result)
            _check_keyboard_focus(snap, probe, result)
        if not _check_overflow(snap, result):
            result.skipped.append(
                f"horizontal-overflow: not measured for {snap.route} (needs the browser scan path)"
            )
    return result


def _check_console(snap: PageSnapshot, result: ScanResult) -> None:
    for msg in snap.console_errors:
        result.findings.append(
            Finding(
                check_id="console-error",
                severity="high",
                route=snap.route,
                title="Console error while rendering the page",
                detail=msg,
                repro=f"Open {snap.url} and watch the browser console.",
            )
        )
    for msg in snap.page_errors:
        result.findings.append(
            Finding(
                check_id="uncaught-exception",
                severity="critical",
                route=snap.route,
                title="Uncaught JavaScript exception",
                detail=msg,
                repro=f"Open {snap.url}; the page throws during load or interaction.",
            )
        )


def _check_failed_requests(snap: PageSnapshot, result: ScanResult) -> None:
    for req in snap.failed_requests:
        result.findings.append(
            Finding(
                check_id="failed-request",
                severity="high",
                route=snap.route,
                title="Network request failed",
                detail=req,
                repro=f"Open {snap.url} and check the Network tab for failing requests.",
            )
        )


def _check_links(
    snap: PageSnapshot,
    probe,
    result: ScanResult,
    local_root: str | None,
    known_routes: list[str] | None,
) -> None:
    if probe is None:
        return
    routes = {r if r.startswith("/") else "/" + r for r in (known_routes or [])}
    seen: set[str] = set()
    for link in probe.links:
        href = link.get("href").strip()
        if not href:
            continue  # handled by keyboard-focus check
        if not is_internal_href(href):
            continue
        path, fragment = split_href(href)

        if not path:  # pure #fragment link
            if fragment and not probe.has_anchor(fragment):
                result.findings.append(
                    Finding(
                        check_id="broken-anchor",
                        severity="medium",
                        route=snap.route,
                        title="Link points to a missing in-page anchor",
                        detail=f'href="#{fragment}" but no element has id="{fragment}" ({_describe_element("a", link.line)})',
                        repro=f"Open {snap.url} and click the link — nothing scrolls into view.",
                    )
                )
            continue

        # Deduplicate per target so nav menus don't flood the report.
        key = path
        if key in seen:
            continue
        seen.add(key)

        if path in snap.link_statuses or href in snap.link_statuses:
            status = snap.link_statuses.get(path, snap.link_statuses.get(href))
            if status is None:
                result.findings.append(
                    Finding(
                        check_id="broken-link",
                        severity="high",
                        route=snap.route,
                        title="Internal link request never completed",
                        detail=f'href="{href}" ({_describe_element("a", link.line, link.text[:60])})',
                        repro=f"Open {snap.url} and click the link to {href}.",
                    )
                )
            elif status >= 400:
                result.findings.append(
                    Finding(
                        check_id="broken-link",
                        severity="high",
                        route=snap.route,
                        title=f"Internal link returns HTTP {status}",
                        detail=f'href="{href}" ({_describe_element("a", link.line, link.text[:60])})',
                        repro=f"Open {snap.url} and click the link to {href}.",
                    )
                )
            continue

        # Offline resolution against local files or the declared route list.
        if local_root:
            rel = path.lstrip("/")
            target = os.path.join(local_root, rel)
            candidates = [target, os.path.join(target, "index.html")]
            if not os.path.splitext(target)[1]:
                candidates.insert(1, target + ".html")
            if not any(os.path.isfile(c) for c in candidates):
                result.findings.append(
                    Finding(
                        check_id="broken-link",
                        severity="high",
                        route=snap.route,
                        title="Internal link target does not exist on disk",
                        detail=f'href="{href}" ({_describe_element("a", link.line, link.text[:60])})',
                        repro=f"Serve {local_root} and click the link to {href}.",
                    )
                )
        elif routes and path not in routes and path + "/" not in routes:
            result.findings.append(
                Finding(
                    check_id="broken-link",
                    severity="high",
                    route=snap.route,
                    title="Internal link points to an unknown route",
                    detail=f'href="{href}" is not in the scanned route list ({_describe_element("a", link.line)})',
                    repro=f"Open {snap.url} and click the link to {href}.",
                )
            )


def _check_accessible_names(snap: PageSnapshot, probe, result: ScanResult) -> None:
    def add(tag: str, line: int, why: str, extra: str = "") -> None:
        result.findings.append(
            Finding(
                check_id="missing-accessible-name",
                severity="medium",
                route=snap.route,
                title=f"{why}",
                detail=_describe_element(tag, line, extra),
                repro=(
                    f"Open {snap.url} with a screen reader (or inspect the accessibility "
                    "tree in DevTools) — the control is announced without a name."
                ),
            )
        )

    for btn in probe.buttons:
        if not accessible_name(btn):
            add("button", btn.line, "<button> has no accessible name")
    for link in probe.links:
        if link.get("href") and not accessible_name(link):
            add("a", link.line, "Link has no accessible name", f'href="{link.get("href")}"')
    for img in probe.images:
        if "alt" not in img.attrs:
            add("img", img.line, "Image is missing its alt attribute", f'src="{img.get("src")}"')
    for inp in probe.inputs:
        if not accessible_name(inp) and not inp.get("aria-labelledby"):
            add(
                "input",
                inp.line,
                "Form control has no label or aria-label",
                f'type="{inp.get("type", "text")}" name="{inp.get("name")}"',
            )


def _check_keyboard_focus(snap: PageSnapshot, probe, result: ScanResult) -> None:
    for link in probe.links:
        if not link.get("href"):
            result.findings.append(
                Finding(
                    check_id="keyboard-focus",
                    severity="medium",
                    route=snap.route,
                    title="<a> without href is not keyboard-focusable",
                    detail=_describe_element("a", link.line, link.text[:60]),
                    repro=f"Open {snap.url} and press Tab — this link is skipped.",
                )
            )
    for el in probe.tabindex_elements:
        raw = el.get("tabindex")
        try:
            value = int(raw)
        except ValueError:
            continue
        if value > 0:
            result.findings.append(
                Finding(
                    check_id="keyboard-focus",
                    severity="low",
                    route=snap.route,
                    title=f"Positive tabindex ({value}) breaks the natural focus order",
                    detail=_describe_element(el.tag, el.line),
                    repro=f"Open {snap.url} and tab through the page — focus jumps unexpectedly.",
                )
            )
        elif value < 0 and el.tag in ("a", "button", "input", "select", "textarea"):
            result.findings.append(
                Finding(
                    check_id="keyboard-focus",
                    severity="medium",
                    route=snap.route,
                    title="Interactive element removed from the tab order (tabindex=-1)",
                    detail=_describe_element(el.tag, el.line),
                    repro=f"Open {snap.url} and press Tab — keyboard users can never reach it.",
                )
            )


def _check_overflow(snap: PageSnapshot, result: ScanResult) -> bool:
    """Emit findings for horizontal overflow. Returns False when not measured."""
    measured = False
    for vp in snap.viewports:
        if vp.horizontal_overflow is None:
            continue
        measured = True
        if vp.horizontal_overflow:
            label = vp.label or f"{vp.width}x{vp.height}"
            result.findings.append(
                Finding(
                    check_id="horizontal-overflow",
                    severity="medium",
                    route=snap.route,
                    title=f"Horizontal overflow at {label}",
                    detail=(
                        f"Page scrolls sideways: scrollWidth={vp.scroll_width}px "
                        f"> viewport width={vp.client_width or vp.width}px."
                    ),
                    repro=f"Open {snap.url} in a {label} window and scroll right.",
                )
            )
    return measured
