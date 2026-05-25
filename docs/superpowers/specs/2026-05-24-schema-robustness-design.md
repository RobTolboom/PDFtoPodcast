# Schema Robustness Improvements — Design Spec

**Date:** 2026-05-24
**Status:** Approved
**Motivation:** Pipeline run on `s12871-026-03928-3` hit `max_iterations_reached` with schema compliance 86.7 % (threshold 95 %) due to three structural schema mismatches and two `schema_repair.py` gaps. A false-positive warning in the podcast abbreviation checker was also identified.

---

## Goals

1. Raise schema compliance so this class of paper passes within the correction budget.
2. Make `schema_repair.py` catch more deterministic issues before wasting a correction iteration.
3. Fix the podcast abbreviation false-positive.

## Out of Scope

- Changing the correction budget (max 3 iterations).
- Changes to prompt templates.
- New extraction fields beyond what is described here.

---

## Change 1 — `common.schema.json`: Allow depth-1 objects in `FigureSummary.key_values`

### Problem

`FigureSummary.key_values` currently allows only `number | string` as values. LLMs correctly extract CONSORT exclusion-reason breakdowns as nested dicts:

```json
"exclusion_reasons": {
  "severe_lung_disease": 65,
  "active_infection": 32,
  "hypersensitivity": 15,
  "other": 8
}
```

This causes a critical schema validation error that persists through all correction iterations because the data is semantically correct — only the schema is too narrow.

### Fix

Extend `additionalProperties` in `FigureSummary.key_values` to accept a third `oneOf` branch: a plain object whose own values are `number | string`. This permits one level of nesting while keeping deeper nesting invalid.

```json
"key_values": {
  "type": "object",
  "additionalProperties": {
    "oneOf": [
      { "type": "number" },
      { "type": "string" },
      {
        "type": "object",
        "description": "Categorical breakdown (e.g. CONSORT exclusion reasons). Values must be scalars.",
        "additionalProperties": {
          "oneOf": [
            { "type": "number" },
            { "type": "string" }
          ]
        }
      }
    ]
  },
  "default": {}
}
```

### Scope

`FigureSummary` lives in `common.schema.json` and is referenced by all five publication-type schemas. After running `make bundle-schemas`, all five `*_bundled.json` files pick up the change automatically.

---

## Change 2 — `interventional_trial.schema.json` + `observational_analytic.schema.json`: Make `ContrastResult.effect` optional

### Problem

Both schemas define `ContrastResult` with `"required": ["outcome_id", "comparison_id", "effect"]`. When a paper reports only a narrative significance statement for a secondary outcome (e.g. "30-day mortality: no significant difference, P>0.05") — with no event counts and no effect size — the LLM adds a contrast with:

```json
"effect": { "p_value": ">0.05", "favors": "neutral" }
```

`ContrastEffect` requires `type` and `point`, so this effect object is invalid. Because `effect` is required, `schema_repair.py` cannot remove it (required fields are never removed). The validation error causes a correction regression and revert.

### Fix

Remove `effect` from `required` in `ContrastResult` in both schemas. Add a guiding description to maintain LLM behaviour when effect data does exist:

```json
"effect": {
  "$ref": "#/$defs/ContrastEffect",
  "description": "Include when the paper reports a quantified effect estimate (RR, OR, HR, MD, etc.). Omit when only a p-value or narrative significance statement is available with no point estimate."
}
```

`ContrastResult.required` becomes `["outcome_id", "comparison_id"]` in both files.

### Why existing `schema_repair.py` is sufficient

`_repair_object` (lines 196–206) already removes optional fields whose value is an object missing required sub-fields. Once `effect` is optional, a partial `{p_value, favors}` object (missing `type` and `point`) is automatically removed during repair — no new repair code needed for this case.

### Scope

Only `interventional_trial.schema.json` and `observational_analytic.schema.json` have `ContrastResult` with `effect` in `required`. The other three publication-type schemas are unaffected.

---

## Change 3 — `schema_repair.py`: Three additions

### 3a. `schema_version` normalisation

**Problem:** LLM outputs `schema_version: "v2"` which fails the pattern `^v\d+\.\d+(\.\d+)?$`. `schema_version` is a required field, so `_violates_constraints` skips it (required fields are never removed). The fix is applied in the LLM correction loop, wasting one iteration.

**Fix:** Add a normalisation step at the top of `repair_schema_violations`, before any recursive repair. If `schema_version` matches `^v\d+$` (major-only, no dot), append `.0`:

```python
def _normalize_schema_version(data: dict[str, Any]) -> None:
    """Normalise bare major-only schema_version (e.g. 'v2' → 'v2.0')."""
    sv = data.get("schema_version", "")
    if isinstance(sv, str) and re.match(r"^v\d+$", sv):
        data["schema_version"] = sv + ".0"
        logger.info("Normalised schema_version: %s -> %s", sv, data["schema_version"])
```

Called in `repair_schema_violations` on the result copy before `_repair_object`.

### 3b. Drop malformed JSON-fragment strings in arrays

**Problem:** In the initial extraction, `interventions[1]` was the string `ontology_terms":[{` — a truncated JSON fragment left when the LLM's output was cut mid-object. `_repair_array` tries to look it up as an ID in the original extraction; it fails the lookup and keeps the string, which then fails schema validation.

**Fix:** In `_repair_array`, before the existing ID-restore logic, detect strings that look like JSON fragments (contain any of `"`, `{`, `[`, `:`) and drop them with a warning:

```python
elif isinstance(item, str) and id_field:
    if any(c in item for c in ('"', '{', '[', ':')):
        logger.warning("Dropping malformed JSON fragment in array: %r", item[:60])
        # do not append — item is dropped
    elif item in original_lookup:
        ...  # existing restore logic
```

This is safe: a valid string ID will never contain these characters.

### 3c. Depth-2+ flattening in `FigureSummary.key_values`

**Problem:** Change 1 permits depth-1 objects in `key_values`. Depth-2+ nesting (an object whose values are themselves objects) remains invalid and could appear if the LLM over-nests.

**Fix:** Add a post-repair pass in `repair_schema_violations` that walks `figures_summary[*].key_values` and flattens any value that is itself a dict whose values contain further dicts. Depth-1 objects are left untouched. Flattening uses `_` as the key separator:

```
{ "breakdown": { "a": { "x": 1 } } }
→ { "breakdown_a_x": 1 }
```

Implementation as a standalone `_flatten_key_values_depth2(figures_summary)` function, called after `_repair_object` when `figures_summary` is present in the data.

---

## Change 4 — `podcast_logic.py`: Fix abbreviation false-positive

### Problem

The abbreviation checker uses `re.IGNORECASE`, so the English conjunction "or" matches the medical abbreviation "OR" (Odds Ratio). The transcript used "or" ~15 times as a conjunction. This produces a spurious `warnings` status and a misleading issue entry, even though the podcast is TTS-ready.

### Fix

Remove `re.IGNORECASE` from the abbreviation search. Medical abbreviations like OR, CI, HR are capitalised when used as abbreviations; the conjunction "or" is not. Case-sensitive matching eliminates the false positive without affecting true positives.

```python
# Before
re.search(rf"\b{re.escape(abbr)}\b", transcript, re.IGNORECASE)

# After
re.search(rf"\b{re.escape(abbr)}\b", transcript)
```

---

## Bundling & Commit Sequence

1. Edit `common.schema.json` (Change 1).
2. Edit `interventional_trial.schema.json` and `observational_analytic.schema.json` (Change 2).
3. Edit `schema_repair.py` (Change 3a, 3b, 3c).
4. Edit `podcast_logic.py` (Change 4).
5. Run `cd schemas && python json-bundler.py` to regenerate all 5 bundled schemas.
6. Run `make format && make lint && make test-fast`.
7. Run `make commit` (pre-commit hooks may fix trailing newlines — run twice if needed).
8. Commit on a feature branch: `fix: schema robustness — key_values depth-1, optional effect, repair gaps, podcast abbr`.

---

## Testing

### Unit tests to add / update

| Test | What it covers |
|---|---|
| `test_figure_summary_key_values_nested_object` | Schema validates depth-1 object values in `key_values` |
| `test_figure_summary_key_values_depth2_rejected` | Schema rejects depth-2 object values |
| `test_schema_repair_flattens_depth2_key_values` | `schema_repair` flattens depth-2 `key_values` correctly |
| `test_schema_repair_normalizes_schema_version` | `v2` → `v2.0`, `v1` → `v1.0`; `v2.0` unchanged |
| `test_schema_repair_drops_json_fragment_string` | Malformed fragment string removed from array |
| `test_contrast_result_effect_optional` | ContrastResult valid without `effect` |
| `test_schema_repair_removes_partial_effect` | Partial `effect` (no `type`/`point`) removed by repair |
| `test_podcast_abbreviation_case_sensitive` | "or" no longer flagged; "OR" still flagged |

### Acceptance criterion

Re-running the pipeline on `s12871-026-03928-3_reference3.pdf` should complete with schema compliance ≥ 95 % and no `max_iterations_reached` warning. Podcast status should be `passed` (not `warnings`).

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Making `effect` optional causes LLMs to omit effect sizes when data exists | Low | Description field explicitly states when to include |
| Depth-1 `key_values` objects cause downstream renderer issues | Low | Renderers already handle `key_values` values generically; depth-1 objects render as nested sub-lists |
| Case-sensitive abbreviation check misses true abbreviation OR | Very low | "OR" as Odds Ratio is always written in capitals in medical text |
