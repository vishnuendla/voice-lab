import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice_assistant.telephony.stream_xml import websocket_and_status_urls
from voice_assistant.web.server import _WS_PATH, _origin_is_allowed, create_app


def test_lab_health_and_index():
    client = TestClient(create_app(load_services=False))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True, "ws": "/ws-lab"}

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    body = page.text
    # Assert on the wiring, not on prose: the copy is free to change.
    for element_id in ("connect", "disconnect", "speak", "stop", "stop-ai", "new-chat", "log"):
        assert f'id="{element_id}"' in body
    assert "user-turn-complete" in body
    assert "/ws-lab" in body


def test_index_asks_for_and_renders_the_session_summary():
    """Disconnect requests the summary over RTVI; /history supplies the last one."""
    body = TestClient(create_app(load_services=False)).get("/").text
    assert "end-session" in body
    assert "session-summary" in body
    assert "onServerMessage" in body
    assert "addSummary" in body


def test_lab_websocket_path_is_not_vobiz_ws():
    assert _WS_PATH == "/ws-lab"
    vobiz_ws, _status = websocket_and_status_urls("https://abc.trycloudflare.com")
    assert vobiz_ws == "wss://abc.trycloudflare.com/ws"
    assert vobiz_ws.endswith("/ws")
    assert not vobiz_ws.endswith("/ws-lab")
    routes = {getattr(route, "path", None) for route in create_app(load_services=False).routes}
    assert "/ws-lab" in routes
    assert "/ws" not in routes


def test_lab_runs_without_a_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app(load_services=False)) as client:
        assert client.app.state.pool is None
        assert client.get("/health").status_code == 200
        assert client.get("/history?user_id=u&session_id=s").json() == {"messages": []}


def test_websocket_origin_defaults_to_loopback_only(monkeypatch):
    monkeypatch.delenv("WEB_LAB_ALLOWED_ORIGINS", raising=False)

    assert _origin_is_allowed("http://127.0.0.1:9000", "127.0.0.1:9000")
    assert _origin_is_allowed("http://localhost:9000/", "localhost:9000")
    assert _origin_is_allowed("http://localhost", "localhost:80")
    assert _origin_is_allowed("http://[::ffff:127.0.0.1]:9000", "[::ffff:127.0.0.1]:9000")
    assert not _origin_is_allowed("https://attacker.example", "localhost:9000")
    assert not _origin_is_allowed("http://localhost:9000", "localhost:7860")
    assert not _origin_is_allowed(None, "localhost:9000")


def test_websocket_origin_allowlist_is_explicit_when_configured(monkeypatch):
    monkeypatch.setenv(
        "WEB_LAB_ALLOWED_ORIGINS",
        "https://voice.example.com:443, https://preview.example.com/",
    )

    assert _origin_is_allowed("https://voice.example.com", "voice.example.com")
    assert _origin_is_allowed("https://preview.example.com", "preview.example.com")
    assert not _origin_is_allowed("http://localhost:7860", "localhost:7860")


def test_websocket_origin_allowlist_with_no_valid_values_fails_closed(monkeypatch):
    monkeypatch.setenv("WEB_LAB_ALLOWED_ORIGINS", " , ")

    assert not _origin_is_allowed("http://localhost:7860", "localhost:7860")


def test_websocket_endpoint_rejects_foreign_origin_before_accept():
    client = TestClient(create_app(load_services=False))

    with pytest.raises(WebSocketDisconnect) as disconnected:
        with client.websocket_connect(
            _WS_PATH,
            headers={"origin": "https://attacker.example", "host": "localhost:7860"},
        ):
            pass

    assert disconnected.value.code == 1008


def test_websocket_endpoint_accepts_matching_loopback_origin(monkeypatch):
    connected = False

    async def close_connection(websocket, *, store=None):
        nonlocal connected
        connected = True
        await websocket.close(code=1000)

    monkeypatch.setattr("voice_assistant.web.server._run_lab_session", close_connection)
    client = TestClient(create_app(load_services=False))

    with client.websocket_connect(
        _WS_PATH,
        headers={"origin": "http://localhost:7860", "host": "localhost:7860"},
    ):
        pass

    assert connected
