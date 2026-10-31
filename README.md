# Voice assistant

Browser voice lab: speak in the tab, get a spoken reply. **Pipecat** runs STT → LLM → TTS. **Sarvam** handles speech; **Groq** handles the LLM, failing over to **OpenRouter** if it errors. Local only — no tunnel required.

Phone/Vobiz and desktop CLI code remain in the tree but are not the active path.

## Requirements

- Python **3.10–3.13** (pinned via `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- API keys:
  - [Groq](https://console.groq.com/keys) (`GROQ_API_KEY`) — the primary LLM
  - [OpenRouter](https://openrouter.ai/) (`OPENROUTER_API_KEY`) — the failover LLM, optional
  - [Sarvam](https://dashboard.sarvam.ai/) (`SARVAM_API_KEY`, with billing credits)

## Setup

```bash
uv sync --group pipecat --group web
cp .env.example .env
```

Edit `.env` and set real values for `GROQ_API_KEY` and `SARVAM_API_KEY`.

Add `OPENROUTER_API_KEY` too and the pipeline fails over to OpenRouter when Groq errors
mid-session. Either key alone is a valid setup: a provider with no key is skipped.

The local mic/speaker bot (`voice-pipecat`, `scripts/test_piper.py`) needs `pyaudio`, which
builds from source: `uv sync --group local` after installing a C compiler and portaudio
headers. The browser lab does not need it.

Optional overrides (see `.env.example`):

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `groq` | `groq` or `openrouter` |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Model slug for the primary provider |
| `LLM_FALLBACK_PROVIDER` | `openrouter` | Used when the primary errors; skipped if its key is unset |
| `LLM_FALLBACK_MODEL` | `minimax/minimax-m3:free` | Model slug for the backup |
| `LLM_MAX_TOKENS` | `180` | Replies are spoken, so they stay short |
| `STT_PROVIDER` / `TTS_PROVIDER` | `sarvam` | Use `whisper` / `piper` if Sarvam has no credits |
| `SARVAM_LANGUAGE` | `en-IN` | |
| `SARVAM_TTS_SPEAKER` | `shubh` | |
| `WEB_LAB_HOST` / `WEB_LAB_PORT` | `127.0.0.1` / `7860` | |
| `DATABASE_URL` | unset | Postgres DSN. Unset = conversations are in-memory only |
| `MAX_MESSAGES` | `20` | Stored turns replayed into a resumed session |
| `MEMORY_EXTRACTION` | on | `0` to skip end-of-session summary + memory extraction |

## Conversation persistence (optional)

Set `DATABASE_URL` and the lab remembers conversations across restarts; leave it unset and nothing
changes. Create the database once, then start the lab — tables are created automatically:

```bash
createdb voice_lab
# .env
DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/voice_lab
```

The browser stores a `user_id` and `session_id` in `localStorage`; **New chat** starts a fresh
conversation. Those ids are not authentication — keep the lab on `127.0.0.1`.

Resuming the *same* session replays its stored turns. Starting a *new* one instead carries over
long-term memories: at disconnect the LLM is asked what is worth remembering about the user, and
those facts are appended to the system prompt of every later session. Set `MEMORY_EXTRACTION=0`
to turn that off. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#persistence).

## Run

```bash
uv run python -m voice_assistant.web
```

Same entry points: `uv run voice-web` or `uv run python -m voice_assistant`.

Open **http://127.0.0.1:7860**, hard-refresh if the page was already open, then:

1. **Connect** — starts one conversation session (keep it connected between turns)
2. **Speak** — mic on; your words stream under **You**
3. **Stop** — mic off; that turn is sent to the LLM
4. Wait for the reply under **Assistant** (Sarvam reads it aloud)
5. **Stop AI** — cuts TTS and the in-flight LLM turn
6. **Disconnect** when finished

Free models can be slow; wait after **Stop** before interrupting.

With `DATABASE_URL` set, **Disconnect** shows a summary of what was discussed before the session
closes, and the next Connect opens with a **Last time** line.

## Layout

```text
src/voice_assistant/
  ai/           # the only place a vendor is named: STT, TTS, LLM chain, chat_once
  pipecat/      # build_services() / run_pipeline(), processors/, prompts/, utils/
  guardrails/   # reply_guard: say something when the LLM says nothing
  session/      # store (Postgres), recall (summary + memories), lifecycle
  web/          # FastAPI lab + static UI, WebSocket /ws-lab
  telephony/    # Vobiz / phone, same pipeline and persistence
  domain/       # errors / models, no vendor imports
  desktop/, agent/, adapters/   # legacy CLI (uv sync --group desktop)
```

Switching a provider is an entry in the builder dict in `ai/` plus an env var; nothing outside
`ai/` names a vendor. Conversation context is in memory for the Connect session unless
`DATABASE_URL` is set — see **Conversation persistence** above.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| Sarvam “credits exhausted” | Top up [Sarvam Billing](https://dashboard.sarvam.ai/billing), then Connect again |
| LLM 404 / “unavailable for free” | Change `LLM_MODEL` (or `LLM_FALLBACK_MODEL`) to a slug that provider serves |
| LLM 429 rate limit | Set the other provider's key so the next turn fails over automatically |
| No spoken reply / empty Assistant | Stay connected; wait after Stop; check the server log for a `Service ... reported an error` failover line |
| Port 7860 already in use | Stop the old process, then start the lab again |

To test without Sarvam, set `STT_PROVIDER=whisper` and `TTS_PROVIDER=piper` in `.env` and restart.

## Development

```bash
uv sync --group dev --group pipecat --group web
uv run pytest
uv run ruff check voice_assistant tests
```
