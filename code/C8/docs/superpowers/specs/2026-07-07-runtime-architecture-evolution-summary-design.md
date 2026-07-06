# Runtime Architecture Evolution Summary Design

Status: active summary spec
Owner: C8 recipe RAG system
Date: 2026-07-07

## Purpose

This document summarizes the staged runtime architecture work completed so far and sets the working contract for the remaining stages.

The project has moved beyond a simple RAG question-answering flow. The target is a focused multi-turn recipe RAG runtime with clear boundaries for safety, turn understanding, reference resolution, retrieval execution, context packing, answer generation, streaming lifecycle, and typed state writeback.

This summary exists because the migration touches the whole chain. A later plan must not be locally correct while breaking the closed runtime path. Every new stage must be checked against this document before implementation.

## Target Posture

The architecture should stay small enough for an internship project but credible enough to explain as a real multi-turn RAG runtime.

The system should not become:

- a general agent runtime;
- a distributed async task platform;
- a queue-based orchestration engine;
- a collection of shadow paths where old and new chains both remain active.

The system should become:

- a context-first recipe RAG chain;
- a typed state-write system;
- a retrieval pipeline with explicit quality and fallback semantics;
- a context packing pipeline that limits parent-document flooding;
- a runtime with state-version awareness and streaming lifecycle semantics.

## Frozen Main Chain

The desired chain remains:

```text
entry
-> turn_id / trace_id
-> basic safety gate
-> read lightweight session snapshot + read_state_version
-> turn understanding
-> reference resolution when needed
-> blocking ambiguity check
-> execution plan
-> query plan if retrieval is needed
-> retrieval executor
-> evidence quality check
-> optional fallback
-> rerank
-> parent expansion
-> section selection / context trimming
-> context pack
-> pre-generation version check
-> answer generation or streaming lifecycle
-> StateUpdatePolicy builds state_diff
-> pre-commit version check
-> commit state_diff or conflict handling
```

Any implementation plan may temporarily leave parts incomplete, but it must not introduce a path that contradicts this chain.

## Stage Summary

### Stage 00: Current State And Migration Boundary

Stage 00 mapped the existing code before migration.

Key conclusions:

- `RecipeRAGSystem.ask_question()` is the main orchestration surface.
- The current code already has useful pieces: conversation state, writeback review, reference resolution, retrieval optimization, parent expansion, structured generation, and web/SSE endpoints.
- The old chain order was wrong for multi-turn behavior because guardrail and turn qualification ran before the session snapshot.
- Old paths may remain only while actively used by the new path. Once a new module owns a responsibility, unused legacy branches must be removed.

### Stage 01: State Contract And Writeback Policy

Stage 01 made state writes typed and field-limited.

Key contract:

```text
execution facts
-> classify answer_type
-> build_state_diff(answer_type, execution_result, old_state)
-> apply allowed fields only
```

Important rules:

- Generation and retrieval functions do not mutate business state directly.
- `smalltalk`, `domain_reject`, `no_result`, `low_confidence`, and `stream_aborted` must not update `current_dish`.
- `recommendation` can update `last_recommendation_list`.
- `detail` can update `current_dish` only with strong target evidence.
- `clarification` only writes `pending_clarification`.
- State writes must be centralized through the policy path.

### Stage 02: Context-First Turn Pipeline

Stage 02 moved context earlier in the chain.

New order:

```text
basic_safety_gate
-> read session snapshot
-> understand_turn(query, snapshot)
-> reference resolution
-> execution plan
```

Important rules:

- The basic safety gate only blocks empty, invalid, malicious, or unsafe input.
- Harmless out-of-domain questions are decided after snapshot by Turn Understanding.
- Follow-up text such as `第一个怎么做`, `这个能不放辣吗`, or `那第二个呢` must not be rejected before context is considered.
- `domain_reject` and `smalltalk` are real control-flow actions, not descriptive labels.
- Only blocking ambiguity may directly ask a clarification question.

### Stage 03: Retrieval Executor And Quality

Stage 03 moved retrieval execution behind one owner.

Key contract:

```text
Query Plan
-> Retrieval Executor
-> primary retrieval
-> fusion
-> evidence quality check
-> optional fallback
-> rerank
```

Important rules:

- Retrieval must not mean "search first, decide how later".
- Metadata is usually soft weighted, not hard filtered, except for strong explicit constraints.
- Fallback is conditional, not always-on.
- Fallback evidence must carry relaxed/fallback markers.
- Low evidence is a result-producing path, not a blank failure branch.
- The old low-level branching retrieval path should not remain active after cutover.

### Stage 04: Context Packing And Answer Modes

Stage 04 moves parent expansion and section selection out of generation helpers.

New ownership:

```text
retrieved chunks
-> parent expansion in ask_question()
-> ContextPacker
-> selected/truncated context_docs
-> generation
```

Important rules:

- `_generate_list_response()` and `_generate_detail_response()` must not call `get_parent_documents()`.
- Generation helpers must receive `context_pack`, not raw chunks.
- Generation helpers must not keep dead old-boundary parameters such as `session_id`, `filters`, `entities`, or `relevant_chunks`.
- `context_pack["context_docs"]` goes to generation.
- `context_pack["parent_docs"]` remains for diagnostics/writeback only.
- `context_pack_trace` belongs on `execution_result`, not duplicated into `query_plan`.
- `ContextPacker` budgets come from `RAGConfig`.
- Existing test fixtures must use recipe-shaped parent docs with selectable `##` sections, because the new path exercises real section selection.

The repeated review problems in Stage 04 established an important rule: test fixtures are part of the runtime chain. When the chain moves, fixtures must move too.

## Stage 05 Direction: Runtime Versioning And Streaming

Stage 05 should not introduce a full async runtime.

Decision:

```text
No full async architecture.
Use lightweight runtime control with async awareness.
```

Stage 05 should add:

- `turn_id`;
- `trace_id`;
- `read_state_version`;
- shared `max_replan_count`;
- pre-generation version checks for state-dependent turns;
- pre-plan or post-reference version checks where state resolution was used;
- pre-commit version checks;
- explicit streaming lifecycle.

Streaming lifecycle should be modeled as:

```text
started
-> retrieval_done
-> streaming
-> completed
```

or:

```text
started
-> retrieval_done
-> streaming
-> aborted
```

or:

```text
started
-> failed
```

Important rules:

- Completed streams may commit the final assistant answer and business state.
- Aborted streams may record lifecycle/history but must not create complete business state.
- An aborted recommendation must not become a valid `last_recommendation_list`.
- State-version mismatches must consume one shared turn-level retry budget.
- Retry exhaustion must return conflict handling instead of looping.
- Pure smalltalk that does not depend on state may skip pre-generation version checks.

## Stage 06 Direction: End-To-End Acceptance

Stage 06 should prove the architecture through behavior, not module existence.

Primary scenario:

```text
推荐三个鸡肉菜
-> 第一个怎么做
-> 这个能不放辣吗
-> 没有豆瓣酱怎么办
-> 给我换个不辣的
-> 谢谢
```

Expected behavior:

- recommendation list survives follow-ups and smalltalk;
- ordinal references resolve only when the previous recommendation list is reliable;
- current dish is not overwritten by smalltalk, no-result, low-evidence, or aborted streams;
- substitution and constraint follow-ups stay attached to the right recipe context;
- final smalltalk does not clear business state.

Additional required scenarios:

- harmless out-of-domain rejection;
- unrelated ordinal text after recommendations;
- missing exact dish;
- sparse metadata preference query;
- stream abort after recommendation;
- rapid state-dependent requests causing retry/conflict behavior.

## Cutover Rule

Every future implementation plan must state:

- what old responsibility is being replaced;
- where production calls are cut to the new path;
- what becomes illegal after cutover;
- what tests prove the new path is active;
- what unused old code must be deleted before acceptance.

Shadow paths are not acceptable. The old path may remain only if it is a thin wrapper actively called by the new architecture and has no independent behavior.

## Test Fixture Rule

When a stage changes the runtime chain, tests must not bypass the new path by accident.

Fixture requirements:

- stub data must resemble real recipe data when section selection or parent expansion is under test;
- stub modules must include every runtime dependency that the new chain reaches;
- monkeypatched helper signatures must match the new production signature;
- low-evidence tests should prove early return by intentionally not adding downstream dependencies;
- stream tests must consume the stream before asserting completed writeback;
- aborted stream tests must stop consumption and assert no complete business state was written.

This rule exists because Stage 04 showed that incomplete fixtures can make a plan look valid while real tests fail at the new boundary.

## Non-Goals

The remaining migration does not require:

- `async`/`await` throughout the RAG chain;
- external queues;
- distributed locks;
- background worker orchestration;
- database transactions;
- LLM judge reranking;
- a generalized agent planner.

These can be revisited only if the project requirement changes. For the current recipe RAG system, explicit lifecycle and state-version boundaries are enough.

## Acceptance For This Summary

This summary is accepted when future specs and plans use it as a checklist:

- Stage 05 must implement runtime versioning and streaming lifecycle without introducing full async orchestration.
- Stage 06 must validate the closed chain through end-to-end scenarios.
- No future plan may retain unused old production paths once the new path covers the behavior.
- No future plan may ignore test fixture migration when production chain ownership moves.
