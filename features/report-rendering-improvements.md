# Feature: Report Rendering Improvements (v1.1)

**Status**: Planning
**Branch**: `feature/report-rendering-v1.1` (not yet created)
**Created**: 2025-11-23
**Author**: Rob Tolboom (with Claude Code)
**Depends on**: `features/report-generation.md` (v1.0 orchestration complete)

---

## Summary

The report generation orchestration (Phases 1-9) is complete with working validation loops, prompts, and schemas. However, the **rendering and output side remains at scaffold level** and does not yet meet the production-ready acceptance criteria promised in the original feature document.

This feature document tracks the work needed to bring rendering to publication-quality output.

---

## Problem Statement

### Current State (v1.0 - Scaffold)

The `src/rendering/latex_renderer.py` is labeled "Phase 4 scaffolding" and produces minimal output:

1. **Templates are bare placeholders**: `templates/latex/vetrix/main.tex`, `sections.tex`, `tables.tex`, `figures.tex` contain basic structure but lack:
   - Publication-quality formatting
   - Source map appendix generation
   - Type-specific appendices (CONSORT checklist, ROBINS-I matrix, etc.)
   - Proper cross-referencing

2. **Figure support incomplete**: Schema allows 8 figure kinds (`schemas/report.schema.json:284-295`):
   - `image`, `rob_traffic_light`, `forest`, `roc`, `calibration`, `prisma`, `consort`, `dag`

   But `src/rendering/figure_generator.py` only implements 4:
   - ✅ `rob_traffic_light`
   - ✅ `forest`
   - ✅ `prisma`
   - ✅ `consort`
   - ❌ `roc` → raises FigureGenerationError
   - ❌ `calibration` → raises FigureGenerationError
   - ❌ `dag` → raises FigureGenerationError
   - ❌ `image` → raises FigureGenerationError

3. **Source map not rendered**: The `source_map` field is required in schema and populated by LLM, but:
   - No renderer consumes `source_map`
   - No appendix generated with page references
   - No inline source references rendered (e.g., `[S1]`, `[S2]`)

4. **No localization system**: Feature doc mentions `templates/locales/` for Dutch/English section titles, but:
   - Directory does not exist
   - Section titles are whatever LLM emits
   - No standardized naming enforced

### Gap Analysis vs Feature Document

| Feature Doc Promise | Current State | Gap |
|---------------------|---------------|-----|
| Publication-ready LaTeX | Minimal article | Major |
| Full figure coverage (8 types) | 4 types implemented | 4 types missing |
| Source map traceability | Not rendered | Complete gap |
| Localization (nl/en) | Not implemented | Complete gap |
| Type-specific appendices | Not implemented | Complete gap |

---

## Scope

### In Scope (v1.1)

1. **LaTeX Template Completion**
   - Professional formatting with proper typography
   - Table of contents, list of tables/figures
   - Structured appendices
   - Cross-referencing (`\ref`, `\pageref`)

2. **Source Map Rendering**
   - Render `source_map` as appendix table
   - Inline source references in text (`[S1]`, `[S2]`)
   - Optional hyperlinks to PDF pages (viewer-dependent)

3. **Extended Figure Support**
   - `image`: Load pre-generated image file
   - `roc`: ROC curve from discrimination metrics
   - `calibration`: Calibration plot (observed vs predicted)
   - `dag`: Directed Acyclic Graph (networkx-based)
   - Graceful fallback when data missing

4. **Localization System**
   - `templates/locales/nl.json` and `en.json`
   - Standardized section titles per language
   - Configurable via `report.layout.language`

5. **Type-Specific Appendices**
   - RCT: CONSORT checklist table
   - Observational: ROBINS-I domain matrix
   - Systematic Review: PRISMA checklist
   - Prediction: PROBAST assessment matrix

### Out of Scope (Deferred)

- Docker containerization (remains deferred)
- Interactive reports / web dashboards
- Custom template upload via UI
- Real-time collaborative editing

---

## Technical Design

### 1. Template Architecture

**Current structure:**
```
templates/latex/vetrix/
├── main.tex          # Entry point (minimal)
├── preamble.tex      # Package imports
├── sections.tex      # Section rendering (basic)
├── tables.tex        # Table styles (basic)
└── figures.tex       # Figure macros (minimal)
```

**Proposed additions:**
```
templates/latex/vetrix/
├── main.tex          # Enhanced with TOC, appendix structure
├── preamble.tex      # Extended packages (appendix, hyperref)
├── sections.tex      # Type-aware section rendering
├── tables.tex        # Publication-quality booktabs
├── figures.tex       # Full figure support
├── appendix.tex      # NEW: Appendix structure
├── sourcemap.tex     # NEW: Source map rendering
└── checklists/       # NEW: Type-specific checklists
    ├── consort.tex
    ├── prisma.tex
    ├── robins-i.tex
    └── probast.tex

templates/locales/
├── nl.json           # Dutch section titles
└── en.json           # English section titles
```

### 2. Source Map Consumer

**Location:** `src/rendering/sourcemap_renderer.py` (NEW)

```python
def render_source_map_appendix(source_map: list[dict]) -> str:
    """
    Render source_map as LaTeX appendix table.

    Input: [{"code": "S1", "page": 5, "section": "Methods", "anchor_text": "..."}]
    Output: LaTeX tabular with Code, Page, Section, Anchor columns
    """

def inject_source_refs(text: str, source_refs: list[str]) -> str:
    """
    Add inline source references to text.

    Input: "Effect size was 0.72", ["S1", "S2"]
    Output: "Effect size was 0.72\\textsuperscript{[S1,S2]}"
    """
```

**Integration points:**
- `latex_renderer.py`: Call `render_source_map_appendix()` at document end
- `render_text_block()`: Call `inject_source_refs()` for each block

### 3. Extended Figure Generator

**Location:** `src/rendering/figure_generator.py` (extend existing)

```python
def _generate_roc_curve(self, figure_block: dict, data: dict) -> Path:
    """
    Generate ROC curve from discrimination metrics.

    Data source: extraction.model_performance.discrimination
    Required: sensitivity, specificity, or AUC data points
    """

def _generate_calibration_plot(self, figure_block: dict, data: dict) -> Path:
    """
    Generate calibration plot (observed vs predicted).

    Data source: extraction.model_performance.calibration
    Required: predicted probabilities, observed frequencies
    """

def _generate_dag(self, figure_block: dict, data: dict) -> Path:
    """
    Generate DAG using networkx + matplotlib.

    Data source: appraisal.confounding_framework.dag
    Required: nodes, edges definitions
    """

def _load_image(self, figure_block: dict, data: dict) -> Path:
    """
    Load pre-generated image file.

    Data source: figure_block['file']
    Validates file exists, copies to output directory
    """
```

**Fallback strategy:**
- If data missing → Insert placeholder text: "Figure could not be generated (missing data)"
- If rendering fails → Log warning, continue without figure

### 4. Localization System

**Locale files:** `templates/locales/{lang}.json`

```json
{
  "sections": {
    "exec_bottom_line": "Klinische Bottom-line",
    "study_snapshot": "Studieoverzicht",
    "quality_assessment": "Kwaliteitsbeoordeling",
    "results_primary": "Primaire Uitkomsten",
    "source_map": "Bronverwijzingen"
  },
  "labels": {
    "table": "Tabel",
    "figure": "Figuur",
    "appendix": "Bijlage"
  }
}
```

**Loader:** `src/rendering/locales.py` (NEW)

```python
def load_locale(language: str) -> dict:
    """Load locale file for language (nl/en)."""

def get_section_title(section_id: str, language: str) -> str:
    """Get localized section title."""
```

**Integration:**
- Override LLM-generated section titles with locale values
- Or validate LLM titles match locale (warning if mismatch)

---

## Implementation Phases

### Phase 1: LaTeX Template Completion (Week 1-2)
**Goal:** Publication-quality base template

**Deliverables:**
- [ ] Enhanced `main.tex` with TOC, appendix structure
- [ ] Professional `tables.tex` with booktabs, longtable
- [ ] Cross-referencing throughout
- [ ] Unit tests for template rendering

**Acceptance:**
- PDF compiles with all sections
- Tables render with professional formatting
- Cross-references resolve correctly

---

### Phase 2: Source Map Rendering (Week 2-3)
**Goal:** Full traceability in output

**Deliverables:**
- [ ] `src/rendering/sourcemap_renderer.py`
- [ ] Source map appendix generation
- [ ] Inline source references in text blocks
- [ ] Integration with `latex_renderer.py`
- [ ] Unit tests for source map rendering

**Acceptance:**
- Appendix shows all source references
- Inline refs visible in text (e.g., `[S1]`)
- References link to appendix entries

---

### Phase 3: Extended Figure Support (Week 3-4)
**Goal:** All 8 figure kinds implemented

**Deliverables:**
- [ ] `_generate_roc_curve()` implementation
- [ ] `_generate_calibration_plot()` implementation
- [ ] `_generate_dag()` implementation
- [ ] `_load_image()` implementation
- [ ] Graceful fallbacks for missing data
- [ ] Unit tests for each figure type

**Acceptance:**
- All figure kinds render without errors
- Missing data → placeholder text (not crash)
- Visual quality acceptable

---

### Phase 4: Localization System (Week 4-5)
**Goal:** Consistent Dutch/English output

**Deliverables:**
- [ ] `templates/locales/nl.json`
- [ ] `templates/locales/en.json`
- [ ] `src/rendering/locales.py` loader
- [ ] Integration with renderers
- [ ] Unit tests for locale loading

**Acceptance:**
- Section titles match selected language
- All labels localized
- Fallback to English if locale missing

---

### Phase 5: Type-Specific Appendices (Week 5-6)
**Goal:** Complete appendices per study type

**Deliverables:**
- [ ] `templates/latex/vetrix/checklists/consort.tex`
- [ ] `templates/latex/vetrix/checklists/prisma.tex`
- [ ] `templates/latex/vetrix/checklists/robins-i.tex`
- [ ] `templates/latex/vetrix/checklists/probast.tex`
- [ ] Conditional appendix inclusion based on study type
- [ ] Integration tests

**Acceptance:**
- RCT reports include CONSORT checklist
- Systematic reviews include PRISMA checklist
- Observational include ROBINS-I matrix
- Prediction include PROBAST matrix

---

## Testing Strategy

### Unit Tests
- Template rendering for each section type
- Source map appendix generation
- Each figure generator function
- Locale loading and fallback

### Integration Tests
- End-to-end PDF generation per study type
- Source map visibility in output
- Figure rendering in context
- Localization per language

### Visual Regression (Optional)
- PDF → image comparison
- Baseline PDFs for each study type

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| DAG rendering complexity | High | Use simple matplotlib layout, defer networkx |
| ROC/calibration data variability | Medium | Robust data validation, graceful fallbacks |
| LaTeX compilation differences | Medium | Test on multiple TeX distributions |
| Locale maintenance burden | Low | Start with core sections only |

---

## Acceptance Criteria (v1.1)

1. **Publication Quality**: PDFs suitable for journal appendices
2. **Figure Coverage**: All 8 schema figure kinds render (or graceful fallback)
3. **Traceability**: Source map appendix present in all reports
4. **Localization**: Dutch and English reports have correct section titles
5. **Type-Specific**: Each study type has appropriate appendix checklist
6. **No Regressions**: All existing tests continue to pass

---

## Related Documentation

- **v1.0 Feature**: [`features/report-generation.md`](report-generation.md)
- **Architecture**: [`ARCHITECTURE.md`](../ARCHITECTURE.md)
- **API Reference**: [`API.md`](../API.md)
- **Report Guide**: [`docs/report.md`](../docs/report.md)
