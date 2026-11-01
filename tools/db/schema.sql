-- SecQA Pentest Framework — findings database schema (SQLite)

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,              -- ISO 8601
    finished_at     TEXT,
    target_path     TEXT NOT NULL,               -- repo path scanned
    scope_summary   TEXT,                        -- JSON snapshot of scope.yml used
    stack_detected  TEXT,                        -- JSON: languages, frameworks, package managers
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,               -- recon | sast | sca | secrets | api | dast | manual
    tool            TEXT,                        -- e.g. semgrep, osv-scanner, gitleaks, zap, manual
    category        TEXT NOT NULL,               -- e.g. sql-injection, xss, idor, exposed-secret, tls-misconfig
    title           TEXT NOT NULL,
    description     TEXT,
    severity        TEXT NOT NULL CHECK (severity IN ('critical','high','medium','low','info')),
    cvss_score      REAL,
    cvss_vector     TEXT,
    cwe_id          TEXT,
    owasp_id        TEXT,                        -- e.g. A03:2021
    iso_control     TEXT,                        -- e.g. A.8.28 Secure coding (ISO/IEC 27001 Annex A)
    file_path       TEXT,
    line_start      INTEGER,
    line_end        INTEGER,
    endpoint        TEXT,                        -- for API/DAST findings
    evidence_path   TEXT,                        -- relative path to screenshot/log stored under evidence/
    remediation     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','approved','rejected','manual')),
    reviewed_by     TEXT,
    reviewed_at     TEXT,
    review_comment  TEXT,
    created_at      TEXT NOT NULL,
    fingerprint     TEXT                         -- hash for de-dup across runs
);

CREATE INDEX IF NOT EXISTS idx_findings_run ON findings(run_id);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);
CREATE INDEX IF NOT EXISTS idx_findings_fingerprint ON findings(fingerprint);

CREATE TABLE IF NOT EXISTS evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id      INTEGER NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,               -- screenshot | request-log | response-log | poc
    path            TEXT NOT NULL,
    caption         TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER REFERENCES runs(id) ON DELETE CASCADE,
    actor           TEXT NOT NULL,               -- agent | human:<name>
    action          TEXT NOT NULL,               -- e.g. "ran sqlmap against /login", "approved finding #12"
    target          TEXT,
    at              TEXT NOT NULL
);
