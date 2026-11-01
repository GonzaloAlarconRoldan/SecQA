#!/usr/bin/env python3
"""Initialize (or migrate) the findings.db SQLite database.

Usage:
    python3 tools/db/init_db.py [--db-path findings.db]
"""
import argparse
import pathlib
import sqlite3

HERE = pathlib.Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.sql"


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the SecQA findings database")
    parser.add_argument("--db-path", default="findings.db", help="Path to the SQLite db file")
    args = parser.parse_args()

    db_path = pathlib.Path(args.db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
    print(f"[ok] database ready at {db_path.resolve()}")


if __name__ == "__main__":
    main()
