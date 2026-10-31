"""Manual Piper speaker test. Requires: uv sync --group pipecat"""

import asyncio

from pipecat.frames.frames import TextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.piper.tts import PiperTTSService
from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)


async def main() -> None:
    print("=" * 60)
    print("PIPER -> WINDOWS SPEAKER TEST")
    print("=" * 60)

    print("Loading Piper...")
    tts = PiperTTSService(
        settings=PiperTTSService.Settings(
            voice="en_US-ryan-high",
        )
    )
    print("Piper ready.")

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=False,
            audio_out_enabled=True,
            input_device_index=None,
            output_device_index=None,
        )
    )

    pipeline = Pipeline([tts, transport.output()])
    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=False,
            enable_metrics=False,
            enable_usage_metrics=False,
        ),
    )

    await task.queue_frame(TextFrame("Hello. This is a Piper voice test."))

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
