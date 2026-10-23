"""Self-contained HTML report: findings + screenshots, no external assets."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from .checks import SEVERITY_ORDER, ScanResult
from .snapshot import PageSnapshot

_BADGE = {
    "critical": "#7f1d1d",
    "high": "#b91c1c",
    "medium": "#b45309",
    "low": "#1d4ed8",
}

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       margin: 0; background: #f6f7f9; color: #1f2430; }
header { background: #111827; color: #f9fafb; padding: 28px 40px; }
header h1 { margin: 0 0 6px; font-size: 22px; }
header p { margin: 2px 0; color: #9ca3af; font-size: 13px; }
main { max-width: 1080px; margin: 0 auto; padding: 24px 40px 64px; }
.summary { display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0; }
.chip { border-radius: 8px; padding: 10px 16px; background: #fff; border: 1px solid #e5e7eb;
        font-size: 14px; }
.chip b { font-size: 20px; display: block; }
section.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
               padding: 18px 22px; margin: 16px 0; }
h2 { font-size: 17px; margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #eceef1;
         vertical-align: top; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; color: #fff; border-radius: 999px; padding: 2px 10px;
         font-size: 11.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .4px; }
code { background: #f1f2f4; border-radius: 4px; padding: 1px 5px; font-size: 12.5px; }
.repro { color: #4b5563; font-size: 12.5px; margin-top: 4px; }
.shots { display: flex; gap: 14px; flex-wrap: wrap; }
.shot { max-width: 340px; }
.shot img { width: 100%; border: 1px solid #d1d5db; border-radius: 6px; display: block; }
.shot figcaption { font-size: 12px; color: #6b7280; margin-top: 4px; }
.empty { color: #6b7280; font-style: italic; }
.note { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px;
        padding: 12px 16px; font-size: 13px; color: #92400e; margin: 16px 0; }
details { margin-top: 6px; }
summary { cursor: pointer; font-size: 12.5px; color: #2563eb; }
"""


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def render_report(result: ScanResult, tool_version: str = "") -> str:
    findings = result.sorted_findings()
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = [
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>UICheck report — {_e(result.base_url or 'offline audit')}</title>",
        f"<style>{_CSS}</style></head><body>",
        "<header>",
        "<h1>UICheck smoke-test report</h1>",
        f"<p>Target: {_e(result.base_url or 'offline audit of saved HTML')} &middot; "
        f"Routes: {len(result.snapshots)} &middot; Generated {generated}"
        + (f" &middot; UICheck {_e(tool_version)}" if tool_version else "")
        + "</p>",
        "<p>Smoke test only — this is not a complete accessibility or security audit.</p>",
        "</header><main>",
    ]

    # Summary chips
    parts.append('<div class="summary">')
    parts.append(f'<div class="chip"><b>{len(findings)}</b>findings</div>')
    for sev in ("critical", "high", "medium", "low"):
        if counts.get(sev):
            color = _BADGE[sev]
            parts.append(
                f'<div class="chip"><b style="color:{color}">{counts[sev]}</b>{sev}</div>'
            )
    parts.append("</div>")

    if result.skipped:
        items = "".join(f"<li>{_e(s)}</li>" for s in sorted(set(result.skipped)))
        parts.append(
            f'<div class="note">Some checks were not run:<ul>{items}</ul></div>'
        )

    # Findings
    parts.append('<section class="card"><h2>Findings</h2>')
    if not findings:
        parts.append('<p class="empty">No findings. All enabled checks passed.</p>')
    else:
        parts.append(
            "<table><thead><tr><th>Severity</th><th>Route</th><th>Finding</th>"
            "<th>Reproduction</th></tr></thead><tbody>"
        )
        for f in findings:
            color = _BADGE.get(f.severity, "#374151")
            parts.append(
                "<tr>"
                f'<td><span class="badge" style="background:{color}">{_e(f.severity)}</span></td>'
                f"<td><code>{_e(f.route)}</code><br><span style='color:#9ca3af;font-size:11.5px'>{_e(f.check_id)}</span></td>"
                f"<td><b>{_e(f.title)}</b><br>{_e(f.detail)}</td>"
                f'<td class="repro">{_e(f.repro)}</td>'
                "</tr>"
            )
        parts.append("</tbody></table>")
    parts.append("</section>")

    # Per-route detail: console errors, failed requests, screenshots
    for snap in result.snapshots:
        parts.append(f'<section class="card"><h2>Route <code>{_e(snap.route)}</code></h2>')
        parts.append(f"<p style='font-size:13px;color:#6b7280'>URL: {_e(snap.url)}</p>")
        if snap.console_errors or snap.page_errors:
            parts.append("<h3 style='font-size:14px'>Console output</h3><ul>")
            for msg in snap.page_errors:
                parts.append(f"<li><b>uncaught:</b> {_e(msg)}</li>")
            for msg in snap.console_errors:
                parts.append(f"<li>{_e(msg)}</li>")
            parts.append("</ul>")
        if snap.failed_requests:
            parts.append("<h3 style='font-size:14px'>Failed requests</h3><ul>")
            for req in snap.failed_requests:
                parts.append(f"<li>{_e(req)}</li>")
            parts.append("</ul>")
        shots = [(vp, vp.screenshot_data_uri()) for vp in snap.viewports]
        shots = [(vp, uri) for vp, uri in shots if uri]
        if shots:
            parts.append('<div class="shots">')
            for vp, uri in shots:
                label = vp.label or f"{vp.width}x{vp.height}"
                overflow = ""
                if vp.horizontal_overflow is True:
                    overflow = " — horizontal overflow detected"
                elif vp.horizontal_overflow is False:
                    overflow = " — no overflow"
                parts.append(
                    f'<figure class="shot"><img src="{uri}" alt="Screenshot at {_e(label)}">'
                    f"<figcaption>{_e(label)}{_e(overflow)}</figcaption></figure>"
                )
            parts.append("</div>")
        if not (snap.console_errors or snap.page_errors or snap.failed_requests or shots):
            parts.append('<p class="empty">No runtime signals captured for this route.</p>')
        parts.append("</section>")

    parts.append("</main></body></html>")
    return "".join(parts)
