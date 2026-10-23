import json
import os

import pytest

from uicheck.cli import build_parser, main
from uicheck.snapshot import PageSnapshot

SITE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "site")


def test_audit_fixture_site(tmp_path, capsys):
    out = str(tmp_path / "report.html")
    code = main([
        "audit",
        f"/={os.path.join(SITE, 'index.html')}",
        f"/about={os.path.join(SITE, 'about.html')}",
        "--local-root", SITE,
        "--out", out,
    ])
    assert code == 1  # fixture site has high-severity bugs
    assert os.path.isfile(out)
    with open(out, encoding="utf-8") as fh:
        html = fh.read()
    assert "pricing.html" in html  # the deliberately broken link shows up
    captured = capsys.readouterr()
    assert "[FAIL]" in captured.out
    assert "report written to" in captured.out


def test_audit_no_fail_flag(tmp_path):
    out = str(tmp_path / "r.html")
    code = main([
        "audit",
        os.path.join(SITE, "index.html"),
        "--local-root", SITE,
        "--out", out,
        "--no-fail",
    ])
    assert code == 0


def test_audit_missing_file(tmp_path, capsys):
    code = main(["audit", "/=does-not-exist.html", "--out", str(tmp_path / "r.html")])
    assert code == 2
    assert "file not found" in capsys.readouterr().err


def test_audit_bad_local_root(tmp_path, capsys):
    code = main([
        "audit",
        os.path.join(SITE, "index.html"),
        "--local-root", os.path.join(SITE, "nope"),
        "--out", str(tmp_path / "r.html"),
    ])
    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_report_from_snapshot_json(tmp_path):
    snap = PageSnapshot(
        route="/", url="http://x/", html='<a href="#nope">x</a>',
        console_errors=["boom"],
    )
    path = tmp_path / "snap.json"
    path.write_text(snap.to_json(), encoding="utf-8")
    out = str(tmp_path / "r.html")
    code = main(["report", str(path), "--out", out])
    assert code == 1
    with open(out, encoding="utf-8") as fh:
        assert "boom" in fh.read()


def test_report_invalid_json(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    code = main(["report", str(path), "--out", str(tmp_path / "r.html")])
    assert code == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_report_wrong_shape_json(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    code = main(["report", str(path), "--out", str(tmp_path / "r.html")])
    assert code == 2
    assert "not a UICheck snapshot" in capsys.readouterr().err


def test_report_non_object_json_items(tmp_path, capsys):
    for payload in ("[1, 2]", '"hello"', "null", '{"route": "/", "url": "u", "viewports": [1]}'):
        path = tmp_path / "bad.json"
        path.write_text(payload, encoding="utf-8")
        code = main(["report", str(path), "--out", str(tmp_path / "r.html")])
        assert code == 2, payload
    assert "not a UICheck snapshot" in capsys.readouterr().err


def test_audit_empty_path_in_route_spec(tmp_path, capsys):
    code = main(["audit", "/x=", "--out", str(tmp_path / "r.html")])
    assert code == 2
    assert "no file specified" in capsys.readouterr().err


def test_audit_empty_route_falls_back_to_basename(tmp_path, capsys):
    code = main([
        "audit",
        f"={os.path.join(SITE, 'index.html')}",
        "--local-root", SITE,
        "--out", str(tmp_path / "r.html"),
    ])
    assert code == 1  # audited as index.html instead of crashing on an empty route


def test_unwritable_out_path_is_clean_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["audit", os.path.join(SITE, "index.html"), "--local-root", SITE, "--out", str(tmp_path)])
    assert excinfo.value.code == 2
    assert "cannot write report" in capsys.readouterr().err


def test_invalid_timeout_rejected(capsys):
    parser = build_parser()
    for bad in ("0", "-5", "soon"):
        with pytest.raises(SystemExit):
            parser.parse_args(["scan", "--base-url", "http://x", "--timeout", bad])
    err = capsys.readouterr().err
    assert "positive integer" in err or "invalid integer" in err


def test_invalid_viewport_rejected(capsys):
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["scan", "--base-url", "http://x", "--viewports", "wide"])
    assert "invalid viewport" in capsys.readouterr().err


def test_scan_requires_base_url():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["scan"])
