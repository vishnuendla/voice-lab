import asyncio
import logging

from pipecat.transports.local.audio import (
    LocalAudioTransport,
    LocalAudioTransportParams,
)

from voice_assistant.config import load_project_dotenv
from voice_assistant.pipecat.pipeline import build_services, run_pipeline

logger = logging.getLogger("voice_assistant.pipecat")

load_project_dotenv()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("starting local Pipecat pipeline (debug aid for the phone product)")

    services = build_services()
    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_passthrough=True,
            input_device_index=None,
            output_device_index=None,
        )
    )
    logger.info("voice assistant ready — speak into the microphone (CTRL+C to stop)")
    await run_pipeline(transport, services, handle_sigint=False)


def run() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("voice assistant stopped")
