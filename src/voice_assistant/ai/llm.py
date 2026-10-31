"""LLM providers, and the failover chain built from them.

Groq is the primary and OpenRouter the backup, but nothing outside this module
knows that: `PROVIDERS` is the single place a provider is described, and both
the live pipeline (`build_llm_stack`) and the one-shot summarizer
(`ai.chat.chat_once`) read it. Adding a provider is one `LLMProvider` entry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pipecat.pipeline.service_switcher import (
    ServiceSwitcher,
    ServiceSwitcherStrategyFailover,
)
from pipecat.processors.frame_processor import FrameProcessor

from voice_assistant.domain.errors import ConfigurationError
from voice_assistant.pipecat.utils import api_key, env_int, env_str, normalize_provider

logger = logging.getLogger("voice_assistant.ai.llm")

DEFAULT_PROVIDER = "groq"
DEFAULT_FALLBACK_PROVIDER = "openrouter"
DEFAULT_MAX_TOKENS = 180


@dataclass(frozen=True)
class LLMProvider:
    """Everything that differs between one OpenAI-compatible provider and another."""

    name: str
    key_env: str
    base_url: str
    default_model: str


PROVIDERS: dict[str, LLMProvider] = {
    "groq": LLMProvider(
        name="groq",
        key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        default_model="openai/gpt-oss-120b",
    ),
    "openrouter": LLMProvider(
        name="openrouter",
        key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
        default_model="minimax/minimax-m3:free",
    ),
}


def provider(name: str, label: str = "LLM_PROVIDER") -> LLMProvider:
    return PROVIDERS[normalize_provider(name, frozenset(PROVIDERS), label)]


def max_tokens() -> int:
    return env_int("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS)


def _service(spec: LLMProvider, model: str, key: str) -> FrameProcessor:
    if spec.name == "groq":
        from pipecat.services.groq.llm import GroqLLMService as Service
    else:
        from pipecat.services.openrouter.llm import OpenRouterLLMService as Service

    logger.info("%s ready model=%s", spec.name, model)
    return Service(
        api_key=key,
        settings=Service.Settings(model=model, max_completion_tokens=max_tokens()),
    )


def build_llm(name: str | None = None) -> FrameProcessor:
    """One LLM service. Raises ConfigurationError when its key is missing."""
    spec = provider(name or env_str("LLM_PROVIDER", DEFAULT_PROVIDER))
    key = api_key(spec.key_env)
    if not key:
        raise ConfigurationError(
            f"{spec.key_env} is missing or still a placeholder in .env. "
            f"Required when LLM_PROVIDER is {spec.name}."
        )
    return _service(spec, env_str("LLM_MODEL", spec.default_model), key)


def configured_chain() -> list[tuple[LLMProvider, str, str]]:
    """(provider, model, key) for the primary then the backup, skipping any whose
    key is unset. A Groq-only deployment must still boot, so a missing backup key
    is not an error -- only an empty chain is."""
    primary = provider(env_str("LLM_PROVIDER", DEFAULT_PROVIDER))
    backup = provider(
        env_str("LLM_FALLBACK_PROVIDER", DEFAULT_FALLBACK_PROVIDER), "LLM_FALLBACK_PROVIDER"
    )

    wanted = [(primary, env_str("LLM_MODEL", primary.default_model))]
    if backup.name != primary.name:
        wanted.append((backup, env_str("LLM_FALLBACK_MODEL", backup.default_model)))

    chain = []
    for spec, model in wanted:
        key = api_key(spec.key_env)
        if key:
            chain.append((spec, model, key))
        else:
            logger.warning("%s has no %s: skipping it in the LLM chain", spec.name, spec.key_env)
    if not chain:
        raise ConfigurationError(
            "No LLM provider is configured. Set GROQ_API_KEY (or OPENROUTER_API_KEY) in .env."
        )
    return chain


def build_llm_stack() -> FrameProcessor:
    """The LLM slot of the pipeline: the primary alone, or the primary wrapped in
    a switcher that fails over to the backup when it errors."""
    chain = configured_chain()
    services = [_service(spec, model, key) for spec, model, key in chain]
    if len(services) == 1:
        logger.info("llm chain: %s (no fallback configured)", chain[0][0].name)
        return services[0]

    logger.info("llm chain: %s", " -> ".join(spec.name for spec, _, _ in chain))
    # ponytail: failover switches the *next* turn -- the turn that errored is
    # lost and EnsureSpokenReply speaks the busy line. If losing a turn on
    # failover matters, re-queue an LLMRunFrame from on_service_switched.
    return ServiceSwitcher(
        services=services,
        strategy_type=ServiceSwitcherStrategyFailover,
    )
