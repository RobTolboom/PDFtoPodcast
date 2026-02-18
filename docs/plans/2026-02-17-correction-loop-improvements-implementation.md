# Correction Loop Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the correction loop so it converges instead of degrading, by adding deterministic repairs, proportional scoring, better prompts, failure feedback, and stuck-loop detection.

**Architecture:** Five independent fixes that reinforce each other. Fix 1 (schema repair) prevents most pattern violations deterministically. Fix 2 (proportional scoring) removes the binary cliff. Fix 3 (prompt rule) prevents at the LLM source. Fix 4 (failure hints) breaks identical retries. Fix 5 (stuck detection) saves wasted LLM calls.

**Tech Stack:** Python 3.10+, pytest, jsonschema, Black/Ruff

---

### Task 1: Create feature branch

**Step 1: Create and switch to feature branch**

Run: `git checkout -b fix/correction-loop-improvements`

**Step 2: Verify branch**

Run: `git branch --show-current`
Expected: `fix/correction-loop-improvements`

---

### Task 2: Add pattern/minimum/enum violation repair to `schema_repair.py`

**Files:**
- Modify: `src/pipeline/schema_repair.py`
- Test: `tests/unit/test_schema_repair.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_schema_repair.py`:

```python
import re


# Extended schema with pattern-constrained and minimum-constrained fields
PATTERN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title"],
    "properties": {
        "title": {"type": "string"},
        "study_id": {
            "type": "string",
            "pattern": "^[A-Za-z0-9._/:;()\\[\\]-]+$",
        },
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["title"],
            "properties": {
                "title": {"type": "string"},
                "pmid": {
                    "type": "string",
                    "pattern": "^\\d{1,8}$",
                },
                "issn": {
                    "type": "string",
                    "pattern": "^\\d{4}-\\d{3}[\\dxX]$",
                },
                "page_count": {
                    "type": "integer",
                    "minimum": 1,
                },
                "authors": {
                    "type": "array",
                    "items": {
                        "$ref": "#/$defs/Author",
                    },
                },
            },
        },
        "outcomes": {
            "type": "array",
            "items": {"$ref": "#/$defs/OutcomeWithISO"},
        },
        "truncated": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "is_truncated": {"type": "boolean"},
                "reason": {
                    "type": "string",
                    "enum": ["token_limit", "page_limit", "timeout", "other"],
                },
            },
        },
    },
    "$defs": {
        "Author": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "orcid": {
                    "type": "string",
                    "pattern": "^(https://orcid\\.org/)?0000-00(0[2-9]|[1-9]\\d)-\\d{4}-\\d{3}[\\dX]$",
                },
            },
        },
        "OutcomeWithISO": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "outcome_id": {"type": "string"},
                "name": {"type": "string"},
                "timepoint_iso8601": {
                    "type": "string",
                    "pattern": "^P(?:(?:\\d+Y)?(?:\\d+M)?(?:\\d+W)?(?:\\d+D)?)?(?:T(?:\\d+H)?(?:\\d+M)?(?:\\d+(?:\\.\\d+)?S)?)?$",
                },
            },
        },
    },
}


class TestRepairPatternViolations:
    """Test repair of empty strings violating pattern constraints."""

    def test_empty_string_pattern_field_removed_when_optional(self):
        """Empty string violating pattern on optional field should be removed."""
        data = {
            "title": "Test",
            "study_id": "",  # violates pattern, optional field
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "study_id" not in result

    def test_valid_pattern_field_preserved(self):
        """Valid pattern-matching string should be preserved."""
        data = {
            "title": "Test",
            "study_id": "NCT12345678",
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert result["study_id"] == "NCT12345678"

    def test_nested_pattern_field_removed(self):
        """Empty string violating pattern in nested object removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study Title",
                "pmid": "",  # violates pattern, optional
                "issn": "",  # violates pattern, optional
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "pmid" not in result["metadata"]
        assert "issn" not in result["metadata"]
        assert result["metadata"]["title"] == "Study Title"

    def test_pattern_in_array_item_refs(self):
        """Empty pattern fields in array items via $ref should be removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study",
                "authors": [
                    {"name": "Smith", "orcid": ""},
                    {"name": "Jones", "orcid": "0000-0002-1234-5678"},
                ],
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "orcid" not in result["metadata"]["authors"][0]
        assert result["metadata"]["authors"][1]["orcid"] == "0000-0002-1234-5678"

    def test_iso8601_empty_string_in_outcomes(self):
        """Empty ISO8601 duration fields in outcomes should be removed."""
        data = {
            "title": "Test",
            "outcomes": [
                {"outcome_id": "O1", "name": "Primary", "timepoint_iso8601": ""},
                {"outcome_id": "O2", "name": "Secondary", "timepoint_iso8601": "P6M"},
            ],
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "timepoint_iso8601" not in result["outcomes"][0]
        assert result["outcomes"][1]["timepoint_iso8601"] == "P6M"

    def test_required_pattern_field_not_removed(self):
        """Required field with pattern violation should NOT be removed."""
        # title is required - even if it were empty, we don't remove required fields
        data = {
            "title": "Test",
            "metadata": {
                "title": "",  # required field, should NOT be removed
                "pmid": "",  # optional, should be removed
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "title" in result["metadata"]  # required, kept
        assert "pmid" not in result["metadata"]  # optional pattern, removed


class TestRepairMinimumViolations:
    """Test repair of values violating minimum constraints."""

    def test_zero_below_minimum_removed_when_optional(self):
        """Value below minimum on optional field should be removed."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study",
                "page_count": 0,  # minimum is 1, optional field
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "page_count" not in result["metadata"]

    def test_valid_minimum_preserved(self):
        """Value meeting minimum should be preserved."""
        data = {
            "title": "Test",
            "metadata": {
                "title": "Study",
                "page_count": 5,
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert result["metadata"]["page_count"] == 5


class TestRepairEnumViolations:
    """Test repair of values violating enum constraints."""

    def test_empty_string_not_in_enum_removed(self):
        """Empty string not in enum on optional field should be removed."""
        data = {
            "title": "Test",
            "truncated": {
                "is_truncated": False,
                "reason": "",  # not in enum, optional
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert "reason" not in result["truncated"]

    def test_valid_enum_preserved(self):
        """Valid enum value should be preserved."""
        data = {
            "title": "Test",
            "truncated": {
                "is_truncated": True,
                "reason": "token_limit",
            },
        }
        result = repair_schema_violations(data, PATTERN_SCHEMA, None)
        assert result["truncated"]["reason"] == "token_limit"
```

**Step 2: Run tests to verify they fail**

Run: `make test-fast`
Expected: New tests FAIL (repair functions don't handle patterns yet)

**Step 3: Implement the pattern/minimum/enum repair**

In `src/pipeline/schema_repair.py`, add a new `_repair_constraint_violations` function and integrate it into the existing `_repair_object` function.

Add these imports at top:
```python
import re
```

Add new helper function after `_get_id_field_for_array`:

```python
def _violates_constraints(
    value: Any,
    prop_schema: dict[str, Any],
    required_fields: list[str],
    field_name: str,
) -> bool:
    """Check if a value violates schema constraints that can be fixed by removal.

    Only returns True for OPTIONAL fields where the value is clearly invalid
    (empty string violating pattern, value below minimum, value not in enum).
    Required fields are never flagged for removal.
    """
    # Never remove required fields
    if field_name in required_fields:
        return False

    # Check string pattern violations
    if isinstance(value, str) and "pattern" in prop_schema:
        try:
            if not re.match(prop_schema["pattern"], value):
                logger.info("Removing optional field '%s': value '%s' violates pattern", field_name, value[:50])
                return True
        except re.error:
            pass  # Invalid regex in schema, skip

    # Check minimum violations (integers/numbers)
    if isinstance(value, (int, float)) and "minimum" in prop_schema:
        if value < prop_schema["minimum"]:
            logger.info("Removing optional field '%s': value %s below minimum %s", field_name, value, prop_schema["minimum"])
            return True

    # Check enum violations
    if "enum" in prop_schema and value not in prop_schema["enum"]:
        logger.info("Removing optional field '%s': value '%s' not in enum %s", field_name, value, prop_schema["enum"])
        return True

    return False
```

Modify `_repair_object` to call constraint checking. Replace the existing function:

```python
def _repair_object(
    obj: dict[str, Any],
    schema_props: dict[str, Any],
    schema_defs: dict[str, Any],
    root_schema: dict[str, Any],
    original: dict[str, Any] | None,
) -> dict[str, Any]:
    """Recursively repair an object according to its schema properties."""
    required_fields = root_schema.get("required", [])

    keys_to_remove = []

    for key, prop_schema in schema_props.items():
        if key not in obj:
            continue

        # Resolve $ref if present
        resolved = prop_schema
        if "$ref" in prop_schema:
            resolved = _resolve_ref(prop_schema["$ref"], schema_defs)
            if not resolved:
                continue

        prop_type = resolved.get("type")

        if prop_type == "array":
            obj[key] = _repair_array(
                obj[key], resolved, schema_defs, original.get(key) if original else None
            )
        elif prop_type == "object":
            if isinstance(obj[key], dict):
                nested_props = resolved.get("properties", {})
                original_nested = original.get(key) if original else None
                obj[key] = _repair_object(
                    obj[key], nested_props, schema_defs, resolved, original_nested
                )
                # Remove disallowed nested properties
                if resolved.get("additionalProperties") is False and nested_props:
                    allowed = set(nested_props.keys())
                    disallowed = [k for k in obj[key] if k not in allowed]
                    for dk in disallowed:
                        logger.info("Removing disallowed property: %s.%s", key, dk)
                        del obj[key][dk]
        else:
            # Leaf field: check for constraint violations
            if _violates_constraints(obj[key], resolved, required_fields, key):
                keys_to_remove.append(key)

    # Remove violating optional fields (outside iteration loop)
    for key in keys_to_remove:
        del obj[key]

    return obj
```

Note the key changes:
1. Extract `required_fields` from `root_schema` (the parent object's schema, which has the `required` list)
2. Add `else` branch for leaf fields that checks constraints via `_violates_constraints`
3. Collect keys to remove and delete after iteration (to avoid modifying dict during iteration)

**Step 4: Run tests to verify they pass**

Run: `make test-fast`
Expected: All new and existing tests PASS

**Step 5: Run format and lint**

Run: `make format && make lint`

**Step 6: Commit**

```bash
git add src/pipeline/schema_repair.py tests/unit/test_schema_repair.py
git commit -m "fix: add deterministic repair for pattern/minimum/enum violations in schema_repair"
```

---

### Task 3: Add proportional schema scoring to `validation.py`

**Files:**
- Modify: `src/validation.py:286-293`
- Test: `tests/unit/test_validation.py`

**Step 1: Write the failing tests**

Add to `tests/unit/test_validation.py`:

```python
from src.validation import validate_extraction_quality


class TestValidateExtractionQualityScoring:
    """Test proportional schema scoring in validate_extraction_quality."""

    def test_no_errors_gives_full_schema_score(self):
        """With no schema errors, schema_score component should be 1.0."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
            },
            "required": ["name"],
        }
        data = {"name": "Test", "age": 30}

        result = validate_extraction_quality(data, schema)

        assert result["schema_compliant"] is True
        # quality_score = 1.0 * 0.5 + completeness * 0.5
        assert result["quality_score"] >= 0.5  # At least schema component

    def test_few_errors_gives_proportional_score(self):
        """A few schema errors should give proportional score, not binary 0."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
                "email": {"type": "string"},
                "city": {"type": "string"},
                "country": {"type": "string"},
            },
            "required": ["name"],
        }
        # age is wrong type - 1 error out of 5 properties
        data = {"name": "Test", "age": "not_a_number", "email": "a@b.com", "city": "X", "country": "Y"}

        result = validate_extraction_quality(data, schema)

        assert result["schema_compliant"] is False
        # Should NOT be 0.0 + completeness*0.5 (binary)
        # Should be proportional: schema_score ~= 1 - 1/5 = 0.8
        # quality_score = 0.8 * 0.5 + completeness * 0.5
        assert result["quality_score"] > 0.5  # Must be above binary floor

    def test_all_errors_gives_low_score(self):
        """Many errors relative to fields should give low score."""
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        }
        data = {"a": "x", "b": "y"}  # 2 errors out of 2 fields

        result = validate_extraction_quality(data, schema)

        # 2 errors / 2 fields = 0.0 schema score
        assert result["quality_score"] <= 0.5
```

**Step 2: Run tests to verify they fail**

Run: `make test-fast`
Expected: `test_few_errors_gives_proportional_score` FAILS (currently gives binary 0)

**Step 3: Implement proportional scoring**

In `src/validation.py`, replace lines 286-293:

```python
    # 3. Calculate overall quality score
    # Schema compliance: 50% weight (proportional to error count)
    # Completeness: 50% weight
    total_fields = completeness["required_fields_total"] + completeness["optional_fields_total"]
    if is_valid:
        schema_score = 1.0
    else:
        schema_score = max(0.0, 1.0 - len(errors) / max(total_fields, 1))
    completeness_score = completeness["completeness_score"]

    quality_score = (schema_score * 0.5) + (completeness_score * 0.5)
    results["quality_score"] = round(quality_score, 3)
```

**Step 4: Run tests**

Run: `make test-fast`
Expected: All PASS

**Step 5: Format and lint**

Run: `make format && make lint`

**Step 6: Commit**

```bash
git add src/validation.py tests/unit/test_validation.py
git commit -m "fix: replace binary schema scoring with proportional error-ratio scoring"
```

---

### Task 4: Add empty-string omission rule to correction prompt

**Files:**
- Modify: `prompts/Extraction-correction.txt:41`

**Step 1: Add the rule**

After line 41 (`- If SCHEMA forbids null for a field, you must not emit that field with null. Omit the field instead.`), add:

```
   - If you do not have a value for an optional field that has a regex pattern constraint
     (e.g., orcid, issn, eissn, pmid, pmcid, ISO 8601 durations, content_hash_sha256, study_id),
     you MUST omit the field entirely. NEVER emit an empty string "" for pattern-constrained fields.
     An empty string "" violates the pattern and causes schema errors.
```

**Step 2: Run tests to verify no regressions**

Run: `make test-fast`
Expected: All PASS (prompt changes don't break unit tests)

**Step 3: Commit**

```bash
git add prompts/Extraction-correction.txt
git commit -m "fix: add explicit empty-string omission rule to correction prompt"
```

---

### Task 5: Add previous-failure context to retry corrections

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py`
- Modify: `src/pipeline/steps/validation.py`
- Test: `tests/unit/test_loop_runner.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_loop_runner.py`:

```python
class TestCorrectionHintsInjection:
    """Test that previous correction failures are communicated to next attempt."""

    def _create_validation_result(
        self,
        completeness: float = 0.95,
        accuracy: float = 0.98,
        schema_compliance: float = 0.97,
        critical_issues: int = 0,
        schema_quality: float = 1.0,
        schema_errors: list | None = None,
    ) -> dict:
        """Create a mock validation result with optional schema errors."""
        return {
            "verification_summary": {
                "completeness_score": completeness,
                "accuracy_score": accuracy,
                "schema_compliance_score": schema_compliance,
                "critical_issues": critical_issues,
                "overall_status": "passed" if critical_issues == 0 else "failed",
            },
            "schema_validation": {
                "quality_score": schema_quality,
                "validation_errors": schema_errors or [],
            },
        }

    def test_correction_hints_injected_after_rollback(self):
        """After rollback, _correction_hints should be injected into validation."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        # Initial validation: below threshold but acceptable
        validation_initial = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.86
        )
        # First correction degrades quality
        validation_degraded = self._create_validation_result(
            completeness=0.75, accuracy=0.80, schema_compliance=0.50,
            schema_errors=["orcid: '' violates pattern", "issn: '' violates pattern"],
        )
        # Second correction (after rollback with hints) improves quality
        validation_improved = self._create_validation_result(
            completeness=0.92, accuracy=0.96, schema_compliance=0.97,
        )

        validate_fn = MagicMock(
            side_effect=[validation_initial, validation_degraded, validation_improved]
        )

        # Track what correct_fn receives
        correct_calls = []

        def mock_correct(extraction, validation):
            correct_calls.append({"extraction": extraction, "validation": validation})
            return {"data": "corrected"}

        correct_fn = MagicMock(side_effect=mock_correct)

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        runner.run()

        # After rollback, the second correct_fn call should have _correction_hints
        assert len(correct_calls) >= 2
        second_validation = correct_calls[1]["validation"]
        assert "_correction_hints" in second_validation
        assert "orcid" in second_validation["_correction_hints"]
```

**Step 2: Run test to verify it fails**

Run: `make test-fast`
Expected: FAIL — `_correction_hints` not injected

**Step 3: Implement hints injection in loop_runner.py**

In `src/pipeline/iterative/loop_runner.py`, modify the `run()` method:

After `correction_retry_count = 0` (line 272), add:
```python
        previous_failure_hints: str | None = None
```

In the rollback branch (around line 454-475), after `"reverting to best iteration for next attempt"`, add:
```python
                    # Build failure hints from the degraded correction's schema errors
                    degraded_errors = corrected_validation.get("schema_validation", {}).get("validation_errors", [])
                    if degraded_errors:
                        # Summarize up to 5 unique error paths
                        error_summary = "; ".join(degraded_errors[:5])
                        previous_failure_hints = (
                            f"PREVIOUS CORRECTION FAILED. It introduced these schema errors: "
                            f"{error_summary}. Do NOT repeat these mistakes. "
                            f"Omit optional fields if you don't have valid values."
                        )
```

Before calling `self.correct_fn` (around line 393), inject hints into the validation:
```python
                # Inject correction hints if available from previous failure
                correction_validation = validation_result
                if previous_failure_hints:
                    correction_validation = {**validation_result, "_correction_hints": previous_failure_hints}

                correction_output = self.correct_fn(current_result, correction_validation)
```

Also clear hints on successful correction (after `last_good_result = corrected_result`):
```python
                    previous_failure_hints = None  # Reset hints on success
```

**Step 4: Implement reading hints in correction step**

In `src/pipeline/steps/validation.py`, in `run_correction_step()`, after building `correction_context` (around line 326), add:

```python
        # Inject previous failure hints if available
        correction_hints = validation_clean.get("_correction_hints", "")
        if correction_hints:
            correction_context += f"\n\nPREVIOUS_CORRECTION_FAILURES: {correction_hints}\n"
```

**Step 5: Run tests**

Run: `make test-fast`
Expected: All PASS

**Step 6: Format and lint**

Run: `make format && make lint`

**Step 7: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py src/pipeline/steps/validation.py tests/unit/test_loop_runner.py
git commit -m "fix: inject previous-failure hints into correction retries after rollback"
```

---

### Task 6: Add stuck loop early exit

**Files:**
- Modify: `src/pipeline/iterative/loop_runner.py`
- Test: `tests/unit/test_loop_runner.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_loop_runner.py`:

```python
from src.pipeline.iterative.loop_runner import FINAL_STATUS_EARLY_STOPPED


class TestStuckLoopEarlyExit:
    """Test early exit when consecutive corrections all degrade quality."""

    def _create_validation_result(
        self,
        completeness: float = 0.95,
        accuracy: float = 0.98,
        schema_compliance: float = 0.97,
        critical_issues: int = 0,
        schema_quality: float = 1.0,
    ) -> dict:
        return {
            "verification_summary": {
                "completeness_score": completeness,
                "accuracy_score": accuracy,
                "schema_compliance_score": schema_compliance,
                "critical_issues": critical_issues,
                "overall_status": "passed" if critical_issues == 0 else "failed",
            },
            "schema_validation": {
                "quality_score": schema_quality,
            },
        }

    def test_early_exit_after_consecutive_rollbacks(self):
        """Loop exits early after 2 consecutive rollbacks instead of burning iterations."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=5,  # High limit to prove early exit works
            show_banner=False,
        )

        validation_initial = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.86
        )
        # All corrections degrade
        validation_degraded = self._create_validation_result(
            completeness=0.70, accuracy=0.78, schema_compliance=0.50
        )

        validate_fn = MagicMock(
            side_effect=[validation_initial, validation_degraded, validation_degraded]
        )
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        assert result.final_status == FINAL_STATUS_EARLY_STOPPED
        # Should exit after 2 rollbacks, not run all 5 iterations
        assert correct_fn.call_count == 2

    def test_no_early_exit_when_corrections_improve(self):
        """Loop continues normally when corrections improve quality."""
        config = IterativeLoopConfig(
            metric_type=MetricType.EXTRACTION,
            max_iterations=3,
            show_banner=False,
        )

        validation_initial = self._create_validation_result(
            completeness=0.80, accuracy=0.85, schema_compliance=0.86
        )
        validation_better = self._create_validation_result(
            completeness=0.85, accuracy=0.90, schema_compliance=0.92
        )
        validation_degraded = self._create_validation_result(
            completeness=0.70, accuracy=0.78, schema_compliance=0.50
        )
        validation_even_better = self._create_validation_result(
            completeness=0.92, accuracy=0.96, schema_compliance=0.97
        )

        validate_fn = MagicMock(
            side_effect=[validation_initial, validation_better, validation_degraded, validation_even_better]
        )
        correct_fn = MagicMock(return_value={"data": "corrected"})

        runner = IterativeLoopRunner(
            config=config,
            initial_result={"data": "test"},
            validate_fn=validate_fn,
            correct_fn=correct_fn,
        )
        result = runner.run()

        # Should NOT early exit — improvement at iter 1 resets counter
        assert result.final_status == FINAL_STATUS_PASSED
```

**Step 2: Run tests to verify they fail**

Run: `make test-fast`
Expected: `test_early_exit_after_consecutive_rollbacks` FAILS

**Step 3: Implement stuck detection**

In `src/pipeline/iterative/loop_runner.py`, in the `run()` method:

After `previous_failure_hints: str | None = None` (added in Task 5), add:
```python
        consecutive_rollbacks = 0
        max_consecutive_rollbacks = 2
```

In the quality-improved branch (around line 445-449), add:
```python
                    consecutive_rollbacks = 0  # Reset on successful correction
```

In the quality-degraded branch (around line 454-475), add after `previous_failure_hints = ...`:
```python
                    consecutive_rollbacks += 1
                    if consecutive_rollbacks >= max_consecutive_rollbacks:
                        self.console.print(
                            f"\n[yellow]⚠️ {consecutive_rollbacks} consecutive corrections "
                            f"degraded quality. Stopping early.[/yellow]"
                        )
                        return self._create_early_stop_result()
```

**Step 4: Update the existing test expectation**

The existing test `test_max_iterations_when_all_corrections_degrade` (in `tests/unit/test_loop_runner.py`) expects `FINAL_STATUS_MAX_ITERATIONS` but will now get `FINAL_STATUS_EARLY_STOPPED`. Update its assertion:

```python
# Was:
assert result.final_status == FINAL_STATUS_MAX_ITERATIONS
# Now:
assert result.final_status == FINAL_STATUS_EARLY_STOPPED
```

And update the `correct_fn.call_count` expectation — with early exit after 2 rollbacks, it should only be called twice:

Check the existing test and adjust accordingly.

**Step 5: Run tests**

Run: `make test-fast`
Expected: All PASS

**Step 6: Format and lint**

Run: `make format && make lint`

**Step 7: Commit**

```bash
git add src/pipeline/iterative/loop_runner.py tests/unit/test_loop_runner.py
git commit -m "fix: early exit correction loop after 2 consecutive quality degradations"
```

---

### Task 7: Update CHANGELOG and documentation

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add changelog entry**

Under `## [Unreleased]` > `### Changed`, add:

```markdown
- Correction loop improvements: deterministic repair for pattern/minimum/enum constraint violations,
  proportional schema scoring (replaces binary pass/fail cliff), explicit empty-string omission rule
  in correction prompt, previous-failure context injected into correction retries, and early exit
  after consecutive quality degradations
```

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add correction loop improvements changelog entry"
```

---

### Task 8: Final verification

**Step 1: Run full test suite**

Run: `make test-fast`
Expected: All tests PASS

**Step 2: Run format + lint**

Run: `make format && make lint`
Expected: Clean

---

Plan complete and saved to `docs/plans/2026-02-17-correction-loop-improvements-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
