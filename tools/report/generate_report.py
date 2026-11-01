#!/usr/bin/env python3
"""Generate a static, self-contained HTML security report from findings.db,
optionally converted to PDF.

Examples:
    # Global report, only approved findings
    python3 tools/report/generate_report.py --status approved

    # Report for a single run
    python3 tools/report/generate_report.py --run-id 3

    # Filtered + PDF (requires a Chromium/Chrome binary on PATH, or --no-pdf)
    python3 tools/report/generate_report.py --severity critical high --status approved --pdf

Only `approved` and `manual` findings should go into a report meant to be
shared externally — `pending`/`rejected` stay in the dashboard for triage.
"""
from __future__ import annotations

import argparse
import html
import json
import pathlib
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
MAPPING_PATH = HERE.parent / "mapping" / "iso_owasp_map.json"

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
SEVERITY_COLOR = {
    "critical": "#e5484d", "high": "#f2994a", "medium": "#f2c94c",
    "low": "#56ccf2", "info": "#9aa3b2",
}

I18N = {
    "es": {
        "title": "Informe de seguridad", "generated": "Generado",
        "scope": "Alcance", "summary": "Resumen ejecutivo",
        "total": "Total de hallazgos", "critical": "Críticos", "high": "Altos",
        "medium": "Medios", "low": "Bajos", "severity": "Severidad",
        "finding": "Hallazgo", "location": "Ubicación", "description": "Descripción",
        "remediation": "Remediación", "evidence": "Evidencia", "ref": "Referencias",
        "filters_applied": "Filtros aplicados", "no_findings": "No se encontraron hallazgos con los filtros indicados.",
        "lang_note": "Idioma",
    },
    "en": {
        "title": "Security report", "generated": "Generated",
        "scope": "Scope", "summary": "Executive summary",
        "total": "Total findings", "critical": "Critical", "high": "High",
        "medium": "Medium", "low": "Low", "severity": "Severity",
        "finding": "Finding", "location": "Location", "description": "Description",
        "remediation": "Remediation", "evidence": "Evidence", "ref": "References",
        "filters_applied": "Filters applied", "no_findings": "No findings matched the given filters.",
        "lang_note": "Language",
    },
}


def load_mapping() -> dict:
    if MAPPING_PATH.exists():
        return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return {}


def fetch_findings(db_path: str, args) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    clauses, params = [], []
    if args.run_id:
        clauses.append("run_id = ?")
        params.append(args.run_id)
    if args.status:
        placeholders = ",".join("?" for _ in args.status)
        clauses.append(f"status IN ({placeholders})")
        params.extend(args.status)
    if args.severity:
        placeholders = ",".join("?" for _ in args.severity)
        clauses.append(f"severity IN ({placeholders})")
        params.extend(args.severity)
    if args.since:
        clauses.append("created_at >= ?")
        params.append(args.since)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(f"SELECT * FROM findings {where}", params).fetchall()
    conn.close()
    findings = [dict(r) for r in rows]
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f["severity"], 9))
    return findings


def esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def render_html(findings: list[dict], args, mapping: dict) -> str:
    lang = args.lang
    t = I18N[lang]

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    filters_desc = []
    if args.run_id:
        filters_desc.append(f"run_id={args.run_id}")
    if args.status:
        filters_desc.append(f"status={','.join(args.status)}")
    if args.severity:
        filters_desc.append(f"severity={','.join(args.severity)}")
    if args.since:
        filters_desc.append(f"since={args.since}")

    rows_html = []
    for f in findings:
        m = mapping.get(f.get("category", ""), {})
        owasp = f.get("owasp_id") or m.get("owasp_id", "—")
        cwe = f.get("cwe_id") or m.get("cwe_id", "—")
        iso = f.get("iso_control") or m.get("iso_control", "—")
        loc = f.get("file_path") or f.get("endpoint") or "—"
        if f.get("line_start"):
            loc += f":{f['line_start']}"
        evidence = ""
        if f.get("evidence_path"):
            evidence = f"<p><b>{t['evidence']}:</b> {esc(f['evidence_path'])}</p>"
        rows_html.append(f"""
        <section class="finding sev-{f['severity']}">
          <div class="finding-head">
            <span class="badge">{f['severity'].upper()}</span>
            <h3>{esc(f['title'])}</h3>
            <span class="status">{esc(f['status'])}</span>
          </div>
          <p class="meta">{t['location']}: <code>{esc(loc)}</code> &nbsp;|&nbsp;
             CWE: {esc(cwe)} &nbsp;|&nbsp; OWASP: {esc(owasp)} &nbsp;|&nbsp;
             ISO/IEC 27001 Annex A: {esc(iso)}</p>
          <p>{esc(f.get('description') or '—')}</p>
          <p><b>{t['remediation']}:</b> {esc(f.get('remediation') or '—')}</p>
          {evidence}
        </section>
        """)

    body = "\n".join(rows_html) if rows_html else f"<p>{t['no_findings']}</p>"

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8" />
<title>{t['title']} — SecQA</title>
<style>
  body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:900px;margin:40px auto;color:#1a1d23;padding:0 20px}}
  h1{{font-size:22px}}
  .meta-bar{{color:#6b7280;font-size:13px;margin-bottom:20px}}
  .kpis{{display:flex;gap:10px;margin:20px 0}}
  .kpi{{flex:1;border:1px solid #e5e7eb;border-radius:8px;padding:10px;text-align:center}}
  .kpi .n{{font-size:22px;font-weight:700}}
  .kpi .l{{font-size:11px;text-transform:uppercase;color:#6b7280}}
  .finding{{border:1px solid #e5e7eb;border-left:5px solid #9aa3b2;border-radius:8px;padding:14px 16px;margin-bottom:14px;page-break-inside:avoid}}
  .finding.sev-critical{{border-left-color:{SEVERITY_COLOR['critical']}}}
  .finding.sev-high{{border-left-color:{SEVERITY_COLOR['high']}}}
  .finding.sev-medium{{border-left-color:{SEVERITY_COLOR['medium']}}}
  .finding.sev-low{{border-left-color:{SEVERITY_COLOR['low']}}}
  .finding.sev-info{{border-left-color:{SEVERITY_COLOR['info']}}}
  .finding-head{{display:flex;align-items:center;gap:10px}}
  .finding-head h3{{margin:0;font-size:15px;flex:1}}
  .badge{{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:#f3f4f6}}
  .status{{font-size:11px;color:#6b7280;text-transform:uppercase}}
  .meta{{font-size:12px;color:#6b7280}}
  code{{background:#f3f4f6;padding:1px 4px;border-radius:4px}}
  @media print {{ body{{margin:0;padding:16px}} }}
</style>
</head>
<body>
  <h1>{t['title']} — SecQA Pentest Framework</h1>
  <div class="meta-bar">
    {t['generated']}: {datetime.now(timezone.utc).isoformat(timespec='seconds')} ·
    {t['filters_applied']}: {esc(', '.join(filters_desc) or '—')}
  </div>
  <div class="kpis">
    <div class="kpi"><div class="n">{len(findings)}</div><div class="l">{t['total']}</div></div>
    <div class="kpi"><div class="n">{counts['critical']}</div><div class="l">{t['critical']}</div></div>
    <div class="kpi"><div class="n">{counts['high']}</div><div class="l">{t['high']}</div></div>
    <div class="kpi"><div class="n">{counts['medium']}</div><div class="l">{t['medium']}</div></div>
    <div class="kpi"><div class="n">{counts['low']}</div><div class="l">{t['low']}</div></div>
  </div>
  {body}
</body>
</html>
"""


def html_to_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path) -> bool:
    """Best-effort PDF export via a headless Chrome/Chromium binary, if present."""
    candidates = [
        "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    binary = next((c for c in candidates if shutil.which(c) or pathlib.Path(c).exists()), None)
    if not binary:
        return False
    cmd = [
        binary, "--headless", "--disable-gpu",
        f"--print-to-pdf={pdf_path}", f"file://{html_path.resolve()}",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        return pdf_path.exists()
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a SecQA security report")
    parser.add_argument("--db-path", default="findings.db")
    parser.add_argument("--run-id", type=int, default=None)
    parser.add_argument("--status", nargs="*", default=["approved", "manual"],
                         help="Finding statuses to include (default: approved manual)")
    parser.add_argument("--severity", nargs="*", default=None)
    parser.add_argument("--since", default=None, help="ISO date, only findings created after it")
    parser.add_argument("--lang", choices=["es", "en"], default="es")
    parser.add_argument("--out", default=None, help="Output HTML path")
    parser.add_argument("--pdf", action="store_true", help="Also render a PDF next to the HTML")
    args = parser.parse_args()

    if not pathlib.Path(args.db_path).exists():
        sys.exit(f"[secqa] database not found: {args.db_path}")

    mapping = load_mapping()
    findings = fetch_findings(args.db_path, args)
    out_html = render_html(findings, args, mapping)

    suffix = f"run{args.run_id}" if args.run_id else "global"
    out_path = pathlib.Path(args.out or f"report_{suffix}_{args.lang}.html")
    out_path.write_text(out_html, encoding="utf-8")
    print(f"[ok] HTML report: {out_path.resolve()}  ({len(findings)} findings)")

    if args.pdf:
        pdf_path = out_path.with_suffix(".pdf")
        if html_to_pdf(out_path, pdf_path):
            print(f"[ok] PDF report: {pdf_path.resolve()}")
        else:
            print("[warn] No Chrome/Chromium binary found for automatic PDF export.")
            print("       Open the HTML file and use the browser's Print -> Save as PDF instead.")


if __name__ == "__main__":
    main()
