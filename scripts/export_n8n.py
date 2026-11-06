"""Download the live workflows into n8n/ with placeholders in place of real values.

Refuses to write a file that still holds a key, a webhook URL or an account id.
"""

import json
import re
import sys
from pathlib import Path

import httpx
from deploy_n8n import check, find_workflow, read_config

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ROOT, env, n8n_base_url

WORKFLOWS = {
    "portfolio qbo setup": ROOT / "n8n" / "qbo-setup.json",
    "portfolio invoice intake": ROOT / "n8n" / "invoice-intake.json",
}
ENV_VALUES = (
    "SLACK_WEBHOOK_URL",
    "QBO_REALM_ID",
    "QBO_SETUP_PATH",
    "EXTRACT_MODEL",
    "INTAKE_TOKEN",
)


def real_values() -> list[tuple[str, str]]:
    """(value, placeholder name) pairs, longest value first so none is cut short."""
    pairs = [(env(name), name) for name in ENV_VALUES]
    pairs += [(value, name) for name, value in read_config("n8n.json").items()]
    return sorted(pairs, key=lambda pair: len(pair[0]), reverse=True)


def unfill(value, pairs: list[tuple[str, str]], account_id: str):
    if isinstance(value, dict):
        return {key: unfill(item, pairs, account_id) for key, item in value.items()}
    if isinstance(value, list):
        return [unfill(item, pairs, account_id) for item in value]
    if not isinstance(value, str):
        return value
    for real, name in pairs:
        value = value.replace(real, f"{{{{{name}}}}}")
    # The account id is a short number, so only replace it where it is an AccountRef.
    return re.sub(
        r"(AccountRef: \{ value: ')" + re.escape(account_id) + "'",
        r"\g<1>{{EXPENSE_ACCOUNT_ID}}'",
        value,
    )


def leaks(text: str, pairs: list[tuple[str, str]]) -> list[str]:
    found = [
        marker for marker in ("sk-ant", "hooks.slack.com", "eyJ") if marker in text
    ]
    found += [name for real, name in pairs if real in text]
    return found


def main() -> None:
    pairs = real_values()
    account_id = str(read_config("qbo.json")["expense_account_id"])
    headers = {"X-N8N-API-KEY": env("N8N_API_KEY")}
    with httpx.Client(base_url=n8n_base_url(), headers=headers, timeout=30) as client:
        for name, path in WORKFLOWS.items():
            workflow_id = find_workflow(client, name)
            if not workflow_id:
                sys.exit(f"workflow '{name}' not found on the server")
            live = check(client.get(f"/api/v1/workflows/{workflow_id}"), "get workflow")
            clean = unfill(
                {
                    "name": live["name"],
                    "nodes": live["nodes"],
                    "connections": live["connections"],
                    "settings": {"executionOrder": live["settings"]["executionOrder"]},
                },
                pairs,
                account_id,
            )
            text = json.dumps(clean, indent=2, ensure_ascii=False) + "\n"
            found = leaks(text, pairs)
            if found:
                sys.exit(
                    f"{path.name} would still contain: {', '.join(found)}. Not written."
                )
            path.write_text(text, encoding="utf-8")
            print(f"exported '{name}' -> {path.relative_to(ROOT)}, no secrets found")


if __name__ == "__main__":
    main()
