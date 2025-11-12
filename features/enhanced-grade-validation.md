# Enhanced GRADE Validation

> Status: Draft (planning)
> Priority: Medium
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
| Imprecision | effect size, 95% CI bounds, MID threshold | event counts, sample size | Triggers when CI crosses MID or is wide relative to effect. |
| Inconsistency | I², model type (fixed/random), number of studies | tau², Cochran Q | Define threshold tiers (≥50% warning, ≥75% high). |
| Publication bias | qualitative summary (`funnel_plot_flag`, Egger p-value) | number of small studies | Accepts reviewer flag when no stats available. |
| Directness | population/setting match indicators, MID metadata | outcome classification | Flags extrapolations outside target population. |
| Effect size sanity | reported effect vs extraction metrics | measurement units | Ensures appraisal references actual extracted numbers. |

2. **Deterministic Validation Engine**
   - Execute rule library inside the appraisal-validation step (not via LLM).
   - Extend `appraisal_validation.schema.json` to capture additional signals (heterogeneity stats, MID info, publication bias summary, `grade_checks`).
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
5. Correction prompt consumes findings (instructions/sections updated).
6. New unit + integration tests cover rule triggers and schema updates.

## Testing Strategy

- Unit tests for rule evaluation helpers (deterministic inputs → expected flags).
- Schema compatibility tests (ensure additional fields remain OpenAI-compliant).
- Integration tests: simulated appraisal JSON failing each rule yields validation warnings.
- Prompt validation: ensure new placeholders added to appraisal correction prompt.

## Open Questions

1. Source of MID thresholds (global default vs per outcome metadata)?
2. How to capture funnel plot assessments without images?
3. Should we allow multiple evidence types (continuous vs binary effects) with distinct rules?
4. How to encode rule overrides when the LLM provides adequate justification?

## Next Steps

1. Align with clinical SME on acceptable default thresholds.
2. Design JSON schema updates & rule configuration format (registry structure, per-rule data requirements).
3. Prototype rule evaluator with mocked appraisal/extraction data.
4. Update prompts and validation logic; add regression tests.
5. Validate end-to-end (schema → validator → prompt feedback) before rollout.
