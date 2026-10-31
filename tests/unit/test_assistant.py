from tests.conftest import FakeLLM, FakeSearchTool
from voice_assistant.agent.assistant import Assistant
from voice_assistant.agent.memory import InMemoryMemoryStore
from voice_assistant.agent.tools.registry import ToolRegistry
from voice_assistant.domain.models import LLMMessage, ToolCall


def _assistant(llm: FakeLLM) -> Assistant:
    memory = InMemoryMemoryStore(max_messages=20, system_prompt="sys")
    tools = ToolRegistry([FakeSearchTool()])
    return Assistant(llm=llm, memory=memory, tools=tools)


def test_direct_answer():
    llm = FakeLLM([LLMMessage(content="Hello there", tool_calls=[])])
    answer = _assistant(llm).ask("hi")
    assert answer == "Hello there"
    assert len(llm.calls) == 1


def test_tool_call_persisted_and_final_answer():
    llm = FakeLLM(
        [
            LLMMessage(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="web_search",
                        arguments='{"query":"weather"}',
                    )
                ],
            ),
            LLMMessage(content="It is sunny today.", tool_calls=[]),
        ]
    )
    assistant = _assistant(llm)
    answer = assistant.ask("What's the weather?")
    assert answer == "It is sunny today."
    assert len(llm.calls) == 2

    messages = llm.calls[1][0]
    roles = [m["role"] for m in messages]
    assert "tool" in roles
    assert any(m.get("tool_calls") for m in messages if m["role"] == "assistant")


def test_follow_up_turn_keeps_tool_context():
    llm = FakeLLM(
        [
            LLMMessage(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="web_search",
                        arguments='{"query":"weather"}',
                    )
                ],
            ),
            LLMMessage(content="It is sunny.", tool_calls=[]),
            LLMMessage(content="You asked about the weather.", tool_calls=[]),
        ]
    )
    assistant = _assistant(llm)
    assistant.ask("What's the weather?")
    answer = assistant.ask("What did I ask?")
    assert answer == "You asked about the weather."
    messages = llm.calls[-1][0]
    assert any(m.get("role") == "tool" for m in messages)
