#!/usr/bin/env python3
"""SecQA Pentest Framework — local review server.

Serves a REST API over the findings.db SQLite database plus the static
dashboard (tools/server/dashboard/). Stdlib only — no third-party
dependencies, so it runs the same way in any project this framework is
copied into.

Usage:
    python3 tools/server/app.py [--db-path findings.db] [--port 8787]

Then open http://127.0.0.1:8787/
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = pathlib.Path(__file__).resolve().parent
DASHBOARD_DIR = HERE / "dashboard"

DB_PATH = "findings.db"  # overridden by --db-path in main()
EVIDENCE_ROOT = "evidence"  # overridden by --evidence-dir in main()

FINDING_FIELDS = {
    "run_id", "source", "tool", "category", "title", "description",
    "severity", "cvss_score", "cvss_vector", "cwe_id", "owasp_id",
    "iso_control", "file_path", "line_start", "line_end", "endpoint",
    "evidence_path", "remediation",
}

REVIEW_FIELDS = {"status", "reviewed_by", "review_comment"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


class Handler(BaseHTTPRequestHandler):
    server_version = "SecQAReview/1.0"

    # ---- helpers -------------------------------------------------
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message, status=400):
        self._send_json({"error": message}, status)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def log_message(self, fmt, *args):  # quieter logs
        pass

    # ---- static file serving for the dashboard --------------------
    def _serve_static(self, rel_path: str):
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        target = (DASHBOARD_DIR / rel_path).resolve()
        if DASHBOARD_DIR not in target.parents and target != DASHBOARD_DIR:
            self._send_error_json("forbidden", 403)
            return
        if not target.is_file():
            self._send_error_json("not found", 404)
            return
        content_type = "text/html; charset=utf-8"
        if target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_evidence(self, rel_path: str):
        root = pathlib.Path(EVIDENCE_ROOT).resolve()
        target = (root / rel_path).resolve()
        if root not in target.parents and target != root:
            self._send_error_json("forbidden", 403)
            return
        if not target.is_file():
            self._send_error_json("not found", 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- routing ---------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if path == "/api/runs":
            return self._list_runs()
        if path == "/api/findings":
            return self._list_findings(qs)
        if path == "/api/stats":
            return self._stats(qs)
        if path.startswith("/evidence/"):
            return self._serve_evidence(path[len("/evidence/"):])
        if path.startswith("/api/"):
            return self._send_error_json("not found", 404)
        return self._serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/findings":
            return self._create_finding()
        return self._send_error_json("not found", 404)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        m = re.match(r"^/api/findings/(\d+)$", parsed.path)
        if m:
            return self._update_finding(int(m.group(1)))
        return self._send_error_json("not found", 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        m = re.match(r"^/api/findings/(\d+)$", parsed.path)
        if m:
            return self._delete_finding(int(m.group(1)))
        return self._send_error_json("not found", 404)

    # ---- handlers ----------------------------------------------------
    def _list_runs(self):
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
            self._send_json([row_to_dict(r) for r in rows])
        finally:
            conn.close()

    def _list_findings(self, qs: dict):
        conn = get_conn()
        try:
            clauses, params = [], []
            if qs.get("run_id"):
                clauses.append("run_id = ?")
                params.append(qs["run_id"])
            if qs.get("status"):
                clauses.append("status = ?")
                params.append(qs["status"])
            if qs.get("severity"):
                clauses.append("severity = ?")
                params.append(qs["severity"])
            if qs.get("category"):
                clauses.append("category = ?")
                params.append(qs["category"])
            if qs.get("source"):
                clauses.append("source = ?")
                params.append(qs["source"])
            if qs.get("q"):
                clauses.append("(title LIKE ? OR description LIKE ? OR file_path LIKE ?)")
                like = f"%{qs['q']}%"
                params.extend([like, like, like])
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = (
                f"SELECT * FROM findings {where} "
                "ORDER BY CASE severity "
                "WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 "
                "WHEN 'low' THEN 3 ELSE 4 END, created_at DESC"
            )
            rows = conn.execute(sql, params).fetchall()
            self._send_json([row_to_dict(r) for r in rows])
        finally:
            conn.close()

    def _stats(self, qs: dict):
        conn = get_conn()
        try:
            clauses, params = [], []
            if qs.get("run_id"):
                clauses.append("run_id = ?")
                params.append(qs["run_id"])
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

            by_severity = conn.execute(
                f"SELECT severity, COUNT(*) c FROM findings {where} GROUP BY severity", params
            ).fetchall()
            by_status = conn.execute(
                f"SELECT status, COUNT(*) c FROM findings {where} GROUP BY status", params
            ).fetchall()
            by_category = conn.execute(
                f"SELECT category, COUNT(*) c FROM findings {where} GROUP BY category ORDER BY c DESC",
                params,
            ).fetchall()
            by_source = conn.execute(
                f"SELECT source, COUNT(*) c FROM findings {where} GROUP BY source", params
            ).fetchall()
            trend = conn.execute(
                "SELECT r.id run_id, r.started_at, "
                "SUM(CASE WHEN f.severity='critical' THEN 1 ELSE 0 END) critical, "
                "SUM(CASE WHEN f.severity='high' THEN 1 ELSE 0 END) high, "
                "SUM(CASE WHEN f.severity='medium' THEN 1 ELSE 0 END) medium, "
                "SUM(CASE WHEN f.severity='low' THEN 1 ELSE 0 END) low "
                "FROM runs r LEFT JOIN findings f ON f.run_id = r.id "
                "GROUP BY r.id ORDER BY r.started_at ASC"
            ).fetchall()

            self._send_json({
                "by_severity": {r["severity"]: r["c"] for r in by_severity},
                "by_status": {r["status"]: r["c"] for r in by_status},
                "by_category": [{"category": r["category"], "count": r["c"]} for r in by_category],
                "by_source": {r["source"]: r["c"] for r in by_source},
                "trend": [row_to_dict(r) for r in trend],
            })
        finally:
            conn.close()

    def _create_finding(self):
        try:
            data = self._read_json_body()
        except json.JSONDecodeError:
            return self._send_error_json("invalid json")

        if not data.get("title") or not data.get("severity"):
            return self._send_error_json("title and severity are required")

        data = {k: v for k, v in data.items() if k in FINDING_FIELDS}
        data.setdefault("source", "manual")
        data.setdefault("tool", "manual")
        data.setdefault("category", "manual-finding")

        conn = get_conn()
        try:
            cols = list(data.keys()) + ["status", "created_at"]
            vals = list(data.values()) + ["manual", now_iso()]
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO findings ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
            conn.commit()
            new_id = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
            self._log_audit(conn, data.get("run_id"), "human:reviewer", f"added manual finding #{new_id}")
            row = conn.execute("SELECT * FROM findings WHERE id = ?", (new_id,)).fetchone()
            self._send_json(row_to_dict(row), 201)
        finally:
            conn.close()

    def _update_finding(self, finding_id: int):
        try:
            data = self._read_json_body()
        except json.JSONDecodeError:
            return self._send_error_json("invalid json")

        allowed = FINDING_FIELDS | REVIEW_FIELDS
        updates = {k: v for k, v in data.items() if k in allowed}
        if not updates:
            return self._send_error_json("no valid fields to update")

        if "status" in updates:
            updates.setdefault("reviewed_at", now_iso())

        conn = get_conn()
        try:
            existing = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
            if not existing:
                return self._send_error_json("finding not found", 404)
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE findings SET {set_clause} WHERE id = ?",
                list(updates.values()) + [finding_id],
            )
            conn.commit()
            if "status" in updates:
                self._log_audit(
                    conn, existing["run_id"], "human:reviewer",
                    f"set finding #{finding_id} status to {updates['status']}",
                )
            row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
            self._send_json(row_to_dict(row))
        finally:
            conn.close()

    def _delete_finding(self, finding_id: int):
        conn = get_conn()
        try:
            existing = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
            if not existing:
                return self._send_error_json("finding not found", 404)
            conn.execute("DELETE FROM findings WHERE id = ?", (finding_id,))
            conn.commit()
            self._log_audit(conn, existing["run_id"], "human:reviewer", f"deleted finding #{finding_id}")
            self._send_json({"ok": True})
        finally:
            conn.close()

    @staticmethod
    def _log_audit(conn, run_id, actor, action):
        conn.execute(
            "INSERT INTO audit_log (run_id, actor, action, at) VALUES (?, ?, ?, ?)",
            (run_id, actor, action, now_iso()),
        )
        conn.commit()


def main() -> None:
    global DB_PATH, EVIDENCE_ROOT
    parser = argparse.ArgumentParser(description="SecQA review server")
    parser.add_argument("--db-path", default="findings.db")
    parser.add_argument("--evidence-dir", default="evidence")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    DB_PATH = args.db_path
    EVIDENCE_ROOT = args.evidence_dir

    if not pathlib.Path(DB_PATH).exists():
        raise SystemExit(
            f"Database not found at {DB_PATH}. Run: python3 tools/db/init_db.py --db-path {DB_PATH}"
        )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[secqa] review dashboard at http://{args.host}:{args.port}/  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
