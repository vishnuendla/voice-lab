from voice_assistant.agent.memory import InMemoryMemoryStore


def test_system_prompt_survives_overflow():
    memory = InMemoryMemoryStore(max_messages=4, system_prompt="system rules")
    memory.add_message({"role": "user", "content": "one"})
    memory.add_message({"role": "assistant", "content": "two"})
    memory.add_message({"role": "user", "content": "three"})
    memory.add_message({"role": "assistant", "content": "four"})
    memory.add_message({"role": "user", "content": "five"})

    messages = memory.get()
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "system rules"
    assert len(messages) == 4


def test_tool_messages_are_stored():
    memory = InMemoryMemoryStore(max_messages=10, system_prompt="sys")
    memory.add_message({"role": "user", "content": "weather?"})
    memory.add_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": '{"query":"weather"}',
                    },
                }
            ],
        }
    )
    memory.add_message(
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "sunny and warm",
        }
    )

    messages = memory.get()
    assert any(m.get("role") == "tool" for m in messages)
    assert messages[-1]["content"] == "sunny and warm"
