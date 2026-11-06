"""Call the QuickBooks setup webhook: create the 7 vendors, pick the expense account.

Writes config/qbo.json with expense_account_id and the vendor ids.
"""

import difflib
import json
import re
import sys
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIG_DIR, DATA_DIR, env, n8n_base_url

TARGETS = ("Supplies", "Office Supplies")
MIN_SCORE = 0.6
US_CITY = re.compile(r"^(?P<city>.+), (?P<state>[A-Z]{2}) (?P<zip>\d{5})$")


def address_fields(vendor: dict) -> dict:
    """Split the printed address lines into QuickBooks BillAddr fields."""
    lines = vendor["address"]
    if vendor["country"] == "US":
        match = US_CITY.match(lines[-1])
        if not match:
            raise ValueError(f"unexpected US address for {vendor['name']}: {lines}")
        return {
            "line1": ", ".join(lines[:-1]),
            "city": match["city"],
            "state": match["state"],
            "postal_code": match["zip"],
            "country": "US",
        }
    return {
        "line1": ", ".join(lines[:-2]),
        "city": lines[-2],
        "state": "",
        "postal_code": lines[-1],
        "country": "GB",
    }


def load_vendors() -> list[dict]:
    path = DATA_DIR / "vendors.json"
    if not path.exists():
        sys.exit("data/vendors.json not found. Run scripts/make_invoices.py first.")
    vendors = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"name": v["name"], "currency": v["currency"], **address_fields(v)}
        for v in vendors
        if v["in_quickbooks"]
    ]


def pick_account(accounts: list[dict]) -> dict | None:
    def score(account: dict) -> float:
        name = account["name"].lower()
        return max(
            difflib.SequenceMatcher(None, name, t.lower()).ratio() for t in TARGETS
        )

    best = max(accounts, key=score, default=None)
    return best if best and score(best) >= MIN_SCORE else None


def main() -> None:
    url = f"{n8n_base_url()}/webhook/{env('QBO_SETUP_PATH')}"
    vendors = load_vendors()
    try:
        resp = httpx.post(url, json={"vendors": vendors}, timeout=180)
    except httpx.HTTPError as exc:
        sys.exit(f"setup webhook unreachable: {exc}")
    if resp.status_code >= 400:
        sys.exit(f"setup webhook failed ({resp.status_code}): {resp.text[:500]}")
    result = resp.json()

    print("vendors:")
    for v in result["vendors"]:
        state = "created" if v["created"] else "already there"
        print(f"  {v['id']:>4}  {v['name']} ({v['currency']}), {state}")
    print("expense accounts:")
    for a in result["accounts"]:
        print(f"  {a['id']:>4}  {a['name']} ({a['subtype']})")

    if len(result["vendors"]) != len(vendors):
        sys.exit(f"expected {len(vendors)} vendors, got {len(result['vendors'])}")
    account = pick_account(result["accounts"])
    if not account:
        sys.exit(
            "no expense account close to 'Supplies'. Pick one from the list above "
            "and save its id in config/qbo.json as expense_account_id."
        )

    CONFIG_DIR.mkdir(exist_ok=True)
    saved = {
        "expense_account_id": account["id"],
        "expense_account_name": account["name"],
        "vendors": {v["name"]: v["id"] for v in result["vendors"]},
    }
    (CONFIG_DIR / "qbo.json").write_text(json.dumps(saved, indent=2) + "\n")
    print(f"expense account: {account['name']} ({account['id']}) -> config/qbo.json")


if __name__ == "__main__":
    main()
