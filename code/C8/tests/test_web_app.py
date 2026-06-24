import json

from web_app import create_app


class _DummyRAGSystem:
    def ask_question(self, question, stream=False, session_id="default"):
        print("查询类型: detail")
        print("检索相关文档...")

        if stream:
            def generate():
                print("生成详细回答...")
                yield "你好，"
                yield "这是流式回答。"

            return generate()

        print("生成详细回答...")
        return "这是完整回答。"


def test_chat_stream_endpoint_only_emits_answer_chunks():
    app = create_app(system_factory=lambda: _DummyRAGSystem())
    client = app.test_client()

    response = client.get("/api/chat/stream?question=测试问题&session_id=test-session")
    payload = b"".join(response.response).decode("utf-8")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert "data: 你好，" in payload
    assert "data: 这是流式回答。" in payload
    assert "event: done" in payload
    assert "查询类型" not in payload
    assert "检索相关文档" not in payload


def test_chat_endpoint_returns_clean_answer_json():
    app = create_app(system_factory=lambda: _DummyRAGSystem())
    client = app.test_client()

    response = client.post(
        "/api/chat",
        data=json.dumps({"question": "测试问题", "session_id": "test-session"}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.get_json() == {"answer": "这是完整回答。"}
