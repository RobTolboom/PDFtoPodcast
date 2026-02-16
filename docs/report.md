# Report Generation Guide

**Module**: `src/pipeline/orchestrator.py` (report functions)
**Rendering**: `src/rendering/latex_renderer.py`, `src/rendering/figure_generator.py`
**Schemas**: `schemas/report.schema.json`, `schemas/report_validation.schema.json`
**Prompts**: `prompts/Report-generation.txt`, `prompts/Report-validation.txt`, `prompts/Report-correction.txt`

---

## Overview

Report Generation is **Step 5** of the PDFtoPodcast pipeline. It transforms structured extraction and appraisal data into professional PDF reports suitable for clinical decision-making, research review, and publication.

### Pipeline Position

```
Classification → Extraction → Validation/Correction → Appraisal → Report Generation
     (1)            (2)              (3)                 (4)            (5)
```

### Key Features

- **Block-based architecture**: Sections contain typed blocks (text, table, figure, callout)
- **Publication-type specific**: RCT gets CONSORT, systematic reviews get PRISMA, etc.
- **Iterative quality control**: Validation → correction loop until quality sufficient
- **Dual rendering**: LaTeX (professional PDFs) or WeasyPrint (HTML→PDF fallback)
- **Figure generation**: RoB traffic lights, forest plots, CONSORT/PRISMA flow diagrams
- **Full traceability**: Source map links report content to original PDF pages

---

## Quick Start

### CLI Usage

```bash
# Full pipeline with report (default)
python run_pipeline.py paper.pdf --llm openai

# Report step only (requires existing extraction + appraisal)
python run_pipeline.py paper.pdf --step report_generation --llm openai

# Custom language and renderer
python run_pipeline.py paper.pdf --report-language en --report-renderer weasyprint

# Disable PDF compilation (LaTeX source only)
python run_pipeline.py paper.pdf --no-report-compile-pdf

# Disable figure generation
python run_pipeline.py paper.pdf --disable-figures
```

### Streamlit UI

1. Navigate to **Settings** tab
2. Enable "Report Generation" step
3. Configure options:
   - **Language**: Dutch (nl) or English (en)
   - **Renderer**: LaTeX or WeasyPrint
   - **Compile PDF**: Toggle PDF compilation
   - **Generate Figures**: Toggle figure generation
4. Run pipeline - report appears as Step 5

---

## Output Files

Report generation produces these files in `tmp/`:

| File | Description |
|------|-------------|
| `paper-report0.json` | Initial report JSON |
| `paper-report_validation0.json` | Validation of initial report |
| `paper-report1.json` | Corrected report (if needed) |
| `paper-report-best.json` | Best iteration selected |
| `paper-report_validation-best.json` | Validation of best report |
| `render/report.tex` | LaTeX source |
| `render/report.pdf` | Compiled PDF |
| `render/report.md` | Markdown fallback |
| `render/figures/` | Generated figures (PNG) |

---

## Report Structure

### Core Sections (All Study Types)

1. **Clinical Bottom-line** (`exec_bottom_line`)
   - Quick decision support (3-5 bullets)
   - Direction of effect, effect size + CI, GRADE certainty

2. **Study Snapshot** (`study_snapshot`)
   - PICOS/PECO table (max 12 rows)
   - Design, population, intervention, outcomes

3. **Study Design** (`study_design`)
   - Design details, setting, flow
   - Interventions/exposures, outcomes

4. **Quality Assessment** (`quality_assessment`)
   - RoB traffic light figure
   - GRADE Summary of Findings table
   - Applicability assessment

5. **Primary Results** (`results_primary`)
   - Effect sizes with 95% CI
   - Clinical interpretation

6. **Secondary Results** (`results_secondary`)
   - Outcomes summary table

7. **Harms/Safety** (`results_harms`)
   - Adverse events per arm
   - Safety summary

8. **Contextualization** (`contextualization`)
   - Comparison with prior literature

9. **Limitations** (`limitations`)
   - Methodological weaknesses

10. **Extended Bottom-line** (`bottom_line_extended`)
    - Synthesis and implications

11. **Source Map** (`source_map`)
    - Traceability appendix

### Type-Specific Sections

| Publication Type | Additional Sections |
|-----------------|---------------------|
| Interventional Trial (RCT) | CONSORT checklist, randomization details |
| Observational | Confounding framework, sensitivity analyses |
| Systematic Review | PRISMA flow, meta-analysis results, publication bias |
| Prediction/Prognosis | PROBAST assessment, discrimination/calibration |

---

## Block Types

Reports use a block-based JSON structure:

### Text Block
```json
{
  "type": "text",
  "style": "bullets",
  "content": [
    "First bullet point",
    "Second bullet point"
  ],
  "source_refs": ["S1", "S2"]
}
```
Styles: `paragraph`, `bullets`, `numbered`

### Table Block
```json
{
  "type": "table",
  "label": "tbl_snapshot",
  "caption": "Study characteristics",
  "table_kind": "snapshot",
  "columns": [
    {"key": "item", "header": "Item", "align": "l"},
    {"key": "value", "header": "Value", "align": "l"}
  ],
  "rows": [
    {"item": "Design", "value": "RCT", "source_refs": ["S1"]}
  ],
  "render_hints": {"table_spec": "ll"}
}
```
Table kinds: `generic`, `snapshot`, `outcomes`, `harms`, `rob_domains`, `grade_sof`, `confounding_matrix`, `meta_results`, `model_metrics`

### Figure Block
```json
{
  "type": "figure",
  "label": "fig_rob",
  "caption": "Risk of Bias assessment",
  "figure_kind": "rob_traffic_light",
  "data_ref": "appraisal.risk_of_bias",
  "render_hints": {"width": "\\linewidth", "placement": "tbp"}
}
```
Figure kinds: `rob_traffic_light`, `forest`, `prisma`, `consort`, `image`

### Callout Block
```json
{
  "type": "callout",
  "variant": "warning",
  "text": "High risk of bias in blinding domain"
}
```
Variants: `warning`, `note`, `implication`, `clinical_pearl`

---

## Quality Metrics

Report validation uses weighted scoring:

| Metric | Weight | Threshold | Description |
|--------|--------|-----------|-------------|
| Accuracy | 35% | ≥0.95 | Data matches extraction/appraisal |
| Completeness | 30% | ≥0.85 | All sections present |
| Cross-reference consistency | 10% | ≥0.90 | Table/figure refs resolve |
| Data consistency | 10% | ≥0.90 | Numbers consistent across sections |
| Schema compliance | 15% | ≥0.95 | Valid JSON structure |

**Quality Score Formula:**
```
quality_score = 0.35 * accuracy
             + 0.30 * completeness
             + 0.10 * cross_ref_consistency
             + 0.10 * data_consistency
             + 0.15 * schema_compliance
```

**Pass criteria:**
- All individual thresholds met
- `critical_issues == 0`

---

## Rendering Options

### LaTeX (Default)

Professional typesetting with:
- `booktabs` tables
- `siunitx` number formatting
- `tcolorbox` callouts
- Custom Vetrix template

**Requirements:** `xelatex` or `pdflatex` installed (via Docker or local TeX Live)

### WeasyPrint (Fallback)

HTML → PDF conversion:
- No LaTeX installation needed
- Simpler styling
- Faster compilation

**Requirements:** `weasyprint` Python package

### Markdown (Always Generated)

Plain text fallback:
- Always written regardless of PDF success
- Useful for version control
- Can be converted with pandoc

---

## Figure Generation

### Supported Figure Types

| Type | Description | Data Source |
|------|-------------|-------------|
| `rob_traffic_light` | Risk of Bias domains | `appraisal.risk_of_bias` |
| `forest` | Forest plot with CI | `extraction.results.contrasts` |
| `prisma` | PRISMA 2020 flow | `extraction.search_results.flow` |
| `consort` | CONSORT flow (multi-arm) | `extraction.population.flow` |

### Error Handling

- **Critical figures** (RoB): Block PDF if generation fails
- **Optional figures** (forest, flows): Insert text placeholder, continue

---

## API Reference

### Main Functions

#### `run_report_with_correction()`

Full iterative report generation loop.

```python
from src.pipeline.orchestrator import run_report_with_correction

result = run_report_with_correction(
    extraction_result=extraction,
    appraisal_result=appraisal,
    classification_result=classification,
    llm=llm_provider,
    file_manager=file_mgr,
    language="nl",
    max_iterations=3,
    quality_thresholds=None,  # Uses defaults
    progress_callback=callback
)

# Returns:
# {
#     "best_report": dict,
#     "best_validation": dict,
#     "iterations": list,
#     "final_status": "passed" | "max_iterations_reached" | "blocked",
#     "iteration_count": int,
#     "improvement_trajectory": list[float]
# }
```

#### `run_report_generation()`

Single-pass report generation (no correction loop).

```python
from src.pipeline.orchestrator import run_report_generation

report = run_report_generation(
    extraction_result=extraction,
    appraisal_result=appraisal,
    classification_result=classification,
    llm=llm_provider,
    report_schema=schema,
    language="nl"
)
```

#### `is_report_quality_sufficient()`

Check if report meets quality thresholds.

```python
from src.pipeline.orchestrator import is_report_quality_sufficient

if is_report_quality_sufficient(validation_result, thresholds):
    print("Report quality acceptable")
```

### Rendering Functions

#### `render_report_to_pdf()`

Full render pipeline: JSON → LaTeX → PDF.

```python
from src.rendering.latex_renderer import render_report_to_pdf

pdf_path = render_report_to_pdf(
    report_json=report,
    output_dir=Path("tmp/render"),
    template_name="vetrix",
    compile_pdf=True,
    enable_figures=True
)
```

#### `render_report_to_tex()`

Generate LaTeX source only.

```python
from src.rendering.latex_renderer import render_report_to_tex

tex_content = render_report_to_tex(
    report_json=report,
    template_name="vetrix"
)
```

### Figure Generation

```python
from src.rendering.figure_generator import FigureGenerator

generator = FigureGenerator(output_dir=Path("tmp/render/figures"))

# Generate specific figure
figure_path = generator.generate_figure(
    figure_block={"type": "figure", "figure_kind": "rob_traffic_light", ...},
    data={"appraisal": appraisal_data}
)
```

---

## Troubleshooting

### LaTeX Compilation Fails

**Symptoms:** PDF not generated, `.log` file shows errors

**Solutions:**
1. Check LaTeX installation: `which xelatex` or `which pdflatex`
2. Install missing packages: `tlmgr install booktabs siunitx tcolorbox`
3. Use WeasyPrint fallback: `--report-renderer weasyprint`
4. Use Docker for consistent environment

### Quality Never Passes

**Symptoms:** Max iterations reached, quality score stuck below threshold

**Solutions:**
1. Check extraction quality (must be ≥0.70)
2. Check appraisal has Risk of Bias data
3. Use `--force-best-report` to accept best available
4. Review validation issues in `report_validation-best.json`

### Missing Figures

**Symptoms:** Placeholders instead of figures in PDF

**Solutions:**
1. Check matplotlib installed: `pip install matplotlib`
2. Verify data_ref paths exist in extraction/appraisal
3. Check `tmp/render/figures/` for generated PNGs
4. Review error messages in console output

---

## Related Documentation

- **Feature Specification:** [`docs/plans/report-generation.md`](plans/report-generation.md)
- **Architecture:** [`ARCHITECTURE.md`](../ARCHITECTURE.md)
- **API Reference:** [`API.md`](../API.md)
- **LaTeX Templates:** [`templates/latex/vetrix/`](../templates/latex/vetrix/)
