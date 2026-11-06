"""Write docs/exceptions.xlsx: one row per invoice that did not post, with the reason in words."""

import sys
from datetime import UTC
from pathlib import Path

import psycopg
from openpyxl import Workbook
from openpyxl.styles import Font

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DOCS_DIR, env

# Short versions of the Slack reasons; the numbers are in the columns next to them.
REASONS = {
    "missing_field": "a required field is empty",
    "sum_mismatch": "line items, subtotal, tax and total do not add up",
    "bad_dates": "a date is missing or not valid, or the due date is before the invoice date",
    "bad_tax_id": "tax id is not a valid EIN or UK VAT number",
    "duplicate": "this invoice number was already posted for this vendor",
    "unknown_vendor": "vendor is not in QuickBooks",
    "currency_mismatch": "invoice currency is not the vendor's currency in QuickBooks",
}
HEADERS = [
    "File",
    "Vendor",
    "Invoice number",
    "Invoice date",
    "Due date",
    "Currency",
    "Subtotal",
    "Tax",
    "Total",
    "Issue codes",
    "Reason",
    "Received (UTC)",
]
WIDTHS = [14, 28, 16, 13, 13, 10, 11, 10, 11, 18, 60, 18]


def reason_text(issues: list[str]) -> str:
    text = "; ".join(REASONS.get(code, code) for code in issues)
    # Upper-case only the first letter: str.capitalize() would turn QuickBooks into quickbooks.
    return text[:1].upper() + text[1:]


def main() -> None:
    with psycopg.connect(env("DATABASE_URL"), connect_timeout=15) as conn:
        rows = conn.execute(
            "select file_name, vendor, invoice_number, issues, extracted, created_at "
            "from invoice_exceptions order by file_name"
        ).fetchall()

    book = Workbook()
    sheet = book.active
    sheet.title = "Exceptions"
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for name, vendor, number, issues, extracted, created_at in rows:
        extracted = extracted or {}
        sheet.append(
            [
                name,
                vendor,
                number,
                extracted.get("invoice_date"),
                extracted.get("due_date"),
                extracted.get("currency"),
                extracted.get("subtotal"),
                extracted.get("tax"),
                extracted.get("total"),
                ", ".join(issues),
                reason_text(issues),
                created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M"),
            ]
        )
        # File names and vendor names come from outside. A value like
        # =HYPERLINK(...) must stay text, not turn into a live formula.
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    for column, width in zip("ABCDEFGHIJKL", WIDTHS):
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2, min_col=7, max_col=9):
        for cell in row:
            cell.number_format = "#,##0.00"
    sheet.freeze_panes = "A2"

    DOCS_DIR.mkdir(exist_ok=True)
    path = DOCS_DIR / "exceptions.xlsx"
    book.save(path)
    print(f"{len(rows)} exceptions -> {path.relative_to(DOCS_DIR.parent)}")


if __name__ == "__main__":
    main()
