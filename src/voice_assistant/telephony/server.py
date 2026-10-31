from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response

from voice_assistant.config import load_project_dotenv
from voice_assistant.pipecat.prompts import CALL_GREETING
from voice_assistant.session.store import SessionNotFound, database_url, open_pool, open_session
from voice_assistant.telephony.handshake import wait_for_vobiz_start
from voice_assistant.telephony.privacy import caller_user_id
from voice_assistant.telephony.stream_xml import (
    https_base_url,
    speak_only_xml,
    stream_answer_xml,
    websocket_and_status_urls,
)

logger = logging.getLogger("voice_assistant.telephony")

load_project_dotenv()

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = 5000


@asynccontextmanager
async def lifespan(app: FastAPI):
    from voice_assistant.pipecat.pipeline import build_services

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("loading Pipecat services for phone calls")
    app.state.services = build_services()
    # CallUUID -> pseudonymous caller id, filled in by /answer so a repeat
    # caller keeps memories across calls. Bounded: popped when the call starts.
    app.state.callers = {}
    app.state.pool = None
    dsn = database_url()
    if dsn:
        app.state.pool = await open_pool(dsn)
        logger.info("call persistence enabled")
    else:
        logger.info("DATABASE_URL not set: calls are in-memory only")
    logger.info("telephony server ready")
    try:
        yield
    finally:
        if app.state.pool is not None:
            await app.state.pool.close()


app = FastAPI(title="Voice assistant telephony", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.api_route("/answer", methods=["GET", "POST"])
async def answer(request: Request):
    # Real Vobiz call webhooks include CallUUID / From / To (often as form or query).
    call_meta = {}
    if request.method == "POST":
        try:
            form = await request.form()
            call_meta = {k: form.get(k) for k in ("CallUUID", "From", "To", "Direction")}
        except Exception:
            call_meta = {}
    if not any(call_meta.values()):
        call_meta = {
            k: request.query_params.get(k) for k in ("CallUUID", "From", "To", "Direction")
        }
    logger.info(
        "answer %s call=%s direction=%s",
        request.method,
        call_meta.get("CallUUID"),
        call_meta.get("Direction"),
    )

    if call_meta.get("CallUUID") and call_meta.get("From"):
        _remember_caller(request.app, call_meta["CallUUID"], call_meta["From"])

    if os.getenv("TELEPHONY_SPEAK_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}:
        xml = speak_only_xml()
        logger.info("TELEPHONY_SPEAK_ONLY=true — returning Speak XML (no WebSocket)")
        return Response(content=xml, media_type="text/xml")

    https_base = https_base_url(str(request.base_url), os.getenv("PUBLIC_BASE_URL", ""))
    websocket_url, status_url = websocket_and_status_urls(https_base)
    xml = stream_answer_xml(websocket_url=websocket_url, status_callback_url=status_url)
    logger.info("answer stream wss=%s", websocket_url)
    return Response(content=xml, media_type="text/xml")


@app.api_route("/stream-status", methods=["GET", "POST"])
async def stream_status(request: Request):
    form = await request.form()
    logger.info(
        "stream status event=%s stream=%s call=%s",
        form.get("Event"),
        form.get("StreamID"),
        form.get("CallUUID"),
    )
    return PlainTextResponse("OK")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client = websocket.client
    logger.info(
        "websocket upgrade from %s:%s",
        getattr(client, "host", "?"),
        getattr(client, "port", "?"),
    )
    await websocket.accept()
    logger.info("vobiz websocket connected")
    try:
        stream_id, call_id = await wait_for_vobiz_start(websocket.receive_text)
        logger.info("vobiz start stream=%s call=%s", stream_id, call_id)
        store = await _open_store(websocket.app, call_id)
    except WebSocketDisconnect:
        logger.info("vobiz websocket disconnected before pipeline start")
        return
    except Exception:
        logger.exception("could not start the phone session")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    try:
        await _run_call(websocket, stream_id, call_id, store=store)
    except WebSocketDisconnect:
        logger.info("vobiz websocket disconnected")
    except Exception:
        logger.exception("phone pipeline failed")
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        # run_pipeline closes the store itself; this covers the paths where it
        # never got that far. close() is an idempotent UPDATE.
        if store is not None:
            await store.close()


# ponytail: a plain dict, so it is per-process and leaks an entry for a call
# that is answered but never streamed. Move it to the pool if that matters.
def _remember_caller(app, call_id: str, from_number: str) -> None:
    hmac_key = os.getenv("CALLER_ID_HMAC_KEY", "").strip() or os.getenv(
        "VOBIZ_AUTH_TOKEN", ""
    ).strip()
    app.state.callers[call_id] = caller_user_id(from_number, hmac_key)


async def _open_store(app, call_id: str):
    """SessionStore for this call, or None when persistence is off.

    A keyed digest of the caller's number is the user id, so memories carry
    across calls without putting the number in the database. Unknown callers
    are scoped to this call alone.
    """
    pool = getattr(app.state, "pool", None)
    if pool is None or not call_id:
        return None
    user_id = getattr(app.state, "callers", {}).pop(call_id, "") or f"call:{call_id}"
    try:
        return await open_session(pool, user_id, call_id)
    except SessionNotFound:
        logger.warning("call %s could not claim a session: not persisting", call_id)
        return None


async def _run_call(websocket: WebSocket, stream_id: str, call_id: str, *, store=None) -> None:
    from pipecat.serializers.plivo import PlivoFrameSerializer
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams,
        FastAPIWebsocketTransport,
    )

    from voice_assistant.pipecat.pipeline import run_pipeline

    serializer = PlivoFrameSerializer(
        stream_id=stream_id,
        call_id=call_id,
        params=PlivoFrameSerializer.InputParams(auto_hang_up=False),
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
            allowed_origins=[],
        ),
    )
    await run_pipeline(
        transport,
        websocket.app.state.services,
        greet=CALL_GREETING,
        handle_sigint=False,
        store=store,
    )


def main() -> None:
    host = os.getenv("TELEPHONY_HOST", _DEFAULT_HOST)
    port = int(os.getenv("TELEPHONY_PORT", str(_DEFAULT_PORT)))
    uvicorn.run(
        "voice_assistant.telephony.server:app",
        host=host,
        port=port,
        reload=False,
    )
