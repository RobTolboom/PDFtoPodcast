# Podcast Show Summary — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a plain-text show summary (citation + synopsis + study-at-a-glance bullets) to the podcast generation step via a second LLM call.

**Architecture:** Extend `podcast.schema.json` with an optional `show_summary` object. Add a `Podcast-summary.txt` prompt. Generate the summary in a second LLM call within `run_podcast_generation()`, validate it, merge into the podcast JSON, and render as plain text.

**Tech Stack:** Python 3.10+, OpenAI GPT-5.1, jsonschema, pytest, Black, Ruff

**Design doc:** `docs/plans/2026-02-17-podcast-show-summary-design.md`

---

### Task 1: Schema — Add show_summary to podcast.schema.json

**Files:**
- Modify: `schemas/podcast.schema.json:56` (after `transcript` property)

**Step 1: Add `show_summary` property**

Insert after the `transcript` property (line 56) and before `tts_config` (line 57):

```json
"show_summary": {
    "type": "object",
    "description": "Plain-text episode summary with citation, synopsis, and structured study-at-a-glance bullets",
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
},
```

Do NOT add `show_summary` to the top-level `required` array (lines 5-9). It stays optional for backward compatibility.

**Step 2: Verify schema is valid JSON**

Run: `python -c "import json; json.load(open('schemas/podcast.schema.json'))"`
Expected: No output (valid JSON)

**Step 3: Commit**

```bash
git add schemas/podcast.schema.json
git commit -m "feat: add show_summary schema to podcast.schema.json"
```

---

### Task 2: Prompt — Create Podcast-summary.txt

**Files:**
- Create: `prompts/Podcast-summary.txt`

**Step 1: Write the prompt file**

Create `prompts/Podcast-summary.txt` with instructions for the LLM to produce a `show_summary` JSON object. The prompt should:

- Receive EXTRACTION_JSON, APPRAISAL_JSON, CLASSIFICATION_JSON, TRANSCRIPT, and SHOW_SUMMARY_SCHEMA as input
- Output a JSON object matching the `show_summary` schema (citation, synopsis, study_at_a_glance)
- Generate a Vancouver/NLM-style citation from extraction metadata (authors, title, journal, year, DOI)
- Write a 2-3 sentence synopsis that summarizes the key finding with GRADE-calibrated language
- Produce study-at-a-glance bullets adapted to study type:
  - RCT: Design/setting, Population, Interventions, Primary outcome, Key secondary, Safety, RoB/GRADE
  - Observational: Design/setting, Population, Exposure/comparator, Primary outcome, Key secondary, Confounding, RoB/GRADE
  - Systematic review: Design/setting, Search/inclusion, Pooled estimate, Heterogeneity, Key secondary, RoB/GRADE
  - Prediction/prognosis: Design/setting, Population, Model/predictors, Discrimination/calibration, RoB/GRADE
  - Editorial: synopsis only, minimal study_at_a_glance (3 general bullets)
- Include exact numbers from extraction (ORs, CIs, p-values, MDs) — no rounding
- Include GRADE certainty inline with outcome bullets
- Last bullet always covers RoB and certainty
- GRADE verb calibration: High→shows/demonstrates, Moderate→likely/probably, Low→may/might, Very Low→very uncertain

**Step 2: Commit**

```bash
git add prompts/Podcast-summary.txt
git commit -m "feat: add Podcast-summary.txt prompt template"
```

---

### Task 3: Prompt loader — Add load_podcast_summary_prompt()

**Files:**
- Modify: `src/prompts.py:376` (after `load_podcast_generation_prompt`)
- Modify: `src/prompts.py:195` (add to `get_all_available_prompts`)
- Modify: `src/prompts.py:408` (add to `validate_prompt_directory`)
- Test: `tests/unit/test_prompts.py:211` (after `TestLoadPodcastGenerationPrompt`)

**Step 1: Write the failing tests**

Add to `tests/unit/test_prompts.py` after line 211, before `class TestPromptsModuleConstants`:

```python
class TestLoadPodcastSummaryPrompt:
    """Tests for podcast summary prompt loading."""

    def test_load_podcast_summary_prompt_success(self):
        """Test that podcast summary prompt loads successfully."""
        prompt = load_podcast_summary_prompt()
        assert prompt is not None
        assert len(prompt) > 0

    def test_load_podcast_summary_prompt_contains_required_sections(self):
        """Test that podcast summary prompt contains key instruction sections."""
        prompt = load_podcast_summary_prompt()
        assert "citation" in prompt.lower()
        assert "synopsis" in prompt.lower()
        assert "study_at_a_glance" in prompt.lower() or "study at a glance" in prompt.lower()

    def test_load_podcast_summary_prompt_file_not_found_raises_error(self):
        """Test that missing podcast summary prompt raises PromptLoadError."""
        with patch("src.prompts.PROMPTS_DIR", Path("/nonexistent")):
            with pytest.raises(PromptLoadError) as exc_info:
                load_podcast_summary_prompt()
            assert "Podcast summary prompt not found" in str(exc_info.value)
```

Also add `load_podcast_summary_prompt` to the import at the top of the test file.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_prompts.py::TestLoadPodcastSummaryPrompt -v`
Expected: FAIL (ImportError — function doesn't exist yet)

**Step 3: Implement load_podcast_summary_prompt()**

Add to `src/prompts.py` after line 376 (after `load_podcast_generation_prompt`):

```python
def load_podcast_summary_prompt() -> str:
    """
    Load the podcast summary prompt from Podcast-summary.txt.

    Returns:
        Podcast summary prompt text

    Raises:
        PromptLoadError: If prompt file not found or cannot be read
    """
    prompt_file = PROMPTS_DIR / "Podcast-summary.txt"

    if not prompt_file.exists():
        raise PromptLoadError(f"Podcast summary prompt not found: {prompt_file}")

    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        raise PromptLoadError(f"Error reading podcast summary prompt: {e}") from e
```

Add to `get_all_available_prompts()` after line 195:

```python
    try:
        load_podcast_summary_prompt()
        prompts["podcast_summary"] = "Podcast show summary from extraction and appraisal"
    except PromptLoadError:
        pass
```

Add to `validate_prompt_directory()` expected_files after line 408:

```python
        "Podcast-summary.txt",
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_prompts.py::TestLoadPodcastSummaryPrompt -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add src/prompts.py tests/unit/test_prompts.py
git commit -m "feat: add load_podcast_summary_prompt() with tests"
```

---

### Task 4: Renderer — Render show summary as plain text

**Files:**
- Modify: `src/rendering/podcast_renderer.py:104` (after transcript, before footer)
- Test: `tests/unit/test_podcast_renderer.py` (add new tests at end)

**Step 1: Write the failing tests**

Add to end of `tests/unit/test_podcast_renderer.py`:

```python
def test_render_podcast_with_show_summary(tmp_path):
    """Test rendering podcast with show_summary as plain text."""
    podcast = {
        "metadata": {"title": "Summary Test", "word_count": 950, "estimated_duration_minutes": 6},
        "transcript": "This is the transcript content for the test.",
        "show_summary": {
            "citation": "Lee D, Lee H. Impact of Suggestions on Dreaming. Anesth Analg. 2025.",
            "synopsis": "This episode examines whether preoperative positive suggestions influence dreaming during IV sedation.",
            "study_at_a_glance": [
                {"label": "Design and setting", "content": "Single-centre, double-blinded RCT (n=188)."},
                {"label": "Primary outcome", "content": "Ketamine increased dream recall (OR 2.14, 95% CI 1.23-3.72; p=0.007)."},
                {"label": "Risk of bias and certainty", "content": "RoB 2 judgment: some concerns; GRADE: moderate."},
            ],
        },
    }

    output_path = tmp_path / "summary.md"
    result_path = render_podcast_to_markdown(podcast, output_path)
    content = result_path.read_text(encoding="utf-8")

    # Verify show summary rendered as plain text
    assert "Citation:" in content
    assert "Lee D, Lee H. Impact of Suggestions" in content
    assert "This episode examines" in content
    assert "Study at a glance" in content
    assert "- Design and setting: Single-centre" in content
    assert "- Primary outcome: Ketamine increased" in content
    assert "- Risk of bias and certainty: RoB 2" in content

    # Verify no markdown formatting in summary section
    # (no bold **, no headings #, just plain text)
    summary_start = content.index("Citation:")
    summary_section = content[summary_start:]
    assert "**" not in summary_section.split("*Generated")[0]
    assert "# " not in summary_section.split("*Generated")[0]


def test_render_podcast_without_show_summary(tmp_path):
    """Test that missing show_summary is handled gracefully (backward compat)."""
    podcast = {
        "metadata": {"title": "No Summary Test"},
        "transcript": "Transcript without a show summary.",
    }

    output_path = tmp_path / "no-summary.md"
    result_path = render_podcast_to_markdown(podcast, output_path)
    content = result_path.read_text(encoding="utf-8")

    # Should render normally without show summary section
    assert "Transcript without a show summary." in content
    assert "Citation:" not in content
    assert "Study at a glance" not in content
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_podcast_renderer.py::test_render_podcast_with_show_summary -v`
Expected: FAIL (no summary section in output)

**Step 3: Implement show summary rendering**

In `src/rendering/podcast_renderer.py`, add a helper function before `render_podcast_to_markdown`:

```python
def _render_show_summary_plain_text(show_summary: dict[str, Any]) -> str:
    """Render show_summary as plain text for podcast apps and web."""
    lines = []

    citation = show_summary.get("citation", "")
    if citation:
        lines.append(f"Citation:\n{citation}")
        lines.append("")

    synopsis = show_summary.get("synopsis", "")
    if synopsis:
        lines.append(synopsis)
        lines.append("")

    bullets = show_summary.get("study_at_a_glance", [])
    if bullets:
        lines.append("Study at a glance")
        for bullet in bullets:
            label = bullet.get("label", "")
            content_text = bullet.get("content", "")
            lines.append(f"- {label}: {content_text}")

    return "\n".join(lines)
```

In `render_podcast_to_markdown`, insert the show summary between the transcript and the footer (after line 106, before the final `"---"`):

Replace the `lines` list construction (lines 97-109) to include the summary:

```python
    lines = [
        f"# {title} - Podcast Script",
        "",
        f"**Duration**: ~{duration} minutes | **Words**: {word_count} | **Language**: {language} | **Audience**: {audience}",
        "",
        "---",
        "",
        transcript,
        "",
        "---",
    ]

    # Append show summary as plain text (if present)
    show_summary = podcast.get("show_summary")
    if show_summary and isinstance(show_summary, dict):
        lines.append("")
        lines.append(_render_show_summary_plain_text(show_summary))
        lines.append("")
        lines.append("---")

    lines.extend([
        "",
        f"*Generated from: {study_id} | Sources: extraction-best.json, appraisal-best.json*",
    ])
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_podcast_renderer.py -v`
Expected: All tests pass (including existing ones)

**Step 5: Commit**

```bash
git add src/rendering/podcast_renderer.py tests/unit/test_podcast_renderer.py
git commit -m "feat: render show summary as plain text in podcast markdown"
```

---

### Task 5: Generation logic — Second LLM call for show summary

**Files:**
- Modify: `src/pipeline/podcast_logic.py:11` (add import)
- Modify: `src/pipeline/podcast_logic.py:277` (after transcript save, before markdown render)

**Step 1: Add import**

Add to imports at line 11:

```python
from ..prompts import load_podcast_generation_prompt, load_podcast_summary_prompt
```

**Step 2: Add show summary generation + validation after transcript validation**

Insert after the transcript validation block (after line 257, before line 259 "Determine validation status"). Add:

```python
        # --- Show Summary Generation (second LLM call) ---
        summary_validation_issues = []
        summary_critical_issues = []

        try:
            console.print("[bold cyan]📝 Generating show summary...[/bold cyan]")
            _call_progress_callback(
                progress_callback, STEP_PODCAST_GENERATION, "generating_summary", {}
            )

            summary_prompt_template = load_podcast_summary_prompt()

            # Build summary prompt context with all inputs including transcript
            summary_schema = schema.get("properties", {}).get("show_summary", {})
            summary_prompt_context = f"""EXTRACTION_JSON:
{json.dumps(extraction_clean, indent=2)}

APPRAISAL_JSON:
{json.dumps(appraisal_clean, indent=2)}

CLASSIFICATION_JSON:
{json.dumps(classification_result, indent=2)}

TRANSCRIPT:
{transcript}

SHOW_SUMMARY_SCHEMA:
{json.dumps(summary_schema, indent=2)}
"""

            summary_json = llm.generate_json_with_schema(
                schema=summary_schema,
                system_prompt=summary_prompt_template,
                prompt=summary_prompt_context,
                schema_name="podcast_show_summary",
                reasoning_effort=llm_settings.reasoning_effort_podcast,
            )

            # Validate show summary
            # Critical: synopsis length
            synopsis = summary_json.get("synopsis", "")
            if len(synopsis) < 50:
                summary_critical_issues.append(
                    f"Synopsis too short ({len(synopsis)} chars). Minimum: 50."
                )
            elif len(synopsis) > 500:
                summary_critical_issues.append(
                    f"Synopsis too long ({len(synopsis)} chars). Maximum: 500."
                )

            # Critical: at least 3 bullets
            bullets = summary_json.get("study_at_a_glance", [])
            if len(bullets) < 3:
                summary_critical_issues.append(
                    f"Too few study-at-a-glance bullets ({len(bullets)}). Minimum: 3."
                )

            # Warning: GRADE language alignment in synopsis
            synopsis_lower = synopsis.lower()
            if grade_certainty in ["low", "very low"]:
                for word in high_certainty_words:
                    if word in synopsis_lower:
                        summary_validation_issues.append(
                            f"High-certainty word '{word}' in synopsis with "
                            f"{grade_certainty} GRADE evidence"
                        )
                        break

            # Warning: citation contains author and year
            citation = summary_json.get("citation", "")
            if not re.search(r"\b\d{4}\b", citation):
                summary_validation_issues.append("Citation may be missing publication year")

            # Merge into podcast JSON
            if not summary_critical_issues:
                podcast_json["show_summary"] = summary_json
                console.print(
                    f"[green]✅ Show summary generated: {len(bullets)} bullets[/green]"
                )
            else:
                console.print(
                    f"[yellow]⚠️  Show summary validation failed: "
                    f"{'; '.join(summary_critical_issues)}[/yellow]"
                )

        except Exception as e:
            console.print(f"[yellow]⚠️  Show summary generation failed: {e}[/yellow]")
            summary_validation_issues.append(f"Generation failed: {e}")
            # Continue — summary is optional, don't fail the podcast step
```

Then update the validation_result dict (around line 270) to include summary validation:

```python
        # Build summary validation result
        if summary_critical_issues:
            summary_validation_status = "failed"
        elif summary_validation_issues:
            summary_validation_status = "warnings"
        else:
            summary_validation_status = "passed"

        summary_validation_result = {
            "status": summary_validation_status,
            "issues": summary_validation_issues + summary_critical_issues,
            "critical_issues": summary_critical_issues,
        }
```

Update the main validation_result to include summary_validation (modify existing dict around line 270-275):

```python
        validation_result = {
            "status": validation_status,
            "issues": validation_issues + critical_issues,
            "critical_issues": critical_issues,
            "ready_for_tts": validation_status != "failed",
            "summary_validation": summary_validation_result,
        }
```

**Step 3: Run existing tests to verify nothing broke**

Run: `make test-fast`
Expected: All existing tests pass

**Step 4: Commit**

```bash
git add src/pipeline/podcast_logic.py
git commit -m "feat: add show summary generation with second LLM call"
```

---

### Task 6: CLI — Show summary info in output

**Files:**
- Modify: `run_pipeline.py:409` (single step display, after podcast issues)
- Modify: `run_pipeline.py:583` (full pipeline summary table)

**Step 1: Update single-step display**

After line 413 (after showing issues), add:

```python
            # Show summary info
            show_summary = podcast.get("show_summary")
            if show_summary:
                bullets = show_summary.get("study_at_a_glance", [])
                console.print(f"[cyan]Show summary:[/cyan] {len(bullets)} bullets")
            summary_val = validation.get("summary_validation", {})
            if summary_val.get("status"):
                console.print(f"[cyan]Summary validation:[/cyan] {summary_val['status']}")
```

**Step 2: Update full pipeline summary table**

Modify line 583 to include summary bullet count:

```python
        show_summary = podcast_data.get("show_summary")
        summary_info = ""
        if show_summary:
            bullet_count = len(show_summary.get("study_at_a_glance", []))
            summary_info = f" | Summary: {bullet_count} bullets"
        podcast_detail = f"{status} | {word_count} words | ~{duration} min{summary_info}"
```

**Step 3: Commit**

```bash
git add run_pipeline.py
git commit -m "feat: show summary info in CLI output"
```

---

### Task 7: Streamlit — Show summary display

**Files:**
- Modify: `src/streamlit_app/screens/execution_artifacts.py:131` (after transcript copy area)

**Step 1: Add show summary display**

After line 131 (after the transcript text_area), add:

```python
        # Show summary display (plain text for copy-paste to podcast apps)
        show_summary = podcast_data.get("show_summary")
        if show_summary:
            citation = show_summary.get("citation", "")
            synopsis = show_summary.get("synopsis", "")
            bullets = show_summary.get("study_at_a_glance", [])

            # Build plain text representation
            summary_lines = []
            if citation:
                summary_lines.append(f"Citation:\n{citation}")
                summary_lines.append("")
            if synopsis:
                summary_lines.append(synopsis)
                summary_lines.append("")
            if bullets:
                summary_lines.append("Study at a glance")
                for bullet in bullets:
                    label = bullet.get("label", "")
                    content_text = bullet.get("content", "")
                    summary_lines.append(f"- {label}: {content_text}")

            summary_text = "\n".join(summary_lines)

            with st.expander("Show Summary"):
                st.text_area(
                    "Copy Show Summary (for podcast apps)",
                    summary_text,
                    height=250,
                    key="podcast_summary_copy",
                )
```

**Step 2: Commit**

```bash
git add src/streamlit_app/screens/execution_artifacts.py
git commit -m "feat: add show summary display in Streamlit UI"
```

---

### Task 8: Documentation — CHANGELOG and design doc

**Files:**
- Modify: `CHANGELOG.md` (add entry under [Unreleased])
- Modify: `docs/plans/2026-02-17-podcast-show-summary-design.md` (mark as implemented)

**Step 1: Add CHANGELOG entry**

Add under `## [Unreleased]`:

```markdown
### Added

- **Podcast Show Summary** - Plain-text episode companion generated alongside the podcast transcript
  - Citation in Vancouver/NLM style, 2-3 sentence narrative synopsis, structured "Study at a glance" bullets
  - Adapts bullet structure to study type (RCT, observational, systematic review, prediction, editorial)
  - Includes exact numbers (ORs, CIs, p-values) and inline GRADE certainty ratings
  - Second LLM call within existing podcast generation step (no new pipeline step)
  - Light validation: synopsis length, bullet count, GRADE language alignment
  - Rendered as plain text in podcast markdown, copy-pasteable into podcast apps
  - CLI shows summary bullet count in pipeline summary table
  - Streamlit UI shows expandable summary with copy button
```

**Step 2: Update design doc status**

Change `**Status:** Approved` to `**Status:** Implemented`

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-02-17-podcast-show-summary-design.md
git commit -m "docs: add show summary changelog entry and update design doc status"
```

---

### Task 9: Verification — Format, lint, test

**Step 1: Run format and lint**

```bash
make format
make lint
```

**Step 2: Run all unit tests**

```bash
make test-fast
```

Expected: All tests pass including new ones.

**Step 3: Run full CI simulation**

```bash
make ci
```

Expected: All checks pass.
