"""end_session is called twice on a normal browser Disconnect -- once early so the
summary can be shown, once from run_pipeline's finally. It must survive that."""

import pytest

from voice_assistant.session import lifecycle
from voice_assistant.session.recall import store_session_recall


class FakeStore:
    def __init__(self, messages=None, summary="a summary"):
        self.ended = False
        self.summary = ""
        self.closed = 0
        self.saved = None
        self.memories_added = []
        self._messages = messages if messages is not None else [
            {"role": "user", "content": "what is the capital of France"},
            {"role": "assistant", "content": "Paris."},
        ]
        self._summary = summary

    async def transcript(self):
        return self._messages

    async def save_summary(self, summary):
        self.saved = summary

    async def add_memories(self, items):
        self.memories_added.extend(items)
        return len(items)

    async def close(self, status="completed"):
        self.closed += 1


class FakePersist:
    def __init__(self):
        self.flushes = 0

    async def flush(self):
        self.flushes += 1


@pytest.fixture
def summarizer(monkeypatch):
    """Stub the LLM round trip; parse_extraction has its own tests."""
    calls = []

    async def fake_extract(transcript):
        calls.append(transcript)
        return "they asked about France", [("Interested in France", 40)]

    monkeypatch.setattr("voice_assistant.session.recall._extract", fake_extract)
    monkeypatch.delenv("MEMORY_EXTRACTION", raising=False)
    return calls


async def test_end_session_flushes_summarizes_and_closes(summarizer):
    store, persist = FakeStore(), FakePersist()

    summary = await lifecycle.end_session(store, persist)

    assert summary == "they asked about France"
    assert persist.flushes == 1
    assert store.saved == "they asked about France"
    assert store.memories_added == [("Interested in France", 40)]
    assert store.closed == 1


async def test_end_session_is_idempotent(summarizer):
    """The early call shows the summary; the finally still has to close cleanly."""
    store, persist = FakeStore(), FakePersist()

    early = await lifecycle.end_session(store, persist, close=False)
    late = await lifecycle.end_session(store, persist)

    assert early == late == "they asked about France"
    assert len(summarizer) == 1, "the transcript must not be summarized twice"
    assert persist.flushes == 1
    assert store.closed == 1, "close is deferred to the second call"


async def test_end_session_without_a_store_is_a_no_op():
    assert await lifecycle.end_session(None, FakePersist()) == ""


async def test_a_failing_summarizer_still_flushes_and_closes(monkeypatch):
    async def boom(_transcript):
        raise RuntimeError("every provider is down")

    monkeypatch.setattr("voice_assistant.session.recall._extract", boom)
    store, persist = FakeStore(), FakePersist()

    assert await lifecycle.end_session(store, persist) == ""
    assert persist.flushes == 1, "the conversation is saved even with no summary"
    assert store.closed == 1


async def test_two_message_session_is_summarized(summarizer):
    """Regression: the turn count used to subtract a system prompt that the
    `messages` table never holds, so the shortest real session got no summary."""
    store = FakeStore()

    assert await store_session_recall(store) == "they asked about France"
    assert store.saved == "they asked about France"


async def test_a_single_message_session_is_not_summarized(summarizer):
    store = FakeStore(messages=[{"role": "user", "content": "hello"}])

    assert await store_session_recall(store) == ""
    assert summarizer == []


async def test_extraction_can_be_switched_off(monkeypatch, summarizer):
    monkeypatch.setenv("MEMORY_EXTRACTION", "0")
    store = FakeStore()

    assert await store_session_recall(store) == ""
    assert store.saved is None


# --- the shared one-shot chat -----------------------------------------------


async def test_chat_once_falls_through_to_the_backup(monkeypatch):
    """The summarizer follows the same Groq -> OpenRouter policy as the conversation."""
    from voice_assistant.ai import chat as chat_mod
    from voice_assistant.ai.llm import PROVIDERS

    tried = []

    def fake_chain():
        return [
            (PROVIDERS["groq"], "groq-model", "gsk-test"),
            (PROVIDERS["openrouter"], "or-model", "sk-or-test"),
        ]

    class FakeClient:
        def __init__(self, *, base_url, **_kwargs):
            self.base_url = base_url
            self.chat = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        @property
        def completions(self):
            return self

        async def create(self, **kwargs):
            tried.append(kwargs["model"])
            if kwargs["model"] == "groq-model":
                raise RuntimeError("429 rate limited")
            message = type("M", (), {"content": "the backup answered"})()
            return type("R", (), {"choices": [type("C", (), {"message": message})()]})()

    monkeypatch.setattr(chat_mod, "configured_chain", fake_chain)
    monkeypatch.setattr("openai.AsyncOpenAI", FakeClient)

    assert await chat_mod.chat_once([{"role": "user", "content": "hi"}]) == "the backup answered"
    assert tried == ["groq-model", "or-model"]


async def test_chat_once_returns_empty_when_every_provider_fails(monkeypatch):
    from voice_assistant.ai import chat as chat_mod
    from voice_assistant.ai.llm import PROVIDERS

    monkeypatch.setattr(
        chat_mod, "configured_chain", lambda: [(PROVIDERS["groq"], "m", "k")]
    )

    class Dead:
        def __init__(self, **_kwargs):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("openai.AsyncOpenAI", Dead)

    assert await chat_mod.chat_once([{"role": "user", "content": "hi"}]) == ""
