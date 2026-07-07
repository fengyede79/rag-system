# Live E2E Expanded Scenario Set Design

Status: draft spec
Owner: C8 recipe RAG system
Date: 2026-07-08

## Purpose

This spec defines how to expand the live E2E scenario set from the current 50-turn baseline to an 80-90 turn evaluation set.

The goal is higher confidence, not an easier score. The current 50-turn set is useful as a regression core, but it is small enough that a few idiosyncratic cases can swing the total pass rate. Expanding the set should make the measured quality more stable while preserving visibility into the risky behaviors the project cares about:

- recipe detail retrieval;
- recommendation retrieval;
- multi-turn reference resolution;
- substitution and constraint followups;
- low-evidence handling;
- domain rejection;
- streaming behavior;
- rapid followup/runtime conflict handling.

This is a testing and reporting spec only. It does not change the frozen RAG runtime architecture.

## Baseline

The current live E2E file is:

```text
e2e/scenarios/live_e2e_scenarios.json
```

It contains 50 turns across these categories:

```text
single_recipe_detail
recommendation_list
multi_turn_reference
substitution_constraint
low_evidence
domain_reject
streaming_sse
rapid_followup_conflict
```

Recent live results:

```text
initial baseline: 38/50
small optimization pass: 39/50
second pass: 42/50
```

The 50-turn set remains the Core Set. It must not be weakened or replaced when the Extended Set is added.

## Non-Goals

This spec must not:

- change the RAG main chain;
- change prompts, retrieval, state writeback, or runtime versioning;
- hide failures by loosening assertions;
- inflate the score with many trivial smalltalk or domain-reject turns;
- remove or rewrite the current 50-turn Core Set;
- require concurrent live requests;
- require all supported models for every validation run.

## Suite Model

The live E2E scenarios should be split into two logical suites:

```text
core: existing 50 turns
extended: additional 30-40 turns
```

The runner/report should be able to display:

```text
Core 50:      X/50
Extended N:   Y/N
Total 80-90:  Z/(50+N)
```

If the scenario schema is changed, each scenario should include:

```json
{
  "suite": "core"
}
```

or:

```json
{
  "suite": "extended"
}
```

If the implementation chooses not to add a schema field, it must still preserve equivalent reporting by deriving suite membership from scenario IDs or files. Explicit `suite` is preferred because it is clearer and easier to audit.

## Target Size

The expanded set should contain:

```text
core: 50 turns
extended: 30-40 turns
total: 80-90 turns
```

Recommended first expansion:

```text
core: 50
extended: 35
total: 85
```

Rationale:

- 80-90 turns is large enough to reduce single-case volatility.
- It remains cheap enough to run serially with a 5 second delay.
- It avoids turning the internship project into a heavy evaluation platform.

## Category Allocation

The Extended Set should emphasize risky behaviors, not easy passes.

Recommended 35-turn Extended Set:

```text
single_recipe_detail:        7
recommendation_list:         7
multi_turn_reference:        7
substitution_constraint:     7
low_evidence:                3
domain_reject:               2
streaming_sse:               1
rapid_followup_conflict:     1
```

This distribution intentionally gives more weight to:

- retrieval coverage;
- recommendation quality;
- multi-turn state;
- constraint followups.

Domain rejection and low-evidence remain present but must not dominate the expanded set.

## Scenario Design Rules

### General Rules

Every added turn must:

- use the real `/api/chat` or `/api/chat/stream` endpoint;
- use real session IDs;
- preserve session state within multi-turn scenarios;
- have explicit assertions;
- avoid fake-only behavior;
- avoid assertions that require one exact wording unless exact wording is the behavior under test.

Assertions should prefer:

```json
"answer_contains_any": ["term1", "term2"]
```

over brittle exact text checks.

Assertions may keep `answer_not_contains` for:

- direct question echo;
- known low-evidence fallback text when evidence is expected;
- out-of-domain content when a domain rejection is expected.

### Single Recipe Detail

Add cases that cover:

- canonical dish names;
- common aliases;
- colloquial names;
- ingredient requests;
- step requests;
- tip requests.

Examples:

```text
西红柿炒鸡蛋需要什么食材？
简易红烧肉怎么做？
南派红烧肉怎么做？
拍黄瓜怎么调味？
鸡翅有哪些做法？
麻婆豆腐怎么不粘锅？
鱼香肉丝需要准备什么？
```

The goal is to distinguish:

- true data absence;
- alias mismatch;
- wrong-dish retrieval;
- parent-document filtering loss.

### Recommendation List

Add cases that cover:

```text
新手
下饭
带饭
不辣
快手
少油
家里已有食材
```

Examples:

```text
推荐三个适合新手的家常菜
推荐几个下饭但不太辣的菜
有什么适合带饭的鸡肉菜？
家里有土豆和鸡蛋，推荐两个菜
推荐几个少油的晚饭菜
```

Recommendation assertions must not allow a single-item answer when the question asks for multiple recommendations, unless the answer explicitly explains that evidence is limited.

### Multi-Turn Reference

Add scenarios that test:

- `第一个`;
- `第二个`;
- `这个`;
- `那个`;
- `刚才那个`;
- followups after smalltalk;
- followups after recommendation refresh.

Examples:

```text
推荐三个豆腐菜
第二个怎么做？
这个适合新手吗？
谢谢
刚才那个需要什么食材？
```

The key behavior is stable reference resolution across ordinary conversation turns.

### Substitution And Constraint Followups

Add scenarios that test:

```text
没有某食材
不放辣椒
少油
少盐
适合带饭
适合新手
热量/减脂
换一个
```

Examples:

```text
麻婆豆腐怎么做？
不能吃辣怎么办？
没有豆瓣酱可以吗？
能少油一点吗？
这个适合带饭吗？
换个不辣的豆腐菜
```

Assertions should require that the answer addresses the constraint, not merely returns generic recipe tips.

### Low Evidence

Add a small number of impossible or unsupported questions.

Examples:

```text
银河火锅鸡怎么做？
空气炸彩虹豆腐需要什么？
不存在的菜能不能少盐？
```

Low-evidence expected answers should require conservative language:

```text
没有找到
不确定
知识库
```

### Domain Reject

Add only a small number of harmless out-of-domain turns.

Examples:

```text
怎么选机械键盘？
怎么学摄影？
```

These should not dominate the expanded set because they are relatively easy and can inflate total pass rate.

### Streaming

Keep streaming coverage small but present.

Examples:

```text
麻婆豆腐怎么做？     endpoint=stream
```

The stream test should assert:

- HTTP 200;
- `sse_done_event=true`;
- answer contains expected recipe terms.

### Rapid Followup / Runtime

Keep this category small in the first expansion. The runner is serial and does not simulate true concurrency. These turns should continue to test versioning-visible behavior rather than pretending to be a full async stress test.

## Reporting Requirements

The live report must include suite-level summaries:

```text
## Suite Summary

| Suite | Total | PASS | FAIL | Pass Rate |
| --- | ---: | ---: | ---: | ---: |
| core | 50 | X | Y | Z% |
| extended | N | X | Y | Z% |
| total | 50+N | X | Y | Z% |
```

The report should also preserve existing summaries:

- status summary;
- model summary;
- category summary;
- generation mode summary;
- retrieval strategy summary;
- failure table;
- slowest turns.

The failure table should include suite information:

```text
| Suite | Model | Scenario | Turn | Status | Generation | Retrieval | Quality Reason | Error |
```

## Acceptance Criteria

For the current primary model:

```text
qwen-plus-2025-07-28
```

The expanded live E2E run is considered healthy when:

```text
Core Set:      >= 45/50
Total Set:     >= 80/90, or equivalent >= 88% if total is not exactly 90
Critical categories: each >= 75%
INFRA_ERROR:   0
RATE_LIMITED:  0, unless explicitly classified as provider-side throttling
```

Critical categories:

```text
single_recipe_detail
recommendation_list
multi_turn_reference
substitution_constraint
```

If Core Set is below `45/50`, the system is not accepted even if Total Set looks good.

If Total Set is strong but a critical category is below `75%`, the report must call that out explicitly.

## Runner Behavior

The runner should support:

```bash
--suite core
--suite extended
--suite all
```

Default should be:

```text
all
```

The existing `--limit-turns` behavior may remain, but suite filtering must happen before turn limiting so these commands are meaningful:

```bash
python e2e/live_e2e_runner.py --suite core --limit-turns 50
python e2e/live_e2e_runner.py --suite extended
python e2e/live_e2e_runner.py --suite all --limit-turns 90
```

## Validation Commands

Primary smoke:

```bash
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --suite core --limit-turns 1 --delay-seconds 0 --max-retries 0
```

Core regression:

```bash
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --suite core --limit-turns 50 --delay-seconds 5 --max-retries 1
```

Expanded run:

```bash
python e2e/live_e2e_runner.py --models qwen-plus-2025-07-28 --suite all --limit-turns 90 --delay-seconds 5 --max-retries 1
```

Optional confidence run:

```bash
python e2e/live_e2e_runner.py --models qwen-max --suite all --limit-turns 90 --delay-seconds 5 --max-retries 1
```

## Risks

The expanded set can hide regressions if the total score is emphasized over the Core Set. Mitigation: always report Core and Extended separately.

The expanded set can inflate confidence if it contains too many easy domain-reject or smalltalk turns. Mitigation: cap easy categories and emphasize retrieval/multi-turn/constraint scenarios.

The expanded set can become flaky if assertions are too wording-specific. Mitigation: use semantic keyword groups and diagnostics rather than exact phrasing.

The expanded run can increase API usage and rate-limit exposure. Mitigation: keep serial execution, 5 second delay, and bounded retries.

## Done Criteria

This expansion is complete when:

- the current 50-turn Core Set is preserved;
- 30-40 Extended turns are added;
- each scenario has suite membership or equivalent derived suite reporting;
- runner supports suite filtering;
- report includes suite summary;
- unit tests cover scenario loading, suite filtering, and suite reporting;
- a 1-turn live smoke passes;
- a Core 50 live run is reported;
- an 80-90 turn expanded live run is reported;
- final notes compare Core, Extended, and Total scores separately.
