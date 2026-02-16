<rules owner="Rob Tolboom" project="PDFtoPodcast" version="2026-02-16">
  <meta_rules>
    <rule_1>Always ask y/n confirmation before performing file, git, build, or CI actions.</rule_1>
    <rule_2>User has final authority; do not change any plan without explicit approval.</rule_2>
    <rule_3>Report a short execution plan with exact commands first; wait for approval.</rule_3>
    <rule_4>Follow repository policies and @CONTRIBUTING.md; do not reinterpret or modify these rules.</rule_4>
    <rule_5>Display the section titles and all applicable rules below verbatim at the start of EVERY response, in this order.</rule_5>
  </meta_rules>

  <workflows>
    <start_of_day>
      <step_1>git pull origin main</step_1>
      <step_2>If dependencies changed: make install-dev</step_2>
    </start_of_day>

    <after_code_change>
      <step_1>make format   <!-- code formatter --></step_1>
      <step_2>make lint     <!-- static checks --></step_2>
      <step_3>make test-fast<!-- quick feedback --></step_3>
    </after_code_change>

    <before_commit>
      <step_1>make commit   <!-- pre-commit preparation --></step_1>
      <step_2>git commit -m "type: description"</step_2>
    </before_commit>

    <before_push>
      <step_1>make ci       <!-- simulate CI locally --></step_1>
      <step_2>git push</step_2>
    </before_push>
  </workflows>

  <feature_planning>
    <planning_phase>
      <rule>Create a feature markdown in the "features" directory with goal, scope, task list, risks, and acceptance criteria.</rule>
    </planning_phase>
    <development>
      <rule>Work in the correct branch; create one if needed and record the branch name in the feature document.</rule>
      <rule>Commit regularly with clear descriptions; run format/lint/tests before each commit.</rule>
      <rule>Push and PR only after explicit user approval.</rule>
    </development>
  </feature_planning>

  <change_management>
    <on_every_change>
      <rule>Update CHANGELOG.md under "Unreleased".</rule>
      <rule>Update relevant documentation (README.md, ARCHITECTURE.md, etc.).</rule>
      <rule>Add appropriate tests or update existing tests.</rule>
      <rule>Update API.md if applicable.</rule>
    </on_every_change>
  </change_management>

  <display_policy>
    <conditions>
      <rule>If the task involves file/git/build/CI actions or branch/PR: display all rules in &lt;meta_rules&gt;, the relevant &lt;workflows&gt; steps, and &lt;change_management&gt;.</rule>
      <rule>Otherwise: display only &lt;meta_rules&gt; and the section headings of this document.</rule>
    </conditions>
    <verbatim>Display must be verbatim; no paraphrasing or summarizing beyond the conditions above.</verbatim>
    <self_reference>This &lt;display_policy&gt; is itself subject to the display requirement.</self_reference>
  </display_policy>

  <project_context>
    <architecture>
      <summary>6-step pipeline: Classification -> Extraction -> Validation/Correction -> Appraisal -> Report -> Podcast</summary>
      <llm>OpenAI GPT-5.1 with strict: False structured output (schema as guidance only)</llm>
      <entry_points>
        <cli>python run_pipeline.py paper.pdf</cli>
        <streamlit>streamlit run app.py</streamlit>
      </entry_points>
    </architecture>

    <key_directories>
      <dir path="src/pipeline/steps/">Modular step implementations (classification, extraction, validation, appraisal, report, podcast)</dir>
      <dir path="src/pipeline/iterative/">Generic IterativeLoopRunner + iteration tracker</dir>
      <dir path="src/pipeline/quality/">Centralized thresholds, metrics, scoring (QualityThresholds dataclass)</dir>
      <dir path="src/pipeline/orchestrator.py">Main orchestration — delegates to steps/ modules, provides backward-compat aliases</dir>
      <dir path="src/llm/">LLM providers (OpenAI, Claude) with BaseLLMProvider interface</dir>
      <dir path="schemas/">JSON schemas + common.schema.json + json-bundler.py for bundling</dir>
      <dir path="prompts/">All prompt templates (extraction, appraisal, report, podcast)</dir>
      <dir path="src/rendering/">Output renderers (LaTeX, WeasyPrint, Markdown, Podcast)</dir>
    </key_directories>

    <gotchas>
      <gotcha>After editing common.schema.json or type schemas: run `cd schemas and python json-bundler.py` to regenerate all 5 *_bundled.json files.</gotcha>
      <gotcha>Pre-commit hooks may modify bundled JSON files (end-of-file-fixer). If first `make commit` fixes files, run it again.</gotcha>
      <gotcha>Tests use markers: @pytest.mark.unit, @pytest.mark.integration, @pytest.mark.slow. `make test-fast` runs unit tests only.</gotcha>
      <gotcha>Patch targets after refactoring: always mock the function where it is USED (src.pipeline.steps.*), not the backward-compat aliases in orchestrator.py.</gotcha>
      <gotcha>IterativeLoopConfig.quality_thresholds expects a QualityThresholds object, not a dict. Convert with QualityThresholds(**dict) if needed.</gotcha>
      <gotcha>LLM can simplify arrays of objects to arrays of strings during correction when system prompt is too large. schema_repair.py provides deterministic fixes.</gotcha>
    </gotchas>

    <code_style>
      <formatter>Black (line-length 100)</formatter>
      <linter>Ruff</linter>
      <types>mypy with --check-untyped-defs</types>
      <python>3.10+</python>
      <docstrings>Google-style for public APIs</docstrings>
    </code_style>

    <environment>
      <required>OPENAI_API_KEY and/or ANTHROPIC_API_KEY in .env</required>
      <optional>MAX_PDF_SIZE_MB (default 10), LLM_TIMEOUT, model overrides</optional>
    </environment>
  </project_context>
</rules>
