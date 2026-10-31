#!/usr/bin/env bash
# Expose the local telephony server via a free Cloudflare quick tunnel.
# Requires: brew install cloudflared  (or see docs/CLOUDFLARE_TUNNEL.md)

set -euo pipefail

PORT="${TELEPHONY_PORT:-5000}"
# Use 127.0.0.1 — on some systems localhost resolves to IPv6 first.
TARGET="http://127.0.0.1:${PORT}"

echo ""
echo "Cloudflare quick tunnel -> ${TARGET}"
echo "1. Start telephony: uv run python -m voice_assistant.apps.telephony"
echo "2. Copy the https://....trycloudflare.com URL below into PUBLIC_BASE_URL in .env"
echo "3. Point Vobiz Answer URL at https://<host>/answer"
echo ""

exec cloudflared tunnel --url "${TARGET}"
