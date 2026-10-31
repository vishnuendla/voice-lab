import pytest

from voice_assistant.agent.tools.registry import ToolRegistry
from voice_assistant.domain.errors import ToolExecutionError
from voice_assistant.domain.models import ToolResult


class _FakeSearchTool:
    name = "web_search"
    schema = {
        "type": "function",
        "function": {
            "name": "web_search",
            "parameters": {"type": "object"},
        },
    }

    def execute(self, arguments: dict) -> ToolResult:
        return ToolResult(context=f"result for {arguments['query']}", sources=[])


def test_valid_query():
    registry = ToolRegistry([_FakeSearchTool()], max_query_length=50)
    result = registry.execute("web_search", {"query": "hello"})
    assert result.context == "result for hello"


def test_missing_query():
    registry = ToolRegistry([_FakeSearchTool()])
    with pytest.raises(ToolExecutionError, match="Missing required argument"):
        registry.execute("web_search", {})


def test_unknown_tool():
    registry = ToolRegistry([_FakeSearchTool()])
    with pytest.raises(ToolExecutionError, match="Unknown tool"):
        registry.execute("calendar", {"query": "x"})


def test_oversized_query():
    registry = ToolRegistry([_FakeSearchTool()], max_query_length=5)
    with pytest.raises(ToolExecutionError, match="exceeds max length"):
        registry.execute("web_search", {"query": "toolong"})
