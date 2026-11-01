from __future__ import annotations

import io
import time
import zipfile

from secqa import cli

from .conftest import start_run

HTML = b"<!doctype html><html><body><script>document.title='k6'</script>k6 dashboard</body></html>"


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _upload(client, run_id, name, data, tool="k6", title=None):
    return client.post(f"/api/runs/{run_id}/reports", data={"tool": tool, **({"title": title} if title else {})},
                       files={"file": (name, data)})


def test_html_report_is_served_sandboxed_via_signed_link(client, project):
    run = start_run(client, kind="performance")
    r = _upload(client, run["id"], "k6-report.html", HTML, title="Load test dashboard")
    assert r.status_code == 201, r.text
    rep = r.json()
    assert (rep["tool"], rep["title"], rep["run_kind"], rep["project_key"]) == (
        "k6", "Load test dashboard", "performance", "SHOP")
    assert rep["view_url"].startswith(f"/r/{rep['id']}/") and rep["view_url"].endswith("/index.html")

    page = client.get(rep["view_url"])
    assert page.status_code == 200 and b"k6 dashboard" in page.content
    csp = page.headers["content-security-policy"]
    assert "sandbox allow-scripts" in csp and "allow-same-origin" not in csp
    assert page.headers["x-content-type-options"] == "nosniff"

    assert [x["id"] for x in client.get(f"/api/runs/{run['id']}/reports").json()] == [rep["id"]]
    assert client.get("/api/tool-reports", params={"project": "SHOP", "tool": "k6"}).json()[0]["id"] == rep["id"]


def test_tampered_or_expired_links_are_rejected(client, project):
    run = start_run(client)
    rep = _upload(client, run["id"], "r.html", HTML).json()
    _, _, rid, exp, sig, entry = rep["view_url"].split("/", 5)
    assert client.get(f"/r/{rid}/{exp}/{'0' * len(sig)}/{entry}").status_code == 403
    assert client.get(f"/r/{rid}/{int(exp) + 1}/{sig}/{entry}").status_code == 403  # exp is signed
    past = int(time.time()) - 10
    assert client.get(f"/r/{rid}/{past}/{sig}/{entry}").status_code == 403
    for traversal in ("../../../../etc/passwd", "%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
                      "..%2f..%2f..%2f..%2fetc%2fpasswd"):
        res = client.get(f"/r/{rid}/{exp}/{sig}/{traversal}")
        assert b"root:" not in res.content, traversal


def test_zip_report_folder_with_assets_and_zip_slip_dropped(client, project, settings):
    run = start_run(client, kind="performance")
    data = _zip({"jmeter/index.html": b"<html><script src='content/js/app.js'></script></html>",
                 "jmeter/content/js/app.js": b"console.log(1)",
                 "../../evil.txt": b"pwned"})
    rep = _upload(client, run["id"], "jmeter-report.zip", data, tool="jmeter").json()
    assert rep["view_url"].endswith("/jmeter/index.html")
    base = rep["view_url"].rsplit("/", 1)[0]
    js = client.get(f"{base}/content/js/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert not list(settings.data_dir.rglob("evil.txt"))


def test_rejects_non_reports(client, project):
    run = start_run(client)
    assert _upload(client, run["id"], "x.txt", b"just text").status_code == 422
    assert _upload(client, run["id"], "x.zip", _zip({"a.json": b"{}"})).status_code == 422
    assert _upload(client, run["id"], "x.html", HTML, tool="evil<script>").json()["tool"] == "other"


def test_delete_report_removes_folder_and_reports_are_not_evidence(client, project, settings):
    run = start_run(client)
    rep = _upload(client, run["id"], "r.html", HTML).json()
    assert len(list((settings.data_dir / "attachments").rglob("index.html"))) == 1
    res = client.post(f"/api/runs/{run['id']}/findings",
                      json=[{"title": "x", "severity": "low", "category": "xss"}]).json()
    d = client.post("/api/projects/SHOP/defects/from-findings", json={"finding_ids": res["ids"]}).json()
    assert client.get(f"/api/defects/{d['id']}").json()["attachments"] == []
    assert client.delete(f"/api/attachments/{rep['id']}").status_code == 204
    assert not list((settings.data_dir / "attachments").rglob("index.html"))
    assert client.get(rep["view_url"]).status_code == 404


def test_cli_zips_report_folder(tmp_path):
    d = tmp_path / "jmeter-report"
    (d / "content").mkdir(parents=True)
    (d / "index.html").write_text("<html></html>")
    (d / "content" / "a.js").write_text("1")
    names = zipfile.ZipFile(io.BytesIO(cli._zip_dir(d))).namelist()
    assert sorted(names) == ["content/a.js", "index.html"]
