# Live E2E Small Optimization Design

Status: draft spec
Owner: C8 recipe RAG system
Date: 2026-07-07

## Purpose

This spec defines a short optimization pass after the first real 50-turn live E2E run.

The frozen runtime architecture is not changing. The live E2E runner now proves that the system can start the real Flask service, send real HTTP/SSE requests, use real data/indexes, and exercise the production runtime path. The first useful report was:

```text
Run: live-e2e-20260707-223633
Model: qwen-plus-2025-07-28
Result: 38 PASS / 12 FAIL
Infra errors: 0
Rate limits: 0
```

The failures are concentrated in two runtime behaviors:

- exact or near-exact recipe requests can fall into low evidence because retrieval does not handle common dish aliases or partial dish names;
- state-dependent constraint followups can lose the current dish and return low evidence or clarification instead of answering against the active recipe.

This pass should improve those behaviors with small, local changes only.

## Non-Goals

This spec must not introduce:

- a new RAG chain;
- a new planner architecture;
- async runtime, queues, workers, or concurrency primitives;
- broad LLM judging;
- large prompt rewrites;
- a second retrieval implementation beside `RetrievalExecutor`;
- fake live E2E shortcuts.

The goal is not to force `50/50` in one pass. The goal is to make a measurable improvement while preserving the frozen architecture.

## Current Model-Call Reality

The live runner sets the requested model through `RAG_LLM_MODEL`, and the Flask service initializes that model through the production path.

However, a live E2E turn does not necessarily call the external LLM. Several valid paths bypass model generation:

- `no_context`: low-evidence direct answer;
- `structured`: deterministic answer from selected recipe sections;
- `smalltalk`: direct conversational template;
- `list_template`: deterministic recommendation list;
- `consistency_blocked`: dish mismatch guard response.

Only `llm` and `llm_stream` generation modes should be expected to produce visible external model usage.

The live report must therefore expose generation mode and model request information. Otherwise a run can honestly use a configured model while still showing little provider-side token usage.

## Optimization Scope

This pass has three scoped changes.

### 1. Alias-Aware Detail Fallback

Problem:

Some live failures look like retrieval coverage failures even for ordinary recipe questions:

- `番茄炒蛋需要什么食材？`
- `红烧肉怎么做？`
- `可乐鸡翅需要准备什么？`
- `凉拌黄瓜怎么调味？`

The system currently treats extracted `dish_name` as a hard exact target. If the knowledge base uses a variant name, the quality check can reject useful candidates and return low evidence.

Design:

- Add a small dish alias resolver used by `RetrievalExecutor`.
- Keep exact dish search first.
- If exact dish evidence is insufficient, try alias or relaxed dish search.
- Alias fallback must be explicit in retrieval trace:
  - `strategy="alias_fallback"` or similar;
  - `dish_alias_used`;
  - `relaxed_filter=true`;
  - `fallback=true`.
- Alias fallback must not become broad search for arbitrary detail questions.

Initial aliases should be intentionally small and based on the live failures:

```python
{
    "番茄炒蛋": ["西红柿炒鸡蛋", "番茄鸡蛋", "番茄炒鸡蛋"],
    "西红柿炒鸡蛋": ["番茄炒蛋", "番茄鸡蛋", "番茄炒鸡蛋"],
    "凉拌黄瓜": ["拍黄瓜", "黄瓜"],
    "可乐鸡翅": ["鸡翅"],
    "红烧肉": ["五花肉"],
}
```

Acceptance:

- Existing exact dish behavior remains unchanged when exact retrieval succeeds.
- Alias fallback only runs after primary quality is insufficient.
- Alias fallback never returns a different dish silently; trace must show alias relaxation.
- At least two previously failing single-recipe live cases should improve, unless the real knowledge base genuinely lacks those recipes or aliases.

### 2. Stateful Constraint Followup Inheritance

Problem:

Several failures are state-dependent followups:

- `没有花生可以吗？`
- `能少油一点吗？`
- `能不能不要辣椒？`
- `这个适合带饭吗？`
- `那第二个怎么做？`

These questions depend on the current dish or the last recommendation list. Some contain no explicit pronoun or ordinal trigger that the current `Turn Understanding` reliably treats as reference resolution.

Design:

- Add lightweight constraint-followup detection in `Turn Understanding`.
- When a query contains substitution or constraint language and the snapshot has `current_dish`, mark it state-dependent:
  - `action="substitution"` for ingredient/seasoning/oil/spice replacement or omission;
  - `answer_mode_hint="substitution"` or `constraint_check`;
  - `should_retrieve=True`;
  - `depends_on_state=True`;
  - `needs_reference_resolution=True`;
  - `reference_trigger="constraint_followup"`.
- When a query contains an ordinal reference such as `第二个` and a recommendation list exists, keep the existing ordinal resolution path.
- Do not force state inheritance for unrelated domain questions.

Detection should be simple and explainable:

```text
substitution tokens: 没有, 不放, 不要, 替代, 换成, 少油, 少盐, 少糖
constraint tokens: 适合带饭, 适合新手, 热量高, 减脂, 不辣
```

Acceptance:

- Followups after `宫保鸡丁怎么做？` should retain `宫保鸡丁` for substitution/constraint questions.
- Low evidence for `没有花生可以吗？`, `能少油一点吗？`, and `能不能不要辣椒？` should be replaced by a grounded answer or an explicit low-confidence answer tied to the current dish.
- `smalltalk` must not update `current_dish`.
- Out-of-domain questions must still be rejected or answered directly without inheriting recipe state.

### 3. Live Report Generation-Mode Observability

Problem:

The current live report shows pass/fail and answer text, but it does not make model usage transparent. This makes it hard to answer whether a configured model was actually called.

Design:

Extend live result records and reports with best-effort diagnostics from the production response:

- `model_requested`;
- `generation_mode`;
- `context_doc_count`;
- `retrieval_strategy`;
- `quality_reason`;
- `selected_dishes`;
- `fallback_used`;
- `dish_alias_used`, when applicable.

If a field is unavailable, record `null`; do not fail the test solely because an optional diagnostic is missing.

The report should include a small generation summary:

```text
Generation Mode Summary
structured: N
no_context: N
llm: N
llm_stream: N
smalltalk: N
list_template: N
```

Acceptance:

- A live report can explain why provider-side model usage may be lower than turn count.
- `llm` and `llm_stream` counts are visible.
- Existing assertion behavior remains unchanged.

## Testing Strategy

Implementation should be test-driven and small.

Unit tests:

- alias fallback triggers only after primary quality fails;
- exact dish match still wins over alias fallback;
- constraint followup with `current_dish` sets state-dependent resolution fields;
- unrelated out-of-domain query does not inherit `current_dish`;
- live report summarizes generation modes.

Integration tests:

- run deterministic acceptance tests for state writeback and final cutover;
- run live E2E runner unit tests;
- run a 1-turn live smoke test before the full live run.

Live acceptance:

```text
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --limit-turns 50 --delay-seconds 5 --max-retries 1
```

Expected improvement:

- baseline: `38 PASS / 12 FAIL`;
- target: at least `44 PASS / 6 FAIL` for the same primary model and scenario set;
- no `INFRA_ERROR`;
- no rate-limit-driven false pass.

If the target is not met, the implementation should preserve the diagnostic report and classify remaining failures instead of hiding them by weakening assertions.

## Boundaries With Frozen Architecture

These changes fit the frozen main chain:

```text
Turn Understanding
-> Reference Resolution
-> Execution Plan
-> Query Plan
-> Retrieval Executor
-> Evidence Quality Check
-> Context Pack
-> Answer Generation
-> StateUpdatePolicy
-> Live Report
```

The only modified responsibilities are:

- `Turn Understanding`: better recognizes state-dependent constraint followups;
- `Retrieval Executor`: performs a bounded alias fallback after insufficient exact evidence;
- `Live E2E Reporter`: exposes diagnostics already produced by the runtime.

No node is added to the main production chain, and no old path is revived.

## Risks

Alias fallback can introduce wrong-dish evidence if it is too broad. Mitigation: keep alias map small, trace every alias, and preserve quality checks.

Constraint followup inheritance can over-attach questions to `current_dish`. Mitigation: only inherit when the query has explicit constraint/substitution language and the snapshot has an active current dish or resolvable recommendation.

Report diagnostics can become coupled to internal response shape. Mitigation: treat diagnostics as optional and best-effort.

## Done Criteria

This pass is complete when:

- the spec has an implementation plan;
- unit tests cover alias fallback, constraint inheritance, and report diagnostics;
- deterministic regression tests pass;
- a real 1-turn live smoke passes;
- a real 50-turn live run is executed and reported;
- the result is compared to the `38/50` baseline;
- any remaining failures are documented as either data coverage, retrieval behavior, answer-generation behavior, or assertion mismatch.
