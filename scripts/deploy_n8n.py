"""Publish a workflow from n8n/ to the server: fill placeholders, create or update, activate.

Usage: python scripts/deploy_n8n.py n8n/qbo-setup.json

The filled-in JSON only lives in memory. The files in n8n/ keep the placeholders.
"""

import json
import re
import sys
from pathlib import Path

import httpx

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import CONFIG_DIR, ConfigError, env, n8n_base_url

PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
ENV_PLACEHOLDERS = (
    "SLACK_WEBHOOK_URL",
    "EXTRACT_MODEL",
    "QBO_SETUP_PATH",
    "QBO_REALM_ID",
)
WORKFLOW_FIELDS = ("name", "nodes", "connections", "settings")


def read_config(name: str) -> dict:
    path = CONFIG_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def config_values() -> dict[str, str]:
    """Placeholder values kept in config/ (credential ids, QuickBooks ids)."""
    values = dict(read_config("n8n.json"))
    qbo = read_config("qbo.json")
    if "expense_account_id" in qbo:
        values["EXPENSE_ACCOUNT_ID"] = qbo["expense_account_id"]
    return values


def fill(value, values: dict[str, str]):
    """Replace {{NAME}} markers in every string of the workflow."""
    if isinstance(value, dict):
        return {key: fill(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [fill(item, values) for item in value]
    if not isinstance(value, str):
        return value

    def lookup(match: re.Match) -> str:
        name = match.group(1)
        if name in ENV_PLACEHOLDERS:
            return env(name)
        if name in values:
            return str(values[name])
        raise ConfigError(
            f"no value for {{{{{name}}}}}. Run the setup step that writes it to config/."
        )

    return PLACEHOLDER.sub(lookup, value)


def check(resp: httpx.Response, action: str) -> dict:
    if resp.status_code >= 400:
        raise RuntimeError(f"{action} failed ({resp.status_code}): {resp.text[:500]}")
    return resp.json()


def find_workflow(client: httpx.Client, name: str) -> str | None:
    cursor = None
    while True:
        params = {"limit": 250, **({"cursor": cursor} if cursor else {})}
        body = check(client.get("/api/v1/workflows", params=params), "list workflows")
        for workflow in body["data"]:
            if workflow["name"] == name:
                return workflow["id"]
        cursor = body.get("nextCursor")
        if not cursor:
            return None


def deploy(path: Path) -> str:
    source = json.loads(path.read_text(encoding="utf-8"))
    source.setdefault("settings", {"executionOrder": "v1"})
    body = fill({key: source[key] for key in WORKFLOW_FIELDS}, config_values())

    headers = {"X-N8N-API-KEY": env("N8N_API_KEY")}
    with httpx.Client(base_url=n8n_base_url(), headers=headers, timeout=30) as client:
        workflow_id = find_workflow(client, body["name"])
        if workflow_id:
            resp = client.put(f"/api/v1/workflows/{workflow_id}", json=body)
            check(resp, "update workflow")
            action = "updated"
        else:
            created = check(client.post("/api/v1/workflows", json=body), "create")
            workflow_id = created["id"]
            action = "created"
        check(client.post(f"/api/v1/workflows/{workflow_id}/activate"), "activate")
    print(f"{action} and activated '{body['name']}' ({workflow_id})")
    return workflow_id


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/deploy_n8n.py n8n/<workflow>.json")
    try:
        deploy(Path(sys.argv[1]))
    except (RuntimeError, httpx.HTTPError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
