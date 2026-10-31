from __future__ import annotations

import logging

from voice_assistant.adapters.llm_openrouter import OpenRouterLLM
from voice_assistant.adapters.search_tavily import TavilySearch
from voice_assistant.agent.assistant import Assistant
from voice_assistant.agent.memory import InMemoryMemoryStore
from voice_assistant.agent.prompts import SYSTEM_PROMPT
from voice_assistant.agent.tools.registry import ToolRegistry
from voice_assistant.agent.tools.web_search import WebSearchTool
from voice_assistant.config import Settings


def build_assistant(settings: Settings, logger: logging.Logger) -> Assistant:
    tools: list = []
    if settings.search_enabled:
        search = TavilySearch(settings)
        tools.append(WebSearchTool(search.search))

    registry = ToolRegistry(tools, max_query_length=settings.max_query_length)
    memory = InMemoryMemoryStore(
        max_messages=settings.max_messages,
        system_prompt=SYSTEM_PROMPT,
    )
    llm = OpenRouterLLM(settings)
    return Assistant(
        llm=llm,
        memory=memory,
        tools=registry,
        logger=logger,
        log_transcripts=settings.log_transcripts,
    )
