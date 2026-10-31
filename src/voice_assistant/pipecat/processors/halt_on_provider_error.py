from __future__ import annotations

import logging

from pipecat.frames.frames import ErrorFrame
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger("voice_assistant.pipecat")


def is_provider_session_error(message: str) -> bool:
    lower = message.lower()
    return "credits exhausted" in lower or "error sending audio to sarvam" in lower


class HaltAfterProviderError(FrameProcessor):
    """Stop the session after one Sarvam/provider failure instead of logging every audio frame.

    Only for errors the session cannot recover from. LLM errors are handled by
    the failover switcher in `ai.llm` and must not reach here.
    """

    def __init__(self) -> None:
        super().__init__()
        self._halted = False
        self._task: PipelineTask | None = None

    def attach(self, task: PipelineTask) -> None:
        self._task = task

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, ErrorFrame)
            and not self._halted
            and self._task is not None
            and is_provider_session_error(frame.error)
        ):
            self._halted = True
            logger.error("%s", frame.error.split(";")[0].strip())
            await self._task.cancel()
            return
        await self.push_frame(frame, direction)
