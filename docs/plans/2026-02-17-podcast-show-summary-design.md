# Podcast Show Summary — Design Document

**Date:** 2026-02-17
**Status:** Approved
**Branch:** feature/podcast-show-summary

## Goal

Add a "show summary" to the podcast generation step that produces a plain-text episode companion: a full citation, a 2-3 sentence narrative synopsis, and structured "Study at a glance" bullet points with numerical detail the audio transcript deliberately omits.

The summary serves two purposes:
1. **Podcast app episode description** (Apple Podcasts, Spotify) — the synopsis hooks listeners
2. **Web companion / clinical quick-reference** — the structured bullets give clinicians the numbers

## Approach

**Approach A (selected):** Extend the existing podcast schema with an optional `show_summary` object. Generate it via a second LLM call within the existing `run_podcast_generation()` step. No new pipeline step.

**Alternatives considered:**
- Separate schema + separate files — overkill, summary is logically part of the podcast episode
- Summarize transcript only — loses numerical detail that is the whole point

## Schema

Add optional `show_summary` to `schemas/podcast.schema.json`:

```json
"show_summary": {
  "type": "object",
  "required": ["citation", "synopsis", "study_at_a_glance"],
  "additionalProperties": false,
  "properties": {
    "citation": {
      "type": "string",
      "description": "Full bibliographic reference in Vancouver/NLM style"
    },
    "synopsis": {
      "type": "string",
      "description": "2-3 sentence narrative summary for podcast app episode descriptions",
      "minLength": 50,
      "maxLength": 500
    },
    "study_at_a_glance": {
      "type": "array",
      "description": "Structured bullet points with label and content",
      "minItems": 3,
      "maxItems": 10,
      "items": {
        "type": "object",
        "required": ["label", "content"],
        "additionalProperties": false,
        "properties": {
          "label": {
            "type": "string",
            "description": "Category label, e.g. 'Design and setting', 'Primary outcome'"
          },
          "content": {
            "type": "string",
            "description": "Full text including numbers, CIs, p-values, GRADE certainty"
          }
        }
      }
    }
  }
}
```

Key decisions:
- Optional field for backward compatibility
- `study_at_a_glance` as array of label/content objects — flexible per study type
- `citation` formatted by the LLM from extraction metadata
- `synopsis` bounded at 50-500 chars

## Prompt

New file: `prompts/Podcast-summary.txt`

**Inputs to the LLM:**
- Extraction JSON (numbers, metadata, outcomes)
- Appraisal JSON (RoB, GRADE ratings)
- Classification result (study type)
- Generated transcript (so synopsis can reference what was discussed)

**Instructions:**
- Generate Vancouver-style citation from extraction metadata
- Write 2-3 sentence synopsis that hooks the reader and summarizes the key finding
- Produce study-at-a-glance bullets adapted to study type:
  - RCT: Design/setting, Population, Interventions, Primary outcome, Key secondary, Safety, RoB/GRADE
  - Observational: Design/setting, Population, Exposure/comparator, Primary outcome, Key secondary, Confounding, RoB/GRADE
  - Systematic review: Design/setting, Search/inclusion, Pooled estimate, Heterogeneity, Key secondary, RoB/GRADE
  - Prediction/prognosis: Design/setting, Population, Model/predictors, Discrimination/calibration, RoB/GRADE
  - Editorial: minimal synopsis only (no structured bullets)
- Include exact numbers (ORs, CIs, p-values, MDs) from extraction — no rounding
- Include GRADE certainty inline with outcomes
- RoB summary in the final bullet
- Synopsis language must match GRADE certainty (same verb calibration as transcript)

## Generation Flow

Within `run_podcast_generation()`:

1. Generate transcript (existing first LLM call)
2. Validate transcript (existing)
3. Generate show summary (new second LLM call, `Podcast-summary.txt`)
4. Validate show summary (new light validation)
5. Merge `show_summary` into podcast JSON
6. Save files

Transcript and summary generation are independent: a failed summary does not fail the podcast step.

## Validation

**Critical checks (hard fail for summary):**
- Schema compliance
- Synopsis length 50-500 chars
- At least 3 study-at-a-glance bullets

**Warning checks:**
- GRADE language alignment in synopsis
- Citation contains author, year, title (heuristic)

**Result structure:** New `summary_validation` field alongside existing `validation` in the result dict.

**Files saved (updated):**
- `{id}-podcast.json` — now includes `show_summary` field
- `{id}-podcast.md` — summary appended below transcript as plain text
- `{id}-podcast_validation.json` — now includes `summary_validation` section

## Rendering

The show summary is rendered as **plain text** — no markdown, no bold, no formatting. Copy-pasteable into podcast apps.

Example output in `-podcast.md`:

```
Citation:
Lee D, Lee H, Lee C, Lee C. The Impact of Preoperative Positive
Suggestions on Dreaming With Intravenous Sedation: A Randomized
Controlled, Blinded Trial. Anesth Analg. 2025;XXX(00):00-00.
doi:10.1213/ANE.0000000000007818.

This episode examines whether preoperative positive suggestions influence
dreaming during IV sedation. In a double-blinded RCT of 188 patients,
ketamine doubled dream recall compared to propofol, though positive
suggestions alone showed no clear effect.

Study at a glance
- Design and setting: Single-centre, double-blinded 2x2 factorial RCT
  in adults (n=188) having elective upper extremity surgery under
  brachial plexus block with IV sedation (Republic of Korea).
- Primary outcome (drug-induced dream recall, DIDR): Dreams were
  recalled in about 23% with propofol vs 40% with ketamine; ketamine
  increased the odds (OR 2.14, 95% CI 1.23-3.72; p=0.007;
  moderate-certainty evidence).
- Risk of bias and certainty: Overall RoB 2 judgment "some concerns";
  certainty for the main DIDR result rated moderate.
```

## UI Integration

**CLI (`run_pipeline.py`):**
Summary bullet count shown in pipeline summary table:
```
Podcast | passed | 1023 words | ~7 min | Summary: 6 bullets
```

**Streamlit (`execution_artifacts.py`):**
- Existing transcript preview unchanged
- New expandable "Show Summary" section with plain text area and copy button
- Download buttons include updated `-podcast.md` with summary

## Target Length

Flexible: 100-400 words total (synopsis + bullets). LLM scales based on study complexity.

## Files Modified

| File | Action |
|------|--------|
| `schemas/podcast.schema.json` | Add optional `show_summary` object |
| `prompts/Podcast-summary.txt` | New prompt for summary generation |
| `src/pipeline/podcast_logic.py` | Second LLM call + summary validation |
| `src/rendering/podcast_renderer.py` | Render summary as plain text in markdown |
| `run_pipeline.py` | Show summary info in CLI summary table |
| `src/streamlit_app/screens/execution_artifacts.py` | Summary preview + copy button |
| `tests/` | Unit tests for summary generation, validation, rendering |
