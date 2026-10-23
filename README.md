# UICheck

Smoke-test CLI for AI-generated web interfaces: point it at a local dev server (or saved HTML files) and get one self-contained HTML report with screenshots, console errors, failed requests, broken links, overflow, and basic accessibility/keyboard problems — before you hand the page to a human.

**Who it's for:** anyone who generates web UIs with AI tools and wants a 10-second sanity check instead of opening DevTools on every route.

> UICheck is a **smoke test**, not a complete accessibility or security audit. It catches the embarrassing stuff; it does not replace axe, Lighthouse, or a real review.

## Quickstart

```bash
# Offline, no browser needed — audit saved HTML files:
python -m uicheck audit "/=fixtures/site/index.html" --local-root fixtures/site --out report.html

# Live scan (needs: pip install playwright && playwright install chromium):
python -m http.server 8000 --directory fixtures/site &
python -m uicheck scan --base-url http://localhost:8000 --routes /,/about.html --out report.html
```

Exit code is `1` when critical/high findings exist (`--no-fail` overrides), `2` on usage/environment errors, `0` otherwise — so it drops straight into CI.

## Demo walkthrough (included fixtures)

`fixtures/site/` is a small "AI-generated" site with deliberate bugs: a link to a nonexistent `pricing.html`, an anchor to a missing `#faq`, images without `alt`, an unlabeled input, an empty icon button, an `<a>` without `href`, a positive `tabindex`, a fixed-width banner that overflows phone viewports, a 404 image, and JavaScript that throws on load.

Offline audit (works anywhere, no browser):

```bash
python -m uicheck audit "/=fixtures/site/index.html" "/about=fixtures/site/about.html" \
  --local-root fixtures/site --base-url http://localhost:8000 --out demo-report.html
```

Real output:

```
[FAIL] 7 findings (0 critical, 1 high, 5 medium, 1 low)
report written to demo-report.html
```

Live scan (with Playwright + Chromium installed):

```bash
python -m http.server 8000 --directory fixtures/site &
python -m uicheck scan --base-url http://localhost:8000 --routes /,/about.html \
  --viewports 375x812:mobile,1280x800:desktop --out demo-report.html
```

Real output (the buggy `/` route fails; `/about.html` passes clean):

```
[FAIL] 12 findings (1 critical, 4 high, 6 medium, 1 low)
report written to demo-report.html
```

The live scan additionally catches the uncaught JS exception, the `console.error`, the 404 image, and the horizontal overflow at 375px, and embeds real screenshots in the report.

> Git Bash on Windows converts leading `/` arguments into Windows paths; prefix scan commands with `MSYS_NO_PATHCONV=1` there.

Open the report in any browser — it's a single self-contained HTML file: severity badges, per-finding reproduction steps, console/network signals, and per-viewport screenshots.

## Commands

| Command | Needs a browser? | What it does |
|---|---|---|
| `scan` | yes (Playwright + Chromium) | Visit routes × viewports, capture screenshots, console errors, failed requests, overflow, link statuses |
| `audit` | no | Static analysis of saved HTML files; resolves internal links against `--local-root` or `--routes` |
| `report` | no | Re-render a report from a saved snapshot JSON |

## Checks

- **Console errors / uncaught exceptions** (live scan) — high / critical
- **Failed network requests** incl. HTTP ≥ 400 (live scan) — high
- **Broken internal links** — HTTP status from the browser, or file/route resolution offline; also `#anchors` with no matching `id` — high / medium
- **Horizontal overflow** per viewport (live scan) — medium
- **Missing accessible names** — empty buttons, links without text, images without `alt`, inputs without labels — medium
- **Keyboard-focus failures** — `<a>` without `href`, interactive elements with `tabindex="-1"`, positive `tabindex` — medium / low

UICheck never modifies your source code. It only reads and reports.

## Development

```bash
python -m pip install pytest   # only test dependency
python -m pytest -q            # 34 tests, no browser, no network
```

Tests cover HTML probing, every check, report rendering, snapshot serialization, and CLI failure paths against saved fixtures. The Playwright path (`uicheck/browser.py`) is imported lazily and exercised manually.

## Known limitations

- Static `audit` mode cannot measure layout overflow, console output, or runtime link status — those checks are skipped and noted in the report.
- Accessible-name detection is a static approximation: it does not evaluate CSS visibility, computed names, or `<label for>` associations.
- Only Chromium is used for live scans; no cross-browser matrix.
- SPA routes that require client-side rendering still work in `scan` (real browser), but `audit` only sees the static HTML you give it.

## Roadmap

1. `scan --save-snapshots` to persist JSON snapshots and diff findings between runs (regression gate for AI codegen loops).
2. Form interaction probes: submit empty forms, click primary buttons, and capture resulting errors.
3. Baseline file support (`--baseline uicheck-baseline.json`) to acknowledge known findings in CI.

## License

MIT — see [LICENSE](LICENSE).
