# Learning guide — browser voice lab

**Start here for the current product.** Run the lab with [README.md](../README.md). Architecture summary: [ARCHITECTURE.md](ARCHITECTURE.md).

Telephony/Vobiz and desktop CLI still exist in the repo; they are **not** the active path. Tunnel notes for the old phone path: [CLOUDFLARE_TUNNEL.md](CLOUDFLARE_TUNNEL.md).

---

## 1. What you are building

A **local browser voice assistant**:

1. You open a tab and press **Connect**.
2. You press **Speak**, talk, then **Stop**.
3. Sarvam turns speech into text; OpenRouter answers; Sarvam speaks the reply.
4. You stay connected for a continuous conversation. **Stop AI** cuts the bot mid-reply.

No public URL, no phone line. History lives in Pipecat’s `LLMContext` until Disconnect, and in
Postgres as well when `DATABASE_URL` is set.

---

## 2. Big picture

```text
┌──────────────────────────────┐
│  web                    │
│  FastAPI + index.html        │
│  WS /ws-lab (protobuf)       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  pipecat/pipeline.py    │
│  build_services / run_pipeline│
│  reply_guard.EnsureSpokenReply│
└──────────────┬───────────────┘
               │
     ┌─────────┴──────────┐
     ▼                    ▼
 Sarvam STT/TTS      OpenRouter LLM
 (or Whisper/Piper)
```

### Dependency rules

1. **`domain/`** must not import `agent/`, `adapters/`, or any app package.
2. **`web`** should stay thin: HTTP/WebSocket wiring only.
3. Vendor choice for STT/TTS belongs in `pipeline.py` / env, not scattered in the UI.

---

## 3. Run it once

```bash
uv sync --group pipecat --group web
cp .env.example .env
# set OPENROUTER_API_KEY and SARVAM_API_KEY
uv run python -m voice_assistant.web
```

Open **http://127.0.0.1:7860** → hard-refresh → **Connect** → **Speak** → **Stop** → wait for speech.

Python must be **3.10–3.13** (see `.python-version`).

---

## 4. UI contract (push-to-talk)

| Button | Effect |
| --- | --- |
| Connect | Opens `/ws-lab`, builds fresh Sarvam sockets from `.env`, starts greeting |
| Speak | `enableMic(true)` + `user-turn-start` |
| Stop | `enableMic(false)`, short delay, then `user-turn-complete` → LLM |
| Stop AI | `interrupt` → cancels bot TTS / in-flight LLM |
| Disconnect | Ends the session and clears in-memory context |

Stay on one Connect for multi-turn chat. Free OpenRouter models can be slow; wait after Stop before hitting Stop AI.

---

## 5. Pipeline pieces to know

### `pipecat/pipeline.py`

- `build_services()` — STT / LLM / TTS / VAD from env (lab passes Sarvam by default).
- `run_pipeline(..., push_to_talk=True)` — uses `ExternalUserTurnStrategies` so only Speak/Stop end the user turn.
- RTVI client messages: `interrupt`, `user-turn-start`, `user-turn-complete`.

### `guardrails/reply_guard.py`

If the LLM finishes with **no speakable text** (or after a provider error on that turn), Sarvam speaks a short fallback. It does **not** kill a live stream just because the first token is slow. Fallbacks are not written into chat history (`append_to_context=False`).

### `web/server.py`

Services are built **on each Connect** so a new `.env` key is picked up without a full process restart of every socket. The process still needs a restart after code changes.

---

## 6. Environment

| Variable | Role |
| --- | --- |
| `OPENROUTER_API_KEY` | Required |
| `SARVAM_API_KEY` | Required for default Sarvam path |
| `LLM_MODEL` | Default free slug in `.env.example` (change if OpenRouter drops it) |
| `STT_PROVIDER` / `TTS_PROVIDER` | `sarvam` (default) or `whisper` / `piper` |
| `SARVAM_LANGUAGE` / `SARVAM_TTS_SPEAKER` | Speech locale / voice |
| `WEB_LAB_HOST` / `WEB_LAB_PORT` | Default `127.0.0.1:7860` |

Never commit `.env`.

---

## 7. Tests and lint

```bash
uv sync --group dev --group pipecat --group web
uv run pytest
uv run ruff check voice_assistant tests
```

Useful unit coverage: lab routes/static (`test_web_lab.py`), provider selection (`test_pipeline_providers.py`), reply-guard helpers (`test_reply_guard.py`).

---

## 8. Common failures

| Symptom | Likely cause |
| --- | --- |
| Sarvam credits exhausted | Top up billing; Connect again |
| OpenRouter 404 on `:free` | Model free tier gone — switch `LLM_MODEL` |
| OpenRouter 429 | Shared free pool busy — wait or BYOK |
| “I did not get an answer…” | LLM ended empty/error; check logs |
| Stale behavior after `.env` edit | Disconnect/Connect; restart uvicorn after code edits |

---

## 9. What is left in the tree (unused)

| Path | Status |
| --- | --- |
| `telephony/` | Vobiz phone Stream — not used for the lab |
| `desktop/` | Push-to-talk CLI |
| `adapters/`, `agent/` | Desktop orchestration + tools |
| Cloudflare / `PUBLIC_BASE_URL` | Phone tunnel only |

If you revive telephony, start from [CLOUDFLARE_TUNNEL.md](CLOUDFLARE_TUNNEL.md) and the telephony app — do not mix it into `/ws-lab`.
