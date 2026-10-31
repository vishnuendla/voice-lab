from types import SimpleNamespace

from voice_assistant.config import TelephonySettings
from voice_assistant.telephony import make_call as make_call_module
from voice_assistant.telephony.privacy import caller_user_id


def test_caller_user_id_is_stable_and_does_not_contain_number():
    number = "+1 (202) 555-0100"

    first = caller_user_id(number, "test-secret")

    assert first.startswith("caller:")
    assert "2025550100" not in first
    assert caller_user_id("+12025550100", "test-secret") == first
    assert caller_user_id(number, "other-secret") != first


def test_caller_user_id_requires_number_and_key():
    assert caller_user_id("+12025550100", "") == ""
    assert caller_user_id("", "test-secret") == ""


def test_outbound_call_output_omits_numbers_and_provider_body(monkeypatch, capsys, caplog):
    settings = TelephonySettings(
        auth_id="test-account",
        auth_token="test-token",
        from_number="+12025550100",
        public_base_url="https://voice.example.test",
    )
    response = SimpleNamespace(status_code=200, ok=True, text="queued for +12025550101")

    def fake_post(*args, **kwargs):
        return response

    monkeypatch.setattr(make_call_module.requests, "post", fake_post)
    make_call_module.make_call(settings, "+12025550101", settings.public_base_url)

    output = capsys.readouterr().out
    assert "+12025550100" not in output
    assert "+12025550101" not in output
    assert response.text not in output
    assert "+12025550101" not in caplog.text
