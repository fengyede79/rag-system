from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HTTPResult:
    http_status: int | None
    answer: str
    latency_ms: int
    error: str | None = None
    sse_done_event: bool | None = None
    diagnostics: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParsedSSE:
    answer: str
    done: bool
    events: list[str]
    error: str | None = None


def parse_sse_events(raw: str) -> ParsedSSE:
    answer_parts: list[str] = []
    events: list[str] = []
    error: str | None = None
    done = False
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        data = "\n".join(data_lines)
        events.append(event_name)
        if event_name == "message":
            answer_parts.append(data)
        elif event_name == "done":
            done = True
        elif event_name == "error":
            error = data
    return ParsedSSE(answer="".join(answer_parts), done=done, events=events, error=error)


def parse_chat_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    answer = str(payload.get("answer", ""))
    diagnostics = payload.get("diagnostics")
    return answer, diagnostics if isinstance(diagnostics, dict) else None


class LiveE2EClient:
    def __init__(self, *, base_url: str, request_timeout_seconds: int, stream_timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.request_timeout_seconds = request_timeout_seconds
        self.stream_timeout_seconds = stream_timeout_seconds

    def wait_until_ready(self, timeout_seconds: int = 180) -> None:
        deadline = time.time() + timeout_seconds
        last_error = ""
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{self.base_url}/", timeout=5) as response:
                    if response.status < 500:
                        return
            except Exception as exc:
                last_error = str(exc)
                time.sleep(2)
        raise RuntimeError(f"service readiness timed out: {last_error}")

    def chat(self, *, question: str, session_id: str) -> HTTPResult:
        started = time.time()
        body = json.dumps(
            {"question": question, "session_id": session_id, "include_diagnostics": True},
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                answer, diagnostics = parse_chat_payload(payload)
                return HTTPResult(
                    http_status=response.status,
                    answer=answer,
                    latency_ms=int((time.time() - started) * 1000),
                    diagnostics=diagnostics,
                )
        except urllib.error.HTTPError as exc:
            return HTTPResult(
                http_status=exc.code,
                answer="",
                latency_ms=int((time.time() - started) * 1000),
                error=f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')}",
            )
        except Exception as exc:
            return HTTPResult(
                http_status=None,
                answer="",
                latency_ms=int((time.time() - started) * 1000),
                error=str(exc),
            )

    def stream(self, *, question: str, session_id: str) -> HTTPResult:
        started = time.time()
        query = urllib.parse.urlencode({"question": question, "session_id": session_id})
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/api/chat/stream?{query}",
                timeout=self.stream_timeout_seconds,
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
                parsed = parse_sse_events(raw)
                return HTTPResult(
                    http_status=response.status,
                    answer=parsed.answer,
                    latency_ms=int((time.time() - started) * 1000),
                    error=parsed.error,
                    sse_done_event=parsed.done,
                )
        except urllib.error.HTTPError as exc:
            return HTTPResult(
                http_status=exc.code,
                answer="",
                latency_ms=int((time.time() - started) * 1000),
                error=f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')}",
                sse_done_event=False,
            )
        except Exception as exc:
            return HTTPResult(
                http_status=None,
                answer="",
                latency_ms=int((time.time() - started) * 1000),
                error=str(exc),
                sse_done_event=False,
            )
