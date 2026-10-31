from __future__ import annotations

import logging

from pipecat.frames.frames import BotStoppedSpeakingFrame, EndFrame, Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

logger = logging.getLogger("voice_assistant.pipecat")


class PersistContext(FrameProcessor):
    """Write new context messages to the store at each turn boundary.

    Sits last in the pipeline, after the assistant aggregator, so the assistant
    turn is already in the context when we flush. Passes every frame through.
    """

    def __init__(self, context, store) -> None:
        super().__init__()
        self._context = context
        self._store = store

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, (BotStoppedSpeakingFrame, EndFrame)):
            await self.flush()

    async def flush(self) -> None:
        try:
            await self._store.flush(self._context)
        except Exception:
            logger.exception("could not persist conversation turn")
