from __future__ import annotations

from tavily import TavilyClient

from voice_assistant.config import Settings
from voice_assistant.domain.errors import ToolExecutionError
from voice_assistant.domain.models import SearchSource, ToolResult


class TavilySearch:
    def __init__(self, settings: Settings, client: TavilyClient | None = None):
        self._settings = settings
        self._client = client or TavilyClient(api_key=settings.tavily_api_key)

    def search(self, query: str) -> ToolResult:
        try:
            response = self._client.search(
                query=query,
                search_depth="advanced",
                max_results=self._settings.search_max_results,
            )
        except Exception as exc:
            raise ToolExecutionError("Web search failed") from exc

        sources: list[SearchSource] = []
        seen_urls: set[str] = set()
        remaining = self._settings.search_max_chars

        for item in response.get("results", []):
            url = (item.get("url") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)

            content = " ".join((item.get("content") or "").split())
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[:remaining].rstrip()
            remaining -= len(content)

            sources.append(
                SearchSource(
                    title=item.get("title") or "",
                    url=url,
                    content=content,
                )
            )

        context = "\n\n".join(source.content for source in sources if source.content)
        return ToolResult(context=context, sources=sources)
