from __future__ import annotations

import base64
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from secqa.hub.routers.insights import mini_markdown

from .conftest import start_run

# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
FINDING = {"title": "IDOR on basket", "severity": "high", "category": "idor", "source": "api",
           "endpoint": "GET /basket?id={id}"}


def _finding(client) -> int:
    run = start_run(client)
    res = client.post(f"/api/runs/{run['id']}/findings", json=[FINDING, FINDING]).json()
    assert res["ids"][0] == res["ids"][1]  # in-batch duplicate maps to the same finding
    return res["ids"][0]


def test_screenshot_evidence_on_finding_travels_to_defect_and_report(client, project):
    fid = _finding(client)
    up = client.post(f"/api/findings/{fid}/attachments", data={"caption": "After: id=3 shows Bob's data"},
                     files={"file": ("after.png", PNG, "image/png")})
    assert up.status_code == 201, up.text
    att = up.json()
    assert (att["kind"], att["content_type"], att["finding_id"]) == ("screenshot", "image/png", fid)
    assert att["created_by"] == "human:tester"

    listed = client.get("/api/findings", params={"project": "SHOP"}).json()["items"][0]
    assert listed["attachment_count"] == 1
    assert client.get(f"/api/findings/{fid}/attachments").json()[0]["caption"].startswith("After")

    d = client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": [fid]}).json()
    detail = client.get(f"/api/defects/{d['id']}").json()
    assert [a["id"] for a in detail["attachments"]] == [att["id"]]

    img = client.get(att["url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.headers["content-disposition"].startswith("inline")

    html = client.get("/api/reports/html", params={"project": "SHOP"}).text
    assert "data:image/png;base64," in html
    assert "After: id=3 shows Bob&#39;s data" in html


def test_fake_image_is_not_served_as_image(client, project):
    fid = _finding(client)
    att = client.post(f"/api/findings/{fid}/attachments",
                      files={"file": ("shot.png", b"<html><script>alert(1)</script>", "image/png")}).json()
    assert att["content_type"] == "application/octet-stream"
    assert att["kind"] == "file"
    got = client.get(att["url"])
    assert got.headers["content-disposition"].startswith("attachment")


def test_delete_attachment(client, project):
    fid = _finding(client)
    att = client.post(f"/api/findings/{fid}/attachments", files={"file": ("a.png", PNG, "image/png")}).json()
    assert client.delete(att["url"]).status_code == 204
    assert client.get(att["url"]).status_code == 404
    assert client.get(f"/api/findings/{fid}/attachments").json() == []


def test_mini_markdown_escapes_before_formatting():
    out = str(mini_markdown("**Loc:** `x<y`\n```\n<script>alert(1)</script>\n```\n<img src=x onerror=1>"))
    assert "<b>Loc:</b>" in out and "<code>x&lt;y</code>" in out
    assert "<script>" not in out and "<img" not in out
    assert "<pre>&lt;script&gt;" in out


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def vuln_lab():
    port = _free_port()
    app = Path(__file__).resolve().parents[1] / "examples" / "vuln-lab" / "app.py"
    proc = subprocess.Popen([sys.executable, str(app), str(port)], stdout=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(5)


def test_capture_sqli_login_bypass_with_highlight_and_masking(vuln_lab, tmp_path):
    pytest.importorskip("playwright")
    from secqa.capture import CaptureError, CaptureOptions, capture

    out = tmp_path / "sqli.png"
    try:
        res = capture(CaptureOptions(url=f"{vuln_lab}/login", output=out, highlight="#role",
                                     fill=[("#email", "' OR 1=1--"), ("input[name=password]", "x")],
                                     click="button", banner="test"))
    except CaptureError as exc:
        if "no browser" in str(exc):
            pytest.skip(str(exc))
        raise
    assert res.final_url.endswith("/account")  # the payload logged us in
    assert res.highlighted == 1
    assert res.masked >= 1  # admin@lab.test was masked
    assert out.read_bytes().startswith(b"\x89PNG")
