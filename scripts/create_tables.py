"""Create the four workflow tables in Supabase from sql/schema.sql."""

import sys
from pathlib import Path

import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, env

TABLES = ("invoices_seen", "invoices_posted", "invoice_exceptions", "invoice_failures")


def main() -> None:
    schema = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn:
        conn.execute(schema)
        found = conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_name = any(%s)",
            [list(TABLES)],
        ).fetchall()
    names = sorted(row[0] for row in found)
    print(f"tables ready: {', '.join(names)}")
    if len(names) != len(TABLES):
        sys.exit(f"missing tables: {set(TABLES) - set(names)}")


if __name__ == "__main__":
    main()
