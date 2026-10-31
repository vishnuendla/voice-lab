from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from voice_assistant.domain.errors import ConfigurationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_project_dotenv() -> None:
    """Load repo-root `.env`, overriding stale shell environment variables."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    tavily_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    record_duration_seconds: float
    language: str
    confidence_threshold: float
    max_messages: int
    log_level: str
    log_transcripts: bool
    search_enabled: bool
    search_max_results: int
    search_max_chars: int
    max_query_length: int
    tts_voice: str

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> Settings:
        if load_dotenv_file:
            load_project_dotenv()

        openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not openrouter_api_key:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is missing. Set it in the environment or a .env file."
            )

        search_enabled = _env_bool("SEARCH_ENABLED", False)
        tavily_api_key = os.getenv("TAVILY_API_KEY", "").strip()
        if search_enabled and not tavily_api_key:
            raise ConfigurationError(
                "TAVILY_API_KEY is missing. Set it or disable search with SEARCH_ENABLED=false."
            )

        return cls(
            openrouter_api_key=openrouter_api_key,
            tavily_api_key=tavily_api_key,
            llm_model=_env_str("LLM_MODEL", "minimax/minimax-m3:free"),
            llm_timeout_seconds=_env_float("LLM_TIMEOUT_SECONDS", 30.0),
            llm_max_retries=_env_int("LLM_MAX_RETRIES", 2),
            whisper_model=_env_str("WHISPER_MODEL", "small"),
            whisper_device=_env_str("WHISPER_DEVICE", "cpu"),
            whisper_compute_type=_env_str("WHISPER_COMPUTE_TYPE", "int8"),
            record_duration_seconds=_env_float("RECORD_DURATION_SECONDS", 5.0),
            language=_env_str("LANGUAGE", "en"),
            confidence_threshold=_env_float("CONFIDENCE_THRESHOLD", -1.2),
            max_messages=_env_int("MAX_MESSAGES", 20),
            log_level=_env_str("LOG_LEVEL", "INFO"),
            log_transcripts=_env_bool("LOG_TRANSCRIPTS", False),
            search_enabled=search_enabled,
            search_max_results=_env_int("SEARCH_MAX_RESULTS", 3),
            search_max_chars=_env_int("SEARCH_MAX_CHARS", 4000),
            max_query_length=_env_int("MAX_QUERY_LENGTH", 500),
            tts_voice=_env_str("TTS_VOICE", "en-US-AriaNeural"),
        )


@dataclass(frozen=True)
class TelephonySettings:
    auth_id: str
    auth_token: str
    from_number: str
    public_base_url: str

    @classmethod
    def from_env(cls, load_dotenv_file: bool = True) -> TelephonySettings:
        if load_dotenv_file:
            load_project_dotenv()

        auth_id = os.getenv("VOBIZ_AUTH_ID", "").strip()
        auth_token = os.getenv("VOBIZ_AUTH_TOKEN", "").strip()
        configured_from = os.getenv("VOBIZ_FROM_NUMBER", "auto").strip()
        public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

        missing = [
            name
            for name, value in (
                ("VOBIZ_AUTH_ID", auth_id),
                ("VOBIZ_AUTH_TOKEN", auth_token),
            )
            if not value
        ]
        if missing:
            raise ConfigurationError(f"Missing telephony settings: {', '.join(missing)}")

        from voice_assistant.telephony.vobiz_numbers import resolve_from_number

        from_number = resolve_from_number(auth_id, auth_token, configured_from)

        return cls(
            auth_id=auth_id,
            auth_token=auth_token,
            from_number=from_number,
            public_base_url=public_base_url,
        )
