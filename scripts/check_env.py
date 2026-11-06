"""Check that each external service answers with the values in .env."""

import sys
from pathlib import Path

import httpx
import psycopg

# Scripts run as files (python scripts/x.py), so the repo root is not on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import env, n8n_base_url

TIMEOUT = 15


def check_n8n() -> None:
    resp = httpx.get(
        f"{n8n_base_url()}/api/v1/workflows",
        params={"limit": 1},
        headers={"X-N8N-API-KEY": env("N8N_API_KEY")},
        timeout=TIMEOUT,
    )
    if resp.status_code == 401:
        raise RuntimeError("API key rejected (401). Check N8N_API_KEY.")
    if resp.status_code == 404:
        raise RuntimeError(
            "public API not found (404). Check N8N_BASE_URL, or set "
            "N8N_PUBLIC_API_DISABLED=false on the server and restart n8n."
        )
    resp.raise_for_status()
    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(
            "answered with something that is not JSON. Check N8N_BASE_URL."
        ) from None
    if "data" not in body:
        raise RuntimeError(
            "answered, but not with a workflow list. Check N8N_BASE_URL."
        )


def check_anthropic() -> None:
    model = env("EXTRACT_MODEL")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": env("ANTHROPIC_API_KEY"),
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "Reply with the word ok."}],
        },
        timeout=60,
    )
    if resp.status_code == 401:
        raise RuntimeError("API key rejected (401). Check ANTHROPIC_API_KEY.")
    if resp.status_code == 404:
        raise RuntimeError(f"model {model} not found (404). Check EXTRACT_MODEL.")
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:300]}")


def check_supabase() -> None:
    try:
        with psycopg.connect(env("DATABASE_URL"), connect_timeout=TIMEOUT) as conn:
            conn.execute("select 1").fetchone()
    except psycopg.Error:
        # libpq errors can quote parts of a malformed URL, password included, so print none of it.
        raise RuntimeError(
            "cannot connect. Check DATABASE_URL and URL-encode special "
            "characters in the password."
        ) from None


def check_slack() -> None:
    resp = httpx.post(
        env("SLACK_WEBHOOK_URL"),
        json={"text": "test from invoice setup"},
        timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:200]}")


CHECKS = {
    "n8n": check_n8n,
    "anthropic": check_anthropic,
    "supabase": check_supabase,
    "slack": check_slack,
}


def main() -> int:
    failed = 0
    for name, check in CHECKS.items():
        try:
            check()
        # ConfigError is a RuntimeError, so a missing variable lands here too.
        except (RuntimeError, httpx.HTTPError) as exc:
            print(f"{name} FAILED: {exc}")
            failed += 1
        else:
            print(f"{name} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
