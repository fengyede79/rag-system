# Conservative Non-RAG Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep any query with recoverable recipe intent on the RAG path, and only route clearly non-recipe queries to a polite non-RAG reply.

**Architecture:** Tighten guardrail classification so recipe signals always win over noisy or adversarial tokens. Add regression tests first for polluted recipe queries and pure off-topic queries, then rerun the evaluation suite and inspect how many failures remain.

**Tech Stack:** Python, pytest, existing RAG routing in `rag_modules/generation_integration.py`, evaluation runner in `evaluation/run_evaluation.py`

---

### Task 1: Lock Down Guardrail Expectations With Tests

**Files:**
- Modify: `E:/rag/my-rag/code/C8/tests/test_query_guardrails.py`
- Test: `E:/rag/my-rag/code/C8/tests/test_query_guardrails.py`

- [ ] **Step 1: Write the failing test**

```python
def test_recipe_signal_overrides_polluted_or_mixed_tokens():
    module = _module()

    assert module._classify_query_guardrail("用铁钉怎么炒蛋炒饭") is None
    assert module._classify_query_guardrail("蛋炒饭里放螺丝可以吗") is None
    assert module._classify_query_guardrail("推荐个早餐，顺便告诉我怎么修玻璃") is None


def test_only_clearly_non_recipe_queries_route_to_polite_feedback():
    module = _module()

    assert module._classify_query_guardrail("你怎么回答这么快") == "out_of_domain"
    assert module._classify_query_guardrail("今天天气怎么样") == "out_of_domain"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q E:/rag/my-rag/code/C8/tests/test_query_guardrails.py`
Expected: FAIL because current guardrail logic still classifies mixed polluted cases too aggressively or does not classify pure non-recipe chat.

- [ ] **Step 3: Write minimal implementation**

```python
# In _classify_query_guardrail(...)
recipe_signal_terms = [...]
chat_signal_terms = [...]

if any(term in normalized_query for term in recipe_signal_terms):
    return None

if any(term in normalized_query for term in chat_signal_terms):
    return "out_of_domain"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q E:/rag/my-rag/code/C8/tests/test_query_guardrails.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add E:/rag/my-rag/code/C8/tests/test_query_guardrails.py E:/rag/my-rag/code/C8/rag_modules/generation_integration.py
git commit -m "test: lock conservative non-rag routing behavior"
```

### Task 2: Implement Conservative Guardrail Routing

**Files:**
- Modify: `E:/rag/my-rag/code/C8/rag_modules/generation_integration.py`
- Test: `E:/rag/my-rag/code/C8/tests/test_query_guardrails.py`

- [ ] **Step 1: Write the failing test**

```python
def test_polite_feedback_answer_invites_recipe_follow_up():
    module = _module()

    answer = module.build_guardrail_answer("你怎么回答这么快", "out_of_domain")

    assert "继续" in answer
    assert "做菜" in answer or "食谱" in answer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -q E:/rag/my-rag/code/C8/tests/test_query_guardrails.py::test_polite_feedback_answer_invites_recipe_follow_up`
Expected: FAIL if the current fallback wording does not consistently include the desired polite redirection.

- [ ] **Step 3: Write minimal implementation**

```python
if reason == "out_of_domain":
    return (
        "这个问题不属于当前食谱知识库适合直接回答的范围。"
        "如果你愿意，我可以继续帮你处理做菜、食材、步骤或菜品推荐相关的问题。"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest -q E:/rag/my-rag/code/C8/tests/test_query_guardrails.py::test_polite_feedback_answer_invites_recipe_follow_up`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add E:/rag/my-rag/code/C8/rag_modules/generation_integration.py E:/rag/my-rag/code/C8/tests/test_query_guardrails.py
git commit -m "feat: add conservative non-rag routing"
```

### Task 3: Re-run Evaluation And Inspect Pollution Impact

**Files:**
- Read: `E:/rag/my-rag/code/C8/evaluation/latest_report.json`

- [ ] **Step 1: Run focused regression tests**

Run: `pytest -q E:/rag/my-rag/code/C8/tests/test_query_guardrails.py E:/rag/my-rag/code/C8/tests/test_conversation_state.py E:/rag/my-rag/code/C8/tests/test_structured_generation.py`
Expected: PASS

- [ ] **Step 2: Run evaluation**

Run: `python -c "from evaluation.run_evaluation import run_evaluation; run_evaluation()" `
Expected: Evaluation completes and refreshes `E:/rag/my-rag/code/C8/evaluation/latest_report.json`

- [ ] **Step 3: Inspect pass rate and remaining failures**

Run: `python - <<'PY'
import json, pathlib
report = json.loads(pathlib.Path(r'E:/rag/my-rag/code/C8/evaluation/latest_report.json').read_text(encoding='utf-8'))
print(report['summary']['pass_rate'])
print(report['summary']['passed_turns'], report['summary']['failed_turns'])
for item in report['failed_turns'][:10]:
    print(item.get('scenario_type'), item.get('question'), item.get('expected_keywords'))
PY`
Expected: Concrete pass rate plus a short list of remaining failures to judge whether pollution handling helped.

- [ ] **Step 4: Summarize pollution-related outcomes**

Report:
- How many clearly off-topic queries now go to polite feedback
- Whether polluted recipe queries still reach RAG
- Updated evaluation pass rate

- [ ] **Step 5: Commit**

```bash
git add E:/rag/my-rag/code/C8/rag_modules/generation_integration.py E:/rag/my-rag/code/C8/tests/test_query_guardrails.py E:/rag/my-rag/code/C8/evaluation/latest_report.json
git commit -m "chore: refresh evaluation after conservative routing update"
```
