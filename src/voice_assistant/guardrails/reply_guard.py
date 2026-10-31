from __future__ import annotations

from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

EMPTY_REPLY_SPEECH = "I did not get an answer from the model. Please try again."
BUSY_REPLY_SPEECH = "The free model is busy right now. Please try again in a moment."
SLOW_REPLY_SPEECH = "The model took too long. Please ask again."


def spoken_fallback_for_error(message: str) -> str:
    """Pick a short spoken line for an LLM/provider failure."""
    lower = message.lower()
    if "429" in message or "rate-limited" in lower or "too many requests" in lower:
        return BUSY_REPLY_SPEECH
    if "timeout" in lower or "took too long" in lower:
        return SLOW_REPLY_SPEECH
    return EMPTY_REPLY_SPEECH


def status_speak_frame(text: str) -> TTSSpeakFrame:
    """Speak a status line without storing it as an assistant chat turn."""
    return TTSSpeakFrame(text=text, append_to_context=False)


class ReplyGuardState:
    """Track whether the current LLM turn produced speakable text."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.in_response = False
        self.got_text = False
        self.interrupted = False
        self.last_error = ""

    def on_start(self) -> None:
        self.in_response = True
        self.got_text = False
        self.interrupted = False
        self.last_error = ""

    def on_error(self, message: str) -> None:
        if message:
            self.last_error = message

    def on_text(self, text: str) -> None:
        if text.strip():
            self.got_text = True

    def on_interrupt(self) -> None:
        self.interrupted = True

    def fallback_after_end(self) -> str | None:
        if not self.in_response:
            return None
        self.in_response = False
        if self.interrupted or self.got_text:
            return None
        if self.last_error:
            return spoken_fallback_for_error(self.last_error)
        return EMPTY_REPLY_SPEECH


class EnsureSpokenReply(FrameProcessor):
    """Speak a fallback if the LLM finishes with no text. Does not interrupt a live stream."""

    def __init__(self) -> None:
        super().__init__()
        self._state = ReplyGuardState()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, InterruptionFrame):
            self._state.on_interrupt()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, ErrorFrame):
            self._state.on_error(frame.error)
            await self.push_frame(frame, direction)
            return

        if direction != FrameDirection.DOWNSTREAM:
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseStartFrame):
            self._state.on_start()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMTextFrame):
            self._state.on_text(getattr(frame, "text", "") or "")
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, LLMFullResponseEndFrame):
            fallback = self._state.fallback_after_end()
            await self.push_frame(frame, direction)
            if fallback:
                await self.push_frame(status_speak_frame(fallback))
            return

        await self.push_frame(frame, direction)
