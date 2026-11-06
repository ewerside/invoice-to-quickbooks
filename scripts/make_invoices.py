"""Generate 50 synthetic vendor invoices as PDFs, plus the answer key.

Writes data/invoices/inv_001.pdf .. inv_050.pdf, data/truth.jsonl and
data/vendors.json, and copies one clean invoice per layout to docs/samples/.
"""

import json
import random
import shutil
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from faker import Faker
from invoice_pdf import render

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR, DOCS_DIR

SEED = 11
COUNT = 50
FIRST_ISSUE = date(2026, 7, 15)
ERRORS = ["sum_mismatch", "bad_dates", "duplicate", "bad_tax_id", "unknown_vendor"]
CENT = Decimal("0.01")

# Catalog rows: description, unit price range, quantity range, fractional quantity.
OFFICE = [
    ("Copy paper, letter, 10 ream case", 38, 62, 1, 12, False),
    ("Black toner cartridge 26A", 70, 140, 1, 4, False),
    ("Ballpoint pens, blue, box of 12", 4, 12, 2, 20, False),
    ("Hanging file folders, box of 25", 14, 28, 1, 10, False),
    ("Sticky notes 3x3, 12 pack", 8, 16, 1, 15, False),
    ("Desk organizer, mesh", 12, 30, 1, 6, False),
    ("Shipping labels, 300 sheets", 22, 45, 1, 5, False),
]
CLEANING = [
    ("Paper towels, case of 12 rolls", 28, 48, 1, 10, False),
    ("Trash liners 33 gal, box of 100", 24, 40, 1, 8, False),
    ("Floor cleaner concentrate, 1 gal", 15, 32, 1, 6, False),
    ("Nitrile gloves, box of 100", 9, 18, 2, 20, False),
    ("Hand soap refill, 1 L", 6, 14, 2, 24, False),
    ("Janitorial service, hours", 28, 45, 1, 12, True),
]
PRINTING = [
    ("Business cards, 500 count", 25, 60, 1, 6, False),
    ("Tri-fold brochures, full color", 0.18, 0.65, 250, 2000, False),
    ("Letterhead, 24 lb, ream", 35, 70, 1, 5, False),
    ("Vinyl banner 3x6 ft", 45, 95, 1, 3, False),
    ("Design time, hours", 55, 90, 1, 6, True),
    ("Window decal, custom", 18, 40, 1, 8, False),
]
IT = [
    ("On-site support, hours", 85, 150, 1, 8, True),
    ("Managed backup, monthly", 49, 120, 1, 1, False),
    ("USB-C docking station", 120, 260, 1, 4, False),
    ("Network cable Cat6, 25 ft", 9, 18, 2, 20, False),
    ("Firewall license renewal", 180, 420, 1, 1, False),
    ("Laptop setup and imaging", 60, 110, 1, 5, False),
]
UK_STATIONERY = [
    ("A4 copier paper, box of 5 reams", 18, 30, 1, 12, False),
    ("Lever arch files, pack of 10", 14, 26, 1, 6, False),
    ("Gel pens, black, pack of 20", 6, 15, 1, 10, False),
    ("Printer toner, black", 45, 110, 1, 4, False),
    ("Whiteboard markers, pack of 8", 5, 11, 1, 12, False),
    ("C5 envelopes, box of 500", 16, 32, 1, 5, False),
]
COFFEE = [
    ("Ground coffee, 2 lb bag", 14, 26, 1, 12, False),
    ("Paper cups 12 oz, sleeve of 50", 5, 9, 2, 20, False),
    ("Creamer pods, box of 192", 18, 30, 1, 4, False),
    ("Bottled water, case of 24", 6, 11, 2, 15, False),
    ("Coffee machine service visit", 75, 140, 1, 1, False),
    ("Tea assortment, 100 bags", 9, 17, 1, 6, False),
]
PACKAGING = [
    ("Double wall cartons 450mm, pack of 25", 22, 40, 1, 10, False),
    ("Bubble wrap roll 750mm x 100m", 18, 35, 1, 6, False),
    ("Packing tape, brown, 6 rolls", 7, 13, 1, 12, False),
    ("Void fill paper, 5 kg", 20, 38, 1, 5, False),
    ("Pallet wrap 400mm", 9, 17, 1, 10, False),
    ("Fragile labels, roll of 500", 6, 12, 1, 8, False),
]
SAFETY = [
    ("Hi-vis vest, class 2", 6, 14, 2, 20, False),
    ("First aid kit refill", 25, 60, 1, 3, False),
    ("Safety glasses, box of 12", 18, 36, 1, 4, False),
    ("Fire extinguisher inspection", 15, 30, 1, 8, False),
    ("Ear plugs, box of 200", 20, 34, 1, 3, False),
    ("Wet floor sign", 12, 22, 1, 4, False),
]

# One row per vendor. The 8th never goes into QuickBooks.
VENDOR_PLANS = [
    ("Office Supply Inc", "US", "A", "INV-{:05d}", 30, "0.08875", OFFICE),
    ("Janitorial Supply LLC", "US", "B", "{:06d}", 15, "0.07", CLEANING),
    ("Print and Copy", "US", "C", "PC-{:04d}", 30, "0.0625", PRINTING),
    ("Tech Services LLC", "US", "A", "2026-{:04d}", 45, "0", IT),
    ("Stationers Ltd", "UK", "B", "SI{:06d}", 30, "0.20", UK_STATIONERY),
    ("Coffee Service", "US", "C", "CS{:05d}", 15, "0.0825", COFFEE),
    ("Packaging Ltd", "UK", "A", "INV/{:05d}", 45, "0.20", PACKAGING),
    ("Safety Supply Co", "US", "B", "SF-{:04d}", 30, "0.04", SAFETY),
]

CLIENT_NAMES = [
    "Maple Street Bakery LLC",
    "Harborview Dental Group",
    "Cedar Ridge Landscaping",
]
NOTES = [
    "Delivered to the back entrance. Signed by front desk.",
    "Please reference the invoice number with your payment.",
    "Prices include delivery inside the local zone.",
    "Partial shipment. Remaining items ship next week at no extra charge.",
    "Thank you for your order. Questions? Reply to the sender of this invoice.",
]


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, ROUND_HALF_UP)


def clean_last_name(fake: Faker) -> str:
    while True:
        name = fake.last_name()
        if name.isalpha():
            return name


def us_city_line(fake: Faker) -> str:
    state = fake.state_abbr(include_territories=False)
    return f"{fake.city()}, {state} {fake.zipcode()}"


def make_vendors(rng: random.Random, fakes: dict) -> list[dict]:
    vendors = []
    for i, (suffix, country, layout, number_fmt, net, rate, catalog) in enumerate(
        VENDOR_PLANS
    ):
        fake = fakes[country]
        # en_GB street addresses can span two lines ("Flat 6\nAaron Gateway").
        street = fake.street_address().split("\n")
        if country == "US":
            address = [*street, us_city_line(fake)]
            tax_id = f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}"
        else:
            address = [*street, fake.city(), fake.postcode()]
            tax_id = f"GB{rng.randint(100000000, 999999999)}"
        vendors.append(
            {
                "name": f"{clean_last_name(fake)} {suffix}",
                "country": country,
                "currency": "USD" if country == "US" else "GBP",
                "address": address,
                "tax_id": tax_id,
                "layout": layout,
                "number_fmt": number_fmt,
                "next_number": rng.randint(1000, 9000),
                "net": net,
                "rate": Decimal(rate),
                "catalog": catalog,
                "in_quickbooks": i < 7,
            }
        )
    return vendors


def make_clients(fake: Faker) -> list[list[str]]:
    return [[name, fake.street_address(), us_city_line(fake)] for name in CLIENT_NAMES]


def next_number(rng: random.Random, vendor: dict) -> str:
    vendor["next_number"] += rng.randint(1, 40)
    return vendor["number_fmt"].format(vendor["next_number"])


def bad_tax_id(vendor: dict) -> str:
    # Drop the last digit: a typo the format check should catch.
    return vendor["tax_id"][:-1]


def transpose_total(total: Decimal) -> Decimal:
    """Swap two adjacent digits of the whole part, like a typing slip."""
    whole, cents = f"{total:.2f}".split(".")
    # Start from the right so the swap never moves a zero to the front.
    for i in reversed(range(len(whole) - 1)):
        if whole[i] != whole[i + 1] and not (i == 0 and whole[1] == "0"):
            swapped = whole[:i] + whole[i + 1] + whole[i] + whole[i + 2 :]
            return Decimal(f"{swapped}.{cents}")
    return total + Decimal("10.00")


def make_items(rng: random.Random, catalog: list) -> list[dict]:
    count = min(rng.randint(1, 6), len(catalog))
    items = []
    for desc, low, high, qty_low, qty_high, fractional in rng.sample(catalog, count):
        if fractional:
            qty = Decimal(rng.choice(["0.5", "1.5", "2", "2.25", "3", "3.75", "4.5"]))
        else:
            qty = Decimal(rng.randint(qty_low, qty_high))
        price = money(round(rng.uniform(low, high), 2))
        items.append(
            {
                "description": desc,
                "quantity": qty,
                "unit_price": price,
                "amount": money(qty * price),
            }
        )
    return items


def make_invoice(
    rng: random.Random, vendor: dict, number: str, client: list, code: str
) -> dict:
    issue = FIRST_ISSUE + timedelta(days=rng.randint(0, 90))
    due = issue + timedelta(days=vendor["net"])
    if code == "bad_dates":
        due = issue - timedelta(days=rng.choice([9, 21, 30]))
    items = make_items(rng, vendor["catalog"])
    subtotal = sum((item["amount"] for item in items), Decimal("0.00"))
    tax = money(subtotal * vendor["rate"])
    total = subtotal + tax
    if code == "sum_mismatch":
        total = transpose_total(total)
    return {
        "vendor": vendor,
        "tax_id": bad_tax_id(vendor) if code == "bad_tax_id" else vendor["tax_id"],
        "number": number,
        "issue": issue,
        "due": due,
        "client": client,
        "items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "note": rng.choice(NOTES),
        "status": code,
    }


def build_batch(rng: random.Random, vendors: list, clients: list) -> list[dict]:
    # One error in each fifth of the batch, so they are spread out.
    codes = ERRORS[:]
    rng.shuffle(codes)
    bands = [(4, 12), (13, 21), (22, 30), (31, 39), (40, 48)]
    error_at = {rng.randint(lo, hi): code for (lo, hi), code in zip(bands, codes)}

    known, unknown = vendors[:7], vendors[7]
    invoices = []
    for i in range(COUNT):
        code = error_at.get(i, "ok")
        if code == "unknown_vendor":
            vendor, number = unknown, next_number(rng, unknown)
        elif code == "duplicate":
            original = rng.choice([inv for inv in invoices if inv["status"] == "ok"])
            vendor, number = original["vendor"], original["number"]
        else:
            vendor = rng.choice(known)
            number = next_number(rng, vendor)
        invoice = make_invoice(rng, vendor, number, rng.choice(clients), code)
        invoice["file"] = f"inv_{i + 1:03d}.pdf"
        invoices.append(invoice)
    return invoices


def truth_row(inv: dict) -> dict:
    vendor = inv["vendor"]
    return {
        "file": inv["file"],
        "layout": vendor["layout"],
        "vendor_name": vendor["name"],
        "vendor_tax_id": inv["tax_id"],
        "vendor_in_quickbooks": vendor["in_quickbooks"],
        "invoice_number": inv["number"],
        "invoice_date": inv["issue"].isoformat(),
        "due_date": inv["due"].isoformat(),
        "currency": vendor["currency"],
        "bill_to": inv["client"][0],
        "line_items": [
            {
                "description": item["description"],
                "quantity": float(item["quantity"]),
                "unit_price": float(item["unit_price"]),
                "amount": float(item["amount"]),
            }
            for item in inv["items"]
        ],
        "subtotal": float(inv["subtotal"]),
        "tax_rate": float(vendor["rate"]),
        "tax": float(inv["tax"]),
        "total": float(inv["total"]),
        "notes": inv["note"] if vendor["layout"] == "C" else None,
        "expected_status": inv["status"],
    }


def main() -> None:
    rng = random.Random(SEED)
    Faker.seed(SEED)
    fakes = {"US": Faker("en_US"), "UK": Faker("en_GB")}
    vendors = make_vendors(rng, fakes)
    clients = make_clients(fakes["US"])
    invoices = build_batch(rng, vendors, clients)

    out_dir = DATA_DIR / "invoices"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("inv_*.pdf"):
        old.unlink()
    for inv in invoices:
        render(inv, out_dir / inv["file"])

    rows = [truth_row(inv) for inv in invoices]
    with open(DATA_DIR / "truth.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(row) + "\n" for row in rows)

    vendor_rows = [
        {key: v[key] for key in ("name", "country", "currency", "tax_id", "address")}
        | {"in_quickbooks": v["in_quickbooks"]}
        for v in vendors
    ]
    (DATA_DIR / "vendors.json").write_text(json.dumps(vendor_rows, indent=2) + "\n")

    samples_dir = DOCS_DIR / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    for layout in "ABC":
        first_ok = next(
            r for r in rows if r["layout"] == layout and r["expected_status"] == "ok"
        )
        target = samples_dir / f"sample_layout_{layout.lower()}.pdf"
        shutil.copy(out_dir / first_ok["file"], target)
        print(f"sample {layout}: {first_ok['file']} -> {target.name}")

    errors = {
        r["file"]: r["expected_status"] for r in rows if r["expected_status"] != "ok"
    }
    ok = sum(1 for r in rows if r["expected_status"] == "ok")
    print(f"{len(rows)} invoices, {ok} ok, errors: {errors}")


if __name__ == "__main__":
    main()
