import pytest

from voice_assistant.config import Settings
from voice_assistant.domain.errors import ConfigurationError


def test_missing_openrouter_key():
    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        Settings.from_env(load_dotenv_file=False)


def test_missing_tavily_when_search_enabled(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("SEARCH_ENABLED", "true")
    with pytest.raises(ConfigurationError, match="TAVILY_API_KEY"):
        Settings.from_env(load_dotenv_file=False)


def test_search_disabled_by_default_without_tavily(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_ENABLED", raising=False)
    settings = Settings.from_env(load_dotenv_file=False)
    assert settings.search_enabled is False
    assert settings.tavily_api_key == ""


def test_search_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    settings = Settings.from_env(load_dotenv_file=False)
    assert settings.search_enabled is False
    assert settings.tavily_api_key == ""
