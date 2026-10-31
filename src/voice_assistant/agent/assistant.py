from __future__ import annotations

import json
import logging

from voice_assistant.agent.tools.registry import ToolRegistry
from voice_assistant.domain.errors import LLMError, ToolExecutionError
from voice_assistant.domain.models import LLMMessage
from voice_assistant.domain.ports import LLMClient, MemoryStore
from voice_assistant.logging_setup import TurnLogger, new_turn_id


class Assistant:
    """Coordinates memory, the LLM, and tools. Depends only on ports."""

    def __init__(
        self,
        llm: LLMClient,
        memory: MemoryStore,
        tools: ToolRegistry,
        logger: logging.Logger | None = None,
        log_transcripts: bool = False,
    ):
        self._llm = llm
        self._memory = memory
        self._tools = tools
        base = logger or logging.getLogger("voice_assistant")
        self._logger = TurnLogger(base, {"turn_id": "-"})
        self._log_transcripts = log_transcripts

    def ask(self, query: str) -> str:
        turn_id = new_turn_id()
        self._logger.extra["turn_id"] = turn_id

        self._memory.add_message({"role": "user", "content": query})
        if self._log_transcripts:
            self._logger.info("user turn received")
        else:
            self._logger.info("user turn received chars=%s", len(query))

        first = self._chat(include_tools=True)
        if not first.tool_calls:
            answer = first.content or ""
            self._memory.add_message({"role": "assistant", "content": answer})
            self._logger.info("assistant answered without tools")
            return answer

        self._memory.add_message(self._assistant_tool_message(first))
        for tool_call in first.tool_calls:
            self._run_tool(tool_call.id, tool_call.name, tool_call.arguments)

        final = self._chat(include_tools=False)
        answer = final.content or ""
        self._memory.add_message({"role": "assistant", "content": answer})
        self._logger.info("assistant answered after tools")
        return answer

    def _chat(self, include_tools: bool) -> LLMMessage:
        tools = self._tools.get_schemas() if include_tools else None
        try:
            return self._llm.chat(self._memory.get(), tools=tools)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError("LLM request failed") from exc

    def _assistant_tool_message(self, message: LLMMessage) -> dict:
        return {
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in message.tool_calls
            ],
        }

    def _run_tool(self, call_id: str, name: str, raw_arguments: str) -> None:
        self._logger.info("calling tool name=%s", name)
        try:
            arguments = json.loads(raw_arguments or "{}")
            if not isinstance(arguments, dict):
                raise ToolExecutionError("Tool arguments must be a JSON object")
            result = self._tools.execute(name, arguments)
            if result.error:
                content = json.dumps({"error": result.error})
            else:
                content = result.context
        except (json.JSONDecodeError, ToolExecutionError) as exc:
            self._logger.warning("tool failed name=%s error=%s", name, exc)
            content = json.dumps({"error": str(exc)})

        self._memory.add_message(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": content,
            }
        )
