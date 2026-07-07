# Live E2E Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a live E2E runner that starts the real Flask service, calls real HTTP/SSE endpoints with real data and real DashScope models, executes 50+ scenario turns with rate limiting, and writes auditable JSONL/Markdown reports.

**Architecture:** Keep live E2E outside the normal fast pytest suite. The runner is a small `e2e/` tool: scenario loader -> service manager -> HTTP/SSE client -> rate-limited executor -> assertion/classification engine -> reporters. It does not add a new RAG path and does not use fake retrieval, fake generation, Flask `test_client`, or monkeypatches for live runs.

**Tech Stack:** Python standard library (`argparse`, `json`, `urllib`, `subprocess`, `time`, `dataclasses`), Flask service already in `web_app.py`, existing `.env` / `RAG_LLM_MODEL` config, pytest for runner-unit tests only.

## Global Constraints

- Real E2E means external local Flask service, not `app.test_client()`.
- Real E2E requests must use `/api/chat` or `/api/chat/stream`.
- Real E2E must use real C8 data/index and a real `DASHSCOPE_API_KEY`.
- Supported model pool: `qwen3-vl-235b-a22b-thinking`, `qwen3-vl-32b-thinking`, `qwen-plus-2025-07-28`, `deepseek-r1-distill-qwen-7b`, `qwen-max`, `glm-5`.
- Default model: `qwen-plus-2025-07-28`.
- Default turn limit: `50`.
- Default delay between live requests: `5` seconds.
- Default max retries: `3`.
- Default rate-limit cooldown: `60` seconds.
- Default host/port: `127.0.0.1:5058`.
- Default request timeout: `120` seconds.
- Default stream timeout: `180` seconds.
- No concurrent API calls.
- Do not print or persist `DASHSCOPE_API_KEY`.
- Do not commit generated `e2e/results/*` files unless explicitly requested.
- Pass threshold: `PASS + FLAKY >= 80%` of executed functional turns; `RATE_LIMITED` and `INFRA_ERROR` are reported separately.

---

## Task 1: Scenario File And Loader

**Files:**
- Create: `code/C8/e2e/__init__.py`
- Create: `code/C8/e2e/scenarios/live_e2e_scenarios.json`
- Create: `code/C8/e2e/scenarios.py`
- Create: `code/C8/tests/test_live_e2e_scenarios.py`

**Interfaces:**
- Produces: `ScenarioTurn`, `Scenario`, `load_scenarios(path: Path) -> list[Scenario]`, `flatten_turns(scenarios: list[Scenario], limit_turns: int | None = None) -> list[tuple[Scenario, ScenarioTurn]]`.
- Later tasks consume loaded scenarios and per-turn assertions.

- [ ] **Step 1: Write failing scenario loader tests**

Create `code/C8/tests/test_live_e2e_scenarios.py`:

```python
from pathlib import Path

from e2e.scenarios import flatten_turns, load_scenarios


SCENARIO_FILE = Path(__file__).resolve().parents[1] / "e2e" / "scenarios" / "live_e2e_scenarios.json"


def test_live_e2e_scenario_file_has_at_least_fifty_turns_and_required_categories():
    scenarios = load_scenarios(SCENARIO_FILE)
    turns = flatten_turns(scenarios)
    categories = {scenario.category for scenario in scenarios}

    assert len(turns) >= 50
    assert {
        "single_recipe_detail",
        "recommendation_list",
        "multi_turn_reference",
        "substitution_constraint",
        "low_evidence",
        "domain_reject",
        "streaming_sse",
        "rapid_followup_conflict",
    }.issubset(categories)


def test_flatten_turns_preserves_scenario_order_and_limit():
    scenarios = load_scenarios(SCENARIO_FILE)
    limited = flatten_turns(scenarios, limit_turns=3)

    assert len(limited) == 3
    assert [turn.question for _, turn in limited] == [
        scenarios[0].turns[0].question,
        scenarios[0].turns[1].question,
        scenarios[0].turns[2].question,
    ]


def test_each_turn_has_http_status_and_min_answer_assertion():
    scenarios = load_scenarios(SCENARIO_FILE)
    for scenario, turn in flatten_turns(scenarios):
        assert turn.endpoint in {"chat", "stream"}
        assert "http_status" in turn.assertions
        assert "min_answer_chars" in turn.assertions or turn.endpoint == "stream"
        assert scenario.session_id
```

- [ ] **Step 2: Run scenario tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_scenarios.py -q
```

Expected:

- FAIL with `ModuleNotFoundError: No module named 'e2e'` or missing scenario file.

- [ ] **Step 3: Create E2E package marker**

Create `code/C8/e2e/__init__.py`:

```python
"""Live E2E acceptance runner package."""
```

- [ ] **Step 4: Add scenario loader**

Create `code/C8/e2e/scenarios.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScenarioTurn:
    question: str
    endpoint: str
    assertions: dict[str, Any]


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    session_id: str
    turns: list[ScenarioTurn]


def load_scenarios(path: Path) -> list[Scenario]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    scenarios: list[Scenario] = []
    for raw in payload["scenarios"]:
        turns = [
            ScenarioTurn(
                question=str(turn["question"]),
                endpoint=str(turn.get("endpoint", "chat")),
                assertions=dict(turn.get("assertions") or {}),
            )
            for turn in raw["turns"]
        ]
        scenarios.append(
            Scenario(
                id=str(raw["id"]),
                category=str(raw["category"]),
                session_id=str(raw["session_id"]),
                turns=turns,
            )
        )
    return scenarios


def flatten_turns(
    scenarios: list[Scenario],
    limit_turns: int | None = None,
) -> list[tuple[Scenario, ScenarioTurn]]:
    flattened: list[tuple[Scenario, ScenarioTurn]] = []
    for scenario in scenarios:
        for turn in scenario.turns:
            flattened.append((scenario, turn))
            if limit_turns is not None and len(flattened) >= limit_turns:
                return flattened
    return flattened
```

- [ ] **Step 5: Add 50+ live scenario turns**

Create `code/C8/e2e/scenarios/live_e2e_scenarios.json`:

```json
{
  "version": 1,
  "scenarios": [
    {
      "id": "single_recipe_detail_001",
      "category": "single_recipe_detail",
      "session_id": "live-detail-001",
      "turns": [
        {"question": "蛋炒饭怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["蛋炒饭", "鸡蛋", "米饭"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "宫保鸡丁怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["宫保鸡丁", "鸡丁", "花生"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "番茄炒蛋需要什么食材？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["番茄", "鸡蛋"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "红烧肉怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["红烧肉", "五花肉", "做法"], "answer_not_contains": ["红烧肉怎么做"]}},
        {"question": "鱼香肉丝的步骤是什么？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["鱼香肉丝", "肉丝", "步骤"], "answer_not_contains": ["鱼香肉丝的步骤是什么"]}},
        {"question": "麻婆豆腐有什么小技巧？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["麻婆豆腐", "豆腐", "技巧"], "answer_not_contains": ["麻婆豆腐有什么小技巧"]}},
        {"question": "可乐鸡翅需要准备什么？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["可乐鸡翅", "鸡翅", "可乐"], "answer_not_contains": ["可乐鸡翅需要准备什么"]}},
        {"question": "土豆丝怎么炒更脆？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["土豆", "土豆丝", "脆"], "answer_not_contains": ["土豆丝怎么炒更脆"]}},
        {"question": "香菇滑鸡怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["香菇", "鸡"], "answer_not_contains": ["香菇滑鸡怎么做"]}},
        {"question": "凉拌黄瓜怎么调味？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["黄瓜", "调味", "凉拌"], "answer_not_contains": ["凉拌黄瓜怎么调味"]}}
      ]
    },
    {
      "id": "recommendation_list_001",
      "category": "recommendation_list",
      "session_id": "live-rec-001",
      "turns": [
        {"question": "推荐三个鸡肉菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["鸡", "推荐", "1."], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "推荐几个不辣的家常菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["推荐", "不辣", "家常"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "家里有鸡蛋和米饭，推荐能做的菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["鸡蛋", "米饭", "蛋炒饭"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "推荐三个适合新手的菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["推荐", "新手", "简单"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "晚饭想吃下饭菜，有什么推荐？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["推荐", "下饭", "1."], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "推荐几个快手菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["推荐", "快手", "1."], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "有什么适合带饭的菜？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["带饭", "推荐", "菜"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "推荐几个素菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["素菜", "推荐", "1."], "answer_not_contains": ["知识库里没有找到可靠"]}}
      ]
    },
    {
      "id": "multi_turn_reference_001",
      "category": "multi_turn_reference",
      "session_id": "live-ref-001",
      "turns": [
        {"question": "推荐三个鸡肉菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["鸡", "1."], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "第一个怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_not_contains": ["第一个怎么做", "知识库里没有找到可靠"]}},
        {"question": "这个能不放辣吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["辣", "不放", "可以"], "answer_not_contains": ["这个能不放辣吗"]}},
        {"question": "没有豆瓣酱怎么办？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["豆瓣酱", "替代", "可以"], "answer_not_contains": ["没有豆瓣酱怎么办"]}},
        {"question": "第二个适合新手吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_not_contains": ["第二个适合新手吗"]}},
        {"question": "第三个要准备哪些食材？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["食材", "准备", "材料"], "answer_not_contains": ["第三个要准备哪些食材"]}},
        {"question": "这个热量高吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 10, "answer_not_contains": ["这个热量高吗"]}},
        {"question": "谢谢", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 4, "answer_contains_any": ["不客气", "继续", "可以"]}},
        {"question": "第一个还能换成不辣的吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["不辣", "可以", "换"], "answer_not_contains": ["第一个还能换成不辣的吗"]}},
        {"question": "那第二个怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_not_contains": ["那第二个怎么做"]}}
      ]
    },
    {
      "id": "substitution_constraint_001",
      "category": "substitution_constraint",
      "session_id": "live-sub-001",
      "turns": [
        {"question": "宫保鸡丁怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["宫保鸡丁", "鸡"], "answer_not_contains": ["宫保鸡丁怎么做"]}},
        {"question": "没有花生可以吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["花生", "可以", "替代"], "answer_not_contains": ["没有花生可以吗"]}},
        {"question": "能少油一点吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["少油", "可以", "油"], "answer_not_contains": ["能少油一点吗"]}},
        {"question": "能不能不要辣椒？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["辣椒", "不放", "可以"], "answer_not_contains": ["能不能不要辣椒"]}},
        {"question": "换个不辣的鸡肉菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["不辣", "鸡", "推荐"], "answer_not_contains": ["知识库里没有找到可靠"]}},
        {"question": "这个适合带饭吗？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["带饭", "适合", "可以"], "answer_not_contains": ["这个适合带饭吗"]}}
      ]
    },
    {
      "id": "low_evidence_001",
      "category": "low_evidence",
      "session_id": "live-low-001",
      "turns": [
        {"question": "不存在的银河炒饭怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["没有找到", "不确定", "知识库"], "answer_not_contains": ["银河炒饭做法如下"]}},
        {"question": "火星土豆丝需要什么材料？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["没有找到", "不确定", "知识库"], "answer_not_contains": ["火星土豆丝需要"]}},
        {"question": "空气炸月亮饼怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["没有找到", "不确定", "知识库"], "answer_not_contains": ["空气炸月亮饼做法"]}},
        {"question": "蓝莓红烧肉盖饭的标准做法？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["没有找到", "不确定", "知识库"], "answer_not_contains": ["蓝莓红烧肉盖饭的标准做法"]}},
        {"question": "不存在的菜能不能少放辣？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["没有找到", "不确定", "知识库"], "answer_not_contains": ["不存在的菜能不能少放辣"]}}
      ]
    },
    {
      "id": "domain_reject_001",
      "category": "domain_reject",
      "session_id": "live-domain-001",
      "turns": [
        {"question": "Python 怎么学？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["食谱", "做菜", "菜"], "answer_not_contains": ["Python 的学习路线"]}},
        {"question": "路由器总断网怎么办？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["食谱", "做菜", "菜"], "answer_not_contains": ["重启路由器"]}},
        {"question": "今天上海天气怎么样？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["食谱", "做菜", "菜"], "answer_not_contains": ["天气"]}},
        {"question": "怎么学习线性代数？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 8, "answer_contains_any": ["食谱", "做菜", "菜"], "answer_not_contains": ["线性代数"]}}
      ]
    },
    {
      "id": "streaming_sse_001",
      "category": "streaming_sse",
      "session_id": "live-stream-001",
      "turns": [
        {"question": "蛋炒饭怎么做？", "endpoint": "stream", "assertions": {"http_status": 200, "sse_done_event": true, "min_answer_chars": 20, "answer_contains_any": ["蛋炒饭", "鸡蛋", "米饭"]}},
        {"question": "推荐三个鸡肉菜", "endpoint": "stream", "assertions": {"http_status": 200, "sse_done_event": true, "min_answer_chars": 20, "answer_contains_any": ["鸡", "推荐", "1."]}},
        {"question": "第一个怎么做？", "endpoint": "stream", "assertions": {"http_status": 200, "sse_done_event": true, "min_answer_chars": 20, "answer_not_contains": ["第一个怎么做"]}},
        {"question": "谢谢", "endpoint": "stream", "assertions": {"http_status": 200, "sse_done_event": true, "min_answer_chars": 4, "answer_contains_any": ["不客气", "继续", "可以"]}}
      ]
    },
    {
      "id": "rapid_followup_conflict_001",
      "category": "rapid_followup_conflict",
      "session_id": "live-rapid-001",
      "turns": [
        {"question": "推荐三个鸡肉菜", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["鸡", "推荐", "1."]}},
        {"question": "第一个怎么做？", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_not_contains": ["第一个怎么做"]}},
        {"question": "不是这个，换个不辣的", "endpoint": "chat", "assertions": {"http_status": 200, "min_answer_chars": 20, "answer_contains_any": ["不辣", "换", "推荐"], "answer_not_contains": ["不是这个，换个不辣的"]}}
      ]
    }
  ]
}
```

- [ ] **Step 6: Run scenario loader tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_scenarios.py -q
```

Expected:

- PASS.

- [ ] **Step 7: Commit**

```bash
git add code/C8/e2e/__init__.py code/C8/e2e/scenarios.py code/C8/e2e/scenarios/live_e2e_scenarios.json code/C8/tests/test_live_e2e_scenarios.py
git commit -m "test: add live e2e scenario matrix"
```

---

## Task 2: Assertion Engine And Report Records

**Files:**
- Create: `code/C8/e2e/assertions.py`
- Create: `code/C8/tests/test_live_e2e_assertions.py`

**Interfaces:**
- Consumes: `Scenario`, `ScenarioTurn`.
- Produces: `TurnResult`, `classify_exception(exc: Exception | str) -> str`, `evaluate_assertions(...) -> TurnResult`.

- [ ] **Step 1: Write failing assertion tests**

Create `code/C8/tests/test_live_e2e_assertions.py`:

```python
from e2e.assertions import TurnResult, classify_error_text, evaluate_assertions


def test_evaluate_assertions_passes_contains_and_not_contains():
    result = evaluate_assertions(
        run_id="r1",
        model="qwen-plus-2025-07-28",
        scenario_id="s1",
        category="single_recipe_detail",
        session_id="sess",
        turn_index=1,
        endpoint="chat",
        question="蛋炒饭怎么做？",
        http_status=200,
        answer="蛋炒饭需要鸡蛋和米饭，先炒鸡蛋再炒饭。",
        assertions={
            "http_status": 200,
            "min_answer_chars": 10,
            "answer_contains_any": ["蛋炒饭", "番茄炒蛋"],
            "answer_contains_all": ["鸡蛋", "米饭"],
            "answer_not_contains": ["知识库里没有找到可靠"],
        },
        latency_ms=123,
        attempt=1,
        sse_done_event=None,
        error=None,
    )

    assert result.status == "PASS"
    assert result.failure_class is None


def test_evaluate_assertions_returns_fail_with_reasons():
    result = evaluate_assertions(
        run_id="r1",
        model="qwen-plus-2025-07-28",
        scenario_id="s1",
        category="single_recipe_detail",
        session_id="sess",
        turn_index=1,
        endpoint="chat",
        question="蛋炒饭怎么做？",
        http_status=200,
        answer="不知道。",
        assertions={
            "http_status": 200,
            "min_answer_chars": 10,
            "answer_contains_any": ["蛋炒饭"],
        },
        latency_ms=123,
        attempt=1,
        sse_done_event=None,
        error=None,
    )

    assert result.status == "FAIL"
    assert result.failure_class == "FAIL"
    assert "min_answer_chars" in result.error
    assert "answer_contains_any" in result.error


def test_classify_rate_limit_and_model_errors():
    assert classify_error_text("HTTP 429: rate limit exceeded") == "RATE_LIMITED"
    assert classify_error_text("timeout waiting for service") == "INFRA_ERROR"
    assert classify_error_text("model not found") == "MODEL_ERROR"


def test_turn_result_json_line_masks_none_values_consistently():
    result = TurnResult(
        run_id="r1",
        model="qwen-max",
        scenario_id="s1",
        category="domain_reject",
        turn_index=1,
        session_id="sess",
        endpoint="chat",
        question="Python 怎么学？",
        http_status=200,
        answer="我主要处理食谱问题。",
        status="PASS",
        failure_class=None,
        latency_ms=42,
        attempt=1,
        error=None,
    )

    payload = result.to_dict()
    assert payload["model"] == "qwen-max"
    assert payload["failure_class"] is None
    assert payload["answer"] == "我主要处理食谱问题。"
```

- [ ] **Step 2: Run assertion tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_assertions.py -q
```

Expected:

- FAIL with `ModuleNotFoundError: No module named 'e2e.assertions'`.

- [ ] **Step 3: Implement assertion engine**

Create `code/C8/e2e/assertions.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PASS = "PASS"
FAIL = "FAIL"
FLAKY = "FLAKY"
RATE_LIMITED = "RATE_LIMITED"
INFRA_ERROR = "INFRA_ERROR"
MODEL_ERROR = "MODEL_ERROR"
DATA_ERROR = "DATA_ERROR"
SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class TurnResult:
    run_id: str
    model: str
    scenario_id: str
    category: str
    turn_index: int
    session_id: str
    endpoint: str
    question: str
    http_status: int | None
    answer: str
    status: str
    failure_class: str | None
    latency_ms: int
    attempt: int
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "scenario_id": self.scenario_id,
            "category": self.category,
            "turn_index": self.turn_index,
            "session_id": self.session_id,
            "endpoint": self.endpoint,
            "question": self.question,
            "http_status": self.http_status,
            "answer": self.answer,
            "status": self.status,
            "failure_class": self.failure_class,
            "latency_ms": self.latency_ms,
            "attempt": self.attempt,
            "error": self.error,
        }


def classify_error_text(error: str) -> str:
    text = (error or "").lower()
    if "429" in text or "rate limit" in text or "too many requests" in text:
        return RATE_LIMITED
    if "timeout" in text or "connection" in text or "port" in text or "service" in text:
        return INFRA_ERROR
    if "model" in text or "invalid_request" in text or "400" in text:
        return MODEL_ERROR
    if "data" in text or "index" in text or "vector" in text:
        return DATA_ERROR
    return INFRA_ERROR


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _failure(reasons: list[str]) -> tuple[str, str | None, str | None]:
    if reasons:
        return FAIL, FAIL, "; ".join(reasons)
    return PASS, None, None


def evaluate_assertions(
    *,
    run_id: str,
    model: str,
    scenario_id: str,
    category: str,
    session_id: str,
    turn_index: int,
    endpoint: str,
    question: str,
    http_status: int | None,
    answer: str,
    assertions: dict[str, Any],
    latency_ms: int,
    attempt: int,
    sse_done_event: bool | None,
    error: str | None,
) -> TurnResult:
    if error:
        failure_class = classify_error_text(error)
        return TurnResult(
            run_id=run_id,
            model=model,
            scenario_id=scenario_id,
            category=category,
            turn_index=turn_index,
            session_id=session_id,
            endpoint=endpoint,
            question=question,
            http_status=http_status,
            answer=answer,
            status=failure_class,
            failure_class=failure_class,
            latency_ms=latency_ms,
            attempt=attempt,
            error=error,
        )

    reasons: list[str] = []
    expected_status = assertions.get("http_status")
    if expected_status is not None and http_status != int(expected_status):
        reasons.append(f"http_status expected {expected_status} got {http_status}")

    min_chars = assertions.get("min_answer_chars")
    if min_chars is not None and len(answer.strip()) < int(min_chars):
        reasons.append(f"min_answer_chars expected {min_chars} got {len(answer.strip())}")

    contains_all = _as_list(assertions.get("answer_contains_all"))
    missing_all = [item for item in contains_all if item not in answer]
    if missing_all:
        reasons.append(f"answer_contains_all missing {missing_all}")

    contains_any = _as_list(assertions.get("answer_contains_any"))
    if contains_any and not any(item in answer for item in contains_any):
        reasons.append(f"answer_contains_any missing all {contains_any}")

    forbidden = [item for item in _as_list(assertions.get("answer_not_contains")) if item in answer]
    if forbidden:
        reasons.append(f"answer_not_contains found {forbidden}")

    regex = assertions.get("answer_regex")
    if regex and not re.search(str(regex), answer):
        reasons.append(f"answer_regex did not match {regex}")

    if assertions.get("sse_done_event") is True and sse_done_event is not True:
        reasons.append("sse_done_event expected true")

    status, failure_class, reason_text = _failure(reasons)
    return TurnResult(
        run_id=run_id,
        model=model,
        scenario_id=scenario_id,
        category=category,
        turn_index=turn_index,
        session_id=session_id,
        endpoint=endpoint,
        question=question,
        http_status=http_status,
        answer=answer,
        status=status,
        failure_class=failure_class,
        latency_ms=latency_ms,
        attempt=attempt,
        error=reason_text,
    )
```

- [ ] **Step 4: Run assertion tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_assertions.py -q
```

Expected:

- PASS.

- [ ] **Step 5: Commit**

```bash
git add code/C8/e2e/assertions.py code/C8/tests/test_live_e2e_assertions.py
git commit -m "test: add live e2e assertion engine"
```

---

## Task 3: HTTP/SSE Client And Rate Limiter

**Files:**
- Create: `code/C8/e2e/client.py`
- Create: `code/C8/e2e/rate_limit.py`
- Create: `code/C8/tests/test_live_e2e_client.py`
- Create: `code/C8/tests/test_live_e2e_rate_limit.py`

**Interfaces:**
- Produces: `LiveE2EClient.chat(...)`, `LiveE2EClient.stream(...)`, `RateLimiter.wait_after_turn()`, `RateLimiter.backoff_seconds(attempt: int)`.

- [ ] **Step 1: Write rate limiter tests**

Create `code/C8/tests/test_live_e2e_rate_limit.py`:

```python
from e2e.rate_limit import RateLimiter


def test_backoff_schedule_is_bounded_and_conservative():
    limiter = RateLimiter(delay_seconds=5, rate_limit_cooldown_seconds=60)

    assert limiter.backoff_seconds(1) == 0
    assert limiter.backoff_seconds(2) == 10
    assert limiter.backoff_seconds(3) == 30
    assert limiter.backoff_seconds(4) == 60
    assert limiter.backoff_seconds(5) == 60


def test_rate_limiter_uses_injected_sleep():
    calls = []
    limiter = RateLimiter(delay_seconds=2, rate_limit_cooldown_seconds=60, sleep_func=calls.append)

    limiter.wait_after_turn()
    limiter.wait_after_rate_limit()

    assert calls == [2, 60]
```

- [ ] **Step 2: Write HTTP/SSE parser tests**

Create `code/C8/tests/test_live_e2e_client.py`:

```python
from e2e.client import parse_sse_events


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
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_rate_limit.py tests/test_live_e2e_client.py -q
```

Expected:

- FAIL with missing modules.

- [ ] **Step 4: Implement rate limiter**

Create `code/C8/e2e/rate_limit.py`:

```python
from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        *,
        delay_seconds: float,
        rate_limit_cooldown_seconds: float,
        sleep_func: Callable[[float], None] | None = None,
    ):
        self.delay_seconds = delay_seconds
        self.rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._sleep = sleep_func or time.sleep

    def backoff_seconds(self, attempt: int) -> float:
        if attempt <= 1:
            return 0
        if attempt == 2:
            return 10
        if attempt == 3:
            return 30
        return 60

    def wait_before_retry(self, attempt: int) -> None:
        seconds = self.backoff_seconds(attempt)
        if seconds > 0:
            self._sleep(seconds)

    def wait_after_turn(self) -> None:
        if self.delay_seconds > 0:
            self._sleep(self.delay_seconds)

    def wait_after_rate_limit(self) -> None:
        if self.rate_limit_cooldown_seconds > 0:
            self._sleep(self.rate_limit_cooldown_seconds)
```

- [ ] **Step 5: Implement HTTP/SSE client**

Create `code/C8/e2e/client.py`:

```python
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class HTTPResult:
    http_status: int | None
    answer: str
    latency_ms: int
    error: str | None = None
    sse_done_event: bool | None = None


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
        body = json.dumps({"question": question, "session_id": session_id}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return HTTPResult(
                    http_status=response.status,
                    answer=str(payload.get("answer", "")),
                    latency_ms=int((time.time() - started) * 1000),
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
```

- [ ] **Step 6: Run client/rate-limit tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_rate_limit.py tests/test_live_e2e_client.py -q
```

Expected:

- PASS.

- [ ] **Step 7: Commit**

```bash
git add code/C8/e2e/client.py code/C8/e2e/rate_limit.py code/C8/tests/test_live_e2e_client.py code/C8/tests/test_live_e2e_rate_limit.py
git commit -m "test: add live e2e http client and rate limiter"
```

---

## Task 4: Service Manager And Report Writers

**Files:**
- Create: `code/C8/e2e/service.py`
- Create: `code/C8/e2e/reporting.py`
- Create: `code/C8/tests/test_live_e2e_reporting.py`

**Interfaces:**
- Produces: `LiveServiceProcess.start()`, `LiveServiceProcess.stop()`, `write_jsonl_report(...)`, `write_markdown_report(...)`.

- [ ] **Step 1: Write reporting tests**

Create `code/C8/tests/test_live_e2e_reporting.py`:

```python
from pathlib import Path

from e2e.assertions import TurnResult
from e2e.reporting import summarize_results, write_jsonl_report, write_markdown_report


def _result(status: str, category: str = "domain_reject") -> TurnResult:
    return TurnResult(
        run_id="run-1",
        model="qwen-plus-2025-07-28",
        scenario_id="s1",
        category=category,
        turn_index=1,
        session_id="sess",
        endpoint="chat",
        question="Python 怎么学？",
        http_status=200,
        answer="我主要处理食谱问题。",
        status=status,
        failure_class=None if status == "PASS" else status,
        latency_ms=100,
        attempt=1,
        error=None,
    )


def test_summarize_results_counts_by_status_model_and_category():
    summary = summarize_results([_result("PASS"), _result("FAIL"), _result("RATE_LIMITED", "streaming_sse")])

    assert summary["by_status"]["PASS"] == 1
    assert summary["by_status"]["FAIL"] == 1
    assert summary["by_status"]["RATE_LIMITED"] == 1
    assert summary["by_model"]["qwen-plus-2025-07-28"] == 3
    assert summary["by_category"]["domain_reject"] == 2


def test_report_writers_create_jsonl_and_markdown(tmp_path: Path):
    results = [_result("PASS"), _result("FAIL")]
    jsonl = tmp_path / "run.jsonl"
    markdown = tmp_path / "run.md"

    write_jsonl_report(jsonl, results)
    write_markdown_report(
        markdown,
        run_id="run-1",
        models=["qwen-plus-2025-07-28"],
        delay_seconds=5,
        results=results,
    )

    assert jsonl.read_text(encoding="utf-8").count("\n") == 2
    report = markdown.read_text(encoding="utf-8")
    assert "Live E2E Report" in report
    assert "qwen-plus-2025-07-28" in report
    assert "| PASS | 1 |" in report
```

- [ ] **Step 2: Run reporting tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_reporting.py -q
```

Expected:

- FAIL with missing `e2e.reporting`.

- [ ] **Step 3: Implement report writers**

Create `code/C8/e2e/reporting.py`:

```python
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from e2e.assertions import TurnResult


def summarize_results(results: list[TurnResult]) -> dict:
    return {
        "total": len(results),
        "by_status": dict(Counter(result.status for result in results)),
        "by_model": dict(Counter(result.model for result in results)),
        "by_category": dict(Counter(result.category for result in results)),
    }


def write_jsonl_report(path: Path, results: list[TurnResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")


def _table(counter: dict[str, int]) -> str:
    lines = ["| Key | Count |", "| --- | ---: |"]
    for key, count in sorted(counter.items()):
        lines.append(f"| {key} | {count} |")
    return "\n".join(lines)


def write_markdown_report(
    path: Path,
    *,
    run_id: str,
    models: list[str],
    delay_seconds: float,
    results: list[TurnResult],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_results(results)
    failures = [result for result in results if result.status not in {"PASS", "FLAKY"}]
    slowest = sorted(results, key=lambda result: result.latency_ms, reverse=True)[:10]

    lines = [
        "# Live E2E Report",
        "",
        f"Run ID: `{run_id}`",
        f"Models: `{', '.join(models)}`",
        f"Delay seconds: `{delay_seconds}`",
        f"Total turns: `{summary['total']}`",
        "",
        "## Status Summary",
        "",
        _table(summary["by_status"]),
        "",
        "## Model Summary",
        "",
        _table(summary["by_model"]),
        "",
        "## Category Summary",
        "",
        _table(summary["by_category"]),
        "",
        "## Failure Table",
        "",
        "| Model | Scenario | Turn | Status | Error |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for result in failures:
        error = (result.error or "").replace("|", "\\|").replace("\n", " ")[:240]
        lines.append(f"| {result.model} | {result.scenario_id} | {result.turn_index} | {result.status} | {error} |")

    lines.extend([
        "",
        "## Slowest Turns",
        "",
        "| Model | Scenario | Turn | Latency ms | Question |",
        "| --- | --- | ---: | ---: | --- |",
    ])
    for result in slowest:
        question = result.question.replace("|", "\\|")[:120]
        lines.append(f"| {result.model} | {result.scenario_id} | {result.turn_index} | {result.latency_ms} | {question} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Implement service manager**

Create `code/C8/e2e/service.py`:

```python
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


class LiveServiceProcess:
    def __init__(
        self,
        *,
        project_dir: Path,
        host: str,
        port: int,
        model: str,
        reuse_server: bool,
    ):
        self.project_dir = project_dir
        self.host = host
        self.port = port
        self.model = model
        self.reuse_server = reuse_server
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        if is_port_open(self.host, self.port):
            if self.reuse_server:
                return
            raise RuntimeError(f"port {self.host}:{self.port} is already in use; pass --reuse-server to use it")

        env = os.environ.copy()
        env["RAG_LLM_MODEL"] = self.model
        env["FLASK_RUN_HOST"] = self.host
        env["FLASK_RUN_PORT"] = str(self.port)
        command = [
            sys.executable,
            "-c",
            (
                "from web_app import create_app; "
                "app=create_app(); "
                f"app.run(host='{self.host}', port={self.port}, debug=False, threaded=True)"
            ),
        ]
        self.process = subprocess.Popen(
            command,
            cwd=str(self.project_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
```

- [ ] **Step 5: Run reporting tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_reporting.py -q
```

Expected:

- PASS.

- [ ] **Step 6: Commit**

```bash
git add code/C8/e2e/reporting.py code/C8/e2e/service.py code/C8/tests/test_live_e2e_reporting.py
git commit -m "test: add live e2e service and reporting helpers"
```

---

## Task 5: Live Runner CLI

**Files:**
- Create: `code/C8/e2e/live_e2e_runner.py`
- Create: `code/C8/tests/test_live_e2e_runner.py`

**Interfaces:**
- Produces CLI `python e2e/live_e2e_runner.py --models ... --limit-turns ...`.

- [ ] **Step 1: Write CLI parsing tests**

Create `code/C8/tests/test_live_e2e_runner.py`:

```python
from pathlib import Path

from e2e.live_e2e_runner import build_arg_parser, parse_models, result_paths


def test_parse_models_splits_and_strips_values():
    assert parse_models("qwen-max, qwen-plus-2025-07-28") == ["qwen-max", "qwen-plus-2025-07-28"]


def test_arg_parser_defaults_match_spec():
    args = build_arg_parser().parse_args([])

    assert args.models == "qwen-plus-2025-07-28"
    assert args.limit_turns == 50
    assert args.delay_seconds == 5
    assert args.max_retries == 3
    assert args.rate_limit_cooldown_seconds == 60
    assert args.host == "127.0.0.1"
    assert args.port == 5058


def test_result_paths_use_run_id_and_results_dir(tmp_path: Path):
    jsonl, markdown = result_paths(tmp_path, "live-e2e-20260707-153000")

    assert jsonl.name == "live-e2e-20260707-153000.jsonl"
    assert markdown.name == "live-e2e-20260707-153000.md"
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_runner.py -q
```

Expected:

- FAIL with missing `e2e.live_e2e_runner`.

- [ ] **Step 3: Implement live runner**

Create `code/C8/e2e/live_e2e_runner.py`:

```python
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e2e.assertions import RATE_LIMITED, TurnResult, evaluate_assertions
from e2e.client import LiveE2EClient
from e2e.rate_limit import RateLimiter
from e2e.reporting import write_jsonl_report, write_markdown_report
from e2e.scenarios import flatten_turns, load_scenarios
from e2e.service import LiveServiceProcess


DEFAULT_SCENARIO_FILE = ROOT / "e2e" / "scenarios" / "live_e2e_scenarios.json"
DEFAULT_RESULTS_DIR = ROOT / "e2e" / "results"


def parse_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def result_paths(results_dir: Path, run_id: str) -> tuple[Path, Path]:
    return results_dir / f"{run_id}.jsonl", results_dir / f"{run_id}.md"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run live E2E acceptance against the real C8 Flask service.")
    parser.add_argument("--models", default="qwen-plus-2025-07-28")
    parser.add_argument("--limit-turns", type=int, default=50)
    parser.add_argument("--delay-seconds", type=float, default=5)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--rate-limit-cooldown-seconds", type=float, default=60)
    parser.add_argument("--stop-model-after-rate-limits", type=int, default=3)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--scenario-file", type=Path, default=DEFAULT_SCENARIO_FILE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5058)
    parser.add_argument("--reuse-server", action="store_true")
    parser.add_argument("--stream-timeout-seconds", type=int, default=180)
    parser.add_argument("--request-timeout-seconds", type=int, default=120)
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def _call_turn(client: LiveE2EClient, *, endpoint: str, question: str, session_id: str):
    if endpoint == "stream":
        return client.stream(question=question, session_id=session_id)
    return client.chat(question=question, session_id=session_id)


def run_model(
    *,
    run_id: str,
    model: str,
    args,
    project_dir: Path,
) -> list[TurnResult]:
    scenarios = load_scenarios(args.scenario_file)
    turns = flatten_turns(scenarios, limit_turns=args.limit_turns)
    service = LiveServiceProcess(
        project_dir=project_dir,
        host=args.host,
        port=args.port,
        model=model,
        reuse_server=args.reuse_server,
    )
    client = LiveE2EClient(
        base_url=f"http://{args.host}:{args.port}",
        request_timeout_seconds=args.request_timeout_seconds,
        stream_timeout_seconds=args.stream_timeout_seconds,
    )
    limiter = RateLimiter(
        delay_seconds=args.delay_seconds,
        rate_limit_cooldown_seconds=args.rate_limit_cooldown_seconds,
    )
    results: list[TurnResult] = []
    rate_limit_count = 0

    service.start()
    try:
        client.wait_until_ready(timeout_seconds=240)
        for turn_number, (scenario, turn) in enumerate(turns, start=1):
            final_result: TurnResult | None = None
            for attempt in range(1, args.max_retries + 2):
                limiter.wait_before_retry(attempt)
                response = _call_turn(
                    client,
                    endpoint=turn.endpoint,
                    question=turn.question,
                    session_id=scenario.session_id,
                )
                final_result = evaluate_assertions(
                    run_id=run_id,
                    model=model,
                    scenario_id=scenario.id,
                    category=scenario.category,
                    session_id=scenario.session_id,
                    turn_index=turn_number,
                    endpoint=turn.endpoint,
                    question=turn.question,
                    http_status=response.http_status,
                    answer=response.answer,
                    assertions=turn.assertions,
                    latency_ms=response.latency_ms,
                    attempt=attempt,
                    sse_done_event=response.sse_done_event,
                    error=response.error,
                )
                if final_result.status != RATE_LIMITED:
                    break
                rate_limit_count += 1
                limiter.wait_after_rate_limit()
                if rate_limit_count >= args.stop_model_after_rate_limits:
                    break

            assert final_result is not None
            results.append(final_result)
            print(
                f"[{model}] {turn_number}/{len(turns)} {scenario.id} "
                f"{final_result.status} {final_result.latency_ms}ms"
            )
            if args.fail_fast and final_result.status not in {"PASS", "FLAKY"}:
                break
            if rate_limit_count >= args.stop_model_after_rate_limits:
                break
            limiter.wait_after_turn()
    finally:
        if not args.reuse_server:
            service.stop()
    return results


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    load_dotenv(ROOT / ".env")
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("DASHSCOPE_API_KEY is required for live E2E", file=sys.stderr)
        return 2

    run_id = f"live-e2e-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    models = parse_models(args.models)
    all_results: list[TurnResult] = []
    for model in models:
        all_results.extend(run_model(run_id=run_id, model=model, args=args, project_dir=ROOT))

    jsonl_path, markdown_path = result_paths(args.results_dir, run_id)
    write_jsonl_report(jsonl_path, all_results)
    write_markdown_report(
        markdown_path,
        run_id=run_id,
        models=models,
        delay_seconds=args.delay_seconds,
        results=all_results,
    )
    print(f"Wrote {jsonl_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_runner.py -q
```

Expected:

- PASS.

- [ ] **Step 5: Add results directory ignore rule**

Modify or create `code/C8/e2e/.gitignore`:

```gitignore
results/
```

- [ ] **Step 6: Commit**

```bash
git add code/C8/e2e/live_e2e_runner.py code/C8/e2e/.gitignore code/C8/tests/test_live_e2e_runner.py
git commit -m "test: add live e2e runner cli"
```

---

## Task 6: Runner Acceptance And Live Execution

**Files:**
- Verify: `code/C8/e2e/live_e2e_runner.py`
- Generated but not committed: `code/C8/e2e/results/live-e2e-*.jsonl`, `code/C8/e2e/results/live-e2e-*.md`

**Interfaces:**
- Consumes all previous tasks.
- Produces a real live E2E result report.

- [ ] **Step 1: Run all runner unit tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_scenarios.py tests/test_live_e2e_assertions.py tests/test_live_e2e_rate_limit.py tests/test_live_e2e_client.py tests/test_live_e2e_reporting.py tests/test_live_e2e_runner.py -q
```

Expected:

- PASS.

- [ ] **Step 2: Run a two-turn live smoke test with conservative delay**

Run:

```bash
cd code/C8
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --limit-turns 2 --delay-seconds 5 --max-retries 3 --request-timeout-seconds 120 --stream-timeout-seconds 180
```

Expected:

- Flask service starts on `127.0.0.1:5058`.
- Two turns execute through HTTP.
- Runner writes one JSONL report and one Markdown report under `code/C8/e2e/results`.
- No `DASHSCOPE_API_KEY` appears in stdout or result files.

- [ ] **Step 3: Inspect smoke report**

Run:

```bash
cd code/C8
Get-ChildItem e2e/results -Filter "live-e2e-*.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Encoding utf8
```

Expected:

- Report contains `Live E2E Report`.
- Report contains `qwen-plus-2025-07-28`.
- Report contains a status table.

- [ ] **Step 4: Run the required 50-turn live E2E acceptance**

Run:

```bash
cd code/C8
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --limit-turns 50 --delay-seconds 5 --max-retries 3 --rate-limit-cooldown-seconds 60 --request-timeout-seconds 120 --stream-timeout-seconds 180
```

Expected:

- At least 50 live turns are attempted unless the model is stopped by configured rate-limit threshold.
- JSONL and Markdown reports are created.
- Any rate-limit turns are marked `RATE_LIMITED`.
- Any infra failures are marked `INFRA_ERROR`.
- Functional failures are marked `FAIL`.

- [ ] **Step 5: Calculate pass threshold from the JSONL report**

Run:

```bash
cd code/C8
python -c "import json; from pathlib import Path; p=sorted(Path('e2e/results').glob('live-e2e-*.jsonl'), key=lambda x:x.stat().st_mtime)[-1]; rows=[json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]; functional=[r for r in rows if r['status'] not in {'RATE_LIMITED','INFRA_ERROR','SKIPPED'}]; passed=[r for r in functional if r['status'] in {'PASS','FLAKY'}]; print(p); print('rows',len(rows),'functional',len(functional),'passed',len(passed),'ratio', (len(passed)/len(functional) if functional else 0)); assert len(rows) >= 50 or any(r['status']=='RATE_LIMITED' for r in rows); assert not functional or len(passed)/len(functional) >= 0.8"
```

Expected:

- Command exits 0 when live E2E meets the spec threshold.
- If it exits non-zero, inspect the Markdown failure table before changing code.

- [ ] **Step 6: Run optional second model confidence pass**

Run:

```bash
cd code/C8
python e2e/live_e2e_runner.py --models qwen-max --limit-turns 50 --delay-seconds 5 --max-retries 3 --rate-limit-cooldown-seconds 60 --request-timeout-seconds 120 --stream-timeout-seconds 180
```

Expected:

- Same report guarantees as Step 4.
- This pass is optional for initial implementation acceptance but recommended before demos.

- [ ] **Step 7: Commit implementation files only**

Generated results are intentionally ignored. Commit runner code and tests:

```bash
git add code/C8/e2e code/C8/tests/test_live_e2e_*.py
git commit -m "test: add live e2e acceptance runner"
```

Do not commit `code/C8/e2e/results/*`.

---

## Self-Review

Spec coverage:

- Real Flask subprocess service is covered by Task 4 and Task 6.
- HTTP `/api/chat` and SSE `/api/chat/stream` are covered by Task 3 and Task 6.
- Real models and `RAG_LLM_MODEL` are covered by Task 4 and Task 5.
- 50+ scenario turns are covered by Task 1.
- Rate limiting, retry, cooldown, and no concurrency are covered by Task 3 and Task 6.
- JSONL and Markdown reports are covered by Task 4 and Task 6.
- Failure classifications are covered by Task 2.
- Secret handling is covered by Task 5 and Task 6 command expectations.

Type consistency:

- `ScenarioTurn.assertions` is a `dict[str, Any]` consumed directly by `evaluate_assertions`.
- `LiveE2EClient.chat()` and `.stream()` both return `HTTPResult`.
- `evaluate_assertions()` returns `TurnResult`; report writers accept `list[TurnResult]`.
- `run_model()` returns `list[TurnResult]`; CLI writes combined model reports.

Scope:

- The plan does not add a new RAG chain.
- The plan does not modify ordinary pytest behavior.
- The final live run is explicit and slow by design.
- The implementation uses only Python stdlib plus existing project dependencies.
