# Feature: Improve CLI Output

**Status**: In Progress (Phase 1-4 complete, Phase 5-7 partial)
**Branch**: `feature/improve-cli-output`
**Created**: 2025-01-19
**Author**: Rob Tolboom (with Claude Code)

**Summary**
- Refactor CLI console output for clarity, consistency, and professionalism
- Standardize on English-only output (remove Dutch/English mix)
- Fix spinner/progress overlap issues
- Add verbose/quiet modes for different use cases
- Reduce duplicate output and improve information hierarchy

---

## Scope

**In scope**
- Standardize all CLI output to English
- Fix Rich spinner overlapping with status messages
- Consistent formatting (headers, dividers, tables)
- Add `--verbose` and `--quiet` CLI flags
- Reduce repetitive output (validation summaries, quality scores)
- Live-updating status table during pipeline execution
- Clear progress indication per step

**Out of scope (v1)**
- Internationalization (i18n) framework for multiple languages
- Log file output (already exists via logging module)
- GUI/TUI alternative interface
- Color theme customization

---

## Problem Statement

### Current Situation

The CLI output has several usability issues identified from real pipeline runs:

#### 1. Language Mixing (Dutch + English)
```
# Dutch in run_pipeline.py:
"Bezig met zes-staps extractie pipeline..."
"Tussenbestanden worden opgeslagen in: tmp/"
"Pipeline voltooid"
"Samenvatting" / "Stap" / "Onderdeel" / "Resultaat"

# English in pipeline steps:
"Uploading PDF for classification..."
"Classification Result:"
"Running schema validation..."
```

**Impact**: Confusing, unprofessional, inconsistent user experience.

#### 2. Spinner Overlaps with Text
```
⠹ Bezig met zes-staps extractie pipeline...Uploading PDF for classification...
⠧ Bezig met zes-staps extractie pipeline...🔎 Predicted type: interventional_trial
```

**Impact**: Hard to read, text runs together, unclear what's happening.

#### 3. Inconsistent Header Formatting
```
═══ STEP 1: CLASSIFICATION ═══        (box-drawing characters)
=== STEP 3: ITERATIVE VALIDATION ===  (ASCII equals signs)
```

**Impact**: Visual inconsistency, looks unpolished.

#### 4. Excessive/Repetitive Output
- Validation results shown 4-5 times per iteration
- Same quality scores displayed multiple times
- Schema errors repeated in full each occurrence
- ~100+ console.print() calls across codebase

**Impact**: Important information buried in noise, hard to follow progress.

#### 5. Static Status Table
The initial pipeline status table:
```
  Stap                       Status
  1. Classificatie           ⏳
  2. Data extractie
```
...never updates during execution.

**Impact**: User doesn't see real-time progress at a glance.

#### 6. No Output Control
- No `--quiet` mode for CI/scripting
- No `--verbose` mode for debugging
- Always full output regardless of context

**Impact**: Too noisy for automation, not detailed enough for debugging.

---

## Desired Situation

### Clean, Consistent Output Example

```
╭──────────────────────────────────────────────────────────╮
│ PDFtoPodcast Pipeline                                    │
│ PDF → Classify → Extract → Validate → Appraise → Output  │
╰──────────────────────────────────────────────────────────╯

📄 Input: dvm.pdf
🤖 Provider: OpenAI (gpt-4.1)
📁 Output: tmp/ (DOI-based naming)

┌─────────────────────────────────────┬──────────┬──────────┐
│ Step                                │ Status   │ Duration │
├─────────────────────────────────────┼──────────┼──────────┤
│ 1. Classification                   │ ✅ Done  │ 24.7s    │
│ 2. Data Extraction                  │ ⏳ Running│          │
│ 3. Validation & Correction          │ ○ Pending│          │
│ 4. Critical Appraisal               │ ○ Pending│          │
│ 5. Report Generation                │ ⏭️ Skip   │          │
│ 6. Podcast Generation               │ ○ Pending│          │
└─────────────────────────────────────┴──────────┴──────────┘

─── Step 2: Data Extraction ───────────────────────────────

  Uploading PDF... done
  Running schema-based extraction...

  ████████████████████░░░░░░░░░░ 67% extracting outcomes

```

### Key Improvements

| Aspect | Before | After |
|--------|--------|-------|
| Language | Mixed Dutch/English | English only |
| Spinner | Overlaps with text | Dedicated line, clears before new output |
| Headers | Inconsistent (`═══` vs `===`) | Consistent Rich styling |
| Verbosity | Always full output | `--quiet` / default / `--verbose` |
| Progress | Static table | Live-updating table with durations |
| Repetition | Same info 4-5x | Show once, summarize at end |

---

## Technical Design

### 1. Output Manager Class

Create a centralized output manager to handle all console output consistently.

**New file**: `src/pipeline/output_manager.py`

```python
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from enum import Enum

class OutputLevel(Enum):
    QUIET = 0    # Errors only, final summary
    NORMAL = 1   # Progress, key results (default)
    VERBOSE = 2  # All details, debug info

class PipelineOutputManager:
    """Centralized output management for consistent CLI experience."""

    def __init__(
        self,
        console: Console | None = None,
        level: OutputLevel = OutputLevel.NORMAL,
    ):
        self.console = console or Console()
        self.level = level
        self._live: Live | None = None
        self._status_table: Table | None = None
        self._step_states: dict[str, str] = {}
        self._step_durations: dict[str, float] = {}

    def start_pipeline(self, pdf_path: str, provider: str, output_dir: str):
        """Display pipeline header and initialize live status table."""

    def update_step(self, step: int, status: str, duration: float | None = None):
        """Update step status in the live table."""

    def step_header(self, step: int, name: str):
        """Display step header (only in NORMAL/VERBOSE mode)."""

    def info(self, message: str, level: OutputLevel = OutputLevel.NORMAL):
        """Print info message if level permits."""

    def success(self, message: str):
        """Print success message with checkmark."""

    def warning(self, message: str):
        """Print warning message."""

    def error(self, message: str):
        """Print error message (always shown)."""

    def progress(self, message: str, current: int, total: int):
        """Show progress bar (NORMAL/VERBOSE only)."""

    def detail(self, message: str):
        """Print detail (VERBOSE only)."""

    def end_pipeline(self, summary: dict):
        """Display final summary table."""
```

### 2. Live Status Table

Use Rich `Live` display for real-time status updates:

```python
from rich.live import Live
from rich.table import Table

def create_status_table(steps: list[dict]) -> Table:
    table = Table(title="Pipeline Progress", box=box.ROUNDED)
    table.add_column("Step", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right", style="dim")

    for step in steps:
        status_icon = {
            "pending": "○",
            "running": "[yellow]⏳[/yellow]",
            "done": "[green]✅[/green]",
            "failed": "[red]❌[/red]",
            "skipped": "[dim]⏭️[/dim]",
        }.get(step["status"], "○")

        table.add_row(
            step["name"],
            status_icon,
            f"{step['duration']:.1f}s" if step.get("duration") else ""
        )

    return table

# Usage with Live context:
with Live(create_status_table(steps), refresh_per_second=4) as live:
    for step in pipeline_steps:
        run_step(step)
        steps[step.index]["status"] = "done"
        live.update(create_status_table(steps))
```

### 3. Spinner Fix

Replace overlapping spinner with proper status context:

**Before (problematic):**
```python
with console.status("Bezig met pipeline...", spinner="dots"):
    console.print("Uploading PDF...")  # Overlaps!
```

**After (clean):**
```python
# Option A: Use Live display instead of status
output.update_step(2, "running")
output.info("Uploading PDF...")

# Option B: Stop spinner before printing
with console.status("Processing...", spinner="dots") as status:
    status.stop()
    console.print("Uploading PDF...")
    status.start()
```

### 4. CLI Flag Integration

**run_pipeline.py additions:**

```python
parser.add_argument(
    "--quiet", "-q",
    action="store_true",
    help="Minimal output (errors and final summary only)"
)
parser.add_argument(
    "--verbose", "-v",
    action="store_true",
    help="Detailed output for debugging"
)

# Determine output level
if args.quiet:
    level = OutputLevel.QUIET
elif args.verbose:
    level = OutputLevel.VERBOSE
else:
    level = OutputLevel.NORMAL

output_manager = PipelineOutputManager(level=level)
```

### 5. Language Standardization

All user-facing strings converted to English:

| Dutch | English |
|-------|---------|
| Bezig met zes-staps extractie pipeline... | Running six-step extraction pipeline... |
| Tussenbestanden worden opgeslagen in | Intermediate files saved to |
| Pipeline voltooid | Pipeline completed |
| Samenvatting | Summary |
| Stap | Step |
| Onderdeel | Component |
| Resultaat | Result |
| Publicatietype | Publication type |
| Classificatie betrouwbaarheid | Classification confidence |
| Val & Corr | Validation & Correction |
| Compleetheid score | Completeness score |

### 6. Output Deduplication

**Validation output reduction:**

```python
# Before: Show full validation 4-5 times
# After: Show once per iteration, summary at end

def display_validation_result(validation: dict, iteration: int):
    """Compact single-line validation summary."""
    scores = validation.get("quality_scores", {})
    output.info(
        f"Iteration {iteration}: "
        f"Schema {scores.get('schema_compliance', 0):.0%} | "
        f"Complete {scores.get('completeness', 0):.0%} | "
        f"Accurate {scores.get('accuracy', 0):.0%}"
    )
```

---

## Files to Modify

### New Files
- `src/pipeline/output_manager.py` - Centralized output management

### Modified Files
| File | Changes |
|------|---------|
| `run_pipeline.py` | Add --quiet/--verbose flags, use OutputManager, translate Dutch strings |
| `src/pipeline/orchestrator.py` | Use OutputManager instead of direct console.print |
| `src/pipeline/iterative/loop_runner.py` | Reduce duplicate output, use OutputManager |
| `src/pipeline/steps/classification.py` | Use OutputManager |
| `src/pipeline/steps/extraction.py` | Use OutputManager |
| `src/pipeline/steps/validation.py` | Use OutputManager, compact output |
| `src/pipeline/steps/appraisal.py` | Use OutputManager |
| `src/pipeline/steps/report.py` | Use OutputManager |
| `src/pipeline/podcast_logic.py` | Use OutputManager |
| `src/pipeline/utils.py` | Update helper functions |

---

## Implementation Phases

### Phase 1: Output Manager Foundation ✅ COMPLETE
**Goal**: Create centralized output management

**Deliverables**:
- [x] `src/pipeline/output_manager.py` with `PipelineOutputManager` class
- [x] `OutputLevel` enum (QUIET, NORMAL, VERBOSE)
- [x] Basic methods: `info()`, `success()`, `warning()`, `error()`, `detail()`
- [ ] Unit tests for output manager (future)

**Acceptance**:
- Output manager can be instantiated with different levels
- Messages filtered correctly by level
- Tests pass

### Phase 2: Live Status Table
**Goal**: Real-time updating progress table

**Deliverables**:
- [ ] `start_pipeline()` method with Live display
- [ ] `update_step()` method for status changes
- [ ] `end_pipeline()` method to finalize display
- [ ] Step duration tracking

**Acceptance**:
- Table updates in real-time during pipeline
- Durations shown for completed steps
- Clean transition between steps

### Phase 3: CLI Integration ✅ COMPLETE
**Goal**: Add --quiet and --verbose flags

**Deliverables**:
- [x] CLI argument parsing for `-q`/`--quiet` and `-v`/`--verbose`
- [ ] OutputManager instantiation in run_pipeline.py (future integration)
- [ ] Pass OutputManager to orchestrator (future integration)

**Acceptance**:
- `--quiet` shows only errors and final summary
- `--verbose` shows all details
- Default shows balanced progress info

### Phase 4: Language Standardization ✅ COMPLETE
**Goal**: Convert all output to English

**Deliverables**:
- [x] Translate all Dutch strings in run_pipeline.py (42+ strings)
- [x] Translate CLI argument help text
- [x] Translate table headers and labels
- [x] Update final summary output
- [x] Translate Dutch strings in orchestrator.py (2 strings)

**Acceptance**:
- No Dutch text in any CLI output
- All user-facing strings in English
- Consistent terminology throughout

### Phase 5: Migrate Pipeline Steps
**Goal**: Update all step modules to use OutputManager

**Deliverables**:
- [ ] Update classification.py
- [ ] Update extraction.py
- [ ] Update validation.py
- [ ] Update appraisal.py
- [ ] Update report.py
- [ ] Update podcast_logic.py

**Acceptance**:
- All steps use OutputManager
- Consistent formatting across steps
- No direct console.print() calls outside OutputManager

### Phase 6: Output Deduplication ✅ COMPLETE
**Goal**: Reduce repetitive output in iterative loops

**Deliverables**:
- [x] Refactor loop_runner.py output
- [x] Compact validation summaries (single line per iteration)
- [x] Single iteration summary per loop
- [ ] Schema errors shown once (with count if repeated) (future)

**Acceptance**:
- Validation info shown once per iteration
- Clear iteration progression
- Important info not buried in noise

### Phase 7: Testing & Documentation
**Goal**: Comprehensive testing and documentation

**Deliverables**:
- [ ] Unit tests for OutputManager
- [ ] Integration tests for CLI flags
- [ ] Update README.md with new CLI options
- [ ] Update CHANGELOG.md
- [ ] Update ARCHITECTURE.md

**Acceptance**:
- All tests pass
- Documentation complete
- `make test` passes

---

## Risks and Mitigations

### Risk 1: Breaking Existing Automation
**Description**: Users may have scripts parsing current CLI output

**Impact**: Medium - could break CI/CD pipelines

**Mitigation**:
- Document changes in CHANGELOG
- `--quiet` mode provides stable, minimal output for parsing
- Consider `--json` output flag for machine-readable results (future)

### Risk 2: Live Display Compatibility
**Description**: Rich Live display may not work in all terminals

**Impact**: Low - Rich handles fallback gracefully

**Mitigation**:
- Rich has built-in terminal capability detection
- Falls back to static output if Live not supported
- Test in common terminals (iTerm, Terminal.app, VS Code)

### Risk 3: Performance Impact
**Description**: Live updates could slow down pipeline

**Impact**: Low - display updates are async

**Mitigation**:
- Limit refresh rate (4/second)
- Disable Live in QUIET mode
- Profile if issues arise

---

## Acceptance Criteria

### Functional
1. **All output in English** - no Dutch text anywhere
2. **--quiet flag** works - only errors and final summary
3. **--verbose flag** works - detailed debug output
4. **Live status table** updates during pipeline execution
5. **No spinner overlap** - text always readable

### Technical
1. **OutputManager** used by all pipeline components
2. **Backward compatible** - default behavior similar to before (but cleaner)
3. **Tests pass** - unit and integration tests
4. **Documentation updated** - README, CHANGELOG, ARCHITECTURE

### Quality
1. **Consistent formatting** - same header style, spacing, colors
2. **Clear progress indication** - user always knows what's happening
3. **Reduced noise** - important info not buried in repetition
4. **Professional appearance** - polished, coherent output

---

## Future Extensions

### v1.1: JSON Output Mode
- `--json` flag for machine-readable output
- Structured result for CI/CD integration
- Progress events as JSON lines

### v1.2: Log File Integration
- `--log-file` to save verbose output to file
- Separate from console output level
- Timestamp each log entry

### v1.3: Progress Callbacks
- Webhook notifications for long-running pipelines
- Integration with external monitoring

---

## References

### Related Features
- `docs/plans/podcast-generation.md` - Uses CLI output
- `ARCHITECTURE.md` - Pipeline architecture documentation

### Rich Library Documentation
- [Rich Console](https://rich.readthedocs.io/en/latest/console.html)
- [Rich Live Display](https://rich.readthedocs.io/en/latest/live.html)
- [Rich Progress](https://rich.readthedocs.io/en/latest/progress.html)
