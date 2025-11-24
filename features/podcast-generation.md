# Feature: Podcast Script Generation

**Status**: Planning
**Branch**: `feature/podcast-generation`
**Created**: 2025-11-24
**Author**: Rob Tolboom (with Claude Code)

**Summary**
- New pipeline step that generates a written podcast script based on extraction + appraisal data.
- Monologue format (single speaker), English by default with Dutch as an option.
- Light validation (factchecking) without full correction loop in v1.
- TTS integration planned as future extension.

## Scope

**In scope**
- Podcast script generation as new step after report generation
- Monologue format (narrative explanation by single host)
- Language support: English (default), Dutch (optional)
- Schema for structured script output
- Light validation: factchecking against extraction/appraisal
- CLI and Streamlit UI integration

**Out of scope (v1)**
- Text-to-Speech (TTS) integration
- Dialogue format (two speakers)
- Audio effects, timing markers, music cues
- Full iterative correction loop

---

## Problem Statement

### Current Situation

The pipeline generates:
1. **Classification** → publication type
2. **Extraction** → structured data
3. **Appraisal** → risk of bias + GRADE
4. **Report** → PDF report

**No audio-friendly output**:
- ❌ No podcast script for oral presentation
- ❌ Report is too technical/formal for audio
- ❌ No narrative summary of findings

### Motivation

- **Accessibility**: Audio content reaches different audience than written reports
- **Efficiency**: Clinicians can listen while commuting, exercising, etc.
- **Engagement**: Narrative format makes complex studies more accessible
- **Reuse**: Extraction + appraisal data already available as foundation

---

## Desired Situation

### Pipeline Workflow (with Podcast)

```
┌──────────────────────────────────────────────────────────────────┐
│  CURRENT PIPELINE                                                │
└──────────────────────────────────────────────────────────────────┘
  1. Classification → publication_type
  2. Extraction → extraction-best.json
  3. Appraisal → appraisal-best.json
  4. Report → report-best.json + report-best.pdf
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  NEW STEP: PODCAST GENERATION                                    │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────┐
  │  PODCAST GENERATION    │
  │  (LLM prompt)          │
  └────────────────────────┘
           │
           ├─ Input: extraction-best + appraisal-best + classification
           ├─ Language: EN (default) or NL
           └─ Output: Narrative monologue script
           │
           ▼
  ┌────────────────────────┐
  │  PODCAST VALIDATION    │
  │  (Light factchecking)  │
  └────────────────────────┘
           │
           ├─ Check: Key outcomes present?
           ├─ Check: Numbers match extraction?
           ├─ Check: Conclusion aligned with GRADE?
           └─ Output: Validation report (issues, no correction)
           │
           ▼
  podcast.json + podcast.md
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  FUTURE EXTENSION                                                │
└──────────────────────────────────────────────────────────────────┘
  6. TTS Integration → podcast.mp3
```

---

## Style & Language Rules

The podcast script must be optimized for audio consumption. These rules are **mandatory** for the generation prompt.

### Absolute Language Rules

1. **No abbreviations or acronyms** anywhere in the transcript
   - Always write terms in full: "confidence interval" (not "CI"), "intensive care unit" (not "ICU"), "hazard ratio" (not "HR"), "milligrams" (not "mg"), "hours" (not "h")
   - This is critical for audio clarity and accessibility

2. **Continuous narrative only**
   - No titles, headings, bullet points, or numbered lists in the spoken text
   - No brackets, stage directions, or markup
   - Produce only flowing paragraphs with natural transitions

3. **No technical identifiers**
   - No DOIs, PMIDs, ISSNs, or author contact details
   - Reference the study by descriptive name if needed

### Numbers Policy

Keep data light and focus on meaning:

1. **Maximum 3 numerical statements** in the entire transcript
   - Prioritise: primary outcome, one key secondary outcome, one key safety outcome (if important)

2. **Format for numbers**:
   - Give absolute counts first, then one essential relative measure only if it changes interpretation
   - Express numbers in words where reasonable ("twelve out of one hundred")
   - Keep numerical statements concise

3. **Qualitative interpretation elsewhere**:
   - Summarise results in plain language without numbers
   - Focus on direction and likely size of effect: "little to no difference", "a small reduction", "a moderate improvement"
   - Emphasise uncertainty where appropriate

### Calibrated Language

Use language that reflects the certainty of evidence:

| Evidence Certainty | Example Phrases |
|-------------------|-----------------|
| High | "shows", "demonstrates", "reduces" |
| Moderate | "likely", "probably", "appears to" |
| Low | "may", "might", "suggests" |
| Very Low | "is very uncertain", "we cannot conclude", "insufficient evidence" |

### Interpretation Requirements

1. **Move beyond recital of figures** - State plainly whether evidence suggests benefit, harm, no important difference, or insufficient evidence
2. **Base judgement on appraisal** - Internal validity, precision, and applicability should inform the narrative
3. **Clinical importance** - If a threshold for clinical importance is specified, state whether it was met; if not reported, acknowledge this
4. **Practice implications** - Make explicit what might reasonably change now and what should not change yet

### Conflicts and Gaps

- If APPRAISAL_JSON and EXTRACTION_JSON disagree, follow EXTRACTION_JSON for raw figures and state uncertainty clearly
- If information is missing, state "insufficiently reported" rather than inferring

---

## Technical Design

### 1. Schema Design

**New schema**: `schemas/podcast.schema.json`

The schema is intentionally simple: metadata plus one continuous transcript field. This produces TTS-ready output without structural fragmentation.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Podcast Script Schema",
  "type": "object",
  "required": ["podcast_version", "metadata", "transcript"],
  "properties": {
    "podcast_version": {
      "type": "string",
      "const": "v1.0"
    },
    "metadata": {
      "type": "object",
      "required": ["title", "language", "word_count", "estimated_duration_minutes"],
      "properties": {
        "title": { "type": "string" },
        "study_id": { "type": "string" },
        "language": { "enum": ["en", "nl"], "default": "en" },
        "target_audience": { "type": "string", "default": "practising clinicians" },
        "word_count": { "type": "integer", "minimum": 500, "maximum": 2000 },
        "estimated_duration_minutes": { "type": "integer", "minimum": 3, "maximum": 15 },
        "generation_timestamp": { "type": "string", "format": "date-time" }
      }
    },
    "transcript": {
      "type": "string",
      "description": "Complete podcast script as one continuous, TTS-ready text. No headings, bullets, or structural markup.",
      "minLength": 500
    }
  }
}
```

### 2. Prompt Architecture

**New prompts**:

#### `prompts/Podcast-generation.txt`

**Purpose**: Generate narrative podcast script from extraction + appraisal

**Input**:
- EXTRACTION_JSON: Validated extraction data
- APPRAISAL_JSON: Risk of bias + GRADE assessment
- CLASSIFICATION_JSON: Publication type
- LANGUAGE: "en" | "nl"
- PODCAST_SCHEMA: podcast.schema.json

**Audience and Tone**:
- Speak directly to the listener using "you"
- Professional but conversational
- Active voice preferred
- One idea per sentence
- Vary sentence length for natural rhythm
- Target duration: 5-8 minutes (800-1,200 words)

**Content Flow** (no visible headings in output; weave smooth transitions):

1. **Hook** - Brief opening on why this matters now for clinicians
2. **Clinical Question** - State the question in plain language and why it matters
3. **Methods Summary** - One compact passage: study design, setting, participant numbers, study arms, primary outcome, time points (minimal numbers)
4. **Findings** - Present results with minimal numerical statements; use qualitative interpretation and uncertainty language
5. **Quality of Evidence** - Discuss risk of bias and certainty as per appraisal, without naming external checklists (e.g., don't say "RoB 2 tool")
6. **Practice Implications** - What this means at the bedside today: 2-3 concrete practice points and what should not change yet
7. **Safety and Limitations** - Brief summary in plain language
8. **Take-home** - One clear sentence capturing overall judgement; invite listener to read the paper

**Self-Check (integrated in prompt)**:

Before finalizing the transcript, the LLM must verify:
1. Every number matches EXTRACTION_JSON exactly
2. Conclusions do not exceed GRADE certainty from APPRAISAL_JSON
3. No facts stated that are not in the source JSONs
4. Missing information stated as "insufficiently reported", not inferred

**Output**: podcast.json (metadata + transcript)

### 3. API Design

```python
# src/pipeline/orchestrator.py

def run_podcast_generation(
    extraction_result: dict,
    appraisal_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    language: str = "en",
    progress_callback: Callable | None = None,
) -> dict:
    """
    Generate podcast script from extraction + appraisal data.

    Args:
        extraction_result: Validated extraction JSON
        appraisal_result: Best appraisal JSON
        classification_result: Classification result
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving output
        language: Script language ("en" | "nl")
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'podcast': dict,           # Generated podcast (metadata + transcript)
            'status': str,             # "success" | "failed"
        }
    """
```

### 4. File Management

**Podcast File Naming**:

```
tmp/
  ├── paper-extraction-best.json
  ├── paper-appraisal-best.json
  ├── paper-report-best.json
  │
  ├── paper-podcast.json              # Generated script (NEW)
  └── paper-podcast.md                # Human-readable version (NEW)
```

### 5. Markdown Rendering

**Output**: `paper-podcast.md`

The markdown file contains a metadata header followed by the complete transcript. No section headings in the transcript itself - it's TTS-ready continuous text.

```markdown
# [Study Title] - Podcast Script

**Duration**: ~6 minutes | **Words**: 950 | **Language**: English | **Audience**: Practising clinicians

---

[Complete transcript as continuous flowing text, ready for TTS...]

---

*Generated from: [Study ID] | Sources: extraction-best.json, appraisal-best.json*
```

---

## Implementation Phases

### Phase 1: Schema & Prompt
**Goal**: Define podcast structure and create generation prompt

**Deliverables**:
- [ ] `schemas/podcast.schema.json` - Simple schema (metadata + transcript)
- [ ] `prompts/Podcast-generation.txt` - Generation prompt with integrated self-check

**Acceptance**:
- Schema validates sample podcast JSON
- Prompt includes all style rules and self-check instructions
- Output is TTS-ready continuous text

### Phase 2: Core Generation
**Goal**: Implement podcast generation in orchestrator

**Deliverables**:
- [ ] `run_podcast_generation()` in orchestrator
- [ ] Language parameter support (en/nl)
- [ ] Schema validation of output

**Acceptance**:
- Podcast generates for all study types
- Output matches schema
- Transcript is continuous text without structural markup

### Phase 3: File Management & Rendering
**Goal**: Save podcast files and render markdown

**Deliverables**:
- [ ] `PipelineFileManager` extensions:
  - `save_podcast()`
  - `load_podcast()`
- [ ] Markdown renderer for podcast script
- [ ] Word count / duration estimation

**Acceptance**:
- Files saved with correct naming
- Markdown readable and well-formatted
- Duration estimate accurate (±1 minute)

### Phase 4: CLI Integration
**Goal**: Add podcast step to CLI pipeline

**Deliverables**:
- [ ] `--step podcast` option
- [ ] `--podcast-language en|nl` option
- [ ] Progress output during generation
- [ ] Integration in full pipeline run

**Example Usage**:
```bash
# Generate podcast (requires extraction + appraisal)
python run_pipeline.py paper.pdf --step podcast --llm openai

# Generate in Dutch
python run_pipeline.py paper.pdf --step podcast --podcast-language nl

# Full pipeline including podcast
python run_pipeline.py paper.pdf --llm openai --include-podcast
```

**Acceptance**:
- CLI generates podcast successfully
- Language option works
- Clear progress/status output

### Phase 5: UI Integration (Streamlit)
**Goal**: Add podcast step to Streamlit execution screen

**Deliverables**:
- [ ] New execution step: "Podcast" (after Report)
- [ ] Language selector (EN/NL)
- [ ] Display generated transcript in UI
- [ ] Download button for markdown
- [ ] Copy transcript button (for TTS tools)

**UI Mock**:
```
┌─────────────────────────────────────────────────────────────────┐
│ 6. PODCAST SCRIPT                                        ✅     │
├─────────────────────────────────────────────────────────────────┤
│ Language: English | Duration: ~6 min | Words: 950              │
│                                                                 │
│ Preview:                                                        │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ What if a simple change in pain management could reduce    │ │
│ │ opioid use by forty percent? That is exactly what          │ │
│ │ researchers set out to investigate in this new trial...    │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ [View Full Script] [Download .md] [Copy for TTS] [Regenerate]   │
└─────────────────────────────────────────────────────────────────┘
```

**Acceptance**:
- Podcast step visible in UI
- Script preview works
- Download produces valid markdown
- Copy button provides clean transcript for TTS

### Phase 6: Testing & Documentation
**Goal**: Comprehensive testing and documentation

**Deliverables**:
- [ ] Unit tests:
  - Schema validation
  - Prompt loading
  - Generation function
- [ ] Integration tests:
  - Full podcast generation for each study type
  - Output is valid continuous text
- [ ] Documentation:
  - README update
  - ARCHITECTURE update
  - CHANGELOG entry

**Acceptance**:
- Test coverage ≥ 85% for podcast code
- All tests pass
- Documentation complete

---

## Risks and Mitigations

### Risk 1: Narrative Quality is Subjective
**Description**: Difficult to define/validate "good" podcast style

**Impact**: Medium - script may be technically correct but boring

**Mitigation**:
- Prompt contains concrete style examples
- User can regenerate with feedback
- Future: A/B testing with sample listeners

### Risk 2: Numbers/Facts Incorrectly Transcribed
**Description**: LLM introduces errors during narrative translation

**Impact**: High - factual errors in audio are serious

**Mitigation**:
- Self-check instructions in generation prompt
- Prompt explicitly requires matching EXTRACTION_JSON exactly
- Numbers policy limits numerical statements to max 3 (reduces error surface)

### Risk 3: Conclusions Overstated
**Description**: Podcast sounds more enthusiastic than GRADE certainty justifies

**Impact**: Medium - misleading clinical implications

**Mitigation**:
- Validation checks alignment with GRADE
- Prompt instructions: "Match enthusiasm to evidence quality"
- Limitations section required

### Risk 4: Language Support (NL) Less Good
**Description**: English LLMs generate suboptimal Dutch

**Impact**: Low - Dutch is optional

**Mitigation**:
- Test with Dutch sample papers
- Consider Dutch-trained models
- Document known limitations

---

## Acceptance Criteria

### Functional

1. **Podcast generates for all 5 study types** as continuous TTS-ready text
2. **Language option works** (EN default, NL optional)
3. **Output in JSON and Markdown** available
4. **CLI and UI integration** complete

### Technical

1. **Schema validates** all generated scripts (metadata + transcript)
2. **Prompt loads correctly** with all style rules
3. **File management** saves with correct naming
4. **Duration estimate** accurate within ±1 minute
5. **Transcript contains no structural markup** (headings, bullets, etc.)

### Quality

1. **Factual accuracy**: Numbers match extraction (self-check in prompt)
2. **GRADE alignment**: Conclusions calibrated to evidence certainty
3. **Completeness**: Key outcomes and limitations present
4. **TTS-ready**: Continuous narrative, no abbreviations, natural flow

---

## Future Extensions

### v1.1: Dialogue Format
- Two speakers (host + expert)
- Turn-taking markers in schema
- Different perspectives/questions

### v1.2: TTS Integration
- Text-to-Speech generation
- Voice selection (male/female, accent)
- Output: podcast.mp3

### v1.3: Audio Enhancements
- Intro/outro music
- Section dividers
- Emphasis markers for TTS

---

## References

### Related Features
- `features/report-generation.md` - Report generation (similar architecture)
- `features/appraisal.md` - Appraisal step (input for podcast)
- `ARCHITECTURE.md` - Pipeline component documentation

### Podcast Best Practices
- Conversational tone guidelines
- Audio-optimized writing techniques
- Scientific communication for lay audiences
