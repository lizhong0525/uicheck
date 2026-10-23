"""UICheck command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .checks import run_checks
from .report import render_report
from .snapshot import PageSnapshot, ViewportResult

DEFAULT_VIEWPORTS = [(375, 812, "mobile"), (1280, 800, "desktop")]


def _parse_viewports(spec: str) -> list[tuple[int, int, str]]:
    """Parse '375x812:mobile,1280x800:desktop' (labels optional)."""
    out = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        size, _, label = chunk.partition(":")
        try:
            w, h = size.lower().split("x")
            width, height = int(w), int(h)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"invalid viewport '{chunk}' - expected WIDTHxHEIGHT[:label], e.g. 375x812:mobile"
            )
        if width <= 0 or height <= 0:
            raise argparse.ArgumentTypeError(f"invalid viewport '{chunk}' - dimensions must be positive")
        out.append((width, height, label))
    if not out:
        raise argparse.ArgumentTypeError("at least one viewport is required")
    return out


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {value!r}")
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return number


def _parse_routes(spec: str) -> list[str]:
    routes = [r.strip() for r in spec.split(",") if r.strip()]
    if not routes:
        raise argparse.ArgumentTypeError("at least one route is required")
    return [r if r.startswith("/") else "/" + r for r in routes]


def _write_report(result, out_path: str) -> None:
    html_text = render_report(result, tool_version=__version__)
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html_text)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        print(f"error: cannot write report to {out_path}: {reason}", file=sys.stderr)
        raise SystemExit(2)


def cmd_scan(args: argparse.Namespace) -> int:
    from .browser import BrowserUnavailable, scan_routes

    try:
        snapshots = scan_routes(
            base_url=args.base_url,
            routes=args.routes,
            viewports=args.viewports,
            timeout_ms=args.timeout * 1000,
        )
    except BrowserUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # unreachable host, DNS failure, etc.
        print(f"error: scan failed - {exc}", file=sys.stderr)
        return 2

    result = run_checks(snapshots, base_url=args.base_url, known_routes=args.routes)
    _write_report(result, args.out)
    _print_summary(result, args.out)
    return 0 if args.no_fail or result.ok else 1


def cmd_audit(args: argparse.Namespace) -> int:
    """Offline static audit of saved HTML files (no browser needed)."""
    snapshots: list[PageSnapshot] = []
    for entry in args.files:
        route, sep, path = entry.partition("=")
        if not sep:
            route, path = os.path.basename(entry), entry
        if not path:
            print(f"error: no file specified in '{entry}' (expected route=path)", file=sys.stderr)
            return 2
        if not route:
            route = os.path.basename(path)
        if not os.path.isfile(path):
            print(f"error: file not found: {path}", file=sys.stderr)
            return 2
        try:
            with open(path, "r", encoding="utf-8") as fh:
                html_text = fh.read()
        except UnicodeDecodeError:
            print(f"error: {path} is not valid UTF-8 text", file=sys.stderr)
            return 2
        snapshots.append(PageSnapshot(route=route, url=os.path.abspath(path), html=html_text))

    local_root = args.local_root
    if local_root and not os.path.isdir(local_root):
        print(f"error: --local-root is not a directory: {local_root}", file=sys.stderr)
        return 2

    result = run_checks(
        snapshots,
        base_url=args.base_url or "",
        local_root=local_root,
        known_routes=args.routes,
    )
    _write_report(result, args.out)
    _print_summary(result, args.out)
    return 0 if args.no_fail or result.ok else 1


def cmd_report(args: argparse.Namespace) -> int:
    """Re-render a report from a saved snapshot JSON file."""
    if not os.path.isfile(args.snapshot):
        print(f"error: file not found: {args.snapshot}", file=sys.stderr)
        return 2
    try:
        with open(args.snapshot, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"error: {args.snapshot} is not valid JSON ({exc})", file=sys.stderr)
        return 2
    items = raw if isinstance(raw, list) else [raw]
    for item in items:
        if not isinstance(item, dict):
            print(f"error: {args.snapshot} is not a UICheck snapshot (expected a JSON object)", file=sys.stderr)
            return 2
    try:
        snapshots = [PageSnapshot.from_json(json.dumps(item)) for item in items]
    except (KeyError, TypeError, AttributeError) as exc:
        print(f"error: {args.snapshot} is not a UICheck snapshot ({exc})", file=sys.stderr)
        return 2
    result = run_checks(snapshots, base_url=args.base_url or "")
    _write_report(result, args.out)
    _print_summary(result, args.out)
    return 0 if args.no_fail or result.ok else 1


def _print_summary(result, out_path: str) -> None:
    counts: dict[str, int] = {}
    for f in result.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    parts = [f"{counts.get(s, 0)} {s}" for s in ("critical", "high", "medium", "low")]
    status = "PASS" if result.ok else "FAIL"
    print(f"[{status}] {len(result.findings)} findings ({', '.join(parts)})")
    print(f"report written to {out_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uicheck",
        description=(
            "Smoke-test AI-generated web interfaces: console errors, failed requests, "
            "broken internal links, horizontal overflow, missing accessible names, and "
            "basic keyboard-focus failures. Not a full accessibility/security audit."
        ),
    )
    parser.add_argument("--version", action="version", version=f"uicheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="live scan with Playwright/Chromium (optional dependency)")
    scan.add_argument("--base-url", required=True, help="e.g. http://localhost:8000")
    scan.add_argument("--routes", type=_parse_routes, default=["/"],
                      help="comma-separated routes, e.g. /,/about,/pricing")
    scan.add_argument("--viewports", type=_parse_viewports, default=DEFAULT_VIEWPORTS,
                      help="comma-separated WIDTHxHEIGHT[:label], e.g. 375x812:mobile,1280x800:desktop")
    scan.add_argument("--timeout", type=_positive_int, default=15, help="per-page timeout in seconds")
    scan.add_argument("--out", default="uicheck-report.html")
    scan.add_argument("--no-fail", action="store_true", help="always exit 0 even with findings")
    scan.set_defaults(func=cmd_scan)

    audit = sub.add_parser("audit", help="offline static audit of saved HTML files (no browser)")
    audit.add_argument("files", nargs="+",
                       help="HTML files, optionally as route=path (e.g. /=site/index.html)")
    audit.add_argument("--local-root", help="directory used to resolve internal links to files")
    audit.add_argument("--routes", type=_parse_routes, default=None,
                       help="declared routes for link checking when --local-root is not used")
    audit.add_argument("--base-url", default="", help="display-only target shown in the report")
    audit.add_argument("--out", default="uicheck-report.html")
    audit.add_argument("--no-fail", action="store_true", help="always exit 0 even with findings")
    audit.set_defaults(func=cmd_audit)

    rep = sub.add_parser("report", help="re-render a report from a saved snapshot JSON")
    rep.add_argument("snapshot", help="snapshot JSON (single object or list)")
    rep.add_argument("--base-url", default="")
    rep.add_argument("--out", default="uicheck-report.html")
    rep.add_argument("--no-fail", action="store_true")
    rep.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
