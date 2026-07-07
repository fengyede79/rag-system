from e2e.client import parse_sse_events, parse_chat_payload


def test_parse_sse_events_collects_messages_and_done():
    raw = (
        "event: message\n"
        "data: 第一段\n\n"
        "event: message\n"
        "data: 第二段\n\n"
        "event: done\n"
        "data: [DONE]\n\n"
    )

    parsed = parse_sse_events(raw)

    assert parsed.answer == "第一段第二段"
    assert parsed.done is True
    assert parsed.events == ["message", "message", "done"]


def test_parse_sse_events_records_error_event():
    raw = "event: error\ndata: {\"message\":\"boom\"}\n\n"

    parsed = parse_sse_events(raw)

    assert parsed.answer == ""
    assert parsed.done is False
    assert parsed.error == "{\"message\":\"boom\"}"


def test_parse_chat_payload_with_diagnostics():
    payload = {
        "answer": "回答",
        "diagnostics": {"generation": {"strategy": "structured"}},
    }

    answer, diagnostics = parse_chat_payload(payload)

    assert answer == "回答"
    assert diagnostics == {"generation": {"strategy": "structured"}}
