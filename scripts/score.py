"""Compare what the workflow extracted with data/truth.jsonl and write docs/results.md.

Usage:
  python scripts/score.py --label "Run 1: first prompt"
  python scripts/score.py --label "Run 2: ..." --append    keep earlier runs in the file
"""

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, DOCS_DIR, env

TEXT_FIELDS = [
    "vendor_name",
    "vendor_tax_id",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
]
MONEY_FIELDS = ["subtotal", "tax", "total"]
LINE_NUMBERS = ["quantity", "unit_price", "amount"]
RESULTS = DOCS_DIR / "results.md"


def same_text(got, want) -> bool:
    return got is not None and str(got).strip() == str(want).strip()


def same_number(got, want) -> bool:
    return isinstance(got, (int, float)) and abs(got - want) <= 0.01 + 1e-9


def load_truth() -> dict[str, dict]:
    with open(DATA_DIR / "truth.jsonl", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    return {row["file"]: row for row in rows}


def load_log() -> dict[str, dict]:
    with open(DATA_DIR / "upload_log.csv", encoding="utf-8") as f:
        return {row["file"]: row for row in csv.DictReader(f)}


def load_outcomes(log: dict[str, dict]) -> dict[str, dict]:
    """What the workflow stored for each file: extracted fields and issues."""
    bill_to_file = {
        r["detail"]: name for name, r in log.items() if r["status"] == "posted"
    }
    outcomes = {}
    with psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn:
        for bill_id, extracted in conn.execute(
            "select bill_id, extracted from invoices_posted"
        ):
            name = bill_to_file.get(bill_id)
            if name:
                outcomes[name] = {"extracted": extracted, "issues": []}
        for name, issues, extracted in conn.execute(
            "select file_name, issues, extracted from invoice_exceptions"
        ):
            outcomes[name] = {"extracted": extracted, "issues": list(issues)}
    return outcomes


def field_diffs(extracted: dict, truth: dict) -> list[str]:
    """Fields where the extraction differs from what the PDF says."""
    diffs = [
        f"{key}: read '{extracted.get(key)}', PDF says '{truth[key]}'"
        for key in TEXT_FIELDS
        if not same_text(extracted.get(key), truth[key])
    ]
    diffs += [
        f"{key}: read {extracted.get(key)}, PDF says {truth[key]}"
        for key in MONEY_FIELDS
        if not same_number(extracted.get(key), truth[key])
    ]
    lines = extracted.get("line_items") or []
    if len(lines) != len(truth["line_items"]):
        diffs.append(
            f"line count: read {len(lines)}, PDF has {len(truth['line_items'])}"
        )
    return diffs


def score(truth: dict, outcomes: dict) -> dict:
    fields = {key: 0 for key in TEXT_FIELDS + MONEY_FIELDS}
    line_count = lines_total = lines_ok = desc_ok = 0
    for name, want in truth.items():
        got = outcomes.get(name, {}).get("extracted") or {}
        for key in TEXT_FIELDS:
            fields[key] += same_text(got.get(key), want[key])
        for key in MONEY_FIELDS:
            fields[key] += same_number(got.get(key), want[key])
        got_lines = got.get("line_items") or []
        line_count += len(got_lines) == len(want["line_items"])
        for i, want_line in enumerate(want["line_items"]):
            lines_total += 1
            got_line = got_lines[i] if i < len(got_lines) else {}
            lines_ok += all(
                same_number(got_line.get(k), want_line[k]) for k in LINE_NUMBERS
            )
            desc_ok += same_text(got_line.get("description"), want_line["description"])
    return {
        "fields": fields,
        "line_count": line_count,
        "lines_total": lines_total,
        "lines_ok": lines_ok,
        "desc_ok": desc_ok,
    }


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def render(label: str, truth: dict, log: dict, outcomes: dict) -> str:
    n = len(truth)
    statuses = {}
    for row in log.values():
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    seconds = [float(r["seconds"]) for r in log.values()]
    out = [f"## {label}", ""]
    out.append(
        "Outcome: "
        + ", ".join(f"{count} {status}" for status, count in sorted(statuses.items()))
        + f". Average {sum(seconds) / len(seconds):.1f} s per invoice."
    )

    planted = [r for r in truth.values() if r["expected_status"] != "ok"]
    caught = 0
    out += ["", "### Planted errors", "", "| File | Planted | Flagged as | Caught |"]
    out.append("| --- | --- | --- | --- |")
    for row in planted:
        issues = outcomes.get(row["file"], {}).get("issues", [])
        hit = row["expected_status"] in issues
        caught += hit
        flagged = ", ".join(issues) or log.get(row["file"], {}).get("status", "missing")
        out.append(
            f"| {row['file']} | {row['expected_status']} | {flagged} | {'yes' if hit else 'no'} |"
        )
    out += ["", f"Caught {caught} of {len(planted)}."]

    clean = [r for r in truth.values() if r["expected_status"] == "ok"]
    alarms = [r for r in clean if log.get(r["file"], {}).get("status") != "posted"]
    out += ["", "### False alarms", ""]
    out.append(f"{len(alarms)} of {len(clean)} clean invoices did not post.")
    if alarms:
        out += ["", "| File | Result | Why |", "| --- | --- | --- |"]
        for row in alarms:
            result = outcomes.get(row["file"], {}).get("issues") or [
                log.get(row["file"], {}).get("status", "missing")
            ]
            got = outcomes.get(row["file"], {}).get("extracted") or {}
            why = "; ".join(field_diffs(got, row)) or "fields match the PDF"
            out.append(f"| {row['file']} | {', '.join(result)} | {why} |")

    s = score(truth, outcomes)
    out += ["", "### Field accuracy", "", "| Field | Correct | Accuracy |"]
    out.append("| --- | --- | --- |")
    for key, ok in s["fields"].items():
        out.append(f"| {key} | {ok}/{n} | {pct(ok, n)} |")
    out.append(
        f"| line item count | {s['line_count']}/{n} | {pct(s['line_count'], n)} |"
    )
    out.append(
        f"| line values (qty, unit price, amount) | {s['lines_ok']}/{s['lines_total']} "
        f"| {pct(s['lines_ok'], s['lines_total'])} |"
    )
    out.append(
        f"| line descriptions | {s['desc_ok']}/{s['lines_total']} "
        f"| {pct(s['desc_ok'], s['lines_total'])} |"
    )
    out.append("")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True, help="title of this run")
    parser.add_argument("--append", action="store_true", help="keep earlier runs")
    args = parser.parse_args()

    truth, log = load_truth(), load_log()
    section = render(args.label, truth, log, load_outcomes(log))
    if args.append and RESULTS.exists():
        text = RESULTS.read_text(encoding="utf-8").rstrip() + "\n\n" + section
    else:
        header = (
            "# Results\n\n"
            f"Scored on {date.today():%Y-%m-%d}: {len(truth)} synthetic invoices, "
            f"model {env('EXTRACT_MODEL')}. Text and dates must match exactly. "
            "Amounts can be off by 0.01 at most.\n\n"
        )
        text = header + section
    RESULTS.write_text(text, encoding="utf-8")
    print(section)


if __name__ == "__main__":
    main()
