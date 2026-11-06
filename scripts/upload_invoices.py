"""Send invoice PDFs to the intake webhook one at a time and log what came back.

Usage:
  python scripts/upload_invoices.py                 all PDFs in data/invoices, by name
  python scripts/upload_invoices.py --files a.pdf b.pdf   log goes to upload_log_files.csv
  python scripts/upload_invoices.py --reset         empty the four tables first
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx
import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, env, n8n_base_url

TABLES = "invoices_seen, invoices_posted, invoice_exceptions, invoice_failures"
LOG_FIELDS = ["file", "http_status", "status", "detail", "seconds"]


def reset_tables() -> None:
    with psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn:
        conn.execute(f"truncate {TABLES} restart identity")
    print(f"emptied {TABLES}")


def upload(client: httpx.Client, url: str, path: Path) -> dict:
    start = time.monotonic()
    try:
        with path.open("rb") as f:
            resp = client.post(url, files={"file": (path.name, f, "application/pdf")})
        http_status = resp.status_code
        try:
            body = resp.json()
        except ValueError:
            # n8n answers with an empty body when the workflow itself errors.
            body = {"status": "error", "detail": resp.text[:200] or "empty response"}
    except httpx.HTTPError as exc:
        body, http_status = {"status": "network_error", "detail": str(exc)}, 0
    status = body.get("status", "error")
    detail = (
        body.get("bill_id")
        or ",".join(body.get("issues", []))
        or body.get("detail", "")
        or body.get("reason", "")
        or body.get("message", "")
    )
    return {
        "file": path.name,
        "http_status": http_status,
        "status": status,
        "detail": detail,
        "seconds": round(time.monotonic() - start, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--files", nargs="+", type=Path, help="send only these PDFs")
    parser.add_argument("--reset", action="store_true", help="empty the tables first")
    args = parser.parse_args()

    files = args.files or sorted((DATA_DIR / "invoices").glob("*.pdf"))
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        sys.exit(f"not found: {', '.join(missing)}")
    if not files:
        sys.exit("no PDFs to send. Run scripts/make_invoices.py first.")
    if args.reset:
        reset_tables()

    url = f"{n8n_base_url()}/webhook/invoice-intake"
    rows = []
    headers = {"X-Intake-Token": env("INTAKE_TOKEN")}
    with httpx.Client(timeout=180, headers=headers) as client:
        for path in files:
            row = upload(client, url, path)
            rows.append(row)
            print(
                f"{row['file']:<22} {row['status']:<17} {row['detail']}  ({row['seconds']}s)"
            )

    # score.py reads upload_log.csv to tie bills back to files, so a few-file
    # test run must not overwrite the log of the full batch.
    log_name = "upload_log_files.csv" if args.files else "upload_log.csv"
    log_path = DATA_DIR / log_name
    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"sent {len(rows)}: {counts}. Log in {log_path.relative_to(DATA_DIR.parent)}")


if __name__ == "__main__":
    main()
