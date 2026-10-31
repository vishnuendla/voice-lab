from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

ReceiveText = Callable[[], Awaitable[str]]


async def wait_for_vobiz_start(receive_text: ReceiveText) -> tuple[str, str]:
    """Read Vobiz WebSocket events until ``start``; leave later ``media`` frames for Pipecat."""
    while True:
        raw = await receive_text()
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Vobiz sent a non-JSON WebSocket message") from exc

        start = message.get("start")
        if message.get("event") != "start" or not isinstance(start, dict):
            continue

        stream_id = start.get("streamId")
        call_id = start.get("callId")
        if not stream_id or not call_id:
            raise ValueError("Vobiz start event missing streamId or callId")
        return str(stream_id), str(call_id)
