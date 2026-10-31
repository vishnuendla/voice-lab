# Cloudflare Tunnel (historical — unused for the browser lab)

> **Not used by the current product.** The browser lab runs on **http://127.0.0.1:7860** only and does not need `cloudflared`. Keep this file for the leftover Vobiz/telephony path under `telephony/`.

Vobiz must reach a local telephony server over the public internet:

- `https://<host>/answer` — webhook that returns Stream XML
- `wss://<host>/ws` — bidirectional audio WebSocket

[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`cloudflared`) exposes `localhost:5000` with HTTPS/WSS. This project historically used the **quick tunnel** flow (`*.trycloudflare.com`).

## Install cloudflared

**Windows (winget):**

```powershell
winget install Cloudflare.cloudflared
```

**macOS:**

```bash
brew install cloudflared
```

**Linux:** see [Cloudflare install docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).

Verify:

```bash
cloudflared --version
```

## Run the telephony stack (legacy)

Use two terminals.

**Terminal 1 — telephony server:**

```bash
uv sync --group pipecat --group telephony
uv run python -m voice_assistant.telephony
```

**Terminal 2 — tunnel:**

```bash
cloudflared tunnel --url http://127.0.0.1:5000
```

Copy the printed `https://….trycloudflare.com` URL into `.env` as `PUBLIC_BASE_URL` (no trailing slash), restart telephony, then place an outbound call with the Vobiz scripts.

## Notes

- Quick tunnel URLs change when you restart `cloudflared`.
- Do not point the browser lab at this tunnel; the lab WebSocket path is `/ws-lab`, not Vobiz `/ws`.
- Prefer documenting phone work in a dedicated branch if telephony becomes the product again.
