from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from voice_assistant.config import load_project_dotenv

# Imported at startup, not on first Connect: pulling in pipecat/torch takes
# seconds and blocks the event loop, which times out the browser's handshake.
from voice_assistant.pipecat.pipeline import build_services, run_pipeline
from voice_assistant.pipecat.prompts import LAB_GREETING
from voice_assistant.session.store import (
    SessionNotFound,
    SessionStore,
    database_url,
    open_pool,
    open_session,
)

logger = logging.getLogger("voice_assistant.web")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_INDEX_HTML = _STATIC_DIR / "index.html"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7860
_WS_PATH = "/ws-lab"


def create_app(*, load_services: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pool = None
        if load_services:
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s %(message)s",
            )
            logger.info(
                "browser lab listening on http://127.0.0.1:%s (services load on Connect)",
                os.getenv("WEB_LAB_PORT", str(_DEFAULT_PORT)),
            )
        app.state.services = None
        if load_services:
            load_project_dotenv()
        dsn = database_url() if load_services else ""
        if dsn:
            app.state.pool = await open_pool(dsn)
            logger.info("conversation persistence enabled")
        else:
            logger.info("DATABASE_URL not set: conversations are in-memory only")
        try:
            yield
        finally:
            if app.state.pool is not None:
                await app.state.pool.close()

    app = FastAPI(title="Voice assistant browser lab", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"ok": True, "ws": _WS_PATH}

    @app.get("/")
    async def index():
        return FileResponse(_INDEX_HTML)

    @app.get("/history")
    async def history(user_id: str = "", session_id: str = ""):
        """Prior turns for this session, so the UI can show a resumed conversation."""
        if _pool(app) is None:
            return {"messages": []}
        try:
            # Read-only: no open_session(), which would create the session and
            # mark it active on a GET.
            store = SessionStore(_pool(app), user_id, session_id)
            messages = await store.history()
            summary = await store.last_summary()
        except SessionNotFound:
            raise HTTPException(status_code=404, detail="session not found") from None
        return {
            "messages": [
                {"role": m.get("role"), "content": m.get("content")}
                for m in messages
                if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
            ],
            "summary": summary,
        }

    @app.websocket(_WS_PATH)
    async def websocket_lab(websocket: WebSocket):
        client = websocket.client
        logger.info(
            "lab websocket upgrade from %s:%s",
            getattr(client, "host", "?"),
            getattr(client, "port", "?"),
        )
        await websocket.accept()
        logger.info("browser lab websocket connected")
        try:
            store = await _open_store(app, websocket)
        except SessionNotFound:
            logger.warning("lab websocket rejected: session not found")
            await websocket.close(code=1008, reason="session not found")
            return
        try:
            await _run_lab_session(websocket, store=store)
        except WebSocketDisconnect:
            logger.info("browser lab websocket disconnected before pipeline start")
        except Exception:
            logger.exception("browser lab pipeline failed")
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            # run_pipeline closes the store itself, but it is never reached when
            # building the services fails. close() is an idempotent UPDATE.
            if store is not None:
                await store.close()

    return app


def _pool(app: FastAPI):
    """None when persistence is off, or when the lifespan never ran (tests)."""
    return getattr(app.state, "pool", None)


async def _open_store(app: FastAPI, websocket: WebSocket):
    """SessionStore for this connect, or None when persistence is off."""
    if _pool(app) is None:
        return None
    user_id = (websocket.query_params.get("user_id") or "").strip()
    session_id = (websocket.query_params.get("session_id") or "").strip()
    if not user_id or not session_id:
        logger.warning("lab websocket without user_id/session_id: not persisting")
        return None
    return await open_session(_pool(app), user_id, session_id)


async def _run_lab_session(websocket: WebSocket, *, store=None) -> None:
    load_project_dotenv()
    # Fresh provider sockets + current .env key on every Connect. Providers and
    # their defaults come from voice_assistant.ai.
    services = build_services()

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            add_wav_header=False,
            serializer=ProtobufFrameSerializer(),
        ),
    )
    await run_pipeline(
        transport,
        services,
        greet=LAB_GREETING,
        handle_sigint=False,
        allow_interruptions=True,
        push_to_talk=True,
        store=store,
    )


app = create_app()


def main() -> None:
    load_project_dotenv()
    host = os.getenv("WEB_LAB_HOST", _DEFAULT_HOST)
    port = int(os.getenv("WEB_LAB_PORT", str(_DEFAULT_PORT)))
    uvicorn.run(
        "voice_assistant.web.server:app",
        host=host,
        port=port,
        reload=False,
    )
