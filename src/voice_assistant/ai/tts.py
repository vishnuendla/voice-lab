"""Text-to-speech providers. Same shape as `ai.stt`: a builder per provider."""

from __future__ import annotations

import logging

from pipecat.services.tts_service import TTSService

from voice_assistant.pipecat.utils import env_str, normalize_provider, require_api_key

logger = logging.getLogger("voice_assistant.ai.tts")

DEFAULT_TTS_PROVIDER = "sarvam"


def _build_sarvam() -> TTSService:
    from pipecat.services.sarvam.tts import SarvamTTSService

    key = require_api_key(
        "SARVAM_API_KEY",
        "SARVAM_API_KEY is missing or still a placeholder in .env. "
        "Required when TTS_PROVIDER is sarvam.",
    )
    language = env_str("SARVAM_LANGUAGE", "en-IN")
    model = env_str("SARVAM_TTS_MODEL", "bulbul:v3")
    voice = env_str("SARVAM_TTS_SPEAKER", "shubh")
    logger.info("loading sarvam tts model=%s voice=%s language=%s", model, voice, language)
    tts = SarvamTTSService(
        api_key=key,
        settings=SarvamTTSService.Settings(model=model, voice=voice, language=language),
    )
    logger.info("sarvam tts ready")
    return tts


def _build_piper() -> TTSService:
    from pipecat.services.piper.tts import PiperTTSService

    voice = env_str("PIPER_VOICE", "en_US-ryan-high")
    logger.info("loading piper voice=%s", voice)
    tts = PiperTTSService(settings=PiperTTSService.Settings(voice=voice))
    logger.info("piper ready")
    return tts


TTS_BUILDERS = {"sarvam": _build_sarvam, "piper": _build_piper}


def build_tts(provider: str | None = None) -> TTSService:
    """Build the TTS service named by `provider` or TTS_PROVIDER."""
    name = normalize_provider(
        provider or env_str("TTS_PROVIDER", DEFAULT_TTS_PROVIDER),
        frozenset(TTS_BUILDERS),
        "TTS_PROVIDER",
    )
    return TTS_BUILDERS[name]()
