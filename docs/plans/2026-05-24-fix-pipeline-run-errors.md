# Fix: Pipeline Run Errors (2026-05-24)

**Branch:** `fix/pipeline-run-errors`

## Goal

Fix four errors observed in a live pipeline run on an interventional trial PDF
(`s12871-026-03928-3_reference.pdf`).

## Errors Fixed

### 1. Max corrections capped at 3 → raised to 5

Schema compliance stalled at 85.3% (below the 95% threshold). More iterations
were needed to converge. The `max_iterations` default in `IterativeLoopConfig`
and the `--max-iterations` CLI flag default were both 3.

**Files:** `src/pipeline/iterative/loop_runner.py:119`, `run_pipeline.py:137`

### 2. Show summary validation: `_metadata` / `usage` unexpected

`podcast_logic.py` validated `summary_json` against a schema with
`additionalProperties: false` without first stripping provider-injected fields.
`_strip_metadata_for_pipeline()` already existed and was called on the main
podcast JSON but was missing on the show summary path.

**File:** `src/pipeline/podcast_logic.py` (~line 301)

### 3. Podcast synopsis too long (500 → 750 char limit)

A well-formed 2–3 sentence synopsis for a complex surgical RCT can be 700+
characters. The `maxLength: 500` constraint in the schema and matching manual
check were too tight. Raised to 750 in both places.

**Files:** `schemas/podcast.schema.json:71`, `src/pipeline/podcast_logic.py:317`

### 4. `sensitivity_analyses[n].effect` missing required fields

Papers reporting sensitivity analyses qualitatively (no numeric estimates)
caused the LLM to produce an `effect` object with only optional fields (e.g.
`favors`) but without the required `type` and `point` fields. `schema_repair.py`
had no logic to remove an optional parent field whose value is an incomplete
object. Extended `_repair_object()` to handle this case.

**File:** `src/pipeline/schema_repair.py`

## Acceptance Criteria

- `make test-fast` passes (171 unit tests)
- `tests/unit/test_podcast_generation.py` passes (17 tests, all new cases covered)
- `tests/unit/test_loop_runner.py` passes (68 tests, default updated)
- `tests/unit/test_schema_repair.py` passes (25 tests, 4 new cases covering incomplete optional objects)
- No regressions in `make lint` or `make format`
