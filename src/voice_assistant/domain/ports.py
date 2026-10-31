from typing import Any, Protocol, runtime_checkable

from voice_assistant.domain.models import LLMMessage, ToolResult, Transcript


@runtime_checkable
class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMMessage: ...


@runtime_checkable
class MemoryStore(Protocol):
    def add_message(self, message: dict[str, Any]) -> None: ...

    def get(self) -> list[dict[str, Any]]: ...


@runtime_checkable
class Tool(Protocol):
    name: str
    schema: dict[str, Any]

    def execute(self, arguments: dict[str, Any]) -> ToolResult: ...


@runtime_checkable
class SpeechToText(Protocol):
    def listen(self) -> Transcript: ...


@runtime_checkable
class TextToSpeech(Protocol):
    def start(self) -> None: ...

    def speak(self, text: str) -> None: ...

    def shutdown(self) -> None: ...
