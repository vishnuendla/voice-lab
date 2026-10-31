from voice_assistant.config import TelephonySettings
from voice_assistant.telephony.handshake import wait_for_vobiz_start
from voice_assistant.telephony.stream_xml import (
    https_base_url,
    stream_answer_xml,
    websocket_and_status_urls,
)


def test_telephony_settings_load_optional_public_url(monkeypatch):
    monkeypatch.setenv("VOBIZ_AUTH_ID", "auth")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "token")
    monkeypatch.setenv("VOBIZ_FROM_NUMBER", "+10000000000")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://abc.trycloudflare.com/")
    settings = TelephonySettings.from_env(load_dotenv_file=False)
    assert settings.public_base_url == "https://abc.trycloudflare.com"


def test_https_base_prefers_public_override():
    assert (
        https_base_url("http://127.0.0.1:5000/", "https://abc.trycloudflare.com")
        == "https://abc.trycloudflare.com"
    )


def test_https_base_upgrades_local_http():
    assert https_base_url("http://127.0.0.1:5000/") == "https://127.0.0.1:5000"


def test_stream_xml_is_bidirectional_mulaw():
    xml = stream_answer_xml(
        websocket_url="wss://abc.trycloudflare.com/ws",
        status_callback_url="https://abc.trycloudflare.com/stream-status",
    )
    assert 'bidirectional="true"' in xml
    assert 'keepCallAlive="true"' in xml
    assert "wss://abc.trycloudflare.com/ws" in xml
    assert "https://abc.trycloudflare.com/stream-status" in xml
    assert "contentType" not in xml


def test_speak_only_xml():
    from voice_assistant.telephony.stream_xml import speak_only_xml

    xml = speak_only_xml("Hello test")
    assert "<Speak>Hello test</Speak>" in xml
    assert "Stream" not in xml


def test_websocket_and_status_urls():
    ws, status = websocket_and_status_urls("https://abc.trycloudflare.com")
    assert ws == "wss://abc.trycloudflare.com/ws"
    assert status == "https://abc.trycloudflare.com/stream-status"


def test_wait_for_vobiz_start_skips_connected_event():
    import asyncio

    messages = [
        '{"event":"connected"}',
        '{"event":"start","start":{"streamId":"s1","callId":"c1"}}',
    ]

    async def receive_text() -> str:
        return messages.pop(0)

    stream_id, call_id = asyncio.run(wait_for_vobiz_start(receive_text))
    assert stream_id == "s1"
    assert call_id == "c1"
