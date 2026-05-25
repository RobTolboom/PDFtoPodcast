# PR #45 Code-Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Address the four reviewer comments on PR #45 (schema robustness) before merging: fix two "dot-separated" wording errors, raise a log level, add a missing interaction test, and document the superpowers directory convention in CLAUDE.md.

**Architecture:** All changes are isolated to `src/pipeline/schema_repair.py`, `tests/unit/test_schema_repair.py`, `CHANGELOG.md`, and `CLAUDE.md`. No schema or prompt changes. No bundling step required.

**Tech Stack:** Python 3.10+, pytest, Black, Ruff, Git (branch `fix/schema-robustness`)

---

## File Map

| File | Action |
|------|--------|
| `src/pipeline/schema_repair.py` | Modify: fix docstring wording (Task 1) + change log level (Task 2) |
| `tests/unit/test_schema_repair.py` | Modify: add WARNING-level log test (Task 2) + add partial-effect interaction test (Task 3) |
| `CHANGELOG.md` | Modify: fix bullet wording (Task 1) |
| `CLAUDE.md` | Modify: document superpowers plan/spec directories (Task 4) |

---

## Task 1 — Fix "dot-separated" wording (docstring + CHANGELOG)

The `_repair_figures_key_values` docstring and the matching CHANGELOG bullet both say **"dot-separated keys"**. The actual separator is `_` (underscore), as the code and tests already demonstrate (`exclusions_pre_screening_medical`). This is a pure text fix — no behaviour change, no tests needed.

**Files:**
- Modify: `src/pipeline/schema_repair.py` lines 282–292 (docstring)
- Modify: `CHANGELOG.md` line 25 (bullet)

- [ ] **Step 1: Fix the docstring in `_repair_figures_key_values`**

Current (lines 282–292 of `src/pipeline/schema_repair.py`):
```python
def _repair_figures_key_values(figures: list[Any]) -> list[Any]:
    """Flatten depth-2+ ``key_values`` objects inside each figure summary.

    Iterates over ``figures`` (a list of FigureSummary objects).  For each
    figure, inspects ``key_values`` and flattens any value that is a depth-2+
    nested object into a depth-1 representation using dot-separated keys.
```

Replace with:
```python
def _repair_figures_key_values(figures: list[Any]) -> list[Any]:
    """Flatten depth-2+ ``key_values`` objects inside each figure summary.

    Iterates over ``figures`` (a list of FigureSummary objects).  For each
    figure, inspects ``key_values`` and flattens any value that is a depth-2+
    nested object into a depth-1 representation using underscore-separated keys
    (e.g. ``breakdown_a_x``).
```

- [ ] **Step 2: Fix the CHANGELOG bullet**

Current (line 25 of `CHANGELOG.md`):
```
- **`schema_repair.py` flattens depth-2+ `key_values` objects in `figures_summary`** — when the LLM produces deeply nested objects inside `key_values` (depth-2 or more), they are flattened to depth-1 using dot-separated keys (e.g. `exclusions.pre_screening.medical`) so the result conforms to the schema constraint
```

Replace with:
```
- **`schema_repair.py` flattens depth-2+ `key_values` objects in `figures_summary`** — when the LLM produces deeply nested objects inside `key_values` (depth-2 or more), they are flattened to depth-1 using underscore-separated keys (e.g. `exclusions_pre_screening_medical`) so the result conforms to the schema constraint
```

- [ ] **Step 3: Format, lint, and run fast tests**

```bash
make format && make lint && make test-fast
```

Expected: all pass, no failures.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/schema_repair.py CHANGELOG.md
git commit -m "docs: fix 'dot-separated' → 'underscore-separated' in docstring and CHANGELOG"
```

---

## Task 2 — Raise fragment-drop log level from INFO to WARNING

Dropping an array item is a **data-loss event** — the LLM's content is permanently discarded. Logging it at `INFO` makes it invisible in default log configurations. The reviewer correctly points out it should be `WARNING`. A test using pytest's `caplog` fixture verifies the level is correct and remains so.

**Files:**
- Modify: `src/pipeline/schema_repair.py` line 385
- Modify: `tests/unit/test_schema_repair.py` (add test to `TestDropMalformedJsonFragments`)

- [ ] **Step 1: Write the failing test**

Add this method at the end of the `TestDropMalformedJsonFragments` class (after `test_fragment_with_colon_dropped`, around line 740 of `tests/unit/test_schema_repair.py`):

```python
    def test_fragment_drop_logged_at_warning(self, caplog):
        """Dropping a JSON-fragment string must be logged at WARNING level.

        Dropping array items is a data-loss event and must be visible even
        in default logging configurations (WARNING threshold).
        """
        import logging

        data = {
            "outcomes": [
                '{"outcome_id": "O2", "name": "Secondary"}',  # JSON fragment
                {"outcome_id": "O1", "name": "Primary"},
            ],
        }
        with caplog.at_level(logging.WARNING, logger="src.pipeline.schema_repair"):
            repair_schema_violations(data, self.FRAGMENT_SCHEMA, None)

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("Dropping" in msg for msg in warning_messages), (
            f"Expected a WARNING log containing 'Dropping', got: {warning_messages}"
        )
```

- [ ] **Step 2: Run the failing test**

```bash
pytest tests/unit/test_schema_repair.py::TestDropMalformedJsonFragments::test_fragment_drop_logged_at_warning -v
```

Expected: **FAIL** — no WARNING records found (currently logged at INFO).

- [ ] **Step 3: Raise the log level in `_repair_array`**

Current (line 384–389 of `src/pipeline/schema_repair.py`):
```python
            if _is_json_fragment_string(item):
                logger.info(
                    "Dropping malformed JSON-fragment string in array (id_field=%s): %.80r",
                    id_field,
                    item,
                )
                continue
```

Replace with:
```python
            if _is_json_fragment_string(item):
                logger.warning(
                    "Dropping malformed JSON-fragment string in array (id_field=%s): %.80r",
                    id_field,
                    item,
                )
                continue
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
pytest tests/unit/test_schema_repair.py::TestDropMalformedJsonFragments::test_fragment_drop_logged_at_warning -v
```

Expected: **PASS**.

- [ ] **Step 5: Run the full fast test suite**

```bash
make format && make lint && make test-fast
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/pipeline/schema_repair.py tests/unit/test_schema_repair.py
git commit -m "fix: raise JSON-fragment drop log level from INFO to WARNING in schema_repair"
```

---

## Task 3 — Add partial-effect interaction test

The reviewer notes that the correctness argument for making `ContrastResult.effect` optional hinges on a single claim: a partial `{p_value, favors}` effect object (missing required `type` and `point`) is removed by `repair_schema_violations` once `effect` is optional. This is tested at the unit level for generic optional objects, but there is no test that uses the **actual ContrastResult/ContrastEffect structure**. This task adds that test.

The test uses a synthetic schema that mirrors the structure of the bundled `interventional_trial` schema — `effect` is optional (not in `required`), but `ContrastEffect` itself requires `type` and `point`. A partial effect must be removed.

**Files:**
- Modify: `tests/unit/test_schema_repair.py` (add new class after `TestDropMalformedJsonFragments`)

- [ ] **Step 1: Write the failing test**

Add this class after `TestDropMalformedJsonFragments` and before `FIGURES_SUMMARY_SCHEMA` in `tests/unit/test_schema_repair.py` (around line 742):

```python
# ---------------------------------------------------------------------------
# Task 3: Interaction test — partial ContrastResult.effect removed by repair
# ---------------------------------------------------------------------------


class TestContrastResultPartialEffectRemoved:
    """Verify that a partial ContrastResult.effect is removed by repair.

    This is the load-bearing correctness test for making ContrastResult.effect
    optional (PR #45 Change 2).  The argument is: once 'effect' is not required,
    a partial effect object missing 'type'/'point' is removed deterministically
    by _repair_object without consuming a correction iteration.

    The schema mirrors the actual structure in interventional_trial_bundled.json.
    """

    # Minimal schema that mirrors ContrastResult / ContrastEffect in the bundled schema.
    # effect is NOT in required — mirrors the Change 2 fix.
    CONTRAST_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": [],
        "properties": {
            "contrasts": {
                "type": "array",
                "items": {
                    "$ref": "#/$defs/ContrastResult",
                },
            },
        },
        "$defs": {
            "ContrastResult": {
                "type": "object",
                "additionalProperties": False,
                "required": ["outcome_id", "comparison_id"],  # effect intentionally absent
                "properties": {
                    "outcome_id": {"type": "string"},
                    "comparison_id": {"type": "string"},
                    "effect": {
                        "$ref": "#/$defs/ContrastEffect",
                    },
                },
            },
            "ContrastEffect": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "point"],
                "properties": {
                    "type": {"type": "string"},
                    "point": {"type": "number"},
                    "p_value": {"type": "number"},
                    "favors": {"type": "string"},
                },
            },
        },
    }

    def test_partial_effect_removed_when_optional(self):
        """A ContrastResult with only p_value+favors in effect should have effect removed.

        This is the concrete test for the correctness argument in Change 2.
        The LLM produces {"p_value": ">0.05", "favors": "neutral"} with no
        'type' or 'point'.  repair_schema_violations must remove 'effect'
        entirely because the sub-object is missing required fields.
        """
        data = {
            "contrasts": [
                {
                    "outcome_id": "O1",
                    "comparison_id": "C1",
                    "effect": {
                        "p_value": 0.07,
                        "favors": "neutral",
                        # Missing required 'type' and 'point'
                    },
                },
            ],
        }
        result = repair_schema_violations(data, self.CONTRAST_SCHEMA, None)

        contrast = result["contrasts"][0]
        assert "effect" not in contrast, (
            "Partial effect (no 'type'/'point') must be removed by repair"
        )
        assert contrast["outcome_id"] == "O1"
        assert contrast["comparison_id"] == "C1"

    def test_complete_effect_preserved(self):
        """A ContrastResult with a complete effect object must be kept unchanged."""
        data = {
            "contrasts": [
                {
                    "outcome_id": "O2",
                    "comparison_id": "C1",
                    "effect": {
                        "type": "RR",
                        "point": 0.57,
                        "favors": "treatment_or_exposure",
                    },
                },
            ],
        }
        result = repair_schema_violations(data, self.CONTRAST_SCHEMA, None)

        contrast = result["contrasts"][0]
        assert "effect" in contrast
        assert contrast["effect"]["type"] == "RR"
        assert contrast["effect"]["point"] == 0.57

    def test_contrast_without_effect_valid(self):
        """A ContrastResult without any effect field is valid (effect is optional)."""
        data = {
            "contrasts": [
                {
                    "outcome_id": "O3",
                    "comparison_id": "C1",
                    # No 'effect' key at all
                },
            ],
        }
        result = repair_schema_violations(data, self.CONTRAST_SCHEMA, None)

        contrast = result["contrasts"][0]
        assert "effect" not in contrast
        assert contrast["outcome_id"] == "O3"
```

- [ ] **Step 2: Run the new tests**

```bash
pytest tests/unit/test_schema_repair.py::TestContrastResultPartialEffectRemoved -v
```

Expected: **all 3 PASS** — the repair logic for optional objects with missing required sub-fields was already implemented in Task 3a of the main fix. These tests validate the existing behaviour using the correct schema structure.

If any fail: investigate `_repair_object` logic — it should already handle this via the `sub_required` / `missing` check at lines 214–224 of `schema_repair.py`.

- [ ] **Step 3: Run the full fast test suite**

```bash
make format && make lint && make test-fast
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_schema_repair.py
git commit -m "test: add ContrastResult partial-effect interaction test for PR #45 Change 2"
```

---

## Task 4 — Document superpowers directories in CLAUDE.md

`CLAUDE.md` currently says planning docs go in `docs/plans/`. The superpowers plugin writes plans to `docs/superpowers/plans/` and specs to `docs/superpowers/specs/`. Both conventions coexist. `CLAUDE.md` should document the superpowers namespace so future sessions do not create plans in the wrong directory.

**Files:**
- Modify: `CLAUDE.md` (the project-level file, not the global `~/.claude/CLAUDE.md`)

- [ ] **Step 1: Add a superpowers namespace note to `feature_planning`**

Locate the `<feature_planning>` section in `CLAUDE.md` (lines 33–43). Replace:

```xml
  <feature_planning>
    <planning_phase>
      <rule>Create a planning markdown in the "docs/plans" directory with goal, scope, task list, risks, and acceptance criteria.</rule>
    </planning_phase>
```

With:

```xml
  <feature_planning>
    <planning_phase>
      <rule>Create a planning markdown in the "docs/plans" directory with goal, scope, task list, risks, and acceptance criteria.</rule>
      <rule>When using the superpowers plugin (brainstorming → writing-plans → subagent-driven-development), plans are written to "docs/superpowers/plans/YYYY-MM-DD-feature.md" and design specs to "docs/superpowers/specs/YYYY-MM-DD-feature-design.md". Both conventions coexist; the superpowers namespace takes precedence when those skills are in use.</rule>
    </planning_phase>
```

- [ ] **Step 2: Verify no other rules are affected**

Read `CLAUDE.md` and confirm the rest of the file is unchanged. No tests are needed for a documentation change.

- [ ] **Step 3: Run lint (CLAUDE.md is XML-in-markdown; ensure no accidental breaks)**

```bash
make lint
```

Expected: pass (linter does not check XML content in markdown files).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document superpowers plan/spec directory convention in CLAUDE.md"
```

---

## Final verification

After all four tasks are committed:

- [ ] **Run the full fast test suite one final time**

```bash
make format && make lint && make test-fast
```

Expected: all tests pass with no warnings.

- [ ] **Confirm all four review findings are addressed**

| Finding | Task | Evidence |
|---------|------|---------|
| `_repair_figures_key_values` docstring says "dot-separated" | Task 1 | docstring now says "underscore-separated keys (e.g. `breakdown_a_x`)" |
| CHANGELOG bullet says "dot-separated" | Task 1 | bullet now says "underscore-separated keys (e.g. `exclusions_pre_screening_medical`)" |
| Fragment drop logged at INFO (data loss) | Task 2 | `logger.warning(...)` + caplog test asserts WARNING |
| Missing ContrastResult.effect interaction test | Task 3 | `TestContrastResultPartialEffectRemoved` — 3 tests |
| `docs/plans` ≠ `docs/superpowers/plans` undocumented | Task 4 | CLAUDE.md updated with superpowers namespace rule |

---

## Self-Review Checklist

**Spec coverage:**
- [x] Docstring wording fix → Task 1 Step 1
- [x] CHANGELOG wording fix → Task 1 Step 2
- [x] `logger.info` → `logger.warning` → Task 2 Step 3
- [x] caplog WARNING-level test → Task 2 Step 1
- [x] Partial effect interaction test (`test_partial_effect_removed_when_optional`) → Task 3 Step 1
- [x] CLAUDE.md superpowers directory documentation → Task 4 Step 1

**Placeholder scan:** No TBD, TODO, or vague steps present.

**Type consistency:** All function names and schema keys match `schema_repair.py` as it exists on `fix/schema-robustness`.
