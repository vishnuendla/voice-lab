import logging
import os
import sys

import requests

from voice_assistant.config import TelephonySettings
from voice_assistant.domain.errors import ConfigurationError

logger = logging.getLogger("voice_assistant.telephony")


def make_call(settings: TelephonySettings, to_number: str, public_base: str) -> None:
    answer_url = f"{public_base.rstrip('/')}/answer"
    url = f"https://api.vobiz.ai/api/v1/Account/{settings.auth_id}/Call/"
    payload = {
        "from": settings.from_number,
        "to": to_number,
        "answer_url": answer_url,
        "answer_method": "POST",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Auth-ID": settings.auth_id,
        "X-Auth-Token": settings.auth_token,
    }
    print(f"Placing call from {settings.from_number} to {to_number}")
    print(f"Answer URL: {answer_url}")
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    logger.info("outbound call status=%s body=%s", resp.status_code, resp.text)
    if resp.ok:
        print(f"Call queued ({resp.status_code}): {resp.text}")
    else:
        print(f"Call failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        settings = TelephonySettings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if os.getenv("VOBIZ_FROM_NUMBER", "auto").strip().lower() == "auto":
        print(f"Using current Vobiz number: {settings.from_number}")

    to = sys.argv[1].strip() if len(sys.argv) > 1 else input("Number to call (+91...): ").strip()
    if not to:
        print("Error: destination number is required.", file=sys.stderr)
        raise SystemExit(1)

    public_base = settings.public_base_url
    if not public_base:
        public_base = input("Public HTTPS base URL (Cloudflare tunnel): ").strip()
    if not public_base:
        print("Error: PUBLIC_BASE_URL is required in .env or as input.", file=sys.stderr)
        raise SystemExit(1)

    make_call(settings, to, public_base)


if __name__ == "__main__":
    main()
