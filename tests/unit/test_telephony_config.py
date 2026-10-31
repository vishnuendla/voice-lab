import pytest

from voice_assistant.config import TelephonySettings
from voice_assistant.domain.errors import ConfigurationError


def test_telephony_settings_missing(monkeypatch):
    monkeypatch.delenv("VOBIZ_AUTH_ID", raising=False)
    monkeypatch.delenv("VOBIZ_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("VOBIZ_FROM_NUMBER", raising=False)
    with pytest.raises(ConfigurationError, match="Missing telephony settings"):
        TelephonySettings.from_env(load_dotenv_file=False)


def test_telephony_settings_auto_from_number(monkeypatch):
    monkeypatch.setenv("VOBIZ_AUTH_ID", "auth")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "token")
    monkeypatch.setenv("VOBIZ_FROM_NUMBER", "auto")

    def fake_fetch(auth_id: str, auth_token: str) -> list[str]:
        assert auth_id == "auth"
        assert auth_token == "token"
        return ["+12025550100"]

    monkeypatch.setattr(
        "voice_assistant.telephony.vobiz_numbers.fetch_owned_numbers",
        fake_fetch,
    )
    settings = TelephonySettings.from_env(load_dotenv_file=False)
    assert settings.from_number == "+12025550100"


def test_telephony_settings_load(monkeypatch):
    monkeypatch.setenv("VOBIZ_AUTH_ID", "auth")
    monkeypatch.setenv("VOBIZ_AUTH_TOKEN", "token")
    monkeypatch.setenv("VOBIZ_FROM_NUMBER", "+10000000000")
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    settings = TelephonySettings.from_env(load_dotenv_file=False)
    assert settings.auth_id == "auth"
    assert settings.from_number == "+10000000000"
    assert settings.public_base_url == ""
