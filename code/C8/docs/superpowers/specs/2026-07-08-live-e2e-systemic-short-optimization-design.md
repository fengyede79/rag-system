# Live E2E Systemic Short Optimization Design

Status: draft spec
Owner: C8 recipe RAG system
Date: 2026-07-08

## Purpose

This spec defines a short, systemic optimization pass after the expanded live E2E run.

The live 85-turn result exposed real failure classes:

```text
Core:      42/50
Extended:  23/35
Total:     65/85
```

The goal is not to adapt to individual test cases. The goal is to use those failures as representatives of broader runtime boundary problems, then fix the smallest general mechanisms that improve the system without changing the frozen main architecture.

The optimization target is:

```text
Total: approximately 75/85 or better
Core:  at least 45/50
```

This is a short optimization pass, not a new architecture stage.

## Non-Goals

This spec must not:

- change the frozen main runtime architecture;
- add asynchronous runtime behavior;
- add a new agent/planner layer;
- loosen assertions as the primary way to improve pass rate;
- special-case specific live E2E scenario IDs;
- special-case exact user questions from the test set;
- add broad, unbounded fallback that turns low-evidence questions into hallucinated answers;
- preserve unused old paths after new module contracts replace them.

## Guiding Rule

Every fix must follow this chain:

```text
badcase -> failure class -> module contract -> general rule -> regression tests
```

The forbidden chain is:

```text
badcase -> exact phrase rule -> pass this one case
```

Concrete live failures may be used as representative examples in tests, but the implemented rule must apply to the class of problem, not only to that example.

## Observed Failure Classes

### 1. Entity Extraction Boundary Failure

Representative symptoms:

```text
可乐鸡翅需要准备什么？ -> dish_name became "可乐鸡翅需要准备什么"
拍黄瓜怎么调味？ -> dish entity was dropped or not normalized
鱼香肉丝需要准备哪些配菜？ -> dish entity was not stably extracted
```

The failure class is:

```text
query contains dish-like entity + intent suffix, but query planning either keeps too much text as dish_name or discards the dish entity entirely.
```

This is not a retrieval-only issue. Bad entity extraction creates bad filters, and bad filters force retrieval into low evidence or wrong-dish context.

### 2. Recommendation Retrieval Policy Failure

Representative symptoms:

```text
推荐三个适合新手的菜 -> no_context
晚饭想吃下饭菜，有什么推荐？ -> no_context
推荐几个下饭但不太辣的菜 -> no_context
```

The failure class is:

```text
list/recommendation queries are evaluated with detail-query retrieval assumptions.
```

Recommendation queries often use soft preference words rather than exact dish names. They need broad-but-controlled retrieval and scoring, not strict dish evidence.

### 3. Constraint Answer Mode Failure

Representative symptoms:

```text
这个适合带饭吗？ -> returned generic tips section
这个适合新手吗？ -> low evidence or generic recipe detail
能少油一点吗？ -> may answer with recipe section instead of adjustment guidance
```

The failure class is:

```text
constraint_check/substitution intent exists in turn understanding, but generation falls back to recipe_detail/tips shape.
```

The answer mode is not just a label. It must control answer shape.

### 4. Evidence Identity Guard Failure

Representative symptoms:

```text
不存在的月亮鸡翅能不能少盐？ -> fallback used real chicken wing recipes as if they answered the fake dish
空气炸彩虹豆腐需要什么？ -> domain rejection instead of food-domain low evidence
```

The failure class is:

```text
synthetic or unsupported dish-like queries are either rejected as non-domain or answered from loosely similar real dishes without enough identity evidence.
```

The system must distinguish:

```text
no_result
similar_reference
relaxed_recommendation
```

These are not the same answer type.

## Design Overview

This optimization adds four small contracts:

```text
Dish Entity Extraction Contract
Recommendation Retrieval Policy
Constraint/Substitution Answer Mode Contract
Evidence Identity Guard
```

They fit inside the existing chain:

```text
Turn Understanding
-> Query Plan
-> Retrieval Executor
-> Context Pack
-> Answer Mode Generation
-> StateUpdatePolicy
```

No new top-level architecture node is added. Each change clarifies an existing node's responsibilities.

## Contract 1: Dish Entity Extraction

### Responsibility

Extract a likely dish entity from a detail query without confusing the dish entity with the intent suffix.

### Interface

Introduce a small, deterministic helper:

```python
@dataclass(frozen=True)
class DishEntityExtraction:
    dish_candidate: str | None
    intent_suffix: str
    confidence: float
    extraction_reason: str
```

Suggested function:

```python
def extract_dish_entity_from_query(query: str) -> DishEntityExtraction:
    ...
```

### General Rules

The extractor should handle patterns such as:

```text
X怎么做
X需要什么
X需要什么食材
X需要准备哪些配菜
X怎么调味
X有什么技巧
X怎么不容易碎
X怎么不粘锅
```

It should split on intent triggers, not on a fixed dish-name allowlist.

It may use the existing bounded alias table only for normalization after extraction:

```text
拍黄瓜 -> 凉拌黄瓜
番茄炒蛋 -> 西红柿炒鸡蛋
```

It must not add one-off rules for exact live E2E question strings.

### Query Plan Integration

`_build_query_plan()` should prefer this extraction result when:

```text
route_type == detail
and existing router dish_name is missing, invalid, or contains intent suffix text
```

If extraction confidence is low, the query plan may leave `dish_name=None` rather than inventing a hard filter.

### Success Criteria

The system should avoid these states:

```text
dish_name == "可乐鸡翅需要准备什么"
dish_name == "鱼香肉丝需要准备哪些配菜"
dish_name == "这个适合带饭吗"
```

The system should prefer:

```text
dish_name == "可乐鸡翅"
dish_name == "鱼香肉丝"
dish_name == None for pure pronoun followup before reference resolution
```

## Contract 2: Recommendation Retrieval Policy

### Responsibility

Treat recommendation/list retrieval as a candidate discovery task, not as exact evidence retrieval for one dish.

### Policy

For:

```text
route_type == list
or execution_plan.action == retrieve_list
```

retrieval should:

- avoid hard `dish_name` filters;
- treat preference words as soft scoring hints;
- allow controlled broad fallback when primary retrieval returns no candidates;
- return multiple candidate dishes when possible;
- mark fallback evidence explicitly.

### Soft Preference Hints

Supported first-pass hints:

```text
新手
简单
下饭
带饭
不辣
快手
少油
晚饭
鸡肉
豆腐
鸡蛋
土豆
```

These hints should not become strict metadata filters unless the data is known to contain reliable matching metadata.

### Controlled Fallback

If primary list retrieval has no candidates:

```text
primary list retrieval
-> if empty, controlled broad retrieval
-> score/trim candidates
-> mark relaxed_filter=true
```

Controlled broad retrieval must still be recipe-domain retrieval. It must not use unrelated content or generate dishes not present in retrieved evidence.

### Success Criteria

For list queries, a no-context answer should be reserved for true data absence. It should not be the default result for ordinary preference-based recommendation requests.

Recommendation answers should usually include at least two dishes when the user asks for several recommendations, unless evidence is truly limited and the answer says so.

## Contract 3: Constraint And Substitution Answer Mode

### Responsibility

Make `constraint_check` and `substitution` answer modes shape the response, rather than allowing generic recipe sections to answer constraint questions.

### Answer Modes

`constraint_check` must answer:

```text
适合 / 不适合 / 不确定
reason based on available recipe context
practical adjustment if useful
```

`substitution` must answer:

```text
can substitute / cannot safely substitute / uncertain
replacement suggestions
impact on taste or process
```

`modify_recipe` may be introduced only if needed as an internal label for:

```text
少油
少盐
少糖
不放辣椒
```

It should not become a new top-level architecture branch.

### Generation Rules

For constraint/substitution modes:

- do not return only a copied `tips` section;
- do not return only `为您推荐：X` when the user requested a constrained replacement;
- include the constraint term when possible;
- be conservative when context does not directly support the answer.

### Structured vs LLM Generation

Structured generation may still provide source material, but final answer shape should be controlled by the answer mode.

If the answer mode is `constraint_check`, a short deterministic template is acceptable:

```text
这道菜[适合/不太适合/不确定是否适合]带饭。依据是...
```

If evidence is weak:

```text
知识库没有明确说明它是否适合带饭，但从步骤/食材看...
```

### Success Criteria

Questions like:

```text
这个适合带饭吗？
这个适合新手吗？
能少油一点吗？
没有豆瓣酱可以吗？
换个不辣的豆腐菜
```

should answer the constraint, not merely return recipe steps or generic tips.

## Contract 4: Evidence Identity Guard

### Responsibility

Prevent weakly related fallback evidence from being presented as if it were evidence for a specific unsupported dish.

### Identity Categories

The retrieval result should distinguish:

```text
exact_identity
alias_identity
similar_reference
no_identity
```

Suggested meanings:

```text
exact_identity: selected dish matches requested dish
alias_identity: selected dish is a configured alias of requested dish
similar_reference: selected dish shares ingredient or style but is not the requested dish
no_identity: no credible dish identity match
```

### Policy

For detail queries with a strong dish candidate:

- exact or alias identity may answer normally;
- similar reference may answer only as reference, not as the requested dish;
- no identity should produce low evidence/no result;
- fallback should never silently erase the requested dish identity.

### Food-Domain Low Evidence

Food-like but unsupported queries should remain inside the food domain:

```text
空气炸彩虹豆腐需要什么？
银河火锅鸡怎么做？
不存在的月亮鸡翅能不能少盐？
```

They should not be answered as generic domain rejection unless the query is clearly non-food.

### Success Criteria

The system should prefer:

```text
知识库里没有找到「月亮鸡翅」的可靠食谱信息。
```

or:

```text
没有找到这道菜的可靠做法；如果你只是想参考鸡翅做法，可以看可乐鸡翅/烤鸡翅。
```

It should not present `可乐鸡翅` as the recipe for `月亮鸡翅`.

## Assertion Policy

Assertion tuning is allowed only after semantic behavior is correct.

Allowed assertion cleanup:

- reduce brittle exact wording;
- add reasonable synonym groups;
- lower `min_answer_chars` only when the answer is semantically correct but concise.

Forbidden assertion cleanup:

- lower thresholds to pass wrong answers;
- remove `answer_not_contains` checks that catch hallucinated confidence;
- count domain rejection as success for food-like unsupported dishes.

## Testing Strategy

### Unit Tests

Add focused tests for:

```text
dish entity extraction
list retrieval policy fallback
constraint answer mode shaping
evidence identity classification
food-domain low evidence
```

Each test should use representative examples, but assert the general contract.

### Regression Tests

Existing deterministic tests must continue to pass:

```text
tests/test_conversation_state.py
tests/test_reference_resolution.py
tests/test_web_app.py
tests/test_retrieval_executor.py
tests/test_turn_understanding.py
```

### Live Tests

After deterministic tests pass, run:

```bash
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --suite core --limit-turns 50 --delay-seconds 5 --max-retries 1
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --suite all --limit-turns 85 --delay-seconds 5 --max-retries 1
```

The live result should be evaluated by failure class, not only by total score.

## Acceptance Criteria

This optimization is accepted when:

```text
Core >= 45/50
Total >= 75/85
No increase in INFRA_ERROR
No increase in RATE_LIMITED unless provider-side throttling is visible
No regression in deterministic runtime tests
```

Additionally, the post-run failure report should show fewer failures in:

```text
low_evidence caused by ordinary recommendation queries
wrong-dish structured answers
constraint questions answered as generic tips
similar-dish fallback presented as exact evidence
```

## Implementation Boundary

Likely files:

```text
rag_modules/dish_entity_extraction.py
rag_modules/retrieval_executor.py
rag_modules/context_packer.py
rag_modules/structured_generation.py or generation_integration.py
rag_modules/turn_understanding.py
main.py
tests/
```

The implementation may touch `main.py` only to wire the new helper contracts into the existing pipeline.

The implementation must not add new old/new parallel runtime paths. If a helper replaces an older extraction or generation path, remove or route away from the old path in the same implementation stage.

## Done Criteria

- Dish entity extraction is centralized behind a tested helper.
- Recommendation list retrieval has a controlled fallback policy.
- Constraint/substitution answer modes produce constraint-shaped answers.
- Evidence identity is represented explicitly enough to prevent wrong-dish fallback answers.
- Deterministic tests pass.
- Core 50 live result is reported.
- All 85 live result is reported.
- Final notes classify remaining failures by systemic class.
