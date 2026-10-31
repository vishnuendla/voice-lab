from collections import deque
from typing import Any


class InMemoryMemoryStore:
    """Process-lifetime conversation history. System prompt is never dropped."""

    def __init__(self, max_messages: int = 20, system_prompt: str | None = None):
        if max_messages < 2:
            raise ValueError("max_messages must be at least 2")
        self._max_messages = max_messages
        self._system: dict[str, Any] | None = None
        self._messages: deque[dict[str, Any]] = deque()
        if system_prompt:
            self._system = {"role": "system", "content": system_prompt}

    def add_message(self, message: dict[str, Any]) -> None:
        if message.get("role") == "system":
            self._system = message
            return
        self._messages.append(message)
        capacity = self._max_messages - (1 if self._system else 0)
        while len(self._messages) > capacity:
            self._messages.popleft()

    def get(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if self._system:
            messages.append(self._system)
        messages.extend(self._messages)
        return messages
