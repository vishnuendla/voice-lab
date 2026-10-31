"""Postgres-backed conversation persistence for the browser voice lab.

Ownership is enforced in SQL: every session and message query carries the
`user_id`, and a session that does not belong to the caller looks exactly like
one that does not exist. Historical tool calls are stored and replayed as
context only -- nothing here executes them.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_HISTORY_LIMIT = 20
MEMORY_RECALL_LIMIT = 10


class SessionNotFound(Exception):
    """The session does not exist, or is not owned by this user. Never say which."""


def database_url() -> str:
    """Empty string means: run without persistence, exactly as before."""
    return (os.getenv("DATABASE_URL") or "").strip()


def history_limit() -> int:
    raw = (os.getenv("MAX_MESSAGES") or "").strip()
    if not raw:
        return DEFAULT_HISTORY_LIMIT
    try:
        return max(2, int(raw))
    except ValueError:
        return DEFAULT_HISTORY_LIMIT


# --- pure helpers (tested without a database) --------------------------------


def as_message_dict(message: Any) -> dict[str, Any]:
    """Coerce whatever Pipecat's context holds into a plain provider-shaped dict."""
    if isinstance(message, dict):
        return message
    dump = getattr(message, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True)
    if is_dataclass(message):
        return asdict(message)
    return {"role": getattr(message, "role", "assistant"), "content": str(message)}


def context_messages(context: Any) -> list[dict[str, Any]]:
    """Read the message list off an LLMContext across Pipecat versions."""
    getter = getattr(context, "get_messages", None)
    raw = getter() if callable(getter) else getattr(context, "messages", [])
    return [as_message_dict(item) for item in raw]


def seed_messages(
    system_prompt: str,
    history: list[dict[str, Any]],
    max_messages: int,
    memories: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Current system prompt (plus long-term memories), then the tail of the
    stored conversation."""
    tail = [m for m in history if m.get("role") != "system"]
    capacity = max(1, max_messages - 1)
    system = {"role": "system", "content": recall_prompt(system_prompt, memories or [])}
    return [system, *tail[-capacity:]]


def new_messages(
    messages: list[dict[str, Any]],
    persisted_count: int,
) -> list[dict[str, Any]]:
    """Messages appended to the context since the last flush."""
    return [m for m in messages[persisted_count:] if m.get("role") != "system"]


def row_for(
    message: dict[str, Any], sequence_number: int
) -> tuple[int, str, str | None, str | None, str | None, str]:
    """Flatten one message into a `messages` row.

    `content` / `tool_call_id` / `tool_calls` are convenience columns for SQL;
    `payload` is the whole message and is what gets replayed.
    """
    content = message.get("content")
    tool_calls = message.get("tool_calls")
    tool_call_id = message.get("tool_call_id")
    return (
        sequence_number,
        str(message.get("role") or "assistant"),
        content if isinstance(content, str) else None,
        tool_call_id if isinstance(tool_call_id, str) else None,
        json.dumps(tool_calls, default=str) if tool_calls else None,
        json.dumps(message, default=str),
    )


def recall_prompt(system_prompt: str, memories: list[str]) -> str:
    """Append long-term memories to the system prompt. Unchanged when there are none."""
    if not memories:
        return system_prompt
    lines = "\n".join(f"- {memory}" for memory in memories)
    return (
        f"{system_prompt.rstrip()}\n\n"
        "What you already know about this user from earlier conversations:\n"
        f"{lines}\n"
        "Use these only when relevant. Never mention that you have notes."
    )


# --- database ---------------------------------------------------------------


async def open_pool(dsn: str):
    """Create the connection pool and apply the schema once."""
    import asyncpg

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    return pool


class SessionStore:
    """One conversation, owned by one user."""

    def __init__(self, pool, user_id: str, session_id: str, *, limit: int | None = None):
        if not user_id or not session_id:
            raise SessionNotFound("user_id and session_id are required")
        self._pool = pool
        self._user_id = user_id
        self._session_id = session_id
        self._limit = limit if limit is not None else history_limit()
        self._persisted = 0
        self._next_seq = 1
        # Session wrap-up state, owned by `session.lifecycle.end_session`: the
        # summary can be asked for before the socket closes and again after.
        self.ended = False
        self.summary = ""

    async def open(self) -> None:
        """Claim or resume the session. Raises SessionNotFound if another user owns it."""
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
                self._user_id,
            )
            await conn.execute(
                "INSERT INTO sessions (id, user_id) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
                self._session_id,
                self._user_id,
            )
            owned = await conn.fetchval(
                "SELECT 1 FROM sessions WHERE id = $1 AND user_id = $2",
                self._session_id,
                self._user_id,
            )
            if not owned:
                raise SessionNotFound("session not found")
            await conn.execute(
                "UPDATE sessions SET status = 'active', ended_at = NULL"
                " WHERE id = $1 AND user_id = $2",
                self._session_id,
                self._user_id,
            )
            highest = await conn.fetchval(
                "SELECT max(sequence_number) FROM messages WHERE session_id = $1",
                self._session_id,
            )
        self._next_seq = (highest or 0) + 1

    async def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """The tail of the conversation, oldest first. Ownership enforced in SQL,
        so this is safe to call without `open()` -- a session owned by someone
        else simply has no history."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT m.payload FROM messages m"
                " JOIN sessions s ON s.id = m.session_id"
                " WHERE m.session_id = $1 AND s.user_id = $2"
                " ORDER BY m.sequence_number DESC LIMIT nullif($3, 0)",
                self._session_id,
                self._user_id,
                self._limit if limit is None else limit,
            )
        return [json.loads(row["payload"]) for row in reversed(rows)]

    async def seed(self, system_prompt: str) -> list[dict[str, Any]]:
        """Messages to build the LLMContext with. Marks them as already stored.

        The system prompt carries this user's long-term memories, so a brand new
        session still starts with what earlier ones learned.
        """
        messages = seed_messages(
            system_prompt,
            await self.history(),
            self._limit + 1,
            await self.memories(),
        )
        self._persisted = len(messages)
        return messages

    # --- long-term memory ---------------------------------------------------

    async def memories(self, limit: int = MEMORY_RECALL_LIMIT) -> list[str]:
        """This user's memories, most important first. Scoped to the user, not
        the session: that is the point of them."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT memory FROM memories WHERE user_id = $1"
                " ORDER BY importance DESC, created_at DESC LIMIT $2",
                self._user_id,
                limit,
            )
        return [row["memory"] for row in rows]

    async def save_summary(self, summary: str) -> None:
        """Store the session summary, so a later session can use it without the
        whole transcript."""
        if not summary.strip():
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET summary = $3 WHERE id = $1 AND user_id = $2",
                self._session_id,
                self._user_id,
                summary.strip(),
            )

    async def last_summary(self) -> str:
        """The summary of this user's most recent *other* finished session, for a
        "last time we spoke" line. Ownership enforced in SQL like every query here."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchval(
                "SELECT summary FROM sessions"
                " WHERE user_id = $1 AND id <> $2 AND summary IS NOT NULL AND summary <> ''"
                " ORDER BY ended_at DESC NULLS LAST, created_at DESC LIMIT 1",
                self._user_id,
                self._session_id,
            )
        return row or ""

    async def add_memories(self, items: list[tuple[str, int]]) -> int:
        """Store extracted facts. Re-learning a fact bumps its importance rather
        than duplicating the row."""
        rows = [
            (self._user_id, self._session_id, text.strip(), max(0, min(100, importance)))
            for text, importance in items
            if text and text.strip()
        ]
        if not rows:
            return 0
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO memories (user_id, source_session_id, memory, importance)"
                " VALUES ($1, $2, $3, $4)"
                " ON CONFLICT (user_id, memory) DO UPDATE"
                " SET importance = greatest(memories.importance, EXCLUDED.importance)",
                rows,
            )
        return len(rows)

    async def transcript(self) -> list[dict[str, Any]]:
        """Every message in this session, oldest first. For summarization."""
        return await self.history(limit=0)

    async def flush(self, context: Any) -> int:
        """Store every context message appended since the last flush. Idempotent."""
        messages = context_messages(context)
        pending = new_messages(messages, self._persisted)
        self._persisted = len(messages)
        if not pending:
            return 0
        rows = [
            (self._session_id, *row_for(message, self._next_seq + offset))
            for offset, message in enumerate(pending)
        ]
        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO messages"
                " (session_id, sequence_number, role, content, tool_call_id,"
                "  tool_calls, payload)"
                " VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)"
                " ON CONFLICT (session_id, sequence_number) DO NOTHING",
                rows,
            )
        self._next_seq += len(rows)
        return len(rows)

    async def close(self, status: str = "completed") -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE sessions SET status = $3, ended_at = now()"
                " WHERE id = $1 AND user_id = $2",
                self._session_id,
                self._user_id,
                status,
            )


async def open_session(pool, user_id: str, session_id: str) -> SessionStore:
    store = SessionStore(pool, user_id, session_id)
    await store.open()
    return store
