import pytest

from voice_assistant.domain.errors import LLMError
from voice_assistant.domain.models import LLMMessage, ToolResult


class FakeLLM:
    def __init__(self, responses: list[LLMMessage]):
        self._responses = list(responses)
        self.calls: list[tuple] = []

    def chat(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        if not self._responses:
            raise LLMError("no scripted response")
        return self._responses.pop(0)


class FakeSearchTool:
    name = "web_search"
    schema = {
        "type": "function",
        "function": {
            "name": "web_search",
            "parameters": {"type": "object"},
        },
    }

    def execute(self, arguments: dict) -> ToolResult:
        return ToolResult(context="search says sunny", sources=[])


@pytest.fixture
def fake_search_tool():
    return FakeSearchTool()
