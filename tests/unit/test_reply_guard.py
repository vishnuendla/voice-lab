from voice_assistant.guardrails.reply_guard import (
    BUSY_REPLY_SPEECH,
    EMPTY_REPLY_SPEECH,
    ReplyGuardState,
    spoken_fallback_for_error,
    status_speak_frame,
)


def test_spoken_fallback_rate_limit():
    assert spoken_fallback_for_error("Error code: 429") == BUSY_REPLY_SPEECH
    assert "busy" in spoken_fallback_for_error("temporarily rate-limited upstream").lower()


def test_spoken_fallback_timeout_and_generic():
    assert "long" in spoken_fallback_for_error("LLM completion timeout").lower()
    assert spoken_fallback_for_error("Provider returned error") == EMPTY_REPLY_SPEECH


def test_status_speak_frame_is_not_stored_in_context():
    frame = status_speak_frame(EMPTY_REPLY_SPEECH)
    assert frame.text == EMPTY_REPLY_SPEECH
    assert frame.append_to_context is False


def test_reply_guard_skips_when_text_arrived():
    state = ReplyGuardState()
    state.on_start()
    state.on_text("Hello Navya")
    assert state.fallback_after_end() is None


def test_reply_guard_speaks_when_llm_empty():
    state = ReplyGuardState()
    state.on_start()
    assert state.fallback_after_end() == EMPTY_REPLY_SPEECH


def test_reply_guard_skips_user_interrupt():
    state = ReplyGuardState()
    state.on_start()
    state.on_interrupt()
    assert state.fallback_after_end() is None


def test_reply_guard_uses_rate_limit_error():
    state = ReplyGuardState()
    state.on_start()
    state.on_error("HTTP 429 Too Many Requests")
    assert state.fallback_after_end() == BUSY_REPLY_SPEECH


def test_reply_guard_idle_end_is_noop():
    state = ReplyGuardState()
    assert state.fallback_after_end() is None


def test_reply_guard_does_not_treat_slow_stream_as_interrupt():
    """A live MiniMax stream with no tokens yet must still be allowed to finish."""
    state = ReplyGuardState()
    state.on_start()
    assert state.interrupted is False
    assert state.in_response is True
    assert state.got_text is False
