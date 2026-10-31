from __future__ import annotations

import time
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from voice_assistant.config import Settings
from voice_assistant.domain.errors import LLMError
from voice_assistant.domain.models import LLMMessage, ToolCall

_TRANSIENT = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)


class OpenRouterLLM:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self._settings = settings
        self._client = client or OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMMessage:
        last_error: Exception | None = None
        attempts = self._settings.llm_max_retries + 1
        for attempt in range(attempts):
            try:
                return self._complete(messages, tools)
            except LLMError:
                raise
            except _TRANSIENT as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
                time.sleep(min(2**attempt, 8))
            except APIStatusError as exc:
                if exc.status_code and exc.status_code >= 500:
                    last_error = exc
                    if attempt == attempts - 1:
                        break
                    time.sleep(min(2**attempt, 8))
                    continue
                raise LLMError(self._format_status_error(exc)) from exc
            except Exception as exc:
                raise LLMError("LLM request failed") from exc

        raise LLMError("LLM request failed after retries") from last_error

    def _format_status_error(self, exc: APIStatusError) -> str:
        model = self._settings.llm_model
        body = exc.body if isinstance(exc.body, dict) else {}
        api_message = ""
        if isinstance(body.get("error"), dict):
            api_message = body["error"].get("message", "")
        if exc.status_code == 404:
            hint = f"Model '{model}' was not found or is unavailable."
            if api_message:
                return f"{hint} OpenRouter: {api_message}"
            return f"{hint} Set LLM_MODEL in .env to a valid slug."
        if api_message:
            return f"LLM request failed ({exc.status_code}): {api_message}"
        return f"LLM request failed ({exc.status_code}): {exc}"

    def _complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> LLMMessage:
        kwargs: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        if not response.choices:
            raise LLMError("LLM returned no choices")

        message = response.choices[0].message
        tool_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            function = getattr(call, "function", None)
            if function is None:
                continue
            tool_calls.append(
                ToolCall(
                    id=call.id,
                    name=function.name,
                    arguments=function.arguments or "{}",
                )
            )

        return LLMMessage(content=message.content, tool_calls=tool_calls)
