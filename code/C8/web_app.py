from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Callable, Optional

from flask import Flask, Response, jsonify, render_template_string, request, stream_with_context

from main import RecipeRAGSystem


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>尝尝咸淡 RAG</title>
  <style>
    :root {
      --bg: #f5efe6;
      --panel: rgba(255, 255, 255, 0.78);
      --panel-strong: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --accent: #f97316;
      --accent-strong: #ea580c;
      --border: rgba(31, 41, 55, 0.12);
      --shadow: 0 18px 50px rgba(31, 41, 55, 0.12);
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(249, 115, 22, 0.18), transparent 30%),
        radial-gradient(circle at bottom right, rgba(59, 130, 246, 0.12), transparent 28%),
        linear-gradient(180deg, #fbf7f2 0%, #f5efe6 100%);
      color: var(--text);
      min-height: 100vh;
    }

    .shell {
      width: min(1080px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 32px;
    }

    .hero {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 16px;
    }

    .title {
      margin: 0;
      font-size: clamp(28px, 3vw, 44px);
      letter-spacing: -0.03em;
    }

    .subtitle {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.6;
      max-width: 52rem;
    }

    .badge {
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(249, 115, 22, 0.12);
      color: var(--accent-strong);
      font-weight: 700;
      white-space: nowrap;
      border: 1px solid rgba(249, 115, 22, 0.18);
    }

    .card {
      background: var(--panel);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .messages {
      min-height: 58vh;
      max-height: 68vh;
      overflow: auto;
      padding: 20px;
    }

    .message {
      display: grid;
      gap: 10px;
      margin-bottom: 16px;
      animation: fadeIn 0.22s ease-out;
    }

    .message.user { justify-items: end; }
    .message.assistant { justify-items: start; }

    .bubble {
      max-width: min(780px, 100%);
      padding: 14px 16px;
      border-radius: 18px;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
      border: 1px solid var(--border);
    }

    .user .bubble {
      background: linear-gradient(135deg, rgba(249, 115, 22, 0.95), rgba(234, 88, 12, 0.92));
      color: white;
      border-color: transparent;
      box-shadow: 0 10px 24px rgba(234, 88, 12, 0.16);
    }

    .assistant .bubble {
      background: var(--panel-strong);
    }

    .meta {
      font-size: 12px;
      color: var(--muted);
      padding: 0 4px;
    }

    .composer {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      padding: 16px;
      border-top: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.72);
    }

    input, button {
      font: inherit;
    }

    input[type="text"] {
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px 16px;
      background: rgba(255, 255, 255, 0.94);
      outline: none;
    }

    input[type="text"]:focus {
      border-color: rgba(249, 115, 22, 0.5);
      box-shadow: 0 0 0 4px rgba(249, 115, 22, 0.12);
    }

    button {
      border: none;
      border-radius: 14px;
      padding: 0 18px;
      background: linear-gradient(135deg, var(--accent), var(--accent-strong));
      color: white;
      font-weight: 700;
      cursor: pointer;
      min-width: 112px;
    }

    button:disabled {
      opacity: 0.65;
      cursor: not-allowed;
    }

    .status {
      min-height: 24px;
      padding: 0 20px 14px;
      color: var(--muted);
      font-size: 13px;
    }

    .typing::after {
      content: " ";
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      background: currentColor;
      animation: pulse 1s infinite ease-in-out;
      margin-left: 6px;
      vertical-align: middle;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    @keyframes pulse {
      0%, 100% { opacity: 0.25; transform: scale(0.7); }
      50% { opacity: 1; transform: scale(1); }
    }

    @media (max-width: 720px) {
      .hero { flex-direction: column; align-items: start; }
      .messages { min-height: 54vh; max-height: 64vh; }
      .composer { grid-template-columns: 1fr; }
      button { width: 100%; height: 48px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <div>
        <h1 class="title">尝尝咸淡 RAG</h1>
        <p class="subtitle">一个很轻的流式问答页面。页面只显示最终回答，检索过程和调试日志留在后端终端里。</p>
      </div>
      <div class="badge">Stream SSE</div>
    </div>

    <div class="card">
      <div id="messages" class="messages"></div>
      <div id="status" class="status"></div>
      <form id="composer" class="composer">
        <input id="question" type="text" placeholder="例如：蛋炒饭怎么做？" autocomplete="off" />
        <button id="send" type="submit">发送</button>
      </form>
    </div>
  </div>

  <script>
    const messages = document.getElementById("messages");
    const composer = document.getElementById("composer");
    const questionInput = document.getElementById("question");
    const sendButton = document.getElementById("send");
    const status = document.getElementById("status");
    const sessionKey = "rag_session_id";
    const sessionId = localStorage.getItem(sessionKey) || crypto.randomUUID();
    localStorage.setItem(sessionKey, sessionId);

    function scrollToBottom() {
      messages.scrollTop = messages.scrollHeight;
    }

    function addMessage(role, text) {
      const block = document.createElement("div");
      block.className = `message ${role}`;
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = text || "";
      block.appendChild(bubble);
      messages.appendChild(block);
      scrollToBottom();
      return bubble;
    }

    function setBusy(busy, text) {
      sendButton.disabled = busy;
      questionInput.disabled = busy;
      status.textContent = text || "";
      status.classList.toggle("typing", busy);
    }

    composer.addEventListener("submit", (event) => {
      event.preventDefault();
      const question = questionInput.value.trim();
      if (!question) return;

      addMessage("user", question);
      const answerBubble = addMessage("assistant", "");
      questionInput.value = "";
      setBusy(true, "正在生成回答...");

      const url = `/api/chat/stream?question=${encodeURIComponent(question)}&session_id=${encodeURIComponent(sessionId)}`;
      const source = new EventSource(url);

      source.onmessage = (event) => {
        answerBubble.textContent += event.data;
        scrollToBottom();
      };

      source.addEventListener("done", () => {
        source.close();
        setBusy(false, "回答完成");
      });

      source.addEventListener("error", () => {
        source.close();
        if (!answerBubble.textContent) {
          answerBubble.textContent = "抱歉，服务暂时不可用。";
        }
        setBusy(false, "请求失败");
      });
    });
  </script>
</body>
</html>
"""


def _default_system_factory() -> RecipeRAGSystem:
    system = RecipeRAGSystem()
    system.initialize_system()
    system.build_knowledge_base()
    return system


def create_app(system_factory: Optional[Callable[[], RecipeRAGSystem]] = None) -> Flask:
    app = Flask(__name__)
    app.config["SYSTEM_FACTORY"] = system_factory or _default_system_factory
    app.config["RAG_SYSTEM"] = None
    app.config["RAG_LOCK"] = threading.Lock()

    def get_system() -> RecipeRAGSystem:
        if app.config["RAG_SYSTEM"] is None:
            with app.config["RAG_LOCK"]:
                if app.config["RAG_SYSTEM"] is None:
                    app.config["RAG_SYSTEM"] = app.config["SYSTEM_FACTORY"]()
        return app.config["RAG_SYSTEM"]

    @app.get("/")
    def index():
        return render_template_string(HTML_PAGE)

    @app.post("/api/chat")
    def chat():
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        session_id = (payload.get("session_id") or "default").strip() or "default"
        if not question:
            return jsonify({"error": "question is required"}), 400

        system = get_system()
        answer = system.ask_question(question, stream=False, session_id=session_id)
        if isinstance(answer, dict):
            answer = answer.get("answer", "")
        return jsonify({"answer": answer})

    @app.get("/api/chat/stream")
    def chat_stream():
        question = (request.args.get("question") or "").strip()
        session_id = (request.args.get("session_id") or "default").strip() or "default"
        if not question:
            return jsonify({"error": "question is required"}), 400

        system = get_system()

        def sse_event(name: str, data: str) -> str:
            lines = data.splitlines() or [""]
            payload = "\n".join(f"data: {line}" for line in lines)
            return f"event: {name}\n{payload}\n\n"

        def generate():
            try:
                answer_stream = system.ask_question(question, stream=True, session_id=session_id)
                if isinstance(answer_stream, str):
                    yield sse_event("message", answer_stream)
                else:
                    for chunk in answer_stream:
                        if chunk:
                            yield sse_event("message", str(chunk))
                yield sse_event("done", "[DONE]")
            except Exception as exc:  # pragma: no cover - surfaced in UI
                yield sse_event("error", json.dumps({"message": str(exc)}, ensure_ascii=False))

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
