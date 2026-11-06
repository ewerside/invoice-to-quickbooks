"""Draw one synthetic invoice as a PDF in one of three layouts."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen.canvas import Canvas

DATE_STYLES = {
    ("US", "A"): "%m/%d/%Y",
    ("US", "B"): "{month} {day}, {year}",
    ("US", "C"): "{mon} {day}, {year}",
    ("UK", "A"): "{day} {mon} {year}",
    ("UK", "B"): "{day} {month} {year}",
    ("UK", "C"): "{day} {mon} {year}",
}
GREY = HexColor("#E8E8E8")
LINE = HexColor("#C8C8C8")
ACCENT = HexColor("#1F4E5F")


def qty_text(qty: Decimal) -> str:
    text = format(qty, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def rate_text(rate: Decimal) -> str:
    return format((rate * 100).normalize(), "f") + "%"


def date_text(d: date, country: str, layout: str) -> str:
    style = DATE_STYLES[(country, layout)]
    if "%" in style:
        return d.strftime(style)
    return style.format(month=f"{d:%B}", mon=f"{d:%b}", day=d.day, year=d.year)


def tax_label(inv: dict) -> str:
    vendor = inv["vendor"]
    word = "VAT" if vendor["country"] == "UK" else "Sales Tax"
    return f"{word} ({rate_text(vendor['rate'])})"


def tax_id_line(inv: dict) -> str:
    if inv["vendor"]["country"] == "UK":
        return f"VAT Reg No: {inv['tax_id']}"
    return f"EIN: {inv['tax_id']}"


def symbol_money(inv: dict, value: Decimal) -> str:
    symbol = "$" if inv["vendor"]["currency"] == "USD" else "£"
    return f"{symbol}{value:,.2f}"


def code_money(inv: dict, value: Decimal) -> str:
    return f"{inv['vendor']['currency']} {value:,.2f}"


def layout_a(c: Canvas, inv: dict, w: float, h: float) -> None:
    """Classic table, vendor block top left."""
    vendor, m = inv["vendor"], 54
    c.setFont("Helvetica-Bold", 15)
    c.drawString(m, h - m, vendor["name"])
    c.setFont("Helvetica", 9.5)
    y = h - m
    for line in vendor["address"] + [tax_id_line(inv)]:
        y -= 13
        c.drawString(m, y, line)

    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(w - m, h - m - 2, "INVOICE")
    meta_y = h - m - 30
    for label, value in (
        ("Invoice #", inv["number"]),
        ("Date", inv["issue_text"]),
        ("Due Date", inv["due_text"]),
    ):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawRightString(w - m - 100, meta_y, label)
        c.setFont("Helvetica", 9.5)
        c.drawRightString(w - m, meta_y, value)
        meta_y -= 14

    y = min(y, meta_y) - 26
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(m, y, "BILL TO")
    c.setFont("Helvetica", 9.5)
    for line in inv["client"]:
        y -= 13
        c.drawString(m, y, line)

    y -= 34
    right = (w - m - 190, w - m - 95, w - m)
    c.setFillColor(GREY)
    c.rect(m, y - 6, w - 2 * m, 20, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(m + 6, y, "Description")
    for x, title in zip(right, ("Qty", "Unit Price", "Amount")):
        c.drawRightString(x - 6, y, title)
    c.setFont("Helvetica", 9.5)
    c.setStrokeColor(LINE)
    for item in inv["items"]:
        y -= 22
        c.drawString(m + 6, y, item["description"])
        c.drawRightString(right[0] - 6, y, qty_text(item["quantity"]))
        c.drawRightString(right[1] - 6, y, symbol_money(inv, item["unit_price"]))
        c.drawRightString(right[2] - 6, y, symbol_money(inv, item["amount"]))
        c.line(m, y - 8, w - m, y - 8)

    y -= 34
    for label, value, font in (
        ("Subtotal", inv["subtotal"], "Helvetica"),
        (tax_label(inv), inv["tax"], "Helvetica"),
        ("Total", inv["total"], "Helvetica-Bold"),
    ):
        c.setFont(font, 10)
        c.drawRightString(right[1] - 6, y, label)
        c.drawRightString(right[2] - 6, y, symbol_money(inv, value))
        y -= 16

    c.setFont("Helvetica", 8.5)
    c.drawString(m, 60, f"Terms: Net {vendor['net']}. Thank you for your business.")


def layout_b(c: Canvas, inv: dict, w: float, h: float) -> None:
    """Two columns, vendor on the right, totals in a box."""
    vendor, m = inv["vendor"], 48
    title = "TAX INVOICE" if vendor["country"] == "UK" else "INVOICE"
    c.setFillColor(ACCENT)
    c.rect(0, h - 80, w, 80, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(m, h - 50, title)
    c.setFillColor(black)

    col = w / 2 + 20
    y = h - 112
    c.setFont("Helvetica-Bold", 12)
    c.drawString(col, y, vendor["name"])
    c.setFont("Helvetica", 9)
    for line in vendor["address"] + [tax_id_line(inv)]:
        y -= 12
        c.drawString(col, y, line)

    left_y = h - 112
    c.setFont("Helvetica-Bold", 8)
    c.drawString(m, left_y, "BILLED TO")
    c.setFont("Helvetica", 9)
    for line in inv["client"]:
        left_y -= 12
        c.drawString(m, left_y, line)
    left_y -= 24
    for label, value in (
        ("Invoice number", inv["number"]),
        ("Issue date", inv["issue_text"]),
        ("Due date", inv["due_text"]),
        ("Currency", vendor["currency"]),
    ):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(m, left_y, label.upper())
        c.setFont("Helvetica", 9.5)
        c.drawString(m + 95, left_y, value)
        left_y -= 14

    y = min(y, left_y) - 30
    right = (w - m - 170, w - m - 85, w - m)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(m, y, "ITEM")
    for x, head in zip(right, ("QUANTITY", "RATE", "LINE TOTAL")):
        c.drawRightString(x, y, head)
    c.setStrokeColor(ACCENT)
    c.line(m, y - 6, w - m, y - 6)
    c.setFont("Helvetica", 9.5)
    for n, item in enumerate(inv["items"]):
        y -= 20
        if n % 2:
            c.setFillColor(GREY)
            c.rect(m, y - 6, w - 2 * m, 20, fill=1, stroke=0)
            c.setFillColor(black)
        c.drawString(m + 4, y, item["description"])
        c.drawRightString(right[0], y, qty_text(item["quantity"]))
        c.drawRightString(right[1], y, f"{item['unit_price']:,.2f}")
        c.drawRightString(right[2], y, f"{item['amount']:,.2f}")

    box_w, box_h = 220, 70
    box_x, box_y = w - m - box_w, y - 40 - box_h
    c.setStrokeColor(ACCENT)
    c.rect(box_x, box_y, box_w, box_h, fill=0, stroke=1)
    row_y = box_y + box_h - 18
    for label, value, font in (
        ("Subtotal", inv["subtotal"], "Helvetica"),
        (tax_label(inv), inv["tax"], "Helvetica"),
        ("Amount due", inv["total"], "Helvetica-Bold"),
    ):
        c.setFont(font, 10)
        c.drawString(box_x + 10, row_y, label)
        c.drawRightString(box_x + box_w - 10, row_y, symbol_money(inv, value))
        row_y -= 20

    c.setFont("Helvetica", 8.5)
    c.drawString(m, box_y + 40, f"Payment terms: {vendor['net']} days from issue.")
    c.drawString(m, box_y + 28, "Pay by bank transfer and quote the invoice number.")


def layout_c(c: Canvas, inv: dict, w: float, h: float) -> None:
    """Compact: items as a list with notes, totals in the footer."""
    vendor, m = inv["vendor"], 42
    c.setFont("Helvetica-Bold", 13)
    c.drawString(m, h - m, vendor["name"])
    c.drawRightString(w - m, h - m, f"No. {inv['number']}")
    c.setFont("Helvetica", 8.5)
    c.drawString(m, h - m - 14, " | ".join(vendor["address"] + [tax_id_line(inv)]))
    c.drawString(m, h - m - 28, f"Issued {inv['issue_text']}    Due {inv['due_text']}")
    c.drawString(m, h - m - 42, "To: " + ", ".join(inv["client"]))
    c.setStrokeColor(LINE)
    c.line(m, h - m - 52, w - m, h - m - 52)

    y = h - m - 74
    for n, item in enumerate(inv["items"], start=1):
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(m, y, f"{n}. {item['description']}")
        c.setFont("Helvetica", 9)
        qty = qty_text(item["quantity"])
        price = code_money(inv, item["unit_price"])
        c.drawString(m + 14, y - 12, f"{qty} x {price}")
        c.drawRightString(w - m, y - 12, code_money(inv, item["amount"]))
        y -= 32

    y -= 8
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(m, y, f"Notes: {inv['note']}")

    c.line(m, 92, w - m, 92)
    c.setFont("Helvetica", 9)
    c.drawString(m, 76, f"Subtotal {code_money(inv, inv['subtotal'])}")
    c.drawCentredString(w / 2, 76, f"{tax_label(inv)} {code_money(inv, inv['tax'])}")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - m, 76, f"TOTAL DUE {code_money(inv, inv['total'])}")
    c.setFont("Helvetica", 8)
    c.drawString(m, 58, f"Payment due within {vendor['net']} days.")


LAYOUTS = {"A": layout_a, "B": layout_b, "C": layout_c}


def render(inv: dict, path: Path) -> None:
    vendor = inv["vendor"]
    size = LETTER if vendor["country"] == "US" else A4
    inv["issue_text"] = date_text(inv["issue"], vendor["country"], vendor["layout"])
    inv["due_text"] = date_text(inv["due"], vendor["country"], vendor["layout"])
    c = Canvas(str(path), pagesize=size)
    c.setTitle(f"Invoice {inv['number']}")
    LAYOUTS[vendor["layout"]](c, inv, *size)
    c.showPage()
    c.save()
