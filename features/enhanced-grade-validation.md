# Enhanced GRADE Validation

> Status: Draft (planning)
> Priority: Medium
> Reference: features/appraisal.md §2 (Prompt Architecture → Appraisal validation future enhancement note, lines ~220-239)

## Goal & Motivation

Strengthen the appraisal validation step with rule-based checks for GRADE assessments. The current validator enforces basic consistency (e.g., RoB “High risk” triggers a downgrade), but does not verify quantitative evidence (CI width, MID thresholds, heterogeneity, publication bias). The enhanced module should provide deterministic safeguards before the LLM output is accepted.

## Scope

1. **Rule Library**
   - Map quantitative cues to GRADE downgrades:
     - Wide confidence intervals / low event counts → imprecision
     - High heterogeneity (I² thresholds) → inconsistency
     - MID (Minimal Important Difference) interpretation → directness
     - Funnel plot or small-study effect signals → publication bias
   - Provide machine-interpretable rule metadata (threshold, rationale, remediation hint).

2. **Validation Engine**
   - Extend `appraisal_validation.schema.json` to capture additional signals (e.g., heterogeneity stats, MID info, publication bias summary).
   - Deterministic checker that compares appraisal JSON against the rule library and extraction context.
   - Emit structured validation findings (severity, domain, recommended downgrade).

3. **LLM Feedback Loop**
   - Feed rule violations back into the appraisal correction prompt (“GRADE assistance module”).
   - Highlight conflicting evidence to guide LLM revisions.

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

## Acceptance Criteria

1. Appraisal validation step surfaces structured findings for:
   - Imprecision (CIs vs MID)
   - Inconsistency (I² thresholds)
   - Publication bias indicators
   - Confidence interval interpretation for effect sizes
2. Validation findings persisted in iteration artifacts.
3. Correction prompt consumes findings (instructions/sections updated).
4. New unit + integration tests cover rule triggers and schema updates.

## Testing Strategy

- Unit tests for rule evaluation helpers (deterministic inputs → expected flags).
- Schema compatibility tests (ensure additional fields remain OpenAI-compliant).
- Integration tests: simulated appraisal JSON failing each rule yields validation warnings.
- Prompt validation: ensure new placeholders added to appraisal correction prompt.

## Open Questions

1. Source of MID thresholds (global default vs per outcome metadata)?
2. How to capture funnel plot assessments without images?
3. Should we allow multiple evidence types (continuous vs binary effects) with distinct rules?

## Next Steps

1. Align with clinical SME on acceptable default thresholds.
2. Design JSON schema updates & rule configuration format.
3. Prototype rule evaluator with mocked appraisal/extraction data.
4. Update prompts and validation logic; add regression tests.
