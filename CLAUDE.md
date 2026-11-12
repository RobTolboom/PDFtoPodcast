# PDFtoPodcast — working agreements

Owner: Rob Tolboom. These rules add to the global rules in ~/.claude/CLAUDE.md.
The user has final authority; when a rule is unclear, ask instead of guessing.

## 1. Approval

### Free: no approval needed
- Reading and searching files, git history, logs and documentation.
- Read-only commands: `git status`, `git log`, `git diff`, listing files,
  static analysis that writes nothing.
- Looking things up on the web.

### Plan first, then execute
- Before changing anything, present a short plan: what changes, in which
  files, and the exact git/build commands involved. Wait for approval.
- An approved plan may be executed on a topic branch without asking again
  for each edit, including `make format`, `make lint` and `make test-fast`.
- Stop and ask again when the work deviates from the approved plan: other
  files, a different approach, a larger scope, or an unexpected failure
  that needs a design choice.
- Never change an approved plan on your own.

### Always ask separately, every time
- `git commit`, `git push`, opening or merging a pull request.
- Deleting files or branches, rewriting history, force operations.
- Adding, removing or upgrading dependencies.
- Changing CI workflows or repository settings.
- Anything that spends API money: a real pipeline run, LLM calls in tests
  or scripts, batch runs. State the expected number of calls first.
- Anything outside this repository.

Approval for one action does not carry over to the next one.

### Never
- Commit directly to `main`.
- Read, print or commit `.env` or any other secret.

## 2. Workflows

Start of day
1. `git checkout main && git pull origin main`
2. If dependencies changed: `make install-dev`

After a code change
1. `make format`
2. `make lint`
3. `make test-fast`

Before a commit
1. `make commit` (run it a second time if the hooks modified files)
2. `git commit -m "type: description"`

Before a push
1. `make ci`
2. `git push`

## 3. Branches and commits

- `main` is protected. Work on short-lived topic branches:
  `feature/...` (or `feat/...`), `fix/...`, `docs/...`, `refactor/...`,
  `test/...`, `chore/...`, `release/...`.
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`,
  `chore:`.
- Commit in small, coherent steps; format, lint and fast tests pass before
  each commit.
- Record the branch name in the plan or design document of the feature.

## 4. Planning

- Small changes: the plan in the conversation is enough.
- Features and refactors: write a plan with goal, scope, task list, risks
  and acceptance criteria.
  - Default location: `docs/plans/`.
  - With the superpowers flow (brainstorming -> writing-plans): design in
    `docs/superpowers/specs/YYYY-MM-DD-feature-design.md`, plan in
    `docs/superpowers/plans/YYYY-MM-DD-feature.md`. This takes precedence
    when those skills are in use.
- Implementation starts only after explicit approval of the plan.

## 5. What a pull request must contain

Check these once per pull request, not for every individual edit.
- Tests: added or updated for changed behaviour.
- `CHANGELOG.md`: an entry under "Unreleased" for anything a user would
  notice. Append to an existing `### Added/Changed/Fixed` heading; do not
  create a duplicate heading.
- Documentation: update `README.md`, `ARCHITECTURE.md`, `API.md` or other
  docs only where the text they contain is no longer true. Do not add
  documentation for its own sake.
- Schemas: if `common.schema.json` or a type schema changed, the bundled
  files are regenerated and committed.

## 6. Reporting

- Before an action that needs separate approval, say in one line what you
  are about to do and why.
- Report results as they are: failing tests with their output, skipped
  steps as skipped, unverified claims as unverified.
- Conversation in Dutch. Code, comments, commit messages and
  documentation in English.

## 7. Project context

### Architecture
- 6-step pipeline: Classification -> Extraction -> Validation/Correction
  -> Appraisal -> Report -> Podcast.
- LLM: OpenAI GPT-5.5 with `strict: False` structured output (the schema
  is guidance only).
- Entry points: `python run_pipeline.py paper.pdf` (CLI) and
  `streamlit run app.py` (web interface).

### Key directories
- `src/pipeline/steps/`: step implementations (classification,
  extraction, validation, appraisal, report, podcast).
- `src/pipeline/iterative/`: generic `IterativeLoopRunner` and iteration
  tracker.
- `src/pipeline/quality/`: thresholds, metrics, scoring
  (`QualityThresholds` dataclass).
- `src/pipeline/orchestrator.py`: orchestration; delegates to `steps/`
  and holds backward-compat aliases.
- `src/llm/`: LLM providers behind the `BaseLLMProvider` interface.
- `schemas/`: JSON schemas, `common.schema.json` and `json-bundler.py`.
- `prompts/`: all prompt templates.
- `src/rendering/`: output renderers (LaTeX, WeasyPrint, Markdown,
  Podcast).

### Gotchas
- After editing `common.schema.json` or a type schema, run
  `make bundle-schemas` (or `cd schemas && python json-bundler.py`) to
  regenerate all 5 `*_bundled.json` files.
- Pre-commit hooks may modify bundled JSON files (end-of-file-fixer). If
  the first `make commit` fixes files, run it again.
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`,
  `@pytest.mark.slow`. `make test-fast` runs unit tests only.
- Patch targets: mock a function where it is USED
  (`src.pipeline.steps.*`), not the aliases in `orchestrator.py`.
- `IterativeLoopConfig.quality_thresholds` expects a `QualityThresholds`
  object, not a dict. Convert with `QualityThresholds(**dict)`.
- During correction the LLM can simplify arrays of objects to arrays of
  strings when the system prompt is too large. `schema_repair.py` applies
  deterministic fixes.

### Code style
- Black (line length 100), Ruff, mypy with `--check-untyped-defs`.
- Python 3.10+. Google-style docstrings for public APIs.

### Environment
- Required: `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` in `.env`.
- Optional: `MAX_PDF_SIZE_MB` (default 10), `LLM_TIMEOUT`, model
  overrides.
