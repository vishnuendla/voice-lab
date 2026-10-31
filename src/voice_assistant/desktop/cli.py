from __future__ import annotations

import logging
import sys

from voice_assistant.adapters.stt_whisper import WhisperSpeechToText
from voice_assistant.adapters.tts_edge import EdgeTextToSpeech
from voice_assistant.config import Settings
from voice_assistant.domain.errors import (
    AudioPlaybackError,
    ConfigurationError,
    LLMError,
    ToolExecutionError,
    TranscriptionError,
)
from voice_assistant.factory import build_assistant
from voice_assistant.logging_setup import TurnLogger, setup_logging

_USER_SAFE_ERROR = "Sorry, I didn't get that. Could you please repeat?"
_CATCH_AGAIN = "I didn't catch that."
_EXIT_PHRASES = {"exit", "quit", "goodbye", "good bye"}


class _TurnIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "turn_id"):
            record.turn_id = "-"
        return True


def _transcript_is_usable(text: str, confidence: float, threshold: float) -> bool:
    return bool(text.strip()) and confidence >= threshold


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    logger = setup_logging(settings)
    for handler in logger.handlers:
        handler.addFilter(_TurnIdFilter())

    turn_log = TurnLogger(logger, {"turn_id": "-"})
    tts = EdgeTextToSpeech(settings)
    tts.start()
    stt = WhisperSpeechToText(settings)
    assistant = build_assistant(settings, logger)

    print("=" * 50)
    print("Voice Assistant (desktop)")
    print("Press ENTER to speak. Say exit to quit.")
    print("=" * 50)

    try:
        while True:
            try:
                input("\nPress ENTER to speak...")
            except EOFError:
                break

            try:
                transcript = stt.listen()
            except TranscriptionError:
                turn_log.exception("transcription failed")
                tts.speak(_CATCH_AGAIN)
                continue

            query = transcript.text.strip()
            if query.lower() in _EXIT_PHRASES:
                print("Goodbye")
                break

            if not _transcript_is_usable(
                query, transcript.confidence, settings.confidence_threshold
            ):
                turn_log.info("rejected empty or low-confidence transcript")
                tts.speak(_CATCH_AGAIN)
                continue

            print(f"\nYou: {query}")
            try:
                answer = assistant.ask(query)
            except (LLMError, ToolExecutionError, AudioPlaybackError):
                turn_log.exception("turn failed")
                tts.speak(_USER_SAFE_ERROR)
                continue

            print(f"\nAssistant: {answer}")
            try:
                tts.speak(answer)
            except AudioPlaybackError:
                turn_log.exception("playback failed")
    except KeyboardInterrupt:
        print("\nGoodbye")
    finally:
        tts.shutdown()
