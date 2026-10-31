from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class LLMMessage:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float


@dataclass(frozen=True)
class SearchSource:
    title: str
    url: str
    content: str


@dataclass(frozen=True)
class ToolResult:
    context: str
    sources: list[SearchSource] = field(default_factory=list)
    error: str | None = None


ChatMessage = dict[str, Any]
