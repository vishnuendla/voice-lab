from __future__ import annotations

from collections.abc import Iterable

from voice_assistant.domain.errors import ToolExecutionError
from voice_assistant.domain.models import ToolResult
from voice_assistant.domain.ports import Tool


class ToolRegistry:
    def __init__(self, tools: Iterable[Tool], max_query_length: int = 500):
        self._tools = {tool.name: tool for tool in tools}
        self._max_query_length = max_query_length

    def get_schemas(self) -> list[dict]:
        return [tool.schema for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(f"Unknown tool: {name}")

        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolExecutionError("Missing required argument: query")
        if len(query) > self._max_query_length:
            raise ToolExecutionError(f"query exceeds max length of {self._max_query_length}")

        return tool.execute({"query": query.strip()})
