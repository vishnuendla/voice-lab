from __future__ import annotations

import requests

from voice_assistant.domain.errors import ConfigurationError

VOBIZ_API_BASE = "https://api.vobiz.ai/api/v1"


def fetch_owned_numbers(auth_id: str, auth_token: str) -> list[str]:
    """Return active E.164 numbers on the Vobiz account."""
    url = f"{VOBIZ_API_BASE}/Account/{auth_id}/numbers"
    headers = {"X-Auth-ID": auth_id, "X-Auth-Token": auth_token}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ConfigurationError(f"Failed to list Vobiz phone numbers: {exc}") from exc

    items = resp.json().get("items", [])
    return [
        str(item["e164"])
        for item in items
        if item.get("e164") and item.get("status", "active") == "active"
    ]


def resolve_from_number(auth_id: str, auth_token: str, configured: str) -> str:
    """Use configured number, or fetch the current trial number when set to auto."""
    configured = configured.strip()
    if configured and configured.lower() != "auto":
        return configured

    numbers = fetch_owned_numbers(auth_id, auth_token)
    if not numbers:
        raise ConfigurationError(
            "No active phone numbers on your Vobiz account. "
            "Set VOBIZ_FROM_NUMBER in .env or purchase a number in the console."
        )
    return numbers[0]
