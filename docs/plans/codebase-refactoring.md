# Feature: Codebase Refactoring

## Doel

Refactoring van de PDFtoPodcast codebase om technische schuld te verminderen, onderhoudbaarheid te verbeteren, en codeduplicatie te elimineren.

## Business Value

- **Onderhoudbaarheid:** Kleinere, gefocuste modules zijn makkelijker te begrijpen en wijzigen
- **Testbaarheid:** Geïsoleerde componenten zijn eenvoudiger te unit-testen
- **Uitbreidbaarheid:** Nieuwe pipeline-stappen of validatie-methoden kunnen schoner worden toegevoegd
- **Onboarding:** Nieuwe teamleden kunnen modules sneller begrijpen

## Scope

### In Scope

1. Opsplitsing `orchestrator.py` (4,851 → ~2,500 regels)
2. Consolidatie van 3x gedupliceerde iteratieve correctie-loops
3. Scheiding UI en business logica in `execution.py`
4. Creatie van herbruikbare quality/iterative modules
5. Optioneel: Extractie van step modules

### Buiten Scope

- Functionele wijzigingen aan de pipeline
- Nieuwe features of pipeline-stappen
- Database of storage wijzigingen
- API wijzigingen (backward compatibility behouden)

## Branch

**Branch naam:** `feature/codebase-refactoring`

## Takenlijst

### Fase 1: Quality Module (Fundament)
- [ ] `src/pipeline/quality/__init__.py`
- [ ] `src/pipeline/quality/metrics.py` - QualityMetrics dataclass
- [ ] `src/pipeline/quality/scoring.py` - safe_score(), quality_rank()
- [ ] `src/pipeline/quality/thresholds.py` - Thresholds + is_quality_sufficient()
- [ ] `tests/unit/test_quality_module.py`

### Fase 2: Iteration Tracking
- [ ] `src/pipeline/iterative/__init__.py`
- [ ] `src/pipeline/iterative/iteration_tracker.py`
- [ ] `src/pipeline/iterative/best_selector.py`
- [ ] `tests/unit/test_iteration_tracker.py`

### Fase 3: Loop Runner
- [ ] `src/pipeline/iterative/loop_runner.py` - IterativeLoopRunner
- [ ] `tests/unit/test_loop_runner.py`

### Fase 4: Migratie Extraction Loop
- [ ] Refactor `run_validation_with_correction()` → IterativeLoopRunner
- [ ] Backward compatibility aliases
- [ ] Valideer bestaande tests

### Fase 5: Migratie Appraisal Loop
- [ ] Refactor `run_appraisal_with_correction()` → IterativeLoopRunner
- [ ] Valideer bestaande tests

### Fase 6: Migratie Report Loop
- [ ] Refactor `run_report_with_correction()` → IterativeLoopRunner
- [ ] Valideer bestaande tests

### Fase 7: Step Modules (Optioneel) ✅
- [x] `src/pipeline/steps/classification.py`
- [x] `src/pipeline/steps/extraction.py`
- [x] `src/pipeline/steps/validation.py`
- [x] `src/pipeline/steps/appraisal.py`
- [x] `src/pipeline/steps/report.py`
- [x] `src/pipeline/steps/podcast.py`

### Fase 8: UI Formatters
- [ ] `src/streamlit_app/formatters/__init__.py`
- [ ] `src/streamlit_app/formatters/result_formatters.py`
- [ ] `src/streamlit_app/formatters/artifact_finder.py`
- [ ] Refactor `execution.py` naar alleen UI
- [ ] `tests/unit/test_result_formatters.py`

## Risico's

| Risico | Impact | Mitigatie |
|--------|--------|-----------|
| Breaking changes in API | Hoog | Backward compatibility aliases behouden |
| Falende tests | Medium | Run `make test` na elke fase |
| Loop Runner te rigide | Medium | Design met callbacks, niet inheritance |
| Streamlit state issues | Laag | Session state structuur niet wijzigen |

## Acceptatiecriteria

1. **Regelreductie:** orchestrator.py van ~4,851 → ~2,500 regels
2. **Geen duplicatie:** Eén `safe_score()`, één `quality_rank()`, één `_extract_metrics()`
3. **Tests:** Alle bestaande tests slagen
4. **Coverage:** Nieuwe modules hebben >80% test coverage
5. **Geen breaking changes:** CLI en Streamlit werken identiek
6. **Documentatie:** ARCHITECTURE.md en CHANGELOG.md bijgewerkt

## Nieuwe Module Structuur

```
src/pipeline/
├── orchestrator.py              # Slanker: alleen step coördinatie
├── quality/
│   ├── __init__.py
│   ├── metrics.py               # QualityMetrics dataclass
│   ├── scoring.py               # Weights, quality_rank()
│   └── thresholds.py            # Drempelwaarden + is_quality_sufficient()
├── iterative/
│   ├── __init__.py
│   ├── loop_runner.py           # Generieke IterativeLoopRunner
│   ├── iteration_tracker.py     # IterationData, degradation detection
│   └── best_selector.py         # select_best_iteration()
└── steps/                       # (Optioneel, fase 7)
    ├── classification.py
    ├── extraction.py
    └── ...

src/streamlit_app/
├── screens/
│   └── execution.py             # Alleen UI rendering
└── formatters/
    ├── result_formatters.py     # Business logica voor weergave
    └── artifact_finder.py       # Bestand discovery logica
```

## Geschatte Effort

| Fase | Beschrijving | Effort |
|------|--------------|--------|
| 1 | Quality Module | 1-2 dagen |
| 2 | Iteration Tracking | 1 dag |
| 3 | Loop Runner | 2-3 dagen |
| 4 | Migratie Extraction | 1-2 dagen |
| 5 | Migratie Appraisal | 1 dag |
| 6 | Migratie Report | 1 dag |
| 7 | Step Modules | 2-3 dagen |
| 8 | UI Formatters | 1-2 dagen |
| **Totaal** | | **10-15 dagen** |

## Referenties

- Plan: `.claude/plans/sprightly-orbiting-cherny.md`
- Architectuur: `ARCHITECTURE.md`
- Bijdragen: `CONTRIBUTING.md`
