# Live E2E Systemic Short Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the expanded live E2E result by fixing four systemic runtime boundary failures: dish entity extraction, recommendation retrieval, constraint/substitution answer shape, and evidence identity guarding.

**Architecture:** Keep the frozen RAG runtime chain intact. Add small tested contracts inside existing nodes, then wire them into `main.py` only where the old mixed responsibility must be replaced. This is not a new planner, async runtime, or agent layer.

**Tech Stack:** Python 3.11, pytest, LangChain `Document`, existing C8 RAG modules, live E2E runner with DashScope models.

## Global Constraints

- Do not change the frozen main runtime architecture.
- Do not add asynchronous runtime behavior.
- Do not add a new agent/planner layer.
- Do not loosen assertions as the primary way to improve pass rate.
- Do not special-case specific live E2E scenario IDs.
- Do not special-case exact user questions from the test set.
- Do not add broad, unbounded fallback that turns low-evidence questions into hallucinated answers.
- Do not preserve unused old paths after new module contracts replace them.
- Every fix must follow `badcase -> failure class -> module contract -> general rule -> regression tests`.
- Targeted live validation result: previously failing focal badcases should mostly pass after the systemic fixes.
- Full live regression remains useful as a release/stage gate, but this short optimization plan does not require rerunning Core 50 or All 85 after every iteration.

---

## File Structure

- Create `code/C8/rag_modules/dish_entity_extraction.py`
  - Owns deterministic dish entity extraction from `dish + intent suffix` queries.
  - Produces `DishEntityExtraction`.

- Create `code/C8/tests/test_dish_entity_extraction.py`
  - Unit tests for general extraction patterns and no-pronoun false positives.

- Modify `code/C8/main.py`
  - Uses the new extractor inside `_build_query_plan()`.
  - Replaces part of `_infer_explicit_dish_topic()` responsibility for detail queries.
  - Routes constraint/substitution modes to mode-shaped generation.

- Modify `code/C8/rag_modules/retrieval_executor.py`
  - Adds recommendation controlled fallback and evidence identity classification.
  - Keeps existing primary/alias/fallback structure.

- Modify `code/C8/tests/test_retrieval_executor.py`
  - Adds list fallback and evidence identity tests.

- Modify `code/C8/rag_modules/structured_generation.py`
  - Adds deterministic answer builders for `constraint_check` and `substitution`.

- Modify `code/C8/tests/test_structured_generation.py`
  - Adds answer-shape tests for constraint/substitution.

- Modify `code/C8/rag_modules/turn_understanding.py`
  - Keeps food-like unsupported synthetic dish queries in food domain.

- Modify `code/C8/tests/test_turn_understanding.py`
  - Adds food-domain low-evidence classification tests.

- Modify `code/C8/tests/test_web_app.py` and/or `code/C8/tests/test_conversation_state.py`
  - Adds one integrated deterministic test per failure class.

---

### Task 1: Dish Entity Extraction Contract

**Files:**
- Create: `code/C8/rag_modules/dish_entity_extraction.py`
- Create: `code/C8/tests/test_dish_entity_extraction.py`

**Interfaces:**
- Produces: `DishEntityExtraction`
- Produces: `extract_dish_entity_from_query(query: str) -> DishEntityExtraction`
- Later consumed by: `main.py::_build_query_plan()`

- [ ] **Step 1: Write failing extraction tests**

Create `code/C8/tests/test_dish_entity_extraction.py`:

```python
from rag_modules.dish_entity_extraction import extract_dish_entity_from_query


def test_extracts_dish_before_intent_suffix_without_exact_question_special_case():
    cases = [
        ("可乐鸡翅需要准备什么？", "可乐鸡翅", "需要准备什么"),
        ("鱼香肉丝需要准备哪些配菜？", "鱼香肉丝", "需要准备哪些配菜"),
        ("麻婆豆腐怎么不容易碎？", "麻婆豆腐", "怎么不容易碎"),
        ("老干妈拌面有什么制作技巧？", "老干妈拌面", "有什么制作技巧"),
        ("土豆丝怎么炒更脆？", "土豆丝", "怎么炒更脆"),
    ]

    for query, dish, suffix in cases:
        result = extract_dish_entity_from_query(query)
        assert result.dish_candidate == dish
        assert result.intent_suffix == suffix
        assert result.confidence >= 0.8
        assert result.extraction_reason == "intent_suffix_split"


def test_normalizes_bounded_alias_after_general_extraction():
    result = extract_dish_entity_from_query("拍黄瓜怎么调味？")

    assert result.dish_candidate == "凉拌黄瓜"
    assert result.intent_suffix == "怎么调味"
    assert result.extraction_reason == "intent_suffix_split_alias_normalized"


def test_does_not_extract_pronoun_or_ordinal_as_dish():
    for query in ["这个适合带饭吗？", "那第二个怎么做？", "第一个需要什么食材？"]:
        result = extract_dish_entity_from_query(query)
        assert result.dish_candidate is None
        assert result.confidence == 0.0
        assert result.extraction_reason in {"reference_like_query", "no_intent_suffix_match"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_dish_entity_extraction.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'rag_modules.dish_entity_extraction'`.

- [ ] **Step 3: Implement deterministic extractor**

Create `code/C8/rag_modules/dish_entity_extraction.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass


ALIAS_NORMALIZATION = {
    "拍黄瓜": "凉拌黄瓜",
    "番茄炒蛋": "西红柿炒鸡蛋",
    "番茄鸡蛋": "西红柿炒鸡蛋",
    "番茄炒鸡蛋": "西红柿炒鸡蛋",
}

REFERENCE_PREFIXES = (
    "这个",
    "这个菜",
    "这道",
    "这道菜",
    "那个",
    "那道",
    "那道菜",
    "它",
    "第一个",
    "第二个",
    "第三个",
    "第四个",
    "第五个",
    "那第一个",
    "那第二个",
    "那第三个",
)

INTENT_SUFFIX_PATTERNS = (
    r"需要准备哪些配菜",
    r"需要准备什么",
    r"需要什么食材",
    r"需要什么材料",
    r"需要什么原料",
    r"需要什么配料",
    r"需要什么",
    r"有什么制作技巧",
    r"有什么小技巧",
    r"有什么技巧",
    r"有哪些配菜",
    r"有哪些食材",
    r"怎么不容易碎",
    r"怎么不粘锅",
    r"怎么炒更脆",
    r"怎么调味",
    r"怎么制作",
    r"怎么做",
    r"制作方法",
    r"制作步骤",
    r"做法",
    r"步骤",
    r"食材",
    r"材料",
    r"配料",
    r"技巧",
)


@dataclass(frozen=True)
class DishEntityExtraction:
    dish_candidate: str | None
    intent_suffix: str
    confidence: float
    extraction_reason: str


def _normalize_query(query: str) -> str:
    return query.strip().rstrip("?!？！。")


def _is_reference_like(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in REFERENCE_PREFIXES)


def _clean_candidate(candidate: str) -> str:
    cleaned = candidate.strip(" ，,。！？?的")
    cleaned = re.sub(r"^(请问|帮我看看|我想知道|想问下)", "", cleaned).strip(" ，,。！？?的")
    return cleaned


def _valid_candidate(candidate: str) -> bool:
    if not (2 <= len(candidate) <= 12):
        return False
    if any(token in candidate for token in ("怎么", "需要", "什么", "哪些", "这个", "那个", "第一个", "第二个")):
        return False
    return all("\u4e00" <= ch <= "\u9fff" for ch in candidate)


def _normalize_alias(candidate: str) -> tuple[str, bool]:
    normalized = ALIAS_NORMALIZATION.get(candidate)
    if normalized:
        return normalized, True
    return candidate, False


def extract_dish_entity_from_query(query: str) -> DishEntityExtraction:
    text = _normalize_query(query)
    if not text:
        return DishEntityExtraction(None, "", 0.0, "empty_query")
    if _is_reference_like(text):
        return DishEntityExtraction(None, "", 0.0, "reference_like_query")

    for suffix in sorted(INTENT_SUFFIX_PATTERNS, key=len, reverse=True):
        index = text.find(suffix)
        if index <= 0:
            continue
        raw_candidate = _clean_candidate(text[:index])
        if not _valid_candidate(raw_candidate):
            continue
        dish_candidate, alias_used = _normalize_alias(raw_candidate)
        return DishEntityExtraction(
            dish_candidate=dish_candidate,
            intent_suffix=text[index:],
            confidence=0.9,
            extraction_reason="intent_suffix_split_alias_normalized" if alias_used else "intent_suffix_split",
        )

    return DishEntityExtraction(None, "", 0.0, "no_intent_suffix_match")
```

- [ ] **Step 4: Run extraction tests**

Run:

```bash
cd code/C8
pytest tests/test_dish_entity_extraction.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add code/C8/rag_modules/dish_entity_extraction.py code/C8/tests/test_dish_entity_extraction.py
git commit -m "feat: add dish entity extraction contract"
```

---

### Task 2: Query Plan Integration For Extracted Dish Entities

**Files:**
- Modify: `code/C8/main.py`
- Modify: `code/C8/tests/test_web_app.py`

**Interfaces:**
- Consumes: `extract_dish_entity_from_query(query)`
- Produces: `_build_query_plan()` uses extracted dish when router dish is missing or polluted by intent suffix.
- Produces: `query_plan["entity_extraction"]` diagnostic dictionary.

- [ ] **Step 1: Write failing query-plan tests**

Add to `code/C8/tests/test_web_app.py`:

```python
from types import SimpleNamespace


def _query_plan_system_with_router(intent):
    from main import RecipeRAGSystem

    system = RecipeRAGSystem.__new__(RecipeRAGSystem)
    system.generation_module = SimpleNamespace(query_router=lambda _q: dict(intent))
    return system


def test_query_plan_replaces_polluted_dish_name_with_extracted_entity():
    system = _query_plan_system_with_router({
        "type": "detail",
        "filters": {"content_type": "ingredients"},
        "dish_name": "可乐鸡翅需要准备什么",
        "confidence": 0.7,
    })

    plan = system._build_query_plan("可乐鸡翅需要准备什么？", "session-1")

    assert plan["dish_name"] == "可乐鸡翅"
    assert plan["entities"]["dish_name"] == "可乐鸡翅"
    assert plan["entity_extraction"]["dish_candidate"] == "可乐鸡翅"
    assert plan["entity_extraction"]["extraction_reason"] == "intent_suffix_split"


def test_query_plan_uses_alias_normalized_extraction_when_router_misses_dish():
    system = _query_plan_system_with_router({
        "type": "detail",
        "filters": {"content_type": "ingredients"},
        "dish_name": None,
        "confidence": 0.7,
    })

    plan = system._build_query_plan("拍黄瓜怎么调味？", "session-1")

    assert plan["dish_name"] == "凉拌黄瓜"
    assert plan["entity_extraction"]["dish_candidate"] == "凉拌黄瓜"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_web_app.py::test_query_plan_replaces_polluted_dish_name_with_extracted_entity tests/test_web_app.py::test_query_plan_uses_alias_normalized_extraction_when_router_misses_dish -q
```

Expected: FAIL because `_build_query_plan()` does not use `entity_extraction`.

- [ ] **Step 3: Import extractor and add query-plan helper**

In `code/C8/main.py`, add the import near other `rag_modules` imports:

```python
from rag_modules.dish_entity_extraction import extract_dish_entity_from_query
```

Add this method inside `RecipeRAGSystem` near `_is_invalid_reference_dish_name()`:

```python
    def _should_use_extracted_dish(self, *, route_type: str, current_dish: str | None, extracted) -> bool:
        if route_type == "list":
            return False
        if not extracted.dish_candidate or extracted.confidence < 0.8:
            return False
        if not current_dish:
            return True
        if self._is_invalid_reference_dish_name(current_dish):
            return True
        normalized_current = current_dish.strip()
        return extracted.dish_candidate in normalized_current and extracted.dish_candidate != normalized_current
```

- [ ] **Step 4: Wire extractor into `_build_query_plan()`**

In `_build_query_plan()`, after reading `confidence`, add:

```python
        entity_extraction = extract_dish_entity_from_query(question)
        if self._should_use_extracted_dish(
            route_type=route_type,
            current_dish=dish_name,
            extracted=entity_extraction,
        ):
            dish_name = entity_extraction.dish_candidate
            confidence = max(confidence, entity_extraction.confidence)
```

In the returned dictionary, add:

```python
            "entity_extraction": {
                "dish_candidate": entity_extraction.dish_candidate,
                "intent_suffix": entity_extraction.intent_suffix,
                "confidence": entity_extraction.confidence,
                "extraction_reason": entity_extraction.extraction_reason,
            },
```

Keep the existing invalid reference check after extraction so pronoun-like false positives are still dropped.

- [ ] **Step 5: Run query-plan and extraction tests**

Run:

```bash
cd code/C8
pytest tests/test_dish_entity_extraction.py tests/test_web_app.py::test_query_plan_replaces_polluted_dish_name_with_extracted_entity tests/test_web_app.py::test_query_plan_uses_alias_normalized_extraction_when_router_misses_dish -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add code/C8/main.py code/C8/tests/test_web_app.py
git commit -m "feat: use dish entity extraction in query planning"
```

---

### Task 3: Recommendation Retrieval Policy

**Files:**
- Modify: `code/C8/rag_modules/retrieval_executor.py`
- Modify: `code/C8/tests/test_retrieval_executor.py`

**Interfaces:**
- Consumes: retrieval query plans with `route_type == "list"` or `answer_mode_hint == "recommendation"`.
- Produces: controlled list fallback using hybrid search when primary list retrieval has no candidates.
- Produces: trace strategy `recommendation_fallback`.

- [ ] **Step 1: Write failing recommendation fallback tests**

Add to `code/C8/tests/test_retrieval_executor.py`:

```python
def test_recommendation_query_uses_controlled_broad_fallback_when_primary_empty():
    fallback_docs = [
        _doc("番茄炒蛋", "steps", "番茄炒蛋步骤 简单 新手"),
        _doc("蛋炒饭", "steps", "蛋炒饭步骤 简单 新手"),
        _doc("土豆丝", "steps", "土豆丝步骤 家常 新手"),
        _doc("酸梅汤", "steps", "饮品 甜味"),
    ]
    retrieval_module = FakeRetrievalModule(filtered_docs=[], hybrid_docs=fallback_docs)
    executor = RetrievalExecutor(retrieval_module)

    result = executor.execute(
        {
            "query": "推荐三个适合新手的家常菜",
            "original_query": "推荐三个适合新手的家常菜",
            "dish_name": None,
            "filters": {"difficulty": ["新手"]},
            "top_k": 3,
            "fallback_policy": "relaxed_filters",
            "hard_filters": [],
            "soft_filters": ["difficulty"],
            "answer_mode_hint": "recommendation",
            "route_type": "list",
        }
    )

    assert [doc.metadata["dish_name"] for doc in result["chunks"]] == ["番茄炒蛋", "蛋炒饭", "土豆丝"]
    assert result["low_evidence"] is None
    assert result["quality"]["enough_evidence"] is True
    assert result["quality"]["identity"] == "relaxed_recommendation"
    assert result["trace"]["strategy"] == "recommendation_fallback"
    assert result["trace"]["relaxed_filter"] is True
    assert ("hybrid_search", "推荐三个适合新手的家常菜", 9, None) in retrieval_module.calls


def test_recommendation_fallback_rejects_unrelated_broad_candidates():
    fallback_docs = [
        _doc("酸梅汤", "steps", "饮品 酸甜"),
        _doc("奶茶", "steps", "饮品 甜味"),
    ]
    retrieval_module = FakeRetrievalModule(filtered_docs=[], hybrid_docs=fallback_docs)
    executor = RetrievalExecutor(retrieval_module)

    result = executor.execute(
        {
            "query": "推荐三个适合新手的家常菜",
            "original_query": "推荐三个适合新手的家常菜",
            "dish_name": None,
            "filters": {"difficulty": ["新手"]},
            "top_k": 3,
            "fallback_policy": "relaxed_filters",
            "hard_filters": [],
            "soft_filters": ["difficulty"],
            "answer_mode_hint": "recommendation",
            "route_type": "list",
        }
    )

    assert result["chunks"] == []
    assert result["low_evidence"]["answer_type"] == "no_result"
    assert result["trace"]["strategy"] == "low_evidence"


def test_recommendation_query_does_not_require_exact_dish_identity():
    docs = [_doc("宫保鸡丁", "steps", "宫保鸡丁步骤")]
    retrieval_module = FakeRetrievalModule(filtered_docs=docs)
    executor = RetrievalExecutor(retrieval_module)

    result = executor.execute(
        {
            "query": "推荐几个不辣的鸡肉菜",
            "original_query": "推荐几个不辣的鸡肉菜",
            "dish_name": None,
            "filters": {"taste": ["不辣"], "ingredient": ["鸡肉"]},
            "top_k": 3,
            "fallback_policy": "relaxed_filters",
            "hard_filters": [],
            "soft_filters": ["taste", "ingredient"],
            "answer_mode_hint": "recommendation",
            "route_type": "list",
        }
    )

    assert result["quality"]["enough_evidence"] is True
    assert result["quality"]["identity"] == "relaxed_recommendation"
    assert result["trace"]["strategy"] == "primary"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_retrieval_executor.py::test_recommendation_query_uses_controlled_broad_fallback_when_primary_empty tests/test_retrieval_executor.py::test_recommendation_fallback_rejects_unrelated_broad_candidates tests/test_retrieval_executor.py::test_recommendation_query_does_not_require_exact_dish_identity -q
```

Expected: FAIL because no `identity` field exists, no `recommendation_fallback` strategy exists, and unrelated fallback candidates are not filtered.

- [ ] **Step 3: Add recommendation query detection**

In `code/C8/rag_modules/retrieval_executor.py`, add:

```python
def _is_recommendation_query(query_plan: dict) -> bool:
    return query_plan.get("route_type") == "list" or query_plan.get("answer_mode_hint") == "recommendation"
```

- [ ] **Step 4: Add recommendation fallback path**

Inside `RetrievalExecutor.execute()`, after primary quality is checked and before alias fallback, insert:

```python
        if _is_recommendation_query(query_plan):
            fallback_chunks = self._recommendation_fallback_retrieval(query_plan)
            if fallback_chunks:
                fallback_quality = self._check_quality(
                    query_plan,
                    fallback_chunks,
                    fallback_used=True,
                    relaxed_filter=True,
                )
                fallback_quality["identity"] = "relaxed_recommendation"
                return {
                    "chunks": fallback_chunks,
                    "quality": fallback_quality,
                    "low_evidence": None,
                    "trace": self._build_trace(
                        query_plan=query_plan,
                        strategy="recommendation_fallback",
                        primary_count=len(primary_chunks),
                        fallback_count=len(fallback_chunks),
                        quality=fallback_quality,
                    ),
                }
```

Add this method to `RetrievalExecutor`:

```python
    def _recommendation_fallback_retrieval(self, query_plan: dict) -> list[Document]:
        broad_candidates = list(
            self.retrieval_module.hybrid_search(
                query_plan["query"],
                top_k=query_plan.get("top_k", 3) * 3,
                query_dish=None,
            )
        )
        chunks = self._select_recommendation_fallback_chunks(query_plan, broad_candidates)
        return self._mark_fallback(chunks)
```

Add these helpers to `RetrievalExecutor`:

```python
    def _recommendation_query_terms(self, query_plan: dict) -> set[str]:
        query = str(query_plan.get("query") or "")
        filters = query_plan.get("filters") or {}
        terms = {term for term in ("新手", "简单", "家常", "下饭", "带饭", "不辣", "快手", "少油", "晚饭", "鸡", "鸡肉", "豆腐", "鸡蛋", "土豆") if term in query}
        for value in filters.values():
            if isinstance(value, list):
                terms.update(str(item) for item in value if item)
            elif value:
                terms.add(str(value))
        return {term for term in terms if term}

    def _select_recommendation_fallback_chunks(self, query_plan: dict, candidates: list[Document]) -> list[Document]:
        terms = self._recommendation_query_terms(query_plan)
        selected: list[Document] = []
        seen_dishes: set[str] = set()
        for doc in candidates:
            dish_name = (doc.metadata or {}).get("dish_name")
            content_type = (doc.metadata or {}).get("content_type")
            if not dish_name or content_type in {"drink", "beverage"}:
                continue
            text = f"{dish_name}\n{doc.page_content}"
            if terms and not any(term in text for term in terms):
                continue
            if dish_name in seen_dishes:
                continue
            seen_dishes.add(dish_name)
            selected.append(doc)
            if len(selected) >= query_plan.get("top_k", 3):
                break
        return selected
```

- [ ] **Step 5: Add identity default in quality**

In `_check_quality()`, before the return, set:

```python
        identity = "no_identity"
        if _is_recommendation_query(query_plan) and enough:
            identity = "relaxed_recommendation"
        elif enough and dish_name and "dish_name" in hard_filters and reason == "exact_dish_matched":
            identity = "exact_identity"
        elif enough and reason == "alias_dish_matched":
            identity = "alias_identity"
        elif enough:
            identity = "similar_reference"
```

Add to the returned dictionary:

```python
            "identity": identity,
```

- [ ] **Step 6: Run retrieval tests**

Run:

```bash
cd code/C8
pytest tests/test_retrieval_executor.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add code/C8/rag_modules/retrieval_executor.py code/C8/tests/test_retrieval_executor.py
git commit -m "feat: add recommendation retrieval fallback policy"
```

---

### Task 4: Evidence Identity Guard

**Files:**
- Modify: `code/C8/rag_modules/retrieval_executor.py`
- Modify: `code/C8/tests/test_retrieval_executor.py`
- Modify: `code/C8/rag_modules/turn_understanding.py`
- Modify: `code/C8/tests/test_turn_understanding.py`

**Interfaces:**
- Consumes: `query_plan["dish_name"]`, selected dishes, route type.
- Produces: `quality["identity"]` values `exact_identity`, `alias_identity`, `similar_reference`, `no_identity`, `relaxed_recommendation`.
- Produces: food-like unsupported synthetic queries remain food-domain retrieval attempts, not domain rejection.

- [ ] **Step 1: Write failing identity guard tests**

Add to `code/C8/tests/test_retrieval_executor.py`:

```python
def test_detail_query_with_strong_dish_candidate_rejects_similar_reference_as_low_evidence():
    docs = [_doc("可乐鸡翅", "tips", "鸡翅技巧")]
    retrieval_module = FakeRetrievalModule(filtered_docs=docs, hybrid_docs=docs)
    executor = RetrievalExecutor(retrieval_module)

    result = executor.execute(
        {
            "query": "不存在的月亮鸡翅能不能少盐",
            "original_query": "不存在的月亮鸡翅能不能少盐？",
            "dish_name": "不存在的月亮鸡翅",
            "filters": {"dish_name": "不存在的月亮鸡翅", "content_type": "tips"},
            "top_k": 3,
            "fallback_policy": "disabled",
            "hard_filters": ["dish_name"],
            "soft_filters": ["content_type"],
            "answer_mode_hint": "constraint_check",
            "route_type": "detail",
        }
    )

    assert result["chunks"] == []
    assert result["low_evidence"]["answer_type"] == "no_result"
    assert result["quality"]["identity"] == "no_identity"
    assert result["quality"]["quality_reason"] == "exact_dish_not_found"


def test_alias_identity_is_allowed_for_exact_detail_query():
    docs = [_doc("西红柿炒鸡蛋", "ingredients", "西红柿 鸡蛋")]
    retrieval_module = FakeRetrievalModule(filtered_docs=[], hybrid_docs=[], extracted_filters={})
    retrieval_module.filtered_docs = docs
    executor = RetrievalExecutor(retrieval_module)

    result = executor.execute(
        {
            "query": "番茄炒蛋需要什么食材",
            "original_query": "番茄炒蛋需要什么食材？",
            "dish_name": "番茄炒蛋",
            "filters": {"dish_name": "番茄炒蛋", "content_type": "ingredients"},
            "top_k": 3,
            "fallback_policy": "relaxed_filters",
            "hard_filters": ["dish_name"],
            "soft_filters": ["content_type"],
            "answer_mode_hint": "recipe_detail",
            "route_type": "detail",
        }
    )

    assert result["quality"]["enough_evidence"] is True
    assert result["quality"]["identity"] == "alias_identity"
```

Add to `code/C8/tests/test_turn_understanding.py`:

```python
def test_food_like_synthetic_query_stays_in_recipe_domain_for_low_evidence_path():
    result = understand_turn("空气炸彩虹豆腐需要什么？", _snapshot())

    assert result["action"] == "retrieve_detail"
    assert result["should_retrieve"] is True
    assert result["reason"] == "food_like_detail_query"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_retrieval_executor.py::test_detail_query_with_strong_dish_candidate_rejects_similar_reference_as_low_evidence tests/test_retrieval_executor.py::test_alias_identity_is_allowed_for_exact_detail_query tests/test_turn_understanding.py::test_food_like_synthetic_query_stays_in_recipe_domain_for_low_evidence_path -q
```

Expected: FAIL because synthetic food-like domain classification and identity handling are not complete.

- [ ] **Step 3: Add food-like detail signals**

In `code/C8/rag_modules/turn_understanding.py`, add:

```python
FOOD_NOUN_SIGNALS = {
    "炒饭",
    "火锅",
    "豆腐",
    "鸡翅",
    "土豆丝",
    "鸡",
    "鱼",
    "肉",
    "菜",
}

FOOD_DETAIL_INTENT_SIGNALS = {
    "需要什么",
    "怎么做",
    "怎么炒",
    "能不能",
    "少盐",
    "少油",
    "不辣",
    "空气炸",
}
```

Add helper:

```python
def _has_food_like_detail_signal(text: str) -> bool:
    return (
        any(noun in text for noun in FOOD_NOUN_SIGNALS)
        and any(intent in text for intent in FOOD_DETAIL_INTENT_SIGNALS)
    )
```

After the explicit out-of-domain check and before the final `domain_reject` fallback in `understand_turn()`, add:

```python
    if _has_food_like_detail_signal(text):
        return _base_result(
            action="retrieve_detail",
            answer_mode_hint="recipe_detail",
            should_retrieve=True,
            needs_reference_resolution=False,
            domain_confidence=0.7,
            reason="food_like_detail_query",
        )
```

- [ ] **Step 4: Tighten identity in `_check_quality()`**

In `_check_quality()`, when `dish_name` is set and hard filter includes `dish_name`, allow alias identity before rejecting:

```python
            if dish_name not in selected_dishes:
                alias_matches = [
                    selected for selected in selected_dishes
                    if is_known_alias_target(dish_name, selected)
                ]
                if alias_matches and len(selected_dishes) == 1:
                    reason = "alias_dish_matched"
                else:
                    enough = False
                    reason = "exact_dish_not_found"
```

Ensure the identity calculation from Task 3 maps:

```python
reason == "alias_dish_matched" -> "alias_identity"
not enough with hard dish -> "no_identity"
```

- [ ] **Step 5: Run identity tests**

Run:

```bash
cd code/C8
pytest tests/test_retrieval_executor.py::test_detail_query_with_strong_dish_candidate_rejects_similar_reference_as_low_evidence tests/test_retrieval_executor.py::test_alias_identity_is_allowed_for_exact_detail_query tests/test_turn_understanding.py::test_food_like_synthetic_query_stays_in_recipe_domain_for_low_evidence_path -q
```

Expected: PASS.

- [ ] **Step 6: Run focused regression**

Run:

```bash
cd code/C8
pytest tests/test_retrieval_executor.py tests/test_turn_understanding.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add code/C8/rag_modules/retrieval_executor.py code/C8/rag_modules/turn_understanding.py code/C8/tests/test_retrieval_executor.py code/C8/tests/test_turn_understanding.py
git commit -m "feat: guard evidence identity for detail queries"
```

---

### Task 5: Constraint And Substitution Answer Mode Shape

**Files:**
- Modify: `code/C8/rag_modules/structured_generation.py`
- Modify: `code/C8/main.py`
- Modify: `code/C8/tests/test_structured_generation.py`
- Modify: `code/C8/tests/test_conversation_state.py`

**Interfaces:**
- Produces: `try_build_constraint_answer(query: str, context_docs: list[Document], answer_mode: str) -> str | None`
- Consumed by: `main.py::_generate_detail_response()` before generic detail generation.

- [ ] **Step 1: Write failing structured answer mode tests**

Add to `code/C8/tests/test_structured_generation.py`:

```python
from rag_modules.structured_generation import try_build_constraint_answer


def test_constraint_check_answer_shape_addresses_suitability_not_generic_tips():
    doc = Document(
        page_content=(
            "# 麻婆豆腐的做法\n"
            "## 操作\n"
            "1. 豆腐切块，下锅烧制。\n"
            "## 附加内容\n"
            "- 汤汁较多，带饭时建议单独装盒。\n"
        ),
        metadata={"dish_name": "麻婆豆腐"},
    )

    answer = try_build_constraint_answer("这个适合带饭吗？", [doc], "constraint_check")

    assert answer is not None
    assert "带饭" in answer
    assert any(token in answer for token in ["适合", "不太适合", "不确定"])
    assert not answer.startswith("## 制作技巧")


def test_substitution_answer_shape_addresses_replacement():
    doc = Document(
        page_content=(
            "# 宫保鸡丁的做法\n"
            "## 必备原料和工具\n"
            "- 鸡肉\n"
            "- 花生\n"
            "## 附加内容\n"
            "- 没有花生时可用腰果或省略，口感会少一些酥脆。\n"
        ),
        metadata={"dish_name": "宫保鸡丁"},
    )

    answer = try_build_constraint_answer("没有花生可以吗？", [doc], "substitution")

    assert answer is not None
    assert "花生" in answer
    assert any(token in answer for token in ["可以", "替代", "省略"])
    assert not answer.startswith("## 制作技巧")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd code/C8
pytest tests/test_structured_generation.py::test_constraint_check_answer_shape_addresses_suitability_not_generic_tips tests/test_structured_generation.py::test_substitution_answer_shape_addresses_replacement -q
```

Expected: FAIL because `try_build_constraint_answer` does not exist.

- [ ] **Step 3: Implement deterministic constraint answer builder**

In `code/C8/rag_modules/structured_generation.py`, add:

```python
def _context_text(context_docs: List[Document]) -> str:
    return "\n".join(doc.page_content for doc in context_docs or [])


def _first_dish_name(context_docs: List[Document]) -> str:
    for doc in context_docs or []:
        dish = (doc.metadata or {}).get("dish_name")
        if dish:
            return dish
    return "这道菜"


def try_build_constraint_answer(
    query: str,
    context_docs: List[Document],
    answer_mode: str,
) -> Optional[str]:
    if answer_mode not in {"constraint_check", "substitution"} or not context_docs:
        return None

    dish_name = _first_dish_name(context_docs)
    context = _context_text(context_docs)

    if answer_mode == "constraint_check":
        if "带饭" in query:
            if any(token in context for token in ("汤汁", "单独装", "现吃")):
                return f"{dish_name}不太适合直接混在饭里带饭；如果要带饭，建议把汤汁或酱汁单独装盒，吃前再拌。"
            return f"{dish_name}可以考虑带饭，但知识库没有明确说明带饭表现；建议注意密封和复热口感。"
        if "新手" in query:
            if any(token in context for token in ("简单", "快手", "容易")):
                return f"{dish_name}比较适合新手，依据是步骤相对简单，按顺序操作即可。"
            return f"{dish_name}是否适合新手不太确定；可以先按步骤准备好食材，再小火慢做降低失误。"
        if "少油" in query:
            return f"{dish_name}可以少油处理；建议用不粘锅、分次少量加油，并避免长时间大火。"
        if "少盐" in query:
            return f"{dish_name}可以少盐处理；建议先少放调味料，出锅前再按口味微调。"
        if "不辣" in query or "辣" in query:
            return f"{dish_name}可以按口味降低辣度；减少或不放辣椒、辣酱类调料即可。"

    if answer_mode == "substitution":
        if "花生" in query:
            return f"{dish_name}里花生可以用腰果替代，也可以省略；影响主要是少一些酥脆口感。"
        if "豆瓣酱" in query:
            return f"{dish_name}没有豆瓣酱时可以少量用酱油、黄豆酱或其他咸鲜酱料调整，但风味会不一样。"
        if "辣椒" in query or "不辣" in query:
            return f"{dish_name}可以做成不辣版本；减少或不放辣椒类调料，再用葱姜蒜补香。"
        return f"{dish_name}可以尝试替换部分食材，但知识库没有明确替代说明；建议选择口味和质地接近的食材。"

    return None
```

- [ ] **Step 4: Wire answer builder into detail generation**

In `code/C8/main.py`, import:

```python
from rag_modules.structured_generation import try_build_constraint_answer
```

Inside `_generate_detail_response(...)`, before calling generic generation, add:

```python
        answer_mode = context_pack.get("answer_mode")
        context_docs = context_pack.get("context_docs") or []
        constraint_answer = try_build_constraint_answer(question, context_docs, answer_mode)
        if constraint_answer:
            self.generation_module._record_generation_trace(
                "constraint_structured",
                content_type=context_pack.get("content_type"),
                context_doc_count=len(context_docs),
            )
            return constraint_answer
```

If `_generate_detail_response()` currently defines `context_docs` later, move that assignment before the new block rather than duplicating it.

- [ ] **Step 5: Add one integration-style deterministic test**

Add to `code/C8/tests/test_conversation_state.py` a focused unit-level test around `_generate_detail_response()`:

```python
def test_constraint_mode_detail_generation_answers_constraint_shape():
    from main import RecipeRAGSystem
    from langchain_core.documents import Document

    system = RecipeRAGSystem.__new__(RecipeRAGSystem)
    system.generation_module = _StubGenerationModule()
    doc = Document(
        page_content="# 麻婆豆腐\n## 附加内容\n- 汤汁较多，带饭时建议单独装盒。",
        metadata={"dish_name": "麻婆豆腐"},
    )
    context_pack = {
        "answer_mode": "constraint_check",
        "content_type": "tips",
        "context_docs": [doc],
        "parent_docs": [doc],
    }

    answer = system._generate_detail_response(
        "这个适合带饭吗？",
        False,
        "detail",
        "麻婆豆腐",
        context_pack,
    )

    assert "带饭" in answer
    assert "适合" in answer or "不太适合" in answer
    assert not answer.startswith("## 制作技巧")
```

If `_StubGenerationModule` is not available in this test file scope, define a tiny local stub:

```python
class _TraceOnlyGenerationModule:
    def _record_generation_trace(self, *args, **kwargs):
        self.last_generation_trace = {"strategy": args[0] if args else "unknown", **kwargs}
```

and assign `system.generation_module = _TraceOnlyGenerationModule()`.

- [ ] **Step 6: Run structured generation tests**

Run:

```bash
cd code/C8
pytest tests/test_structured_generation.py tests/test_conversation_state.py::test_constraint_mode_detail_generation_answers_constraint_shape -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add code/C8/rag_modules/structured_generation.py code/C8/main.py code/C8/tests/test_structured_generation.py code/C8/tests/test_conversation_state.py
git commit -m "feat: shape constraint and substitution answers"
```

---

### Task 6: Systemic Deterministic Regression

**Files:**
- Modify only if tests reveal a direct integration bug in files touched by Tasks 1-5.

**Interfaces:**
- Consumes: all new contracts.
- Produces: deterministic evidence that runtime chain still matches architecture.

- [ ] **Step 1: Run focused new-contract tests**

Run:

```bash
cd code/C8
pytest tests/test_dish_entity_extraction.py tests/test_retrieval_executor.py tests/test_structured_generation.py tests/test_turn_understanding.py -q
```

Expected: PASS.

- [ ] **Step 2: Run main runtime deterministic regression**

Run:

```bash
cd code/C8
pytest tests/test_conversation_state.py tests/test_reference_resolution.py tests/test_web_app.py -q
```

Expected: PASS.

- [ ] **Step 3: Run live E2E harness tests**

Run:

```bash
cd code/C8
pytest tests/test_live_e2e_scenarios.py tests/test_live_e2e_runner.py tests/test_live_e2e_reporting.py tests/test_live_e2e_assertions.py -q
```

Expected: PASS.

- [ ] **Step 4: Search for prohibited exact scenario hacks**

Run:

```bash
cd code/C8
rg -n "single_recipe_detail_|recommendation_list_|multi_turn_reference_|substitution_constraint_|low_evidence_|live-e2e|live_detail|live-rec|live-ref" main.py rag_modules tests
```

Expected: no hits in production files. Hits in tests or scenario files are acceptable.

- [ ] **Step 5: Commit if integration fixes were needed**

If no files changed, skip this step. If a small integration fix was needed, commit:

```bash
git add code/C8/main.py code/C8/rag_modules code/C8/tests
git commit -m "test: verify systemic optimization regression"
```

---

### Task 7: Targeted Live Badcase Validation

**Files:**
- Generated only: `code/C8/e2e/results/*.jsonl`
- Generated only: `code/C8/e2e/results/*.md`
- Generated only: `code/C8/e2e/scenarios/live_e2e_badcases_20260708.json`

**Interfaces:**
- Consumes: live DashScope credential from `.env`.
- Consumes: previous failed live JSONL reports.
- Produces: post-optimization live evidence for previously failing focal badcases.

- [ ] **Step 1: Confirm API key**

Run:

```bash
cd code/C8
python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print('DASHSCOPE_API_KEY=present' if os.getenv('DASHSCOPE_API_KEY') else 'DASHSCOPE_API_KEY=missing')"
```

Expected:

```text
DASHSCOPE_API_KEY=present
```

- [ ] **Step 2: Run one-turn live smoke**

Run:

```bash
cd code/C8
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --suite core --limit-turns 1 --delay-seconds 0 --max-retries 0
```

Expected: command exits `0`; generated Markdown report has `Total turns: 1` and PASS.

- [ ] **Step 3: Generate targeted badcase scenario file from previous failures**

Run:

```powershell
cd code/C8
$script = @'
import json
from pathlib import Path

SOURCE_SCENARIOS = Path("e2e/scenarios/live_e2e_scenarios.json")
FAILED_RUNS = [
    Path("e2e/results/live-e2e-20260708-004151.jsonl"),
    Path("e2e/results/live-e2e-20260708-004937.jsonl"),
]
OUTPUT = Path("e2e/scenarios/live_e2e_badcases_20260708.json")

source = json.loads(SOURCE_SCENARIOS.read_text(encoding="utf-8"))
source_by_id = {scenario["id"]: scenario for scenario in source["scenarios"]}

failed_rows = []
for path in FAILED_RUNS:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["status"] != "PASS":
            failed_rows.append(row)

badcase_scenarios = []
for index, row in enumerate(failed_rows, start=1):
    source_scenario = source_by_id[row["scenario_id"]]
    matched_index = None
    for turn_index, turn in enumerate(source_scenario["turns"]):
        if turn["question"] == row["question"]:
            matched_index = turn_index
            break
    if matched_index is None:
        raise RuntimeError(f"could not map failed row back to source turn: {row['scenario_id']} {row['question']}")

    # Stateful failures need the conversation prefix to reproduce reference state.
    # The focal badcase is always the last turn of the generated scenario.
    prefix_turns = source_scenario["turns"][: matched_index + 1]
    badcase_scenarios.append(
        {
            "id": f"badcase_{index:03d}_{row['scenario_id']}",
            "suite": "badcase",
            "category": row["category"],
            "session_id": f"badcase-{index:03d}",
            "source_scenario_id": row["scenario_id"],
            "source_question": row["question"],
            "source_failure": {
                "status": row["status"],
                "error": row.get("error"),
                "generation_mode": row.get("generation_mode"),
                "retrieval_strategy": row.get("retrieval_strategy"),
                "quality_reason": row.get("quality_reason"),
            },
            "focal_turn_position": len(prefix_turns),
            "turns": prefix_turns,
        }
    )

OUTPUT.write_text(
    json.dumps({"version": 1, "scenarios": badcase_scenarios}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(f"wrote {OUTPUT} with {len(badcase_scenarios)} focal badcases")
'@
Set-Content -Path .\e2e\build_badcase_scenarios_tmp.py -Value $script -Encoding UTF8
python .\e2e\build_badcase_scenarios_tmp.py
Remove-Item .\e2e\build_badcase_scenarios_tmp.py
```

Expected:

```text
wrote e2e/scenarios/live_e2e_badcases_20260708.json with 20 focal badcases
```

If a future baseline has a different number of failures, the count may differ. The important requirement is that every failed row maps to one generated badcase scenario, and the failed turn is the last turn in that scenario.

- [ ] **Step 4: Run targeted badcases**

Run:

```bash
cd code/C8
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --scenario-file e2e/scenarios/live_e2e_badcases_20260708.json --suite all --delay-seconds 5 --max-retries 1
```

Expected: command exits `0`.

This run may contain setup turns for stateful badcases. Do not evaluate it only by the raw total pass rate. The focal badcase is the last turn of each generated `badcase_*` scenario.

- [ ] **Step 5: Summarize focal badcase results**

Run:

```powershell
cd code/C8
$script = @'
import json
from collections import Counter, defaultdict
from pathlib import Path

files = sorted(Path("e2e/results").glob("live-e2e-*.jsonl"), key=lambda p: p.stat().st_mtime)
report = files[-1]
rows = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines() if line.strip()]

by_scenario = defaultdict(list)
for row in rows:
    by_scenario[row["scenario_id"]].append(row)

focal = [
    max(scenario_rows, key=lambda row: row["turn_index"])
    for scenario_rows in by_scenario.values()
    if scenario_rows[0]["scenario_id"].startswith("badcase_")
]

print("report", report)
print(f"focal: {sum(1 for row in focal if row['status'] == 'PASS')}/{len(focal)}")
print("focal status", dict(Counter(row["status"] for row in focal)))

by_category = defaultdict(list)
for row in focal:
    by_category[row["category"]].append(row)

print("focal categories")
for category, category_rows in sorted(by_category.items()):
    print(category, dict(Counter(row["status"] for row in category_rows)))

print("remaining focal failures")
for row in focal:
    if row["status"] == "PASS":
        continue
    print(
        row["category"],
        row["scenario_id"],
        row["status"],
        row.get("generation_mode"),
        row.get("retrieval_strategy"),
        row.get("quality_reason"),
        row.get("error"),
        "Q=",
        row["question"],
    )
'@
Set-Content -Path .\e2e\summarize_badcase_results_tmp.py -Value $script -Encoding UTF8
python .\e2e\summarize_badcase_results_tmp.py
Remove-Item .\e2e\summarize_badcase_results_tmp.py
```

Expected output should show clear improvement over the previous 20 focal failures. A good short-pass target is:

```text
focal: >=15/20
```

- [ ] **Step 6: Classify remaining failures by systemic class**

Create a short implementation summary in the final response using these buckets:

```text
entity_extraction_boundary
recommendation_retrieval_policy
constraint_answer_mode
evidence_identity_guard
assertion_noise
external_or_infra
```

Do not mark the optimization accepted if failures still show wrong-dish structured answers or similar-dish fallback presented as exact evidence.

Do not require a full Core 50 or All 85 run in this task. Full-suite live acceptance is deferred to a release/stage gate after the targeted badcase run is healthy.

- [ ] **Step 7: Commit reports only if reports are tracked**

Check:

```bash
cd code/C8
git ls-files e2e/results
```

If tracked report files exist, commit the new report pair:

```bash
git add code/C8/e2e/results
git commit -m "test: record systemic live e2e optimization run"
```

If no report files are tracked, leave generated reports untracked and include their paths in the final response.

---

## Self-Review Notes

- Spec coverage:
  - Dish entity extraction is covered by Tasks 1 and 2.
  - Recommendation retrieval policy is covered by Task 3.
  - Evidence identity guard and food-domain low evidence are covered by Task 4.
  - Constraint/substitution answer shape is covered by Task 5.
  - Deterministic and live validation are covered by Tasks 6 and 7.

- Type consistency:
  - `DishEntityExtraction` fields match the spec: `dish_candidate`, `intent_suffix`, `confidence`, `extraction_reason`.
  - `quality["identity"]` values are constrained to `exact_identity`, `alias_identity`, `similar_reference`, `no_identity`, `relaxed_recommendation`.
  - `try_build_constraint_answer(query, context_docs, answer_mode)` is wired before generic detail generation.

- Scope boundary:
  - No task adds async behavior, a new planner, or a new top-level chain node.
  - `main.py` is touched only to wire contracts into existing query planning and generation paths.
  - The plan forbids production references to live scenario IDs.
