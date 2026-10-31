# Architecture

## Current product

The **browser voice lab** is the active runtime:

```text
Browser tab (mic + speakers)
  → WebSocket /ws-lab (protobuf)
  → Pipecat pipeline
  → Sarvam STT → Groq LLM (OpenRouter on failover) → Sarvam TTS
  → audio back to the tab
```

Run: `uv run python -m voice_assistant.web` → **http://127.0.0.1:7860**.

Local only. No Cloudflare tunnel.

Conversation context is in memory for one Connect session unless `DATABASE_URL`
is set. With it, turns are written to Postgres as they happen, the session is
summarized when it ends, and long-term memories carry into the next one.

`telephony/` (Vobiz) and `desktop/` (CLI) remain in the tree but are not the product path.

## Layers

Everything lives under `src/voice_assistant/`:

```text
ai/               → the only place a vendor is named: build_stt / build_tts /
                    build_llm_stack, plus chat_once for non-pipeline calls
pipecat/          → build_services() / run_pipeline(), processors/, prompts/, utils/
guardrails/       → reply_guard (speak something when the LLM says nothing)
session/          → store (Postgres), recall (summary + memories), lifecycle
web/, telephony/  → a transport each, both calling the same run_pipeline
domain/           → errors / models (no vendor imports)
adapters/, agent/, desktop/ → legacy CLI path (uv sync --group desktop)
```

Rules:

1. `domain/` does not import `agent/`, `adapters/`, or any app package.
2. `web/` and `telephony/` build a transport and call `build_services` / `run_pipeline`.
3. **Vendors are named only in `ai/`.** `STT_PROVIDER`, `TTS_PROVIDER`, `LLM_PROVIDER`
   and `LLM_FALLBACK_PROVIDER` pick from the builder dicts there; adding a provider is
   one entry, and no other module changes.
4. `PipelineServices.llm` is a bare `FrameProcessor`, so the slot takes one service or
   a failover switcher wrapping several without the pipeline knowing which.

## Browser conversation flow

Push-to-talk in the tab:

```text
Connect
  → greeting TTS
  → Speak (mic on) → STT transcripts under "You"
  → Stop (mic off) → user turn ends → LLM
  → assistant text + Sarvam TTS
  → Stop AI interrupts bot TTS/LLM
  → stay connected for the next turn
```

Turn boundaries are driven by client messages (`user-turn-start` / `user-turn-complete`), not Smart Turn mid-sentence.

## Pipeline graph

```text
transport.input()
  → STT (Sarvam or Whisper)
  → HaltAfterProviderError
  → LLM user aggregator (+ Silero VAD; external turn strategies in PTT mode)
  → LLM (Groq, OpenRouter on failover)
  → EnsureSpokenReply (spoken fallback if LLM ends with no text; no live interrupt)
  → TTS (Sarvam or Piper)
  → transport.output()
  → LLM assistant aggregator
  → PersistContext (only when DATABASE_URL is set)
```

`EnsureSpokenReply` speaks a short status line when a completion finishes empty or with an error. Status lines use `TTSSpeakFrame(append_to_context=False)` so they are not stored as assistant chat turns.

## Persistence

Optional, and off unless `DATABASE_URL` is set — without it the lab behaves exactly as before,
with one in-memory `LLMContext` per Connect.

| Piece | Role |
| --- | --- |
| `session/schema.sql` | `users` / `sessions` / `messages`, applied on startup (`CREATE TABLE IF NOT EXISTS`, no migration tool) |
| `session/store.py` | `SessionStore`: ownership check, history load, turn flush, `last_summary` |
| `pipecat/processors/persist_context.py` | `PersistContext`, flushes new context messages at each turn boundary |
| `session/recall.py` | End-of-session summary + long-term memory extraction |
| `session/lifecycle.py` | `end_session`: flush, summarize, close — idempotent, called from both paths |

The browser mints `lab_user_id` and `lab_session_id` in `localStorage` and sends them as
`?user_id=&session_id=` on `/ws-lab`. On Connect the context is seeded with the current
`SYSTEM_PROMPT` plus the last `MAX_MESSAGES` (default 20) stored turns, so a session resumes
across a server restart. **New chat** mints a fresh `session_id`.

Ordering is by `sequence_number`, never by timestamp. Stored tool calls are replayed as context
only — they are never re-executed. `messages.tool_call_id` and `messages.tool_calls` are
convenience columns for SQL; `messages.payload` holds the whole provider-shaped message and is
what gets replayed.

### Tables

| Table | Holds |
| --- | --- |
| `users` | one row per `user_id` |
| `sessions` | one conversation, owned by a user, with `status` and a `summary` |
| `messages` | ordered turns, including tool calls and tool results |
| `memories` | durable facts about a user, carried across sessions, `importance` 0-100 |

### Long-term memory

When the session ends, after the final flush, `recall.store_session_recall` sends the transcript
through `ai.chat.chat_once` — the same Groq → OpenRouter chain the conversation used — and asks
for a summary plus up to five durable facts. The summary lands on
`sessions.summary`; the facts land in `memories`, keyed `(user_id, memory)` so re-learning a fact
raises its importance instead of duplicating the row.

`end_session` runs on two paths and is idempotent, so the transcript is summarized once either
way. Clicking **Disconnect** sends an `end-session` client message first, so the summary is
computed while the socket is still open and pushed back over RTVI as a `session-summary` server
message — the tab shows it as a card before disconnecting. A hard socket drop or a closed tab
never reaches that, so `run_pipeline`'s `finally` does the same work with nobody listening. On the
next Connect, `GET /history` returns the previous session's summary as a "Last time" line.

`SessionStore.seed` appends the user's top memories to the system prompt on every Connect, so a
brand new session still knows what earlier ones learned. Memories are read with
`WHERE user_id = $1`: they never cross users. The whole path is best-effort and wrapped in a
`try/except` — a failed extraction never loses a conversation that already happened. Disable it
with `MEMORY_EXTRACTION=0`.

Every session and message query carries the `user_id`, and a session owned by someone else is
reported as `session not found`. Those ids are **self-asserted by the browser, not
authentication** — anyone can claim any id, so do not expose this lab beyond `127.0.0.1` without
adding real login.

## uv groups

| Group | Purpose |
| --- | --- |
| `pipecat` | Shared pipeline (incl. Sarvam) |
| `web` | FastAPI + uvicorn + asyncpg for the lab |
| `dev` | pytest, pytest-asyncio, ruff |
| `telephony` | Vobiz phone server (same pipeline, same persistence) |
| `local` | Local mic/speaker transport for `pipecat/bot.py` (needs portaudio) |
| `desktop` | Legacy push-to-talk CLI: `desktop/`, `agent/`, `adapters/` |

Default groups: `pipecat` + `web`.

## Related docs

| Doc | Purpose |
| --- | --- |
| [README.md](../README.md) | Setup, run, troubleshooting |
| [LEARNING_GUIDE.md](LEARNING_GUIDE.md) | Onboarding for the current lab |
| [CLOUDFLARE_TUNNEL.md](CLOUDFLARE_TUNNEL.md) | Historical Vobiz tunnel notes (unused) |
