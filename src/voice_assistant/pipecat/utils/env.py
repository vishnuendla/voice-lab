from __future__ import annotations

import os

from voice_assistant.domain.errors import ConfigurationError

PLACEHOLDER_KEYS = frozenset(
    {
        "your_openrouter_key_here",
        "your_groq_key_here",
        "your_vobiz_auth_id",
        "your_vobiz_auth_token",
        "your_sarvam_key_here",
    }
)


def api_key(env_name: str) -> str:
    """The key, or "" when it is unset or still a .env placeholder."""
    key = os.getenv(env_name, "").strip().strip('"').strip("'").strip()
    return "" if key in PLACEHOLDER_KEYS else key


def require_api_key(env_name: str, missing_message: str) -> str:
    key = api_key(env_name)
    if not key:
        raise ConfigurationError(missing_message)
    return key


def normalize_provider(value: str, allowed: frozenset[str], label: str) -> str:
    name = value.strip().lower()
    if name not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ConfigurationError(f"Unknown {label} {value!r}. Expected one of: {choices}.")
    return name


def env_str(name: str, default: str) -> str:
    """A trimmed env var, falling back to `default` when unset or blank."""
    return (os.getenv(name) or "").strip() or default


def env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc
