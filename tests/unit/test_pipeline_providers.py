from types import SimpleNamespace

import pytest
from pipecat.pipeline.service_switcher import ServiceSwitcher

from voice_assistant.ai import llm as llm_mod
from voice_assistant.ai import stt as stt_mod
from voice_assistant.ai import tts as tts_mod
from voice_assistant.domain.errors import ConfigurationError
from voice_assistant.pipecat import pipeline as pipeline_mod
from voice_assistant.pipecat.utils import require_api_key


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    """Providers read the environment directly, so start every test from nothing."""
    for name in (
        "LLM_PROVIDER",
        "LLM_FALLBACK_PROVIDER",
        "LLM_MODEL",
        "LLM_FALLBACK_MODEL",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "STT_PROVIDER",
        "TTS_PROVIDER",
    ):
        monkeypatch.delenv(name, raising=False)


def _patch_builders(monkeypatch):
    monkeypatch.setattr(pipeline_mod, "load_project_dotenv", lambda: None)
    seen = {}

    def fake_stt(name=None):
        seen["stt"] = name
        return SimpleNamespace(kind="stt", provider=name)

    def fake_tts(name=None):
        seen["tts"] = name
        return SimpleNamespace(kind="tts", provider=name)

    monkeypatch.setattr(pipeline_mod, "build_stt", fake_stt)
    monkeypatch.setattr(pipeline_mod, "build_tts", fake_tts)
    monkeypatch.setattr(pipeline_mod, "build_llm_stack", lambda: SimpleNamespace(kind="llm"))
    monkeypatch.setattr(pipeline_mod, "_build_vad", lambda: SimpleNamespace(kind="vad"))
    return seen


# --- STT / TTS selection -----------------------------------------------------


def test_build_services_passes_provider_through(monkeypatch):
    seen = _patch_builders(monkeypatch)

    services = pipeline_mod.build_services(stt_provider="sarvam", tts_provider="sarvam")

    assert seen == {"stt": "sarvam", "tts": "sarvam"}
    assert services.llm.kind == "llm"
    assert services.vad.kind == "vad"


def test_stt_and_tts_default_to_sarvam(monkeypatch):
    """One default, in ai/. The web lab used to disagree with the pipeline."""
    monkeypatch.setattr(stt_mod, "STT_BUILDERS", {"sarvam": lambda: "sarvam-stt"})
    monkeypatch.setattr(tts_mod, "TTS_BUILDERS", {"sarvam": lambda: "sarvam-tts"})

    assert stt_mod.build_stt() == "sarvam-stt"
    assert tts_mod.build_tts() == "sarvam-tts"


def test_stt_provider_env_overrides_default(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "whisper")
    monkeypatch.setattr(stt_mod, "STT_BUILDERS", {"sarvam": dict, "whisper": lambda: "whisper"})

    assert stt_mod.build_stt() == "whisper"


def test_rejects_unknown_stt_provider():
    with pytest.raises(ConfigurationError, match="STT_PROVIDER"):
        stt_mod.build_stt("deepgram")


def test_sarvam_stt_requires_api_key(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="SARVAM_API_KEY"):
        stt_mod.build_stt("sarvam")


def test_sarvam_tts_rejects_placeholder_key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "your_sarvam_key_here")
    with pytest.raises(ConfigurationError, match="SARVAM_API_KEY"):
        tts_mod.build_tts("sarvam")


def test_api_key_strips_quotes(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", '"sk-test-quoted"')
    assert require_api_key("SARVAM_API_KEY", "missing") == "sk-test-quoted"


# --- LLM chain and failover --------------------------------------------------


def test_chain_defaults_to_groq_then_openrouter(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    chain = llm_mod.configured_chain()

    assert [spec.name for spec, _, _ in chain] == ["groq", "openrouter"]
    assert chain[0][1] == llm_mod.PROVIDERS["groq"].default_model


def test_chain_skips_a_provider_with_no_key(monkeypatch):
    """A Groq-only deployment must still boot."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    chain = llm_mod.configured_chain()

    assert [spec.name for spec, _, _ in chain] == ["groq"]


def test_chain_is_empty_only_when_nothing_is_configured():
    with pytest.raises(ConfigurationError, match="No LLM provider"):
        llm_mod.configured_chain()


def test_chain_honours_model_overrides(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "meta-llama/llama-3.3-70b-instruct:free")

    chain = llm_mod.configured_chain()

    assert [model for _, model, _ in chain] == [
        "llama-3.3-70b-versatile",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]


def test_chain_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    with pytest.raises(ConfigurationError, match="LLM_PROVIDER"):
        llm_mod.configured_chain()


def test_single_provider_builds_a_bare_service(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")

    stack = llm_mod.build_llm_stack()

    assert not isinstance(stack, ServiceSwitcher)


def test_two_providers_build_a_failover_switcher(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    stack = llm_mod.build_llm_stack()

    assert isinstance(stack, ServiceSwitcher)
    assert len(stack.services) == 2
    # Groq answers until it errors; the switcher then moves to OpenRouter.
    assert stack.strategy.active_service is stack.services[0]


def test_same_primary_and_fallback_is_not_duplicated(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    assert len(llm_mod.configured_chain()) == 1


def test_max_tokens_is_configurable(monkeypatch):
    assert llm_mod.max_tokens() == llm_mod.DEFAULT_MAX_TOKENS
    monkeypatch.setenv("LLM_MAX_TOKENS", "512")
    assert llm_mod.max_tokens() == 512
