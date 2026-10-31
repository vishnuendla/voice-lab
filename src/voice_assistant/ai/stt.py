"""Speech-to-text providers.

Add one by writing a builder and putting it in `STT_BUILDERS`. Nothing outside
this module needs to know which provider is in use.
"""

from __future__ import annotations

import logging

from pipecat.services.stt_service import STTService

from voice_assistant.pipecat.utils import env_str, normalize_provider, require_api_key

logger = logging.getLogger("voice_assistant.ai.stt")

DEFAULT_STT_PROVIDER = "sarvam"


def _build_sarvam() -> STTService:
    from pipecat.services.sarvam.stt import SarvamSTTService

    key = require_api_key(
        "SARVAM_API_KEY",
        "SARVAM_API_KEY is missing or still a placeholder in .env. "
        "Required when STT_PROVIDER is sarvam.",
    )
    language = env_str("SARVAM_LANGUAGE", "en-IN")
    model = env_str("SARVAM_STT_MODEL", "saaras:v3")
    logger.info("loading sarvam stt model=%s language=%s", model, language)
    stt = SarvamSTTService(
        api_key=key,
        settings=SarvamSTTService.Settings(model=model, language=language),
    )
    logger.info("sarvam stt ready")
    return stt


def _build_whisper() -> STTService:
    from pipecat.services.whisper.stt import WhisperSTTService

    model = env_str("WHISPER_MODEL", "base")
    logger.info("loading whisper model=%s", model)
    stt = WhisperSTTService(
        settings=WhisperSTTService.Settings(model=model, language=env_str("LANGUAGE", "en")),
        device=env_str("WHISPER_DEVICE", "cpu"),
        compute_type=env_str("WHISPER_COMPUTE_TYPE", "int8"),
    )
    logger.info("whisper ready")
    return stt


STT_BUILDERS = {"sarvam": _build_sarvam, "whisper": _build_whisper}


def build_stt(provider: str | None = None) -> STTService:
    """Build the STT service named by `provider` or STT_PROVIDER."""
    name = normalize_provider(
        provider or env_str("STT_PROVIDER", DEFAULT_STT_PROVIDER),
        frozenset(STT_BUILDERS),
        "STT_PROVIDER",
    )
    return STT_BUILDERS[name]()
