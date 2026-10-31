"""Turn a finished conversation into a summary and long-term memories.

Step 6 of the architecture: after a session ends, ask the LLM what is worth
remembering, so the next session starts knowing it instead of replaying the
whole transcript. Best-effort by design -- a failure here must never break a
conversation that already happened.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger("voice_assistant.session.recall")

MAX_MEMORIES = 5
_MIN_TURNS = 2

_EXTRACT_PROMPT = f"""You are reviewing a finished voice conversation.

Reply with JSON only, in exactly this shape:
{{"summary": "...", "memories": [{{"memory": "...", "importance": 60}}]}}

- summary: at most three sentences on what happened and what is unresolved.
- memories: at most {MAX_MEMORIES} durable facts about the user -- their name, preferences,
  projects, constraints, or commitments. Each is one standalone sentence that
  will still be true next week.
- importance: 0-100. 80+ identity and stated preferences, 40-70 ongoing work,
  below 30 trivia.
- Skip anything transient (the weather, one-off questions), anything the
  assistant said about itself, and anything you are unsure about. An empty
  memories list is a correct answer.
"""


def extraction_enabled() -> bool:
    """On by default wherever persistence is on. `MEMORY_EXTRACTION=0` disables."""
    raw = (os.getenv("MEMORY_EXTRACTION") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def transcript_text(messages: list[dict[str, Any]], max_chars: int = 6000) -> str:
    """Render the stored messages as a plain transcript. Keeps the tail, which is
    the part a summary is most likely to need."""
    lines = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            lines.append(f"{role}: {content.strip()}")
    text = "\n".join(lines)
    return text[-max_chars:] if len(text) > max_chars else text


def parse_extraction(reply: str) -> tuple[str, list[tuple[str, int]]]:
    """Pull the summary and memories out of an LLM reply.

    Tolerant on purpose: the free models this project targets wrap JSON in prose
    or code fences. Returns empty results rather than raising.
    """
    match = re.search(r"\{.*\}", reply or "", re.DOTALL)
    if not match:
        return "", []
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return "", []
    if not isinstance(data, dict):
        return "", []

    summary = data.get("summary")
    summary = summary.strip() if isinstance(summary, str) else ""

    memories: list[tuple[str, int]] = []
    for item in data.get("memories") or []:
        if isinstance(item, str):
            text, importance = item, 50
        elif isinstance(item, dict):
            text = item.get("memory") or item.get("text") or ""
            importance = item.get("importance", 50)
        else:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        try:
            score = max(0, min(100, int(importance)))
        except (TypeError, ValueError):
            score = 50
        memories.append((text.strip(), score))
    return summary, memories[:MAX_MEMORIES]


async def _extract(transcript: str) -> tuple[str, list[tuple[str, int]]]:
    """Summarize through the same Groq -> OpenRouter chain the conversation used."""
    from voice_assistant.ai.chat import chat_once

    reply = await chat_once(
        [
            {"role": "system", "content": _EXTRACT_PROMPT},
            {"role": "user", "content": transcript},
        ]
    )
    return parse_extraction(reply)


async def store_session_recall(store) -> str:
    """Summarize this session, store its summary and memories, return the summary.

    Never raises: a conversation that already happened must not be lost because
    the summarizer was unavailable.
    """
    if not extraction_enabled():
        return ""
    try:
        # `messages` holds no system rows -- SessionStore.flush filters them --
        # so this counts real turns with nothing to subtract.
        messages = await store.transcript()
        if len(messages) < _MIN_TURNS:
            return ""
        transcript = transcript_text(messages)
        if not transcript:
            return ""
        summary, memories = await _extract(transcript)
        await store.save_summary(summary)
        stored = await store.add_memories(memories)
        logger.info("session recall stored: summary=%s memories=%d", bool(summary), stored)
        return summary
    except Exception:
        logger.exception("could not extract session recall (conversation is still saved)")
        return ""
