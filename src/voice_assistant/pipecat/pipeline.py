"""Build and run one Pipecat session.

Provider choice lives in `voice_assistant.ai`; this module only wires services
into a pipeline and manages the session around it. Nothing here names a vendor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.stt_service import STTService
from pipecat.services.tts_service import TTSService
from pipecat.transports.base_transport import BaseTransport
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies

from voice_assistant.ai import build_llm_stack, build_stt, build_tts
from voice_assistant.config import load_project_dotenv
from voice_assistant.guardrails.reply_guard import EnsureSpokenReply, status_speak_frame
from voice_assistant.pipecat.processors import HaltAfterProviderError, PersistContext
from voice_assistant.pipecat.prompts import SYSTEM_PROMPT
from voice_assistant.session.lifecycle import end_session

logger = logging.getLogger("voice_assistant.pipecat")


@dataclass
class PipelineServices:
    """STT / LLM / TTS / VAD used for one session.

    `llm` is a bare FrameProcessor on purpose: it may be a single provider's
    service or a failover switcher wrapping several. The pipeline does not care.
    """

    stt: STTService
    llm: FrameProcessor
    tts: TTSService
    vad: SileroVADAnalyzer


def _build_vad() -> SileroVADAnalyzer:
    return SileroVADAnalyzer(
        params=VADParams(
            confidence=0.7,
            start_secs=0.2,
            stop_secs=0.4,
            min_volume=0.6,
        )
    )


def build_services(
    *,
    stt_provider: str | None = None,
    tts_provider: str | None = None,
) -> PipelineServices:
    """Build STT / LLM / TTS / VAD from the current environment."""
    load_project_dotenv()
    return PipelineServices(
        stt=build_stt(stt_provider),
        llm=build_llm_stack(),
        tts=build_tts(tts_provider),
        vad=_build_vad(),
    )


def _user_aggregator_params(services: PipelineServices, *, push_to_talk: bool):
    if push_to_talk:
        return LLMUserAggregatorParams(
            vad_analyzer=services.vad,
            user_turn_strategies=ExternalUserTurnStrategies(),
        )
    return LLMUserAggregatorParams(vad_analyzer=services.vad)


async def run_pipeline(
    transport: BaseTransport,
    services: PipelineServices,
    *,
    greet: str | None = None,
    handle_sigint: bool = False,
    allow_interruptions: bool = True,
    push_to_talk: bool = False,
    store=None,
) -> None:
    """Run one Pipecat session on an already-configured transport.

    With a `store` (a `voice_assistant.session.store.SessionStore`) the context
    resumes from Postgres, every new turn is written back, and the session is
    summarized when it ends. Without one the session is in-memory only.
    """
    seed = (
        await store.seed(SYSTEM_PROMPT)
        if store is not None
        else [{"role": "system", "content": SYSTEM_PROMPT}]
    )
    context = LLMContext(messages=seed)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=_user_aggregator_params(services, push_to_talk=push_to_talk),
    )
    halt_on_provider_error = HaltAfterProviderError()
    spoken_reply = EnsureSpokenReply()

    processors = [
        transport.input(),
        services.stt,
        halt_on_provider_error,
        user_aggregator,
        services.llm,
        spoken_reply,
        services.tts,
        transport.output(),
        assistant_aggregator,
    ]
    persist = PersistContext(context, store) if store is not None else None
    if persist:
        processors.append(persist)
    pipeline = Pipeline(processors)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=allow_interruptions,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )
    halt_on_provider_error.attach(task)

    @task.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        kind = getattr(message, "type", None)
        if kind == "interrupt":
            await rtvi.interrupt_bot()
        elif kind == "user-turn-start":
            await task.queue_frames([UserStartedSpeakingFrame()])
        elif kind == "user-turn-complete":
            await task.queue_frames([UserStoppedSpeakingFrame()])
        elif kind == "end-session":
            # The client is about to disconnect and wants the summary while the
            # transport is still up. `finally` below still runs; end_session is
            # idempotent, so the summary is computed once either way.
            summary = await end_session(store, persist, close=False)
            await rtvi.send_server_message({"type": "session-summary", "summary": summary})

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        if greet:
            # Not a chat turn: keep it out of the context so a resumed session
            # does not re-persist the greeting on every connect.
            await task.queue_frames([status_speak_frame(greet)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        await task.cancel()

    runner = PipelineRunner(handle_sigint=handle_sigint)
    try:
        await runner.run(task)
    finally:
        await end_session(store, persist)
