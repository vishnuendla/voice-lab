"""One-shot, non-streaming chat against the configured provider chain.

The live conversation runs through Pipecat's streaming services; work that
happens outside a pipeline -- summarizing a finished session -- needs a plain
request/response call. It walks the same Groq -> OpenRouter chain from
`ai.llm.PROVIDERS`, so there is exactly one place that decides which model
answers and with which key.
"""

from __future__ import annotations

import logging
from typing import Any

from voice_assistant.ai.llm import configured_chain
from voice_assistant.pipecat.utils import env_int

logger = logging.getLogger("voice_assistant.ai.chat")

DEFAULT_TIMEOUT_SECONDS = 30


async def chat_once(messages: list[dict[str, Any]], *, max_tokens: int | None = None) -> str:
    """Ask the first provider that answers. Returns "" if none does.

    Best-effort by design: every caller so far is background work that must not
    take a conversation down with it.
    """
    from openai import AsyncOpenAI

    timeout = env_int("LLM_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
    last_error: Exception | None = None

    for spec, model, key in configured_chain():
        try:
            client = AsyncOpenAI(
                base_url=spec.base_url, api_key=key, timeout=timeout, max_retries=0
            )
            async with client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    **({"max_completion_tokens": max_tokens} if max_tokens else {}),
                )
            if response.choices:
                return response.choices[0].message.content or ""
            logger.warning("%s returned no choices", spec.name)
        except Exception as exc:  # noqa: BLE001 - any provider failure means: try the next one
            last_error = exc
            logger.warning("%s failed (%s), trying the next provider", spec.name, exc)

    logger.error("every LLM provider failed: %s", last_error)
    return ""
