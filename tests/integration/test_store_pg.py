"""Runs only with a real Postgres. Set DATABASE_URL, then: uv run pytest tests/integration"""

import json
import os
import uuid

import pytest

pytest.importorskip("asyncpg")

from voice_assistant.session.store import SessionNotFound, SessionStore, open_pool

DSN = (os.getenv("DATABASE_URL") or "").strip()

pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL not set")


class FakeContext:
    """Stands in for Pipecat's LLMContext: a growing list of message dicts."""

    def __init__(self, messages):
        self._messages = list(messages)

    def get_messages(self):
        return list(self._messages)

    def append(self, message):
        self._messages.append(message)


@pytest.fixture
async def pool():
    pool = await open_pool(DSN)
    yield pool
    await pool.close()


async def test_turns_survive_a_restart_and_stay_ordered(pool):
    user_id = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"

    store = SessionStore(pool, user_id, session_id)
    await store.open()
    context = FakeContext(await store.seed("system prompt"))
    context.append({"role": "user", "content": "first question"})
    context.append({"role": "assistant", "content": "first answer"})
    assert await store.flush(context) == 2
    assert await store.flush(context) == 0  # idempotent
    context.append({"role": "user", "content": "second question"})
    assert await store.flush(context) == 1
    await store.close()

    # A new process: same ids, fresh store.
    resumed = SessionStore(pool, user_id, session_id)
    await resumed.open()
    seeded = await resumed.seed("system prompt")
    assert seeded[0] == {"role": "system", "content": "system prompt"}
    assert [m["content"] for m in seeded[1:]] == [
        "first question",
        "first answer",
        "second question",
    ]

    # Sequence numbers continue rather than restarting.
    resumed_context = FakeContext(seeded)
    resumed_context.append({"role": "assistant", "content": "second answer"})
    assert await resumed.flush(resumed_context) == 1
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT sequence_number, role FROM messages WHERE session_id = $1"
            " ORDER BY sequence_number",
            session_id,
        )
    assert [r["sequence_number"] for r in rows] == [1, 2, 3, 4]
    assert [r["role"] for r in rows] == ["user", "assistant", "user", "assistant"]
    await resumed.close()


async def test_another_user_cannot_open_the_session(pool):
    owner = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"
    await SessionStore(pool, owner, session_id).open()

    intruder = SessionStore(pool, f"test-user-{uuid.uuid4()}", session_id)
    with pytest.raises(SessionNotFound):
        await intruder.open()


async def test_tool_columns_mirror_the_payload(pool):
    """The diagram's `tool_call_id` / `tool_calls` columns are filled, and the
    payload stays the source of truth."""
    user_id = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"
    store = SessionStore(pool, user_id, session_id)
    await store.open()
    call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "web_search", "arguments": '{"query":"weather"}'},
    }
    context = FakeContext(await store.seed("system prompt"))
    context.append({"role": "user", "content": "weather?"})
    context.append({"role": "assistant", "content": None, "tool_calls": [call]})
    context.append({"role": "tool", "tool_call_id": "call_1", "content": "22 degrees"})
    context.append({"role": "assistant", "content": "It is 22 degrees."})
    assert await store.flush(context) == 4

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content, tool_call_id, tool_calls FROM messages"
            " WHERE session_id = $1 ORDER BY sequence_number",
            session_id,
        )
    assert [r["role"] for r in rows] == ["user", "assistant", "tool", "assistant"]
    assert json.loads(rows[1]["tool_calls"]) == [call]
    assert rows[2]["tool_call_id"] == "call_1"
    assert rows[0]["tool_calls"] is None

    # Resuming replays the tool call as history, unchanged.
    resumed = SessionStore(pool, user_id, session_id)
    await resumed.open()
    seeded = await resumed.seed("system prompt")
    assert seeded[2] == {"role": "assistant", "content": None, "tool_calls": [call]}
    assert seeded[3]["tool_call_id"] == "call_1"


async def test_summary_is_stored_on_the_session(pool):
    user_id = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"
    store = SessionStore(pool, user_id, session_id)
    await store.open()
    await store.save_summary("  The user is building a voice assistant.  ")
    async with pool.acquire() as conn:
        summary = await conn.fetchval("SELECT summary FROM sessions WHERE id = $1", session_id)
    assert summary == "The user is building a voice assistant."

    # An empty summary must not wipe a good one.
    await store.save_summary("   ")
    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT summary FROM sessions WHERE id = $1", session_id)


async def test_memories_carry_into_a_brand_new_session(pool):
    user_id = f"test-user-{uuid.uuid4()}"
    first_session = f"test-session-{uuid.uuid4()}"
    store = SessionStore(pool, user_id, first_session)
    await store.open()
    assert await store.add_memories(
        [("Name is Vishnu.", 90), ("Prefers concise answers.", 60), ("  ", 10)]
    ) == 2

    # A different session, same user: the memories arrive in the system prompt.
    second_session = f"test-session-{uuid.uuid4()}"
    fresh = SessionStore(pool, user_id, second_session)
    await fresh.open()
    seeded = await fresh.seed("be brief")
    assert len(seeded) == 1  # no message history, only the enriched prompt
    assert "Name is Vishnu." in seeded[0]["content"]
    assert "Prefers concise answers." in seeded[0]["content"]

    # Most important first.
    assert await fresh.memories() == ["Name is Vishnu.", "Prefers concise answers."]


async def test_relearning_a_memory_bumps_importance_instead_of_duplicating(pool):
    user_id = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"
    store = SessionStore(pool, user_id, session_id)
    await store.open()
    await store.add_memories([("Name is Vishnu.", 40)])
    await store.add_memories([("Name is Vishnu.", 95)])
    await store.add_memories([("Name is Vishnu.", 10)])  # never downgrades
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT memory, importance FROM memories WHERE user_id = $1", user_id
        )
    assert len(rows) == 1
    assert rows[0]["importance"] == 95


async def test_memories_are_private_to_their_user(pool):
    owner = f"test-user-{uuid.uuid4()}"
    intruder = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"
    store = SessionStore(pool, owner, session_id)
    await store.open()
    await store.add_memories([("Owner's secret project is codenamed Falcon.", 80)])

    other = SessionStore(pool, intruder, f"test-session-{uuid.uuid4()}")
    await other.open()
    assert await other.memories() == []
    assert "Falcon" not in (await other.seed("be brief"))[0]["content"]


async def test_importance_out_of_range_is_clamped_not_rejected(pool):
    """The CHECK constraint would raise; the store clamps first."""
    user_id = f"test-user-{uuid.uuid4()}"
    store = SessionStore(pool, user_id, f"test-session-{uuid.uuid4()}")
    await store.open()
    assert await store.add_memories([("too high", 5000), ("too low", -20)]) == 2
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT memory, importance FROM memories WHERE user_id = $1 ORDER BY memory", user_id
        )
    assert [(r["memory"], r["importance"]) for r in rows] == [("too high", 100), ("too low", 0)]


async def test_transcript_returns_every_turn_past_the_recall_limit(pool):
    """`history()` is capped for context; `transcript()` is not, so the
    summarizer sees the whole session."""
    user_id = f"test-user-{uuid.uuid4()}"
    session_id = f"test-session-{uuid.uuid4()}"
    store = SessionStore(pool, user_id, session_id, limit=4)
    await store.open()
    context = FakeContext(await store.seed("sys"))
    for i in range(12):
        context.append({"role": "user", "content": f"q{i}"})
    assert await store.flush(context) == 12

    assert len(await store.history()) == 4
    full = await store.transcript()
    assert [m["content"] for m in full] == [f"q{i}" for i in range(12)]


async def test_schema_is_idempotent_on_an_existing_database(pool):
    """`open_pool` re-applies schema.sql on every start, including the ALTERs."""
    from voice_assistant.session.store import SCHEMA_PATH

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(sql)
        await conn.execute(sql)


async def test_last_summary_returns_the_previous_session_not_this_one(pool):
    """The "Last time" line on reconnect must not echo the session you are in."""
    user_id = f"test-user-{uuid.uuid4()}"
    earlier, current = f"s-{uuid.uuid4()}", f"s-{uuid.uuid4()}"

    old = SessionStore(pool, user_id, earlier)
    await old.open()
    await old.save_summary("we talked about the deployment plan")
    await old.close()

    new = SessionStore(pool, user_id, current)
    await new.open()
    await new.save_summary("this session is still going")

    assert await new.last_summary() == "we talked about the deployment plan"


async def test_last_summary_never_crosses_users(pool):
    theirs, mine = f"test-user-{uuid.uuid4()}", f"test-user-{uuid.uuid4()}"

    other = SessionStore(pool, theirs, f"s-{uuid.uuid4()}")
    await other.open()
    await other.save_summary("their private conversation")
    await other.close()

    ours = SessionStore(pool, mine, f"s-{uuid.uuid4()}")
    await ours.open()

    assert await ours.last_summary() == ""


async def test_last_summary_is_empty_with_no_earlier_session(pool):
    store = SessionStore(pool, f"test-user-{uuid.uuid4()}", f"s-{uuid.uuid4()}")
    await store.open()

    assert await store.last_summary() == ""
