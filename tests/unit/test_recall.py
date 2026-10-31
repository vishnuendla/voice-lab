from voice_assistant.session.recall import (
    MAX_MEMORIES,
    extraction_enabled,
    parse_extraction,
    transcript_text,
)


def test_parses_the_documented_shape():
    summary, memories = parse_extraction(
        '{"summary": "Talked about Python.",'
        ' "memories": [{"memory": "Name is Vishnu.", "importance": 90}]}'
    )
    assert summary == "Talked about Python."
    assert memories == [("Name is Vishnu.", 90)]


def test_parses_json_wrapped_in_prose_and_code_fences():
    reply = 'Sure!\n```json\n{"summary": "s", "memories": []}\n```\nHope that helps.'
    assert parse_extraction(reply) == ("s", [])


def test_bad_replies_yield_nothing_instead_of_raising():
    for reply in ("", "no json here", "{not json}", "[1, 2, 3]", None):
        assert parse_extraction(reply) == ("", [])


def test_importance_is_clamped_and_defaulted():
    _summary, memories = parse_extraction(
        '{"memories": [{"memory": "a", "importance": 500},'
        ' {"memory": "b", "importance": -5},'
        ' {"memory": "c", "importance": "high"},'
        ' {"memory": "d"}]}'
    )
    assert memories == [("a", 100), ("b", 0), ("c", 50), ("d", 50)]


def test_bare_strings_are_accepted_as_memories():
    _summary, memories = parse_extraction('{"memories": ["likes tea", "  ", 7]}')
    assert memories == [("likes tea", 50)]


def test_memory_count_is_capped():
    items = ",".join(f'{{"memory": "m{i}"}}' for i in range(20))
    _summary, memories = parse_extraction('{"memories": [' + items + ']}')
    assert len(memories) == MAX_MEMORIES


def test_transcript_keeps_only_spoken_turns_in_order():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
        {"role": "tool", "content": "result"},
        {"role": "assistant", "content": "hi there"},
    ]
    assert transcript_text(messages) == "user: hello\nassistant: hi there"


def test_transcript_keeps_the_tail_when_too_long():
    messages = [{"role": "user", "content": "x" * 100} for _ in range(10)]
    text = transcript_text(messages, max_chars=50)
    assert len(text) == 50
    assert text.endswith("x")


def test_extraction_is_on_by_default_and_off_when_disabled(monkeypatch):
    monkeypatch.delenv("MEMORY_EXTRACTION", raising=False)
    assert extraction_enabled() is True
    for value in ("0", "false", "no", "OFF"):
        monkeypatch.setenv("MEMORY_EXTRACTION", value)
        assert extraction_enabled() is False
    monkeypatch.setenv("MEMORY_EXTRACTION", "1")
    assert extraction_enabled() is True
