# PR Description: RAG Generation and Web Refactor

Date: `2026-07-03`

Suggested PR title: `[codex] Refactor RAG generation and web app structure`

## Summary

This change reorganizes the recipe RAG application around clearer module boundaries and more predictable runtime behavior.

- Split the oversized generation integration logic into focused helper modules:
  - `guardrail.py`
  - `prompts.py`
  - `stream_handler.py`
  - `structured_generation.py`
- Moved the Flask chat page from inline Python HTML into `templates/index.html`.
- Centralized query filter extraction in the retrieval layer instead of keeping it in `main.py`.
- Tightened conversation and retrieval support code with small correctness and maintainability fixes.
- Updated evaluation parsing, tests, dependencies, and repository documentation to match the refactor.

## Why

Before this change, too much behavior was concentrated in `generation_integration.py` and the Flask entrypoint:

- prompt construction, guardrails, structured answering, and streaming fallbacks were mixed together
- the web UI template lived inline in Python, which made the route file harder to read and maintain
- some retrieval and metadata logic was duplicated across modules
- cache loading and document lookup paths had avoidable fragility

The refactor keeps the same overall feature set, but makes the code easier to reason about, safer to evolve, and simpler to test.

## What Changed

### 1. Generation pipeline decomposition

- Extracted guardrail classification and fallback answers into `rag_modules/guardrail.py`.
- Extracted prompt templates and no-context fallback generation into `rag_modules/prompts.py`.
- Extracted safe `invoke` / `stream` wrappers into `rag_modules/stream_handler.py`.
- Extracted Markdown-structure-based answer assembly into `rag_modules/structured_generation.py`.
- Updated `generation_integration.py` to orchestrate these pieces instead of owning every responsibility directly.

### 2. Web app structure cleanup

- Replaced `render_template_string(...)` with `render_template(...)`.
- Moved the page markup into `code/C8/templates/index.html`.
- Simplified `web_app.py` so it focuses on routing and SSE behavior.
- Tightened SSE event formatting so emitted event payloads are structured more consistently.

### 3. Retrieval and data support improvements

- Moved metadata filter extraction into `RetrievalOptimizationModule.extract_filters_from_query(...)`.
- Reused a shared ingredient keyword list from `DataPreparationModule`.
- Added chunk-cache versioning and checksum validation.
- Added a parent-document index map to avoid repeated linear scans.
- Hardened a few matching branches against missing dish-name metadata.

### 4. Small correctness fixes

- Fixed conversation summary logic to pick the last user turn correctly.
- Corrected route rule iteration so priority ordering stays explicit.
- Improved evaluation JSON parsing to tolerate LLM responses wrapped in Markdown code fences.
- Adjusted default index path resolution to live under the project code directory.

### 5. Documentation and dependency updates

- Refreshed the root `README.md` to describe the project as a fuller RAG application rather than a minimal demo.
- Added missing dependency declarations such as `python-dotenv`, `numpy`, and `pytest`.

## Impact

- Lower maintenance cost for the generation path
- Cleaner separation between orchestration and helper logic
- Easier future work on prompts, guardrails, streaming, and structured answers
- A more maintainable Flask entrypoint
- Better cache safety and slightly more robust retrieval behavior

## Validation

Executed:

```bash
pytest code/C8/tests
```

Result:

- `38 passed`

Also checked:

```bash
git diff --check
```

Result:

- no diff-format or trailing-whitespace errors blocking commit

