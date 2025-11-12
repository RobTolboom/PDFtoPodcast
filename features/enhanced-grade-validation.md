# Enhanced GRADE Validation

> Status: Draft (planning)
> Priority: Medium
> Branch: `feature/enhanced-grade-validation`
> Parent Feature: `features/appraisal.md`
> Reference: features/appraisal.md §2 (Prompt Architecture → Appraisal validation future enhancement note, lines ~220-239)

## Goal & Motivation

Strengthen the appraisal validation step with rule-based checks for GRADE assessments. The current validator enforces basic consistency (e.g., RoB “High risk” triggers a downgrade), but does not verify quantitative evidence (CI width, MID thresholds, heterogeneity, publication bias). The enhanced module should provide deterministic safeguards before the LLM output is accepted.

## Scope

1. **Modular Rule Library**
   - Single Python module with shared helpers + study/tool-specific rule registries (RoB2, ROBINS-I, AMSTAR 2, PROBAST, etc.).
   - Map quantitative cues to GRADE downgrades:
     - Wide confidence intervals / low event counts → imprecision
     - High heterogeneity (I² thresholds) → inconsistency
     - MID (Minimal Important Difference) interpretation → directness
     - Funnel plot or small-study effect signals → publication bias
   - Store rule metadata (threshold, rationale, remediation hint, severity) for traceability.
   - Document required data feeds per rule (e.g., effect size + CI + MID for imprecision, I² + model type for inconsistency, funnel-plot summary flags for publication bias) so schema/extraction updates are explicit.
   - Rule configuration lives in a structured registry (Python dataclasses or JSON/YAML) to keep thresholds editable without touching core logic.
   - Severity ladder: `info` (advisory), `warning` (should downgrade), `error` (blocker unless override rationale provided).

### Rule Input Matrix (draft)

| Rule | Required Inputs | Optional Inputs | Notes |
| --- | --- | --- | --- |
| Imprecision | effect size, 95% CI bounds, MID threshold (per outcome or default) | event counts, sample size | Triggers when CI crosses MID or is wide relative to effect; falls back to outcome-class default MID if per-outcome value missing. |
| Inconsistency | I², model type (fixed/random), number of studies | tau², Cochran Q | Define threshold tiers (≥50% warning, ≥75% high). |
| Publication bias | structured signal: `qualitative_flag`, `egger_p_value` or other proxy | number of small studies | Accepts reviewer flag when no stats available; schema gets `publication_bias_signal` object. |
| Directness | population/setting match indicators, MID metadata | outcome classification | Flags extrapolations outside target population. |
| Effect size sanity | reported effect vs extraction metrics | measurement units | Ensures appraisal references actual extracted numbers. |

2. **Deterministic Validation Engine**
   - Execute rule library inside the appraisal-validation step (Tier 2a, before the LLM-driven validation).
   - Extend `appraisal_validation.schema.json` to capture additional signals (heterogeneity stats, MID info, publication bias summary, `grade_validation_signals`, `grade_checks`, `grade_validation_version`).
   - Gate every rule behind explicit input checks; missing data yields “data_insufficient” warnings instead of crashes.
   - Emit structured findings persisted in the iteration validation JSON (e.g., `iterations[i]["validation"]["grade_checks"]`).
   - Avoid mutating `*-appraisal-best.json`; keep findings tied to validation artifacts until an iteration passes.

3. **LLM Feedback Loop**
   - Feed structured violations into the appraisal correction prompt (new placeholder/section).
   - Use findings as advisory input; LLM still supplies narrative corrections but cannot bypass rule severity without rationale.

## Out of Scope (Deferred)

- Automated funnel-plot analysis (requires image parsing).
- Dynamic estimation of MID per outcome (needs clinician input).
- UI visualization of GRADE rule hits.

## Dependencies

- `appraisal.schema.json` / `appraisal_validation.schema.json`
- `prompts/Appraisal-validation.txt` & `prompts/Appraisal-correction.txt`
- Iterative validation-correction pipeline (Step 3).

## Integration Architecture

| Tier | Component | Purpose | Notes |
| --- | --- | --- | --- |
| 1 | Schema validation | Structure + type checks | Existing JSON Schema validation step. |
| 2a | **Rule-based GRADE validation (new)** | Deterministic quantitative safeguards | Runs once schema valid; emits `grade_checks` + `grade_validation_signals`. |
| 2b | LLM appraisal validation | Narrative/semantic QA | Receives rule findings as structured context; can justify overrides. |
| 3 | Correction loop | LLM fixes issues & re-validates | Rule findings feed into correction prompt to ensure issues addressed. |

Rules fail fast: when Tier 2a surfaces `error` severities the pipeline halts before expensive Tier 2b calls. `warning` findings allow Tier 2b to continue but must be justified. Tier 3 only runs if Tier 2b passes or produces actionable corrections referencing the deterministic findings.

## Schema Extensions

`appraisal_validation.schema.json` additions (all optional to preserve backward compatibility):

- `grade_validation_version` (string enum: `"v1.0"` LLM-only, `"v2.0"` LLM + deterministic).
- `grade_validation_signals` object mirroring extraction metrics used by rules:
  - `ci_width_vs_mid_ratio` (number)
  - `i2_threshold_exceeded` (boolean)
  - `small_study_effect_detected` (boolean)
  - `event_count_per_arm` (object `{intervention, control}`)
  - `funnel_inspection_flag` (enum)
- `grade_checks` array of findings:

```json
{
  "rule_id": "IMP-001",
  "domain": "imprecision",
  "severity": "error",
  "recommended_downgrade": 2,
  "finding": "CI 0.62-1.41 crosses null and MID",
  "remediation_hint": "Downgrade 2 levels for imprecision",
  "supporting_data": {"ci_lower": 0.62, "ci_upper": 1.41, "mid_range": "0.75-1.25"},
  "override_reason": null
}
```

No changes needed to `appraisal.schema.json` beyond reusing existing `I2_pct`, `tau2`, `egger_p_value`, and `funnel_inspection`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Over-constraining LLM output | False negatives, excessive corrections | Make rules advisory with severity levels; allow overrides when rationale is explicit. |
| Medical nuance of MID thresholds | Incorrect downgrade flags | Encode conservative defaults and mark as “needs clinical review” in findings. |
| Schema bloat | Larger token footprint | Keep new fields optional and reuse existing structures when possible. |
| Missing input signals | Script errors, incomplete checks | Add per-rule guards + “data_insufficient” findings; rely on schema to flag mandatory data. |

## Acceptance Criteria & Success Metrics

1. Appraisal validation step surfaces structured findings for:
   - Imprecision (CIs vs MID)
   - Inconsistency (I² thresholds)
   - Publication bias indicators
   - Confidence interval interpretation for effect sizes
2. Validator never raises on missing inputs; each skipped rule outputs a `data_insufficient` entry.
3. Every downgrade suggested by the validator appears in `grade_checks` with severity + remediation hint.
4. Validation findings persisted in iteration artifacts.
5. Correction prompt consumes findings (instructions/sections updated) and differentiates between rule severities.
6. `grade_validation_version` recorded for every run to distinguish LLM-only vs combined validation.
7. New unit + integration tests cover rule triggers, schema updates, and prompt placeholders.

## Rule Library Format

```python
@dataclass(frozen=True)
class GRADERule:
    rule_id: str
    domain: Literal["imprecision", "inconsistency", "publication_bias", "directness", "effect_sanity"]
    severity: Literal["info", "warning", "error"]
    condition: Callable[[dict], bool]
    recommended_downgrade: int
    rationale_template: str
    remediation_hint: str


IMPRECISION_CI_CROSSES_NULL = GRADERule(
    rule_id="IMP-001",
    domain="imprecision",
    severity="error",
    condition=lambda data: (
        data["ci_lower"] < 1.0 < data["ci_upper"]
        and (data["ci_lower"] < 0.75 or data["ci_upper"] > 1.25)
    ),
    recommended_downgrade=2,
    rationale_template="CI {ci_lower}-{ci_upper} crosses null and exceeds MID bounds (0.75-1.25).",
    remediation_hint="Downgrade by 2 levels for imprecision unless MID justification provided."
)
```

Rule registries live in `src/grade_rules.py`, exposing `GRADE_RULES = {"dichotomous": [...], "continuous": [...]}` so providers can register tool-specific variants without touching the evaluator.

## Testing Strategy

- **Unit fixtures**:
  - `tests/fixtures/rct_wide_ci.json` → MD -0.5 (CI -2.1 to 1.1, MID 1.0) ⇒ triggers `IMP-001` downgrade 2.
  - `tests/fixtures/meta_high_i2.json` → `I2_pct`: 78, `tau2`: 0.15 ⇒ triggers `INC-001` downgrade 2.
  - `tests/fixtures/funnel_asymmetry.json` → `funnel_inspection`: "asymmetrical", `egger_p_value`: 0.04 ⇒ `PUB-002` warning.
  - `tests/fixtures/low_events.json` → event counts < 100 total ⇒ `IMP-003` info advisory.
- **Schema tests**: validate new optional fields with `make check` and ensure `grade_validation_version` defaults to `"v1.0"` when field absent.
- **Integration tests**: run deterministic validator on sample appraisal JSON; assert `grade_checks` appended to `iterations[i].validation`.
- **Prompt tests**: confirm `prompts/Appraisal-correction.txt` consumes `{{grade_checks}}` placeholder and LLM instructions mention deterministic overrides.

## Design Decisions

1. **MID thresholds**: Use GRADE handbook defaults (`RR 0.75-1.25` for dichotomous, `0.5 SD` for continuous). When outcome-level `mid_threshold` present, prefer it; otherwise log `needs_clinical_review` flag in findings.
2. **Funnel plot assessments**: Reuse `extraction.synthesis_quality.funnel_inspection` and `egger_p_value`. Rule triggers when funnel flag is `"asymmetrical"` **and** `egger_p_value < 0.10`. No image parsing required.
3. **Evidence-type scope**: Phase 1 supports dichotomous outcomes; continuous outcomes reuse CI width rule with generic MID default. Time-to-event outcomes slated for Phase 2.
4. **LLM override handling**: `grade_checks[].override_reason` stores LLM justifications. Validator downgrades severity from `error`→`warning` when override length ≥ 30 chars and references clinical rationale keywords (e.g., “MID consensus”, “subgroup”).

## Implementation Phases

### Phase 1: Rule Library Definition (Ready)
- Deliverables:
  - `src/grade_rules.py` dataclasses + default thresholds.
  - `tests/unit/test_grade_rules.py` covering ≥1 rule per GRADE domain.
- Acceptance:
  - Registry exposes dichotomous rules with thresholds configurable via constants.

### Phase 2: Deterministic Checker Implementation
- Deliverables:
  - `src/pipeline/grade_validator.py` with evaluation engine.
  - Wiring into validation runner between schema and LLM validation.
  - Integration fixtures covering imp/red/het scenarios.
- Acceptance:
  - Rule checker executes < 2s per appraisal.
  - Emits `grade_checks` + `grade_validation_version="v2.0"`.

### Phase 3: LLM Feedback Integration
- Deliverables:
  - Update `prompts/Appraisal-correction.txt` with `grade_checks` placeholder.
  - Orchestrator passes findings into correction step.
  - End-to-end test verifying LLM references deterministic issues.
- Acceptance:
  - Correction loop resolves rule violations or supplies override reason.

### Phase 4: Documentation & Rollout
- Deliverables:
  - `docs/appraisal.md` section on deterministic rules.
  - README + ARCHITECTURE updates.
  - CHANGELOG entry under “Unreleased”.
- Acceptance:
  - Feature flag `--enable-grade-rules` documented; default rollout plan approved.

## Backward Compatibility

- Legacy appraisals (LLM-only) remain valid; no forced re-validation.
- CLI flag `--enable-grade-rules` opts into deterministic checks until rollout complete.
- `grade_validation_version` clarifies whether Tier 2a ran.
- New schema fields optional; absence interpreted as `"v1.0"`.

## Performance Considerations

| Validation Type | Expected Time | Coverage | Role |
| --- | --- | --- | --- |
| Schema validation | < 1s | Structural | Fast failure on malformed data. |
| **Rule-based GRADE** | **~2s** | Quantitative | Catch obvious inconsistencies before LLM. |
| LLM validation | ~15s | Semantic + narrative | Deep appraisal reasoning. |
| Correction loop | ~15s per iteration | Remediation | Applies fixes informed by `grade_checks`. |

Fail-fast behavior reduces LLM spend by halting when deterministic “error” findings occur.

## Change Management Checklist

- [ ] Update `CHANGELOG.md` (Unreleased).
- [ ] Update `ARCHITECTURE.md` diagram of validation cascade.
- [ ] Update `README.md` with deterministic rules overview.
- [ ] Update `API.md` / `VALIDATION_STRATEGY.md` for new module.
- [ ] Add new tests (unit + integration) and ensure `make test-fast` passes.
- [ ] Attach feature plan link into `features/appraisal.md`.
