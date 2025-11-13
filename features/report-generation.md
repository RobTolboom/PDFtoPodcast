# Feature: Structured Report Generation with LaTeX Rendering

**Status**: Planning
**Branch**: `feature/report-generation`
**Created**: 2025-11-13
**Updated**: 2025-11-13 (v0.3 - Critical review improvements)
**Author**: Rob Tolboom (with Claude Code)

**Summary**
- Automatic generation of structured, professional reports from extraction and appraisal data via LLM-driven JSON output and LaTeX rendering to PDF.
- Block-based architecture separates content from presentation, with iterative validation/correction for quality assurance and type-specific modules for flexibility.
- Main risks are LaTeX complexity and figure generation; mitigations include template-based rendering, phased implementation, and extensive test coverage.

## Scope

**In scope**
- Iterative report generation step after appraisal, including validation and correction prompts
- Block-based JSON structure (`text`, `table`, `figure`, `callout`) for LaTeX rendering
- Support for all publication types (interventional, observational, evidence_synthesis, prediction_prognosis, editorials_opinion)
- Type-specific report sections and appendices (RoB 2, ROBINS-I, CONSORT, PRISMA, PROBAST)
- LaTeX renderer (JSON → LaTeX → PDF) with template system
- Figure generators (traffic light, forest plots, ROC curves, CONSORT/PRISMA flows)
- Full traceability via Source Map with hyperlinks
- CLI and Streamlit UI integration
- Dutch and English output (configurable)

**Out of scope**
- Alternative output formats (HTML, DOCX, Markdown) - only LaTeX/PDF in v1.0
- Interactive reports or web-based dashboards
- Real-time collaborative editing of reports
- Automatic contextualization with literature databases (PubMed, Cochrane) - future feature
- Custom LaTeX templates via UI upload - only built-in templates in v1.0
- Direct PDF annotation or markup tools

---

## Problem Statement

### Current Situation

The pipeline extracts structured data and performs critical appraisal, but produces **no readable final report**:

- **Extraction & Appraisal** (current pipeline):
  - PDF → Classification → Extraction (validated) → Appraisal (validated)
  - **Output**: JSON files with all data and quality assessment
  - Fully structured but not human-readable for end users

- **No Report Generation**:
  - ❌ No integrated overview for clinicians, researchers, editors
  - ❌ No visual presentation (tables, figures) of results
  - ❌ No clinical bottom-line in accessible format
  - ❌ No risk-of-bias visualizations (traffic lights)
  - ❌ No GRADE Summary of Findings tables
  - ❌ No traceability to original PDF pages in report

### Pain Points

1. **Inaccessible Output**: JSON not readable for non-technical users (clinicians, policymakers)
2. **Manual Reporting Required**: Users must write reports from JSON data themselves
3. **No Standardization**: Each report different, inconsistent presentation
4. **Missed Insights**: Important findings lost in large JSON structures
5. **No Visual Impact**: Tables and figures missing, difficult to see trends/patterns
6. **Time-consuming**: Hours of work to produce professional report from extraction/appraisal
7. **Quality Control Difficult**: Hard to verify completeness and correctness without report

### Motivation

Evidence-based medicine and scientific communication require **accessible, professional reports**:

- ✅ **Executive Summary**: Quick decision-making with clinical bottom-line
- ✅ **Visual Presentation**: Tables and figures for overview and impact
- ✅ **Methodological Transparency**: RoB/GRADE clearly presented
- ✅ **Traceability**: Source references to original PDF
- ✅ **Standardization**: Consistent structure following evidence synthesis best practices
- ✅ **Accessibility**: Broad audience (clinicians, researchers, editors, policymakers)

**Benefits of automatic reporting:**
- Fast production of professional reports (minutes vs. hours)
- Consistent quality and structure
- Full integration of extraction + appraisal data
- Reproducible and transparent
- PDF output directly usable for publication, presentations, dossiers

---

## Desired Situation

### Pipeline Workflow (with Report Generation)

```
┌──────────────────────────────────────────────────────────────────┐
│  CURRENT PIPELINE                                                │
└──────────────────────────────────────────────────────────────────┘
  1. Classification → publication_type
  2. Extraction → extraction.json
  3. Validation & Correction → extraction-best.json (iterative)
  4. Critical Appraisal → appraisal-best.json (iterative)
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  NEW STEP: REPORT GENERATION (Iterative)                        │
└──────────────────────────────────────────────────────────────────┘
           │
           ▼
  ┌────────────────────────┐
  │  REPORT GENERATION     │
  │  (LLM creates JSON)    │
  └────────────────────────┘
           │
           ├─ Input: classification.json + extraction-best.json + appraisal-best.json
           ├─ Prompt: Report-generation.txt (type-specific sections)
           └─ Output: report0.json (structured blocks)
           │
           ▼
  ┌────────────────────────┐
  │  REPORT VALIDATION     │
  │  (Report-validation)   │
  └────────────────────────┘
           │
           ▼
     Quality Sufficient?
           │
    ┌──────┴──────┐
   YES           NO
    │              │
    ▼              ▼
  ┌─────┐   Iterations < MAX?
  │ OK  │          │
  └─────┘    ┌─────┴─────┐
            YES          NO
             │             │
             ▼             ▼
    ┌─────────────────┐  ┌──────────┐
    │  CORRECTION     │  │ STOP MAX │
    │  (Report-       │  │  (select │
    │   correction)   │  │   best)  │
    └─────────────────┘  └──────────┘
             │
             └──[LOOP BACK TO REPORT VALIDATION]
           │
           ▼
  report-best.json
           │
           ▼
  ┌────────────────────────┐
  │  LATEX RENDERING       │
  │  (JSON → LaTeX → PDF)  │
  └────────────────────────┘
           │
           ├─ Generate LaTeX sections from blocks
           ├─ Render tables (booktabs)
           ├─ Generate figures (traffic light, forest, ROC, etc.)
           ├─ Insert Source Map with hyperlinks
           └─ Compile to PDF (pdflatex/xelatex)
           │
           ▼
  paper-report.pdf (FINAL OUTPUT)
           │
           ▼
┌──────────────────────────────────────────────────────────────────┐
│  DOWNSTREAM USAGE                                                │
└──────────────────────────────────────────────────────────────────┘
  5. Podcast Script Generation (uses report for narrative)
  6. Evidence Database (indexes reports)
```

### Key Changes

1. **New Pipeline Step**: Report Generation after appraisal, before podcast script
2. **Block-based Architecture**: JSON with `text`, `table`, `figure`, `callout` blocks
3. **Iterative Quality Control**: Validation → Correction loop for report JSON
4. **LaTeX Rendering Pipeline**: JSON → LaTeX → PDF with template system
5. **Figure Generation**: Automatically generated visualizations from data
6. **Type-specific Modules**: Flexible sections per publication type
7. **Source Map Integration**: Traceability with hyperlinks to PDF pages

---

## Technical Design

### 1. Schema Design

**New Schema**: `schemas/report.schema.json`

**Core Principles**:
- ✅ **Block-based**: Sections contain arrays of typed blocks
- ✅ **LaTeX-ready**: Render hints for table specs, figure placement, labels
- ✅ **Traceable**: Source refs at block and cell level
- ✅ **Type-safe**: Strict enum values, additionalProperties: false
- ✅ **Flexible**: Type-specific sections via conditionals
- ✅ **Self-contained**: No external $refs, all definitions inline (like appraisal.schema.json)

**Note**: Report schema follows the same pattern as `appraisal.schema.json` and `validation.schema.json` - it is a pipeline schema (direct `.schema.json` extension) and is self-contained with all definitions inline. **No bundling required** ✅

**Schema Structure**:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "report",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "report_version": {"type": "string", "const": "v1.0"},
    "study_type": {
      "enum": [
        "interventional",
        "observational",
        "systematic_review",
        "prediction",
        "editorials"
      ]
    },
    "metadata": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "title": {"type": "string"},
        "doi": {"type": "string"},
        "authors": {"type": "array", "items": {"type": "string"}},
        "journal": {"type": "string"},
        "publication_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}
      },
      "required": ["title"]
    },
    "layout": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "language": {"enum": ["nl", "en"]},
        "template": {"type": "string", "default": "vetrix"},
        "numbering": {"type": "boolean", "default": true}
      },
      "required": ["language"]
    },
    "sections": {
      "type": "array",
      "items": {"$ref": "#/definitions/section"}
    },
    "source_map": {
      "type": "array",
      "items": {"$ref": "#/definitions/sourceRef"}
    }
  },
  "required": ["report_version", "study_type", "metadata", "layout", "sections"],
  "definitions": {
    "section": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "subsections": {
          "type": "array",
          "items": {"$ref": "#/definitions/section"}
        },
        "blocks": {
          "type": "array",
          "items": {"$ref": "#/definitions/block"}
        }
      },
      "required": ["id", "title"]
    },
    "block": {
      "oneOf": [
        {"$ref": "#/definitions/textBlock"},
        {"$ref": "#/definitions/tableBlock"},
        {"$ref": "#/definitions/figureBlock"},
        {"$ref": "#/definitions/calloutBlock"}
      ]
    },
    "textBlock": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": {"const": "text"},
        "style": {"enum": ["paragraph", "bullets", "numbered"]},
        "content": {
          "type": "array",
          "items": {"type": "string"},
          "minItems": 1
        },
        "source_refs": {
          "type": "array",
          "items": {"type": "string"}
        }
      },
      "required": ["type", "style", "content"]
    },
    "tableBlock": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": {"const": "table"},
        "label": {"type": "string", "pattern": "^tbl_[a-z0-9_]+$"},
        "caption": {"type": "string"},
        "table_kind": {
          "enum": [
            "generic",
            "snapshot",
            "outcomes",
            "harms",
            "rob_domains",
            "grade_sof",
            "confounding_matrix",
            "meta_results",
            "model_metrics"
          ]
        },
        "columns": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "properties": {
              "key": {"type": "string"},
              "header": {"type": "string"},
              "align": {"enum": ["l", "c", "r", "S"]}
            },
            "required": ["key", "header", "align"]
          },
          "minItems": 1
        },
        "rows": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": true
          }
        },
        "render_hints": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "table_spec": {"type": "string"},
            "landscape": {"type": "boolean"},
            "longtable": {"type": "boolean"}
          }
        }
      },
      "required": ["type", "columns", "rows"]
    },
    "figureBlock": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": {"const": "figure"},
        "label": {"type": "string", "pattern": "^fig_[a-z0-9_]+$"},
        "caption": {"type": "string"},
        "figure_kind": {
          "enum": [
            "image",
            "rob_traffic_light",
            "forest",
            "roc",
            "calibration",
            "prisma",
            "consort",
            "dag"
          ]
        },
        "data_ref": {"type": "string"},
        "file": {"type": "string"},
        "render_hints": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "width": {"type": "string"},
            "placement": {"type": "string", "default": "tbp"},
            "subcaptions": {
              "type": "array",
              "items": {"type": "string"}
            }
          }
        }
      },
      "required": ["type", "figure_kind"]
    },
    "calloutBlock": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "type": {"const": "callout"},
        "variant": {"enum": ["warning", "note", "implication", "clinical_pearl"]},
        "text": {"type": "string", "minLength": 10}
      },
      "required": ["type", "variant", "text"]
    },
    "sourceRef": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "code": {"type": "string", "pattern": "^S[0-9]+$"},
        "page": {"type": "integer", "minimum": 1},
        "section": {"type": "string"},
        "table_id": {"type": "string"},
        "figure_id": {"type": "string"},
        "anchor_text": {"type": "string"}
      },
      "required": ["code", "page"]
    }
  }
}
```

**Key Features**:
- **Section hierarchy**: Sections can contain subsections (recursive)
- **Block types**: Text, Table, Figure, Callout with strict typing
- **Labels**: Automatic LaTeX-compatible labels (`tbl_*`, `fig_*`)
- **Render hints**: LaTeX-specific metadata (table_spec, placement, width)
- **Source map**: Central traceability with codes (`S1`, `S2`, etc.)

### 2. Prompt Architecture

#### A. `prompts/Report-generation.txt`
**Purpose**: Generate structured report JSON from extraction + appraisal data

**Input**:
- `CLASSIFICATION_JSON`: Publication type + metadata
- `EXTRACTION_JSON`: Validated extraction data
- `APPRAISAL_JSON`: Validated appraisal data
- `REPORT_SCHEMA`: report.schema.json
- `LANGUAGE`: "nl" or "en"

**Output Contract**:
```
GOAL
Emit exactly ONE JSON object that validates against report.schema.json.

AUDIENCE
Broad audience: clinicians (practical interpretation), researchers (methodological
details), journal editors (quality assessment), policymakers (evidence grading).

REPORT STRUCTURE
Core sections (all study types):
1. exec_bottom_line - Clinical bottom-line (1 page, bullets)
2. study_snapshot - PICOS/PECO table (12 rows max)
3. study_design - Design, setting, flow, interventions/exposures
4. outcome_definitions - Outcomes, timepoints, measurement methods
5. quality_assessment - RoB traffic light + GRADE SoF + applicability
6. results_primary - Primary outcome(s) with effect sizes
7. results_secondary - Secondary outcomes
8. results_harms - Safety/adverse events
9. contextualization - Placement vs prior literature
10. limitations - Methodological limitations
11. bottom_line_extended - Extended interpretation + implications
12. source_map - Traceability appendix

Type-specific sections (append to core):
- RCT: consort_checklist, randomization_details
- Observational: confounding_framework, dag_diagram, sensitivity_analyses
- Systematic Review: prisma_flow, meta_analysis_results, publication_bias
- Prediction: probast_assessment, discrimination_calibration, clinical_utility

BLOCK-BASED OUTPUT
Each section contains blocks:
- textBlock: {type:"text", style:"bullets|paragraph|numbered", content:["..."], source_refs:["S1"]}
- tableBlock: {type:"table", label:"tbl_snapshot", caption:"...", columns:[...], rows:[...], render_hints:{}}
- figureBlock: {type:"figure", label:"fig_rob", figure_kind:"rob_traffic_light", data_ref:"appraisal.risk_of_bias"}
- calloutBlock: {type:"callout", variant:"warning|note|implication", text:"..."}

TRACEABILITY
- Every data point gets source_refs: ["S1", "S2"]
- Source map: [{"code":"S1", "page":5, "table_id":"Table 2", "anchor_text":"Baseline characteristics"}]
- Bundle identical sources per row to reduce noise

EVIDENCE-LOCKED
- No external knowledge beyond extraction + appraisal
- Priority: Extraction > Appraisal > Classification
- If information absent: OMIT the field or note in text
- All numeric data from extraction with exact values + CIs
```

**Section Templates** (examples):

```json
{
  "id": "exec_bottom_line",
  "title": "Clinical Bottom-line",
  "blocks": [
    {
      "type": "text",
      "style": "bullets",
      "content": [
        "Moderate certainty that intervention X reduces pain at 24h (RR 0.72, 95% CI 0.61-0.86)",
        "Effect clinically relevant (NNT=8) but missing data concerns",
        "Generalizable to tertiary centers, unclear for primary care"
      ],
      "source_refs": ["S1", "S2", "S10"]
    }
  ]
},
{
  "id": "study_snapshot",
  "title": "Study Snapshot",
  "blocks": [
    {
      "type": "table",
      "label": "tbl_snapshot",
      "caption": "Core characteristics of the study",
      "table_kind": "snapshot",
      "columns": [
        {"key": "label", "header": "Item", "align": "l"},
        {"key": "value", "header": "Value", "align": "l"}
      ],
      "rows": [
        {"label": "Study design", "value": "Parallel-group RCT", "source_refs": ["S3"]},
        {"label": "Population", "value": "n=420 adults, elective surgery", "source_refs": ["S4"]},
        {"label": "Intervention", "value": "Propofol 2mg/kg IV", "source_refs": ["S5"]},
        {"label": "Control", "value": "Sevoflurane 2% inhalation", "source_refs": ["S6"]},
        {"label": "Primary outcome", "value": "Pain (NRS) at 24h postoperative", "source_refs": ["S7"]},
        {"label": "Follow-up", "value": "30 days", "source_refs": ["S8"]},
        {"label": "GRADE certainty", "value": "Moderate ⊕⊕⊕○", "source_refs": ["S9"]}
      ],
      "render_hints": {"table_spec": "ll"}
    }
  ]
},
{
  "id": "quality_assessment",
  "title": "Quality and Bias",
  "blocks": [
    {
      "type": "figure",
      "label": "fig_rob",
      "caption": "Risk of Bias per domain (RoB 2)",
      "figure_kind": "rob_traffic_light",
      "data_ref": "appraisal.risk_of_bias",
      "render_hints": {"width": "\\linewidth", "placement": "tbp"}
    },
    {
      "type": "table",
      "label": "tbl_grade_sof",
      "caption": "GRADE Summary of Findings",
      "table_kind": "grade_sof",
      "columns": [
        {"key": "outcome", "header": "Outcome", "align": "l"},
        {"key": "effect", "header": "Effect (95% CI)", "align": "l"},
        {"key": "n", "header": "N", "align": "r"},
        {"key": "certainty", "header": "Certainty", "align": "l"},
        {"key": "reasons", "header": "Reasons", "align": "l"}
      ],
      "rows": [
        {
          "outcome": "Pain 24h",
          "effect": "RR 0.72 (0.61-0.86)",
          "n": "410",
          "certainty": "Moderate ⊕⊕⊕○",
          "reasons": "RoB (-1), Imprecision (-1)",
          "source_refs": ["S10", "S11"]
        }
      ],
      "render_hints": {"table_spec": "l l r l l"}
    }
  ]
}
```

**Detailed Section Specifications** (for prompt):

**Section 1-3: Front Matter** (auto-generated by LaTeX renderer, not in JSON)
1. **Title page**: Title, authors, journal, DOI, publication date, QR code
2. **Table of contents**: Auto-generated from section titles
3. **List of tables and figures**: Auto-generated from `\listoftables` and `\listoffigures`

**Section 4: Clinical Bottom-line**
- **Purpose**: Quick decision for clinicians without reading full report
- **Content**:
  - Direction of effect (benefit/harm/no difference)
  - Effect size + 95% CI (primary outcome)
  - GRADE certainty (High/Moderate/Low/Very low)
  - Key risks (RoB concerns briefly mentioned)
  - Applicability (setting, population)
- **Presentation**: 3-5 bullets, compact formulation, no tables
- **Format**: `textBlock` with `style:"bullets"`, max 5 items

**Prompt Instructions** (Report-generation.txt):
```
Section 4: Clinical Bottom-line
- Purpose: Quick decision support (3-5 bullets, max 1 page)
- Content: Direction, effect + CI, GRADE certainty, key risks, applicability
- Format: textBlock with style="bullets"
```

**Section 5: Study Snapshot**
- **Purpose**: One-screen overview of core characteristics
- **Content**: PICOS/PECO + key figures
  - Study design (RCT, cohort, etc.)
  - Population (N, characteristics)
  - Intervention/Exposure (dosage, timing)
  - Control/Comparator
  - Primary outcome (name, timepoint)
  - Main effect measure (RR, MD, HR with CI)
  - GRADE certainty primary outcome
  - Setting (single/multi-center, country)
- **Presentation**: 2-column table ("label"–"value"), maximum 12 rows
- **Format**: `tableBlock` with `table_kind:"snapshot"`

**Prompt Instructions** (Report-generation.txt):
```
Section 5: Study Snapshot
- Purpose: One-screen PICOS overview (max 12 rows)
- Format: tableBlock with table_kind="snapshot", 2 columns (label-value)
```

**Section 6: Study Design and Execution**
- **Purpose**: Reproducibility and plausibility of study
- **Subsections**:
  - 6.1 **Design/setting/centers**: RCT type (parallel/cluster/crossover), open-label vs blinded, number of centers, recruitment period
  - 6.2 **Population and flow**: N randomized, N analyzed, attrition per arm with reasons, ITT vs PP, CONSORT/PRISMA flow
  - 6.3 **Interventions/Exposures**: Dose, route, timing, co-interventions, adherence, protocol deviations
  - 6.4 **Outcome definitions**: Primary/secondary outcomes, measurement tools, timepoints, minimally important difference
  - 6.5 **Statistical approach**: Sample size calculation, analysis plan, multiplicity handling, subgroup pre-specification
- **Detail**: Brief in main text, full specifications in appendix if lengthy
- **Figures**: CONSORT/PRISMA flow if applicable
- **Example**: Mix of `textBlock` (paragraphs) and `figureBlock` (flow diagram)

**Section 7: Quality & Bias**
- **Purpose**: Internal quality and certainty of evidence
- **Subsections**:
  - 7.1 **Risk-of-Bias overview**: Traffic light figure + summary per domain (1-2 sentences per domain)
  - 7.2 **GRADE per outcome**: SoF table with outcome, effect, N, certainty, downgrades
  - 7.3 **Applicability**: External validity (population, intervention, setting, generalizability)
- **Presentation**: Figure (traffic light) + table (GRADE SoF) + text (applicability)
- **Example**: `figureBlock` (`rob_traffic_light`) + `tableBlock` (`grade_sof`) + `textBlock`

**Section 8: Primary Outcome(s)**
- **Purpose**: Complete but scannable result of main question
- **Content**: Per primary outcome:
  - Compact summary (1-2 sentences)
  - Per-arm results (N, events, mean±SD, median [IQR])
  - Contrast effect (RR, MD, HR with 95% CI, p-value)
  - Clinical interpretation (NNT, MID exceeded?)
  - GRADE certainty
- **Presentation**: Text + table (per-arm + contrast)
- **Figures**: Forest plot if subgroups/sensitivity relevant
- **Example**: `textBlock` + `tableBlock` + optional `figureBlock` (`forest`)

**Section 9: Secondary Outcomes**
- **Purpose**: Completeness without overloading main text
- **Content**: Same structure as Section 8, but more compact (no extensive interpretation)
- **Presentation**: Outcome Summary table (all secondary outcomes in 1 table)
  - Columns: Outcome, Measure, Estimate, 95% CI, p, GRADE, N
- **Forest**: Only if direction differs from primary or clinically very relevant
- **Example**: `tableBlock` (`outcomes`) + optional text

**Section 10: Harms/Safety**
- **Purpose**: Balance benefit vs. harm
- **Content**:
  - Adverse events per arm (event rates, SAEs separate)
  - Severity grading (CTCAE if available)
  - Withdrawals due to adverse events
  - Mortality (all-cause if reported)
- **Presentation**: Harms table (rows = AE types, columns = arms + RR/RD)
- **Rule**: Never hide in appendix, always in main body
- **Example**: `tableBlock` (`harms`)

**Section 11: Subgroups and Sensitivity**
- **Purpose**: Robustness and heterogeneity
- **Content**:
  - Subgroup analyses (only show pre-specified, disclaim post-hoc)
  - Interaction tests (p-value for interaction)
  - Sensitivity analyses (ITT vs PP, imputation methods, per-protocol adherence)
  - For observational: E-values, negative controls, quantitative bias analysis
- **Presentation**:
  - Text: 1 paragraph per subgroup with interaction test
  - Forest: Grid-forest if multiple subgroups (columns = strata)
  - Table: Sensitivity analyses results
- **Example**: `textBlock` + optional `figureBlock` (`forest` with subgroups) + `tableBlock`

**Section 12: Exploratory/Estimands/Protocol Deviations**
- **Purpose**: Transparency about unexpected findings and protocol issues
- **Content**:
  - Estimands (ICH E9(R1)): treatment policy vs hypothetical vs composite
  - Protocol deviations (major deviations per arm, impact on results)
  - Exploratory analyses (clearly label as hypothesis-generating)
  - Post-hoc analyses (with rationale why added)
- **Presentation**: Text, no figures (unless estimand critically affects interpretation)
- **Example**: `textBlock` (paragraph) + optional `calloutBlock` (warning about exploratory nature)

**Section 13: Contextualization**
- **Purpose**: Placement vs existing literature
- **Content**:
  - Comparison with prior trials/meta-analyses (direction, effect size)
  - Unique aspects of current study (new population, dosage, comparator)
  - Clinical significance (practice-changing? confirmatory? incremental?)
  - Implementation implications (guidelines, formularies)
- **Presentation**: Text (2-3 paragraphs), no new data
- **Rule**: Only synthesis, no hallucination
- **Example**: `textBlock` (paragraph), possibly `calloutBlock` (implication)

**Section 14: Limitations**
- **Purpose**: Honest assessment of methodological weaknesses
- **Content**:
  - RoB concerns elaborated (link to Section 7 but more detail)
  - GRADE downgrades rationale (imprecision: CI width, inconsistency: I², indirectness: PICO mismatch)
  - Design limitations (open-label, surrogate outcomes, short follow-up)
  - Generalizability concerns (selected population, expert centers)
- **Presentation**: Bullets or numbered list (4-8 items), honest but not exaggerated
- **Example**: `textBlock` (bullets)

**Section 15: Extended Bottom-line and Implications**
- **Purpose**: Synthesis and take-home message
- **Content**:
  - Summary of main findings (benefit + harm)
  - GRADE conclusion (we are [certainty] that intervention X does Y)
  - Implications for clinical practice (who, when, how to apply)
  - Implications for research (knowledge gaps, next studies)
  - Balance between benefit/harm/cost (if cost data available)
- **Presentation**: 2-3 paragraphs, accessible language
- **Example**: `textBlock` (paragraph) + optional `calloutBlock` (clinical_pearl)

**Section 16: Source Map**
- **Purpose**: Full traceability without inline citations
- **Content**: Table with Report-Item-ID → {page, section/table/figure, anchor_text}
- **Presentation**: Appendix table, 4 columns:
  - Code (S1, S2, ...)
  - Page (integer)
  - Location (e.g., "Table 2", "Methods section", "Figure 3 legend")
  - Anchor text (short snippet from original, max 50 chars)
- **Hyperlinks**: Superscripts in main text link to this table
- **Example**: `tableBlock` (`generic`) with `source_map` data

**Section 17: Type-specific Appendices**
- **Purpose**: Depth without overloading main text
- **Content per type**:
  - **RCT**: CONSORT checklist (25 items, yes/no/page#), randomization details (sequence generation method, allocation concealment mechanism, implementation)
  - **Observational**: ROBINS-I detail matrix (7 domains × signaling questions), confounding framework (DAG nodes/edges, adjustment sets), E-value calculations
  - **Systematic Review**: PRISMA checklist (27 items), meta-analysis tables (pooled effects per outcome, heterogeneity stats), funnel plot asymmetry tests
  - **Prediction**: PROBAST detail matrix (4 domains × risk + applicability), discrimination metrics (C-statistic, AUC, 95% CI), calibration plots (observed vs predicted), net benefit/decision curve
- **Presentation**: Checklists as tables, diagrams as figures, method details as text
- **Example**: Mix of `tableBlock`, `figureBlock`, `textBlock` depending on study type

#### B. `prompts/Report-validation.txt`
**Purpose**: Validate report JSON for completeness, accuracy, consistency

**Input**:
- `REPORT_JSON`: Generated report
- `EXTRACTION_JSON`: Original extraction (for cross-checking)
- `APPRAISAL_JSON`: Original appraisal (for cross-checking)
- `REPORT_SCHEMA`: report.schema.json

**Verification Checks**:

1. **Completeness Assessment** (30% weight)
   - All core sections present? (exec_bottom_line, study_snapshot, quality_assessment, results_primary, etc.)
   - Type-specific sections present for study type?
   - All outcomes from extraction included in results?
   - Source map complete? (all source_refs codes present)
   - Tables/figures referenced in text?

2. **Accuracy Verification** (35% weight)
   - Numeric data matches extraction? (effect sizes, CIs, p-values, sample sizes)
   - GRADE ratings match appraisal?
   - RoB judgements match appraisal?
   - No hallucinated data (all claims traceable to extraction/appraisal)?
   - Metadata correct? (title, DOI, authors, journal)

3. **Logical Consistency Checks** (20% weight)
   - Bottom-line consistent with results + GRADE?
   - Limitations align with RoB issues?
   - Contextualization consistent with study design?
   - Source refs resolve? (all codes in source_map)

4. **Schema Compliance** (15% weight)
   - Required fields present?
   - Enum values exact match?
   - Block types valid?
   - Labels follow pattern? (`tbl_*`, `fig_*`)
   - Render hints valid?

**Output**: Validation report JSON
```json
{
  "validation_version": "v1.0",
  "validation_summary": {
    "overall_status": "passed|warning|failed",
    "completeness_score": 0.92,
    "accuracy_score": 0.95,
    "logical_consistency_score": 0.90,
    "schema_compliance_score": 1.0,
    "critical_issues": 0,
    "quality_score": 0.93
  },
  "issues": [
    {
      "severity": "critical|moderate|minor",
      "category": "missing_section|data_mismatch|broken_reference|schema_violation",
      "field_path": "sections[5].blocks[0].content",
      "description": "Primary outcome effect size (RR 0.68) does not match extraction (RR 0.72)",
      "recommendation": "Correct effect size to RR 0.72 (95% CI 0.61-0.86) from extraction.results.contrasts[0]"
    }
  ]
}
```

**Scoring Thresholds** (default):
- `completeness_score >= 0.85`
- `accuracy_score >= 0.95` (high threshold - data correctness critical)
- `logical_consistency_score >= 0.85`
- `schema_compliance_score >= 0.95`
- `critical_issues == 0`

**Note on Metric Naming**:
- Report uses `logical_consistency_score` (bottom-line aligns with results + GRADE + RoB)
- This is consistent with appraisal's `logical_consistency_score` (overall = worst domain rule)
- Extraction uses `accuracy_score` (data matches PDF)
- **These are DISTINCT metrics** with different validation logic:
  - **Appraisal logical_consistency**: Domain-level RoB/GRADE rule enforcement
  - **Report logical_consistency**: Cross-section consistency (executive ↔ results ↔ limitations)

**Quality Score Formula**:
```
quality_score = 0.35 * accuracy_score
              + 0.30 * completeness_score
              + 0.20 * logical_consistency_score
              + 0.15 * schema_compliance_score
```

#### C. `prompts/Report-correction.txt`
**Purpose**: Correct report JSON based on validation issues

**Input**:
- `VALIDATION_REPORT`: Issues from report validation
- `ORIGINAL_REPORT`: Flawed report JSON
- `EXTRACTION_JSON`: Source data for corrections
- `APPRAISAL_JSON`: Source data for corrections
- `REPORT_SCHEMA`: report.schema.json

**Correction Workflow**:
1. **Fix Data Mismatches**
   - Re-check extraction for correct values
   - Update effect sizes, CIs, sample sizes
   - Correct GRADE/RoB references to appraisal

2. **Complete Missing Sections**
   - Add missing core sections
   - Add missing type-specific sections
   - Add missing outcomes from extraction

3. **Strengthen Traceability**
   - Add missing source_refs
   - Complete source_map entries
   - Fix broken references

4. **Schema Compliance Fixes**
   - Correct enum casing
   - Fix label patterns
   - Add missing required fields
   - Remove disallowed properties

**Output**: Corrected report JSON (ready for re-validation)

### 3. API Design

#### New High-Level Function

```python
# src/pipeline/orchestrator.py

def run_report_with_correction(
    extraction_result: dict,
    appraisal_result: dict,
    classification_result: dict,
    llm_provider: str,
    file_manager: PipelineFileManager,
    language: str = "nl",
    max_iterations: int = 3,
    quality_thresholds: dict | None = None,
    progress_callback: Callable | None = None,
) -> dict:
    """
    Run report generation with automatic iterative correction until quality is sufficient.

    Workflow:
        1. Generate report JSON from extraction + appraisal
        2. Validate report (completeness, accuracy, consistency, schema)
        3. If quality insufficient and iterations < max:
           - Run correction
           - Validate corrected report
           - Repeat until quality OK or max iterations reached
        4. Select best iteration based on quality metrics
        5. Return best report + validation + iteration history

    Args:
        extraction_result: Validated extraction JSON
        appraisal_result: Validated appraisal JSON
        classification_result: Classification result (for metadata + publication_type)
        llm_provider: LLM provider name ("openai" | "claude")
        file_manager: File manager for saving report iterations
        language: Report language ("nl" | "en")
        max_iterations: Maximum correction attempts after initial report (default: 3)
        quality_thresholds: Custom thresholds, defaults to:
            {
                'completeness_score': 0.85,
                'accuracy_score': 0.95,
                'logical_consistency_score': 0.85,
                'schema_compliance_score': 0.95,
                'critical_issues': 0
            }
        progress_callback: Optional callback for progress updates

    Returns:
        dict: {
            'best_report': dict,  # Best report JSON
            'best_validation': dict,  # Validation of best report
            'iterations': list[dict],  # All iteration history with metrics
            'final_status': str,  # "passed" | "max_iterations_reached" | "failed"
            'iteration_count': int,  # Total iterations performed
            'improvement_trajectory': list[float],  # Quality scores per iteration
        }

    Raises:
        SchemaLoadError: If report.schema.json cannot be loaded or is invalid
        ValueError: If schema validation fails on any iteration
        LLMProviderError: If LLM calls fail

    Example:
        >>> report_result = run_report_with_correction(
        ...     extraction_result=extraction,
        ...     appraisal_result=appraisal,
        ...     classification_result=classification,
        ...     llm_provider="openai",
        ...     file_manager=file_mgr,
        ...     language="nl",
        ...     max_iterations=3
        ... )
        >>> report_result['final_status']
        'passed'
        >>> len(report_result['best_report']['sections'])
        12
    """
```

#### Helper Functions

```python
def run_report_generation(
    extraction_result: dict,
    appraisal_result: dict,
    classification_result: dict,
    llm_provider: str,
    report_schema: dict,
    language: str = "nl",
) -> dict:
    """
    Run single report generation (no iteration).

    Returns: report JSON
    """

def validate_report(
    report_result: dict,
    extraction_result: dict,
    appraisal_result: dict,
    report_schema: dict,
    llm_provider: str,
) -> dict:
    """
    Validate report JSON using Report-validation.txt prompt.

    Checks:
    - Completeness (all sections, outcomes, source map)
    - Accuracy (data matches extraction/appraisal)
    - Consistency (bottom-line aligns with results)
    - Schema compliance (enums, required fields, labels)

    Returns: validation report JSON
    """

def correct_report(
    report_result: dict,
    validation_report: dict,
    extraction_result: dict,
    appraisal_result: dict,
    report_schema: dict,
    llm_provider: str,
) -> dict:
    """
    Correct report JSON using Report-correction.txt prompt.

    Fixes issues from validation_report:
    - Data mismatches
    - Missing sections/outcomes
    - Broken references
    - Schema violations

    Returns: corrected report JSON
    """

def select_best_report_iteration(iterations: list[dict]) -> dict:
    """
    Select best report iteration using quality_score ranking.

    Primary ranking metric: quality_score (weighted composite)
        quality_score = 0.35 * accuracy_score
                      + 0.30 * completeness_score
                      + 0.20 * logical_consistency_score
                      + 0.15 * schema_compliance_score

    Tie-breakers (in order):
        1. No critical_issues (mandatory filter)
        2. Highest accuracy_score (data correctness paramount)
        3. Lowest iteration number (prefer earlier success)

    Returns: best iteration dict with report + validation
    """
```

### 4. File Management

**Report File Naming** (consistent with extraction/appraisal):

```
tmp/
  ├── paper-extraction-best.json
  ├── paper-appraisal-best.json
  │
  ├── paper-report0.json                  # Initial report (NEW)
  ├── paper-report_validation0.json       # Validation of report (NEW)
  ├── paper-report1.json                  # Corrected report (NEW)
  ├── paper-report_validation1.json
  ├── paper-report-best.json              # Selected best report (NEW)
  ├── paper-report_validation-best.json
  │
  └── paper-report.pdf                    # Final rendered PDF (NEW)
```

**Note on File Naming**: Files are stored using PipelineFileManager pattern:
- **Iteration files**: `{identifier}-{step}{n}.json` (no dash between step and number)
  - Example: `paper-report0.json`, `paper-report1.json`
- **Best files**: `{identifier}-{step}-best.json` (status="best" parameter)
  - Example: `paper-report-best.json`
- **Validation files**: `{identifier}-{step}_validation{n}.json` (underscore in step name itself)
  - Example: `paper-report_validation0.json`, `paper-report_validation1.json`

This matches existing extraction/appraisal file naming exactly (see file_manager.py:66-103).

**File Manager Methods** (extend existing PipelineFileManager):

```python
class PipelineFileManager:
    # ... existing methods ...

    def save_report_iteration(
        self,
        iteration: int,
        report_result: dict,
        validation_result: dict | None = None,
    ) -> tuple[Path, Path | None]:
        """Save report iteration files"""

    def load_report_iteration(
        self,
        iteration: int,
    ) -> tuple[dict, dict | None]:
        """Load report iteration files"""

    def save_best_report(
        self,
        report_result: dict,
        validation_result: dict,
    ) -> tuple[Path, Path]:
        """Save selected best report"""

    def get_report_iterations(self) -> list[dict]:
        """Get all report iterations with metadata"""

    def save_report_pdf(
        self,
        pdf_path: Path,
    ) -> Path:
        """Save final rendered PDF"""
```

### 5. LaTeX Renderer Architecture

**Component**: `src/rendering/latex_renderer.py` (NEW module)

**Purpose**: Convert report JSON → LaTeX → PDF

**Main Function**:

```python
def render_report_to_pdf(
    report_json: dict,
    output_path: Path,
    template_name: str = "vetrix",
    figure_generator: FigureGenerator | None = None,
) -> Path:
    """
    Render report JSON to PDF via LaTeX.

    Args:
        report_json: Validated report JSON
        output_path: Output PDF path
        template_name: LaTeX template name (default: "vetrix")
        figure_generator: Optional custom figure generator

    Returns:
        Path to generated PDF

    Raises:
        LaTeXCompilationError: If pdflatex/xelatex compilation fails
        FigureGenerationError: If figure generation fails
        TemplateNotFoundError: If template doesn't exist

    Workflow:
        1. Load LaTeX template
        2. Generate figures (traffic light, forest, etc.)
        3. Render sections → LaTeX
        4. Render tables → LaTeX (booktabs)
        5. Insert figure references
        6. Build source map hyperlinks
        7. Compile LaTeX → PDF
        8. Return PDF path
    """
```

**Template Structure**:

```
templates/latex/
  ├── vetrix/
  │   ├── main.tex           # Main template with placeholders
  │   ├── preamble.tex       # Packages and macros
  │   ├── sections.tex       # Section rendering rules
  │   ├── tables.tex         # Table styles
  │   ├── figures.tex        # Figure placement rules
  │   └── bibliography.bib   # Citation template (future)
  └── minimal/
      └── main.tex           # Simple template for testing
```

**Preamble** (`templates/latex/vetrix/preamble.tex`):

```latex
\usepackage{booktabs}           % Professional tables
\usepackage{longtable}          % Multi-page tables
\usepackage{threeparttable}     % Table notes
\usepackage{siunitx}            % Number formatting
\usepackage{caption}            % Caption customization
\usepackage{subcaption}         % Subfigures
\usepackage{xcolor}             % Colors for traffic lights
\usepackage{hyperref}           % Hyperlinks
\usepackage{cleveref}           % Cross-references
\usepackage{pgfplots}           % Forest plots
\usepackage{geometry}           % Page layout
\usepackage{microtype}          % Typography
\usepackage{fontspec}           % Font selection (xelatex)

% Custom macros
\newcommand{\ES}[4]{\textbf{#1} #2\,(95\%\,CI #3--#4)}  % Effect size
\newcommand{\SRC}[1]{\textsuperscript{\hyperref[sources:#1]{[#1]}}}  % Source code
```

**Block Renderers**:

```python
class BlockRenderer:
    """Base class for rendering report blocks to LaTeX"""

    def render_text_block(self, block: dict) -> str:
        """Render textBlock → LaTeX (paragraph, bullets, numbered)"""

    def render_table_block(self, block: dict) -> str:
        """Render tableBlock → LaTeX (booktabs, siunitx)"""

    def render_figure_block(self, block: dict, figures_dir: Path) -> str:
        """Render figureBlock → LaTeX (includegraphics)"""

    def render_callout_block(self, block: dict) -> str:
        """Render calloutBlock → LaTeX (tcolorbox)"""
```

**Example Table Rendering**:

```python
def render_table_block(self, block: dict) -> str:
    label = block.get('label', '')
    caption = block.get('caption', '')
    columns = block['columns']
    rows = block['rows']
    render_hints = block.get('render_hints', {})

    # Build column spec
    col_spec = render_hints.get('table_spec',
                                 ''.join(c['align'] for c in columns))

    # Build LaTeX
    latex = []
    latex.append(r'\begin{table}[tbp]')
    latex.append(r'\centering')
    latex.append(r'\caption{' + caption + r'}')
    if label:
        latex.append(r'\label{' + label + r'}')
    latex.append(r'\begin{tabular}{' + col_spec + r'}')
    latex.append(r'\toprule')

    # Headers
    headers = ' & '.join(c['header'] for c in columns)
    latex.append(headers + r' \\')
    latex.append(r'\midrule')

    # Rows
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col['key'], '')
            # Add source refs if present
            if 'source_refs' in row:
                refs = ''.join(r'\SRC{' + ref + r'}' for ref in row['source_refs'])
                value = str(value) + refs
            cells.append(str(value))
        latex.append(' & '.join(cells) + r' \\')

    latex.append(r'\bottomrule')
    latex.append(r'\end{tabular}')
    latex.append(r'\end{table}')

    return '\n'.join(latex)
```

### 6. Figure Generation Strategy

**Component**: `src/rendering/figure_generator.py` (NEW module)

**Supported Figure Types**:

1. **RoB Traffic Light** (`rob_traffic_light`)
   - Input: `appraisal.risk_of_bias`
   - Output: Colored grid (green/yellow/red) per domain
   - Library: matplotlib + custom layout

2. **Forest Plot** (`forest`)
   - Input: `extraction.results.contrasts` + subgroups
   - Output: Forest plot with effect sizes + CIs
   - Library: `forestplot` package or custom matplotlib

3. **ROC Curve** (`roc`)
   - Input: `extraction.performance` (sensitivity, specificity points)
   - Output: ROC curve with AUC
   - Library: scikit-learn + matplotlib

4. **Calibration Plot** (`calibration`)
   - Input: `extraction.performance.calibration`
   - Output: Calibration curve (observed vs predicted)
   - Library: scikit-learn + matplotlib

5. **CONSORT Flow** (`consort`)
   - Input: `extraction.population.flow`
   - Output: CONSORT diagram (enrollment → randomization → analysis)
   - Library: GraphViz or custom matplotlib

6. **PRISMA Flow** (`prisma`)
   - Input: `extraction.search_results.flow`
   - Output: PRISMA diagram (identification → screening → included)
   - Library: GraphViz or custom matplotlib

7. **DAG** (`dag`)
   - Input: `extraction.causal_strategy.dag`
   - Output: Directed acyclic graph
   - Library: networkx + matplotlib or GraphViz

**Figure Generator Interface**:

```python
class FigureGenerator:
    """Generate figures from extraction/appraisal data"""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_figure(
        self,
        figure_block: dict,
        data: dict,  # Full report JSON for data_ref resolution
    ) -> Path:
        """
        Generate figure from block specification.

        Args:
            figure_block: figureBlock from report JSON
            data: Full data dict for resolving data_ref

        Returns:
            Path to generated figure file (PNG/PDF)

        Raises:
            FigureGenerationError: If generation fails
            DataRefNotFoundError: If data_ref cannot be resolved
        """
        figure_kind = figure_block['figure_kind']

        if figure_kind == 'rob_traffic_light':
            return self._generate_rob_traffic_light(figure_block, data)
        elif figure_kind == 'forest':
            return self._generate_forest_plot(figure_block, data)
        elif figure_kind == 'roc':
            return self._generate_roc_curve(figure_block, data)
        # ... etc.

    def _generate_rob_traffic_light(
        self,
        figure_block: dict,
        data: dict,
    ) -> Path:
        """Generate RoB traffic light figure"""
        # Extract data via data_ref
        data_ref = figure_block['data_ref']  # "appraisal.risk_of_bias"
        rob_data = self._resolve_data_ref(data_ref, data)

        # Create figure
        fig, ax = plt.subplots(figsize=(8, 4))

        # Plot domains as colored boxes
        domains = rob_data['domains']
        colors = {
            'Low risk': 'green',
            'Some concerns': 'yellow',
            'High risk': 'red'
        }

        for i, domain in enumerate(domains):
            judgement = domain['judgement']
            color = colors.get(judgement, 'gray')
            ax.add_patch(plt.Rectangle((0, i), 1, 1, color=color))
            ax.text(1.1, i+0.5, domain['domain'], va='center')

        # Overall judgement
        overall_color = colors.get(rob_data['overall'], 'gray')
        ax.add_patch(plt.Rectangle((0, len(domains)+0.5), 1, 1,
                                   color=overall_color, linewidth=2))
        ax.text(1.1, len(domains)+1, 'Overall', va='center', weight='bold')

        ax.set_xlim(0, 5)
        ax.set_ylim(0, len(domains)+1.5)
        ax.axis('off')

        # Save
        output_path = self.output_dir / f"{figure_block['label']}.png"
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close(fig)

        return output_path

    def _resolve_data_ref(self, data_ref: str, data: dict) -> dict:
        """Resolve dot-notation data reference (e.g., 'appraisal.risk_of_bias')"""
        keys = data_ref.split('.')
        result = data
        for key in keys:
            result = result[key]
        return result
```

---

## Implementation Phases

### Phase 1: JSON Schema + Prompt (Week 1)
**Goal**: Define report structure and generation prompt

**Deliverables**:
- [ ] `schemas/report.schema.json` (complete with all block types, ~500 lines)
- [ ] `prompts/Report-generation.txt` (comprehensive instructions, ~800 lines)
- [ ] Schema validation tests (unit tests for schema correctness)
- [ ] Prompt dry-run with mock data (manual validation)

**Testing**:
- Schema validates against sample report JSONs
- Prompt produces valid JSON for all study types
- Manual review of generated report structure

**Acceptance**:
- Schema complete with all definitions
- Prompt covers all core + type-specific sections
- Sample reports validate successfully

### Phase 2: Report Generator (Orchestrator) (Week 2)
**Goal**: Implement basic report generation in pipeline

**Deliverables**:
- [ ] `src/pipeline/orchestrator.py`:
  - `run_report_generation()` (single-pass generator)
  - LLM call with extraction + appraisal input
  - Schema validation of output
- [ ] Integration with `run_single_step()` dispatch
- [ ] File manager methods (`save_report_iteration`, etc.)
- [ ] Unit tests for report generation function

**Testing**:
- Single-pass generation works for all study types
- Output validates against schema
- Files saved with correct naming

**Acceptance**:
- Report generation produces valid JSON
- Integration in pipeline complete
- Unit tests pass

### Phase 3: Validation & Correction Loop (Week 2-3)
**Goal**: Implement iterative quality improvement

**Deliverables**:
- [ ] `prompts/Report-validation.txt` (~300 lines)
- [ ] `prompts/Report-correction.txt` (~400 lines)
- [ ] `src/pipeline/orchestrator.py`:
  - `run_report_with_correction()` (main iterative function)
  - `validate_report()` (validation wrapper)
  - `correct_report()` (correction wrapper)
  - `select_best_report_iteration()` (best selection)
  - Quality threshold evaluation
  - Iteration loop with stop criteria
- [ ] Integration tests (full loop with mock LLM)

**Testing**:
- Validation catches known errors (data mismatches, missing sections)
- Correction fixes validation issues
- Best iteration selection works correctly
- Integration tests cover all study types

**Acceptance**:
- Iterative loop runs to completion
- Quality improves across iterations
- Best report selected correctly

### Phase 4: LaTeX Renderer (Basic) (Week 3-4)
**Goal**: Basic LaTeX rendering (no figures yet)

**Deliverables**:
- [ ] `src/rendering/latex_renderer.py` (NEW module)
  - `render_report_to_pdf()` (main function)
  - `BlockRenderer` class (text, table, callout)
  - Template loading and placeholder substitution
- [ ] `templates/latex/vetrix/` (LaTeX templates)
  - `main.tex`, `preamble.tex`, `sections.tex`, `tables.tex`
- [ ] LaTeX compilation pipeline (pdflatex/xelatex)
- [ ] Unit tests for block renderers

**Testing**:
- Text blocks render correctly
- Tables render with booktabs
- Callouts render with tcolorbox
- PDF compiles without errors

**Acceptance**:
- Basic PDF generation works
- All block types (except figures) render
- LaTeX compilation reliable

### Phase 5: Figure Generators (Week 4-5)
**Goal**: Generate all figure types from data

**Deliverables**:
- [ ] `src/rendering/figure_generator.py` (NEW module)
  - `FigureGenerator` class
  - `_generate_rob_traffic_light()` (RoB visual)
  - `_generate_forest_plot()` (forest plots)
  - `_generate_roc_curve()` (ROC curves)
  - `_generate_calibration_plot()` (calibration)
  - `_generate_consort_flow()` (CONSORT diagram)
  - `_generate_prisma_flow()` (PRISMA diagram)
  - `_generate_dag()` (DAG visualization)
- [ ] Figure integration in `BlockRenderer`
- [ ] Unit tests for each figure type

**Testing**:
- Each figure type generates correctly
- Figures embed in LaTeX correctly
- High-resolution output (300 dpi)
- Edge cases handled (missing data, extreme values)

**Acceptance**:
- All 7 figure types implemented
- Figures render in PDF
- Visual quality acceptable

### Phase 6: UI Integration (Streamlit) (Week 5)
**Goal**: Add report step to Streamlit UI

**Deliverables**:
- [ ] New execution step: "Report Generation" (after Appraisal)
- [ ] Real-time progress updates during iterations
- [ ] Display report summary:
  - Study snapshot table
  - GRADE ratings
  - Download PDF button
- [ ] Iteration history visualization
- [ ] Manual re-run option

**UI Mock**:
```
┌─────────────────────────────────────────────────────┐
│ 5. REPORT GENERATION                         ✅     │
├─────────────────────────────────────────────────────┤
│ Report Quality: Passed (score: 0.94)               │
│ Iterations: 2                                       │
│                                                     │
│ Sections: 12 core + 3 type-specific                │
│ Tables: 5 (snapshot, outcomes, harms, RoB, GRADE) │
│ Figures: 3 (RoB traffic light, forest, CONSORT)   │
│                                                     │
│ [📄 Download PDF] [📊 View Report JSON]            │
│ [🔄 Regenerate Report]                             │
└─────────────────────────────────────────────────────┘
```

**Testing**:
- UI updates during report generation
- PDF download works
- Report summary displays correctly
- Manual regeneration works

**Acceptance**:
- Report step integrated in execution flow
- PDF downloadable from UI
- Iteration history accessible

### Phase 7: CLI Support (Week 6)
**Goal**: Add report step to CLI pipeline

**Deliverables**:
- [ ] `run_pipeline.py`:
  - New step: `--step report`
  - Integration in full pipeline (ALL_PIPELINE_STEPS include report)
  - Progress output for iterations
  - PDF output path logging
  - CLI flags (consistent with appraisal naming pattern):
    - `--report-language` (nl|en, default: nl)
    - `--report-max-iter` (default: 3)
    - `--report-template` (default: vetrix)
    - `--report-single-pass` (skip correction loop, like --appraisal-single-pass)
    - `--skip-report` (disable report step entirely, for backward compatibility)
- [ ] Error handling and user feedback

**Example Usage**:
```bash
# Run full pipeline with report
python run_pipeline.py paper.pdf --llm openai

# Run report only (requires extraction + appraisal)
python run_pipeline.py paper.pdf --step report --llm openai

# Custom language and template
python run_pipeline.py paper.pdf --step report --report-language en --report-template minimal

# Single-pass mode (no iterative correction)
python run_pipeline.py paper.pdf --step report --report-single-pass

# Skip report in full pipeline
python run_pipeline.py paper.pdf --llm openai --skip-report
```

**Testing**:
- CLI runs with --step report
- Full pipeline includes report
- Custom flags work correctly
- Error messages clear

**Acceptance**:
- CLI supports report generation
- Full pipeline produces PDF
- Documentation updated (README + docs/report.md)

### Phase 8: Testing & Documentation (Week 6-7)
**Goal**: Comprehensive testing and documentation

**Deliverables**:
- [ ] Unit tests:
  - Report generation routing (`test_report_functions.py`)
  - Report validation quality helpers (`test_report_quality.py`)
  - LaTeX renderer blocks (`test_latex_renderer.py`)
  - Figure generators (`test_figure_generator.py`)
  - File management (`test_file_manager.py`)
- [ ] Integration tests:
  - `tests/integration/test_report_full_loop.py` (5 study types, all iterations)
  - End-to-end PDF generation
- [ ] Documentation:
  - `docs/report.md` (complete report generation guide)
  - README section "Generating Reports"
  - ARCHITECTURE update (report module)
  - API.md update (report functions)
  - LaTeX template documentation
- [ ] CHANGELOG entries
- [ ] Test data/fixtures:
  - Sample reports for each study type
  - Expected PDF outputs (visual regression)

**Test Strategy**:
1. **Unit Tests**: Each function isolated
2. **Integration Tests**: Full report loop + rendering
3. **End-to-End Tests**: CLI + UI with real PDFs
4. **Visual Regression**: PDF output comparison

**Acceptance**:
- Test coverage ≥ 90% for report code
- All tests pass
- Documentation complete
- Sample PDFs generated successfully

---

## Testing Strategy

### Test Cases by Study Type

#### 1. Interventional Trial (RCT)
**Test Data**: RCT extraction + RoB 2 appraisal

**Expected Report Sections**:
- Core: exec_bottom_line, study_snapshot, study_design, quality_assessment, results_primary, results_secondary, results_harms, contextualization, limitations, bottom_line_extended, source_map
- Type-specific: consort_checklist, randomization_details

**Expected Tables**:
- `tbl_snapshot`: PICOS + key characteristics
- `tbl_outcomes`: All outcomes with effect sizes + GRADE
- `tbl_harms`: Adverse events per arm
- `tbl_rob_domains`: RoB 2 domains with rationales
- `tbl_grade_sof`: Summary of Findings

**Expected Figures**:
- `fig_rob`: Traffic light (5 domains + overall)
- `fig_forest_primary`: Forest plot for primary outcome
- `fig_consort`: CONSORT flow diagram

**Validation Issues to Test**:
- Missing outcome in results section
- Effect size mismatch with extraction
- GRADE rating mismatch with appraisal
- Broken source reference
- Missing type-specific section

#### 2. Observational Analytic
**Test Data**: Cohort study extraction + ROBINS-I appraisal

**Expected Sections**:
- Core + Type-specific: confounding_framework, dag_diagram, sensitivity_analyses

**Expected Tables**:
- `tbl_confounding_matrix`: Variables, methods, residual confounding
- `tbl_sensitivity`: E-values, negative controls, bias analysis

**Expected Figures**:
- `fig_rob`: Traffic light (7 ROBINS-I domains)
- `fig_dag`: Directed acyclic graph (if available)

#### 3. Systematic Review
**Test Data**: Meta-analysis extraction + AMSTAR 2 appraisal

**Expected Sections**:
- Core + Type-specific: prisma_flow, meta_analysis_results, publication_bias

**Expected Figures**:
- `fig_prisma`: PRISMA flow diagram
- `fig_forest_meta`: Pooled forest plot with I²
- `fig_funnel`: Funnel plot (if publication bias assessed)

#### 4. Prediction Model
**Test Data**: Prediction model extraction + PROBAST appraisal

**Expected Sections**:
- Core + Type-specific: probast_assessment, discrimination_calibration, clinical_utility

**Expected Figures**:
- `fig_roc`: ROC curve with AUC
- `fig_calibration`: Calibration plot
- `fig_dca`: Decision curve analysis (if available)

#### 5. Editorial
**Test Data**: Editorial extraction + argument quality appraisal

**Expected Sections**:
- Core (adapted): argument_structure, evidence_base, counterarguments

**Expected Tables**:
- `tbl_claims`: Claims with evidence type + support strength

### Edge Cases

1. **Missing Data**: Incomplete extraction → report notes limitations
2. **Max Iterations Reached**: Quality never sufficient → select best + warning
3. **Schema Validation Failure**: Report JSON invalid → correction fixes
4. **LaTeX Compilation Failure**: Template error → clear error message + fallback
5. **Figure Generation Failure**: Data insufficient → skip figure + note in text
6. **Large Report**: >50 pages → longtable + page breaks
7. **Unicode Characters**: Greek letters, symbols → fontspec/xelatex handles

### Performance Metrics

**Target Benchmarks** (design goals):
- **Report generation time**: < 45s per iteration (GPT-4o)
- **Validation time**: < 20s per iteration
- **Correction time**: < 45s per iteration
- **Figure generation time**: < 10s per figure
- **LaTeX compilation time**: < 15s (pdflatex)
- **Total report pipeline**: < 3 minutes for 3 iterations + rendering

**Empirical Benchmarks** (to be added after Phase 8):
After testing on 25 representative papers (5 per study type), add empirical data:
```markdown
### Performance Benchmarks (Empirical - Phase 8)

Tested on 25 representative papers (5 per study type):
- **Report generation**: X.Xs average (range Y-Z, GPT-4o)
- **Validation**: X.Xs average
- **Correction**: X.Xs average
- **Figure generation**:
  - RoB traffic light: X.Xs (matplotlib)
  - Forest plot: X.Xs (custom rendering)
  - CONSORT flow: X.Xs (GraphViz)
  - ROC curve: X.Xs (scikit-learn)
- **LaTeX compilation**: X.Xs average (pdflatex), X.X% failure rate first attempt
- **Total pipeline** (3 iterations + rendering): Xm XXs average

Failure modes observed:
- LaTeX unicode errors: X% (xelatex fallback resolves Y%)
- Figure data missing: X% (graceful degradation to note in text)
- Max iterations reached: X% (quality score still >0.XX)
```

---

## Best Practices for Reporting

### Content Principles

1. **Executive with Hard Numbers**
   - Bottom-line always contains: direction, effect size with 95% CI, GRADE certainty
   - No vague language ("seems to help") but concrete statements ("reduces pain with RR 0.72")
   - Maximum 1 page, readable in 2 minutes

   **Examples**:
   ```
   ❌ BAD: "The intervention seems to help with pain."
   ✅ GOOD: "Moderate certainty that intervention X reduces pain at 24h (RR 0.72, 95% CI 0.61-0.86)"
   ```

   **JSON Example**:
   ```json
   {
     "type": "text",
     "style": "bullets",
     "content": [
       "Moderate certainty that propofol reduces postoperative pain at 24h (RR 0.72, 95% CI 0.61-0.86)",
       "Effect clinically relevant (NNT=8) but missing data concerns (10% attrition)",
       "Generalizable to tertiary centers, unclear for primary care"
     ],
     "source_refs": ["S1", "S10", "S14"]
   }
   ```

2. **Results Always with Confidence Intervals**
   - 95% CI mandatory for all effect measures
   - P-values secondary (never without CI)
   - Absolute effect measures alongside relative (NNT, risk difference)

3. **Harms Never Hidden**
   - Safety data always in main body (Section 10), never only in appendix
   - Serious adverse events shown separately
   - Withdrawals due to adverse events explicit

4. **Subgroups: Only Pre-specified**
   - Post-hoc subgroups clearly labeled as exploratory
   - Always show interaction test (p-value)
   - No "cherry-picking" of significant subgroups

5. **Traceability Via Source Map**
   - No long inline page numbers in text
   - Superscript codes (`[S12]`) per data point/claim
   - Central Source Map table in Section 16

### Presentation Principles

6. **Visual Hierarchy**
   - Executive sections (4-5) most prominent
   - Methods/quality (6-7) for transparency but not overwhelming
   - Results (8-12) extensive but scannable with tables
   - Context/interpretation (13-15) synthesis without new data

7. **Tables vs. Figures**
   - **Table** for compact, multi-outcome data (Outcome Summary, Harms)
   - **Figure** for direction/heterogeneity (forest), diagnostics (ROC), flow (CONSORT)
   - One outcome per forest for readability
   - Multiple outcomes in forest-grid only for logical clusters

8. **GRADE Transparency**
   - SoF table always before detailed results (in Section 7)
   - Downgrades explicit with rationale (not just "imprecision -1")
   - Executive shows only primary outcome certainty

9. **Source References**
   - Bundle identical sources per table row (not each cell separately)
   - Max 3 source codes per data point for readability
   - Source Map sorted by code (S1, S2, ...) not by page

### Pitfalls to Avoid

10. **Too Many Forest Plots in Main Text**
    - ❌ Forest for every outcome → overload
    - ✅ Forest only for primary + clinically critical secondary

11. **Hiding GRADE Reasons**
    - ❌ "Moderate certainty" without explanation
    - ✅ "Moderate ⊕⊕⊕○: Downgraded for risk of bias (-1) and imprecision (-1)"

    **JSON Example**:
    ```json
    {
      "outcome": "Pain 24h",
      "effect": "RR 0.72 (0.61-0.86)",
      "n": "410",
      "certainty": "Moderate ⊕⊕⊕○",
      "reasons": "RoB (-1): Open-label design. Imprecision (-1): CI crosses MID.",
      "source_refs": ["S10", "S11"]
    }
    ```

12. **Inconsistency Text vs. Table**
    - ❌ Text says RR 0.72, table shows RR 0.68
    - ✅ Validation prompt checks cross-consistency

13. **Uncontrolled Significance Hunting**
    - ❌ Showing "significant" post-hoc subgroups without correction
    - ✅ Multiplicity disclosure + Bonferroni/FDR where relevant

14. **Methodological Details in Executive**
    - ❌ Bottom-line with "computer-generated random sequence via IWRS"
    - ✅ Bottom-line focuses on clinical impact, details in Section 6

15. **Hallucination of Contextualization**
    - ❌ "This contradicts Smith 2020 meta-analysis" (not in extraction)
    - ✅ Only comparison if extraction contains it, otherwise omit

### LaTeX-specific Best Practices

16. **Table Specs Consistent**
    - Use `siunitx` S-column for numeric data
    - `l` for text, `c` for short labels, `r` for counts
    - Max 7 columns for readability without landscape

17. **Figure Placement**
    - Default `[tbp]` (top/bottom/page), not `[h]` (here - forces whitespace)
    - Grouped figures: use `subcaption` instead of multiple floats
    - Landscape: only for wide tables (>10 columns)

18. **Cross-references**
    - Use `\Cref{tbl:outcomes,fig:rob}` → "Tables 3 and Figure 2"
    - Never hardcode "see table 3" (renumbering breaks)

19. **Unicode Handling**
    - GRADE symbols: use direct UTF-8 (⊕⊕⊕○) with `fontspec`
    - Greek letters: direct UTF-8 (α, β) instead of `$\alpha$` for inline text
    - Compile with `xelatex` if unicode issues

20. **Hyperlinks Subtle**
    - Source ref superscripts: `\hyperref[sources:S12]{[S12]}` (no color change)
    - Internal links: `hidelinks` option in hyperref (no red boxes)

---

## Acceptance Criteria

### Functional

1. **Report generation works for all 5 study types** with correct sections
2. **Iterative correction** improves quality scores across iterations
3. **Best iteration selected** based on validation scores
4. **PDF rendering** produces professional, publication-ready output
5. **Figures generated** automatically from extraction/appraisal data
6. **Source map** provides complete traceability to original PDF
7. **Type-specific sections** included based on publication type
8. **Language support** works for both Dutch and English
9. **UI integration** allows report generation and PDF download
10. **CLI support** runs report step standalone or in full pipeline

### Technical

1. **Schema validation** catches all malformed report JSONs
2. **Block rendering** correctly converts all block types to LaTeX
3. **Figure generation** produces high-quality images (300 dpi)
4. **LaTeX compilation** reliable (handles unicode, long tables, page breaks)
5. **Template system** allows easy customization
6. **Error handling** graceful failures with clear messages
7. **Test coverage** ≥ 90% for report code
8. **Documentation** complete (README, docs/report.md, ARCHITECTURE, API)

### Quality

1. **Completeness**: All core sections present, all outcomes included
2. **Accuracy**: All numeric data matches extraction exactly
3. **Consistency**: Bottom-line aligns with results + GRADE
4. **Traceability**: All claims have source references
5. **Visual quality**: Tables and figures clear and professional
6. **Readability**: Report accessible to target audiences

### User Experience

1. **Clear progress indicators** during report generation iterations
2. **Intuitive PDF download** from UI
3. **Iteration history accessible** for transparency
4. **Error messages actionable** when report generation fails
5. **Fast turnaround**: < 3 minutes from extraction to PDF

---

## Risks and Mitigations

### Risk 1: LaTeX Compilation Complexity
**Description**: LaTeX compilation errors difficult to debug (missing packages, syntax errors, unicode issues)

**Impact**: High - report generation fails without clear user feedback

**Mitigation**:
- Use minimal preamble with only essential packages
- Extensive LaTeX escaping for special characters
- Fallback to xelatex for unicode issues
- Capture LaTeX error logs and parse for common issues
- Unit tests for each block renderer with edge cases
- Template validation before rendering
- Clear error messages with troubleshooting steps

### Risk 2: Figure Generation Quality
**Description**: Automatically generated figures may be low-quality or incorrect

**Impact**: Medium - figures unreadable or misleading

**Mitigation**:
- High-resolution output (300 dpi) by default
- Manual validation of figure generators with test data
- Fallback to "figure not available" note if generation fails
- Visual regression tests (compare PDFs)
- Allow manual figure upload override (future)
- Document figure requirements and limitations

### Risk 3: Prompt Token Limits
**Description**: Extraction + appraisal + schema + prompt exceeds context window

**Impact**: Medium - report generation fails for complex papers

**Mitigation**:
- Use long-context models (GPT-4o: 128k context, Claude 3.5 Sonnet: 200k context)
- Typical extraction + appraisal + prompt: ~15k-25k tokens (well within limits)
- **Future enhancement** (NOT in v1.0): Truncate extraction to essential fields if needed
  - Implementation plan: Keep study_design, population, outcomes, results, risk_of_bias
  - Omit: Full text extractions, supplementary tables, detailed appendices
  - Trigger: If total input tokens > 100k (safety margin for 128k models)
- Document maximum supported complexity (e.g., max 50 outcomes, max 20 tables)
- Provide "lite" report option with fewer sections (future feature)

### Risk 4: LLM Hallucination in Report
**Description**: LLM adds data not present in extraction/appraisal

**Impact**: High - report contains false information

**Mitigation**:
- Strong validation prompt checks all data against sources
- High accuracy_score threshold (0.95)
- Correction prompt removes unsupported claims
- Unit tests verify no hallucinated data in sample reports
- Manual spot-checks of generated reports

### Risk 5: Type-specific Complexity
**Description**: Different study types require very different report structures

**Impact**: Medium - prompt becomes too complex or misses edge cases

**Mitigation**:
- Modular section definitions in prompt
- Clear conditional logic for type-specific sections
- Separate validation rules per study type
- Test coverage for all 5 study types
- Document type-specific requirements

### Risk 6: PDF File Size
**Description**: High-resolution figures → large PDF files (>50 MB)

**Impact**: Low - slow downloads, storage issues

**Mitigation**:
- Compress images before embedding
- Use PDF compression (gs -dPDFSETTINGS=/ebook)
- Configurable DPI (default 300, option for 150)
- Warn user if file size exceeds threshold

### Risk 7: Template Maintenance
**Description**: LaTeX templates become outdated or incompatible

**Impact**: Low - templates need frequent updates

**Mitigation**:
- Use stable LaTeX packages (booktabs, siunitx)
- Version templates with schema version
- Document template customization guidelines
- Automated tests catch template regressions

---

## Open Questions & Dependencies

### Open Questions

1. **Language Support**: Start with only Dutch, or both (NL + EN) in v1.0?
   - **Proposal**: Both languages in v1.0, language parameter required

2. **Template Customization**: Should UI support template upload?
   - **Proposal**: No in v1.0, only built-in templates

3. **Figure Formats**: PNG vs PDF for embedded figures?
   - **Proposal**: PDF for vector graphics (ROC, forest), PNG for raster (traffic light)

4. **Citation Style**: How to reference original paper in report?
   - **Proposal**: DOI + full citation in metadata, footnote on first page

5. **Report Versioning**: How to handle schema changes in future?
   - **Proposal**: `report_version` field in JSON, backwards compatibility in renderer

### Migration & Compatibility

**v1.0 → v1.1+ Schema Changes**:
- `report_version` field in JSON tracks schema version (e.g., "v1.0", "v1.1")
- LaTeX renderer checks version before rendering:
  ```python
  if report_json['report_version'] == 'v1.0':
      apply_v1_0_renderer()
  elif report_json['report_version'] == 'v1.1':
      apply_v1_1_renderer()
  ```
- Old reports (v1.0) remain readable and renderable
- New features (v1.1+) are opt-in (e.g., new block types, new section IDs)
- Breaking changes: Major version bump (v2.0) with migration script

**Enabling Report in Existing Workflows**:
- **Backward compatible**: Pipeline works WITHOUT report (optional step)
- **CLI**: Report generation ONLY runs if:
  - Full pipeline: `--llm openai` (includes all steps by default)
  - Explicit step: `--step report`
  - Opt-out: `--skip-report` flag disables report step
- **Streamlit**: Report step has "Skip" button (like other steps)
- **Existing scripts**: No breaking changes
  - Old scripts calling `run_four_step_pipeline()` continue to work (4 steps: classification, extraction, validation, appraisal)
  - New `run_five_step_pipeline()` adds report as step 5 (opt-in)
- **File outputs**: Report files (`paper-report0.json`, `paper-report.pdf`) only created if report step runs
- **Error handling**: If report fails, pipeline continues (logs error but doesn't block downstream steps like podcast)

### Dependencies

**Pipeline Dependencies** (HARD REQUIREMENTS):
- **Classification** must be complete with valid publication_type
  - Used for: Report section routing (type-specific sections)
  - Error handling: If classification missing or invalid → BLOCK report generation

- **Extraction** must be complete with quality_score ≥ 0.90
  - Used for: All report data (results, population, methods, outcomes)
  - Error handling: If extraction quality_score < 0.90 → LOG WARNING but proceed with report (add disclaimer in Section 14: Limitations)
  - Rationale: Low extraction quality → poor report quality, but blocking prevents any output

- **Appraisal** must be complete with final_status = "passed" or "max_iterations_reached"
  - Used for: RoB traffic lights (Section 7), GRADE tables (Section 7), quality assessment, limitations
  - Error handling:
    - If appraisal final_status = "failed" critically → BLOCK report generation, show error in UI/CLI
    - If appraisal final_status = "max_iterations_reached" with quality_score ≥ 0.70 → Proceed with report but add disclaimer: "Appraisal quality below optimal threshold. Manual review recommended for Section 7 (Quality & Bias)."
    - If appraisal final_status = "early_stopped_degradation" → Proceed with best appraisal iteration
  - Rationale: Report **cannot** generate meaningful Section 7 (Quality & Bias) or Section 14 (Limitations) without appraisal RoB/GRADE data

**Dependency Validation** (in `run_report_with_correction()`):
```python
# Pseudo-code for dependency checks
if not classification_result:
    raise ValueError("Classification required for report generation")

if not extraction_result:
    raise ValueError("Extraction required for report generation")

if extraction_result.get('quality_score', 0) < 0.90:
    logger.warning("Extraction quality below 0.90 - report quality may be affected")
    # Add to report metadata: extraction_quality_warning = True

if not appraisal_result:
    raise ValueError("Appraisal required for report generation")

if appraisal_result.get('final_status') in ['failed_schema_validation', 'failed_llm_error']:
    raise ValueError("Appraisal failed critically - cannot generate report without RoB/GRADE data")

if appraisal_result.get('final_status') == 'max_iterations_reached':
    if appraisal_result.get('best_validation', {}).get('quality_score', 0) < 0.70:
        raise ValueError("Appraisal quality too low (< 0.70) - manual appraisal required before reporting")
    else:
        logger.warning("Appraisal reached max iterations - report Section 7 may need manual review")
        # Add to report metadata: appraisal_quality_warning = True
```

**LLM Dependencies**:
- **LLM Providers** must be available (OpenAI + Anthropic accounts)
- Context window requirements:
  - Classification JSON: ~500-1000 tokens
  - Extraction JSON: ~5,000-15,000 tokens (varies by paper complexity)
  - Appraisal JSON: ~2,000-5,000 tokens
  - Report schema: ~2,000 tokens
  - Report generation prompt: ~3,000-4,000 tokens
  - **Total input**: ~12,500-27,000 tokens (well within GPT-4o 128k / Claude 3.5 Sonnet 200k limits)

**Rendering Dependencies**:
- **LaTeX Distribution** must be installed (TeX Live, MiKTeX)
- **Python Packages**: matplotlib, seaborn, scikit-learn, networkx, pygraphviz (optional for DAG)
- **System Fonts**: For xelatex fontspec (system-dependent)

---

## Next Steps (after Feature Document Approval)

1. **Review Feature Document** with stakeholders
2. **Prioritize Phases** (suggested: 1 → 2 → 3 → 4, defer 5-6 for beta release)
3. **Setup LaTeX Environment** (install TeX Live, test compilation)
4. **Start Phase 1**: Draft schema and generation prompt
5. **Pilot Testing**: Generate sample report from existing extraction/appraisal
6. **Iterate**: Refine schema/prompt based on pilot results

---

## References

### Evidence Synthesis Standards
- **CONSORT**: https://www.consort-statement.org/ (RCT reporting)
- **PRISMA**: http://www.prisma-statement.org/ (Systematic review reporting)
- **GRADE**: https://www.gradeworkinggroup.org/ (Evidence certainty)
- **Cochrane Handbook**: https://training.cochrane.org/handbook (Evidence synthesis guide)

### LaTeX Resources
- **TikZ/PGF**: https://www.overleaf.com/learn/latex/TikZ_package (Graphics)
- **booktabs**: https://ctan.org/pkg/booktabs (Professional tables)
- **siunitx**: https://ctan.org/pkg/siunitx (Number formatting)
- **Overleaf Templates**: https://www.overleaf.com/latex/templates (Inspiration)

### Related Features
- `features/appraisal.md` - Critical appraisal feature (complete)
- `features/iterative-validation-correction.md` - Validation pattern (template)
- `ARCHITECTURE.md` - Pipeline component documentation
- `schemas/report.schema.json` - Report output schema (to be created)
- `prompts/Report-*.txt` - Report generation prompts (to be created)
