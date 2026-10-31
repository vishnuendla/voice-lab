import json

import pytest

from voice_assistant.session.store import (
    SessionNotFound,
    SessionStore,
    new_messages,
    recall_prompt,
    row_for,
    seed_messages,
)


def test_seed_puts_current_system_prompt_first_and_drops_the_stored_one():
    history = [
        {"role": "system", "content": "an old prompt"},
        {"role": "user", "content": "hello"},
    ]
    seeded = seed_messages("current prompt", history, 20)
    assert seeded[0] == {"role": "system", "content": "current prompt"}
    assert [m["role"] for m in seeded].count("system") == 1
    assert seeded[1]["content"] == "hello"


def test_seed_keeps_only_the_tail():
    history = [{"role": "user", "content": str(i)} for i in range(10)]
    seeded = seed_messages("sys", history, 4)
    assert len(seeded) == 4
    assert [m["content"] for m in seeded[1:]] == ["7", "8", "9"]


def test_new_messages_returns_only_the_unseen_tail():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "one"},
        {"role": "assistant", "content": "two"},
    ]
    assert new_messages(messages, 2) == [{"role": "assistant", "content": "two"}]
    assert new_messages(messages, 3) == []
    assert new_messages(messages, 0) == messages[1:]


def test_row_for_text_content():
    seq, role, content, tool_call_id, tool_calls, payload = row_for(
        {"role": "user", "content": "hi"}, 7
    )
    assert (seq, role, content) == (7, "user", "hi")
    assert (tool_call_id, tool_calls) == (None, None)
    assert json.loads(payload) == {"role": "user", "content": "hi"}


def test_row_for_keeps_structured_content_in_the_payload_only():
    parts = [{"type": "text", "text": "hi"}]
    _seq, _role, content, _tid, _tc, payload = row_for({"role": "user", "content": parts}, 1)
    assert content is None
    assert json.loads(payload)["content"] == parts


def test_row_for_preserves_a_tool_call_message():
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "web_search", "arguments": '{"query":"weather"}'},
            }
        ],
    }
    _seq, role, content, tool_call_id, tool_calls, payload = row_for(message, 3)
    assert (role, content) == ("assistant", None)
    assert tool_call_id is None
    # The convenience column mirrors what the payload already holds.
    assert json.loads(tool_calls) == message["tool_calls"]
    assert json.loads(payload) == message


def test_row_for_extracts_a_tool_result_id():
    message = {"role": "tool", "tool_call_id": "call_1", "content": "22 degrees"}
    _seq, role, content, tool_call_id, tool_calls, _payload = row_for(message, 4)
    assert (role, content, tool_call_id, tool_calls) == ("tool", "22 degrees", "call_1", None)


def test_recall_prompt_is_unchanged_without_memories():
    assert recall_prompt("be brief", []) == "be brief"


def test_recall_prompt_appends_memories_to_the_system_prompt():
    prompt = recall_prompt("be brief", ["Name is Vishnu.", "Prefers Python."])
    assert prompt.startswith("be brief")
    assert "- Name is Vishnu." in prompt
    assert "- Prefers Python." in prompt


def test_seed_carries_memories_in_the_system_message():
    seeded = seed_messages("sys", [], 20, ["Name is Vishnu."])
    assert seeded[0]["role"] == "system"
    assert "Name is Vishnu." in seeded[0]["content"]
    # Memories ride along with the prompt; they are not extra turns.
    assert len(seeded) == 1


def test_store_requires_both_ids():
    with pytest.raises(SessionNotFound):
        SessionStore(object(), "", "session-1")
    with pytest.raises(SessionNotFound):
        SessionStore(object(), "user-1", "")
