import pytest

# build_assistant wires the desktop mic/speaker adapters:
#   uv sync --group desktop
pytest.importorskip("sounddevice")
pytest.importorskip("edge_tts")
pytest.importorskip("tavily")

import logging

from voice_assistant.config import Settings
from voice_assistant.factory import build_assistant


def test_build_assistant_without_search(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("SEARCH_ENABLED", "false")

    settings = Settings.from_env(load_dotenv_file=False)
    logger = logging.getLogger("test")
    assistant = build_assistant(settings, logger)

    assert assistant._tools.get_schemas() == []
