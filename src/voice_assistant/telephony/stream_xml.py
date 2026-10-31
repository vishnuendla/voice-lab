from __future__ import annotations

from xml.sax.saxutils import escape


def https_base_url(request_base_url: str, public_base_url: str = "") -> str:
    """Prefer PUBLIC_BASE_URL (Cloudflare tunnel / production host) over the local request URL."""
    base = (public_base_url or request_base_url).strip().rstrip("/")
    if base.startswith("http://"):
        return "https://" + base[len("http://") :]
    if base.startswith("https://"):
        return base
    return f"https://{base}"


def websocket_and_status_urls(https_base: str) -> tuple[str, str]:
    host = https_base.removeprefix("https://")
    return f"wss://{host}/ws", f"{https_base}/stream-status"


def stream_answer_xml(*, websocket_url: str, status_callback_url: str | None = None) -> str:
    """Vobiz Stream XML — matches official docs (bidirectional + keepCallAlive)."""
    status_attr = ""
    if status_callback_url:
        status_attr = (
            f'\n      statusCallbackUrl="{escape(status_callback_url)}"'
            '\n      statusCallbackMethod="POST"'
        )
    # Keep the body URL on its own line with no leading spaces — some providers
    # are picky about Stream text content.
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        "  <Stream\n"
        '      bidirectional="true"\n'
        '      keepCallAlive="true"'
        f"{status_attr}>\n"
        f"{escape(websocket_url)}\n"
        "  </Stream>\n"
        "</Response>\n"
    )


def speak_only_xml(text: str = "Hello. Your telephony server is reachable.") -> str:
    """Debug XML: keep the call up with Speak only (no Stream / WebSocket)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Speak>{escape(text)}</Speak>\n"
        "</Response>\n"
    )
