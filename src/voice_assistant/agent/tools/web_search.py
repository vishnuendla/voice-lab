from collections.abc import Callable

from voice_assistant.domain.models import ToolResult


class WebSearchTool:
    name = "web_search"
    schema = {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for recent or real-time information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    }
                },
                "required": ["query"],
            },
        },
    }

    def __init__(self, search: Callable[[str], ToolResult]):
        self._search = search

    def execute(self, arguments: dict) -> ToolResult:
        return self._search(arguments["query"])
