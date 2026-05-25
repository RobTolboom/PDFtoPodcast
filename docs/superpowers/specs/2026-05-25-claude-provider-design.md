# Claude Provider Modernization — Design Spec

**Date:** 2026-05-25
**Status:** Approved
**Goal:** Make the PDFtoPodcast pipeline fully functional with Claude as the LLM provider, using the modern Anthropic API.

---

## Background

A `ClaudeProvider` skeleton exists in `src/llm/claude_provider.py` but is non-functional due to:

- Default model `claude-3-5-sonnet-20241022` was retired February 19, 2026
- `temperature` parameter passed on all calls — returns 400 on Opus 4.7
- Schema guidance via prompt-stuffing instead of native `output_config.format`
- PDF base64-encoded and re-uploaded on every call (3+ times per pipeline run)
- `reasoning_effort` parameter silently ignored
- `max_tokens` default of 4096 is too low for complex medical JSON extractions

---

## Scope

### Files changed
- `src/llm/claude_provider.py` — full rewrite
- `src/config.py` — update model default, max_tokens default

### Files unchanged
- `src/llm/base.py` — interface contract stays identical
- `src/llm/__init__.py` — factory function unchanged
- All pipeline steps (`classification.py`, `extraction.py`, `validation.py`, `appraisal.py`, `report.py`, `podcast.py`) — zero changes
- `src/pipeline/orchestrator.py` — zero changes

---

## Architecture

### Data flow

```
Pipeline step calls:
  llm.generate_json_with_pdf(pdf_path, schema, reasoning_effort="high")
                    │
                    ▼
  ClaudeProvider._pdf_cache hit?
    NO  → client.beta.files.upload(pdf_path) → cache file_id
    YES → reuse cached file_id
                    │
                    ▼
  client.messages.create(
    model="claude-opus-4-7",
    thinking={"type": "adaptive", "display": "summarized"},
    output_config={
      "effort": "high",
      "format": {"type": "json_schema", "schema": schema}
    },
    messages=[{document: file_id reference} + {text: prompt}]
  )
```

---

## Provider Design

### Initialization

```python
class ClaudeProvider(BaseLLMProvider):
    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.timeout,
        )
        self._pdf_cache: dict[str, str] = {}  # str(pdf_path) → file_id
```

- `temperature` never passed to any API call (400 on Opus 4.7)
- `jsonschema` dependency removed — no longer needed
- `_extract_json_from_markdown()` helper removed — not needed with native structured output

### `generate_text`

- Adds `thinking={"type": "adaptive", "display": "summarized"}`
- No `temperature`
- Response: extract first `TextBlock` from `response.content` (skipping `ThinkingBlock`s)

### `generate_json_with_schema`

- Uses `output_config={"format": {"type": "json_schema", "schema": schema}}` — replaces schema-in-system-prompt approach
- Maps `reasoning_effort` → `output_config={"effort": reasoning_effort}` when provided
- Adds `thinking={"type": "adaptive", "display": "summarized"}`
- No `temperature`, no `jsonschema.validate()` post-check
- Response: first `TextBlock` → `json.loads()`

### `generate_json_with_pdf`

PDF upload strategy uses internal caching:

1. **First call** for a given `pdf_path`: upload via `client.beta.files.upload()`, store `file_id` in `_pdf_cache[str(pdf_path)]`
2. **Subsequent calls** with same `pdf_path`: look up `file_id` from `_pdf_cache`, skip upload entirely
3. Reference PDF in message content as `{"type": "document", "source": {"type": "file", "file_id": file_id}}`
4. Apply same `output_config` + `thinking` as `generate_json_with_schema`

This means within a single step's correction loop, repeated calls to `generate_json_with_pdf` with the same PDF path upload the file only once and reuse the cached `file_id`.

**Important scope note:** The orchestrator (`src/pipeline/orchestrator.py`) creates a new provider instance per step via `get_llm_provider(llm_provider)`. The `_pdf_cache` is therefore per-instance, not shared across steps. The primary benefit is within a step's iterative correction loop (e.g., validation/correction may call `generate_json_with_pdf` multiple times on the same PDF).

### `cleanup_pdf_files()` — new method

```python
def cleanup_pdf_files(self) -> None:
    """Delete all uploaded PDF files from the Anthropic Files API and clear cache."""
    for file_id in self._pdf_cache.values():
        self.client.beta.files.delete(file_id)
    self._pdf_cache.clear()
```

- Called after a step completes (optional — Files API auto-expires after 30 days)
- Safe to call multiple times (cache is cleared after first call)

### Response parsing (shared logic)

```python
def _extract_text_block(self, response) -> str:
    """Extract first TextBlock from response, skipping ThinkingBlocks."""
    for block in response.content:
        if block.type == "text":
            return block.text
    raise LLMProviderError("No text output in response — only thinking blocks received")
```

---

## Config Changes (`src/config.py`)

| Setting | Old default | New default | Env var |
|---|---|---|---|
| `anthropic_model` | `claude-3-5-sonnet-20241022` | `claude-opus-4-7` | `ANTHROPIC_MODEL` |
| `anthropic_max_tokens` | `4096` | `32000` | `ANTHROPIC_MAX_TOKENS` |

No new env vars. Existing `reasoning_effort_*` settings (`low`/`medium`/`high`) map directly to Claude's `effort` levels.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Upload failure (`APIError` on `files.upload`) | Raise `LLMProviderError` with clear message; no base64 fallback |
| `output_config` schema rejection (400) | Raise `LLMProviderError` with schema name in message |
| Response has no `TextBlock` (thinking only) | Raise `LLMProviderError("No text output in response — only thinking blocks received")` |
| `json.JSONDecodeError` | Raise `LLMProviderError` with 200-char content preview |
| `RateLimitError` / `APITimeoutError` | Retry up to 3 times with exponential backoff (tenacity, unchanged) |

Upload failures do **not** fall back to base64 inline — silent fallback would mask configuration problems.

---

## Testing (`tests/unit/test_claude_provider.py`)

New unit test file covering:

1. **`generate_text`** — mocked `client.messages.create`; asserts `thinking` param present, `temperature` absent
2. **`generate_json_with_schema`** — asserts `output_config.format` set correctly; `effort` mapped from `reasoning_effort`; result is parsed dict
3. **`generate_json_with_pdf` — first call** — asserts `client.beta.files.upload` called once, `file_id` used in message
4. **`generate_json_with_pdf` — second call same path** — asserts `files.upload` NOT called again; cached `file_id` reused
5. **`cleanup_pdf_files`** — asserts `files.delete` called for each cached `file_id`; cache cleared
6. **Error: upload failure** — `APIError` on upload → `LLMProviderError` raised
7. **Error: no text block** — response with only `ThinkingBlock` → `LLMProviderError` raised
8. **Error: invalid JSON** — `TextBlock` with non-JSON text → `LLMProviderError` raised

All tests use `unittest.mock.patch` — no real API calls.

---

## Acceptance Criteria

- [ ] `LLM_PROVIDER=claude` pipeline run completes successfully on a real medical PDF
- [ ] Within a step's correction loop, a second call with the same PDF path reuses the cached `file_id` (verified via log: "Reusing uploaded file")
- [ ] `reasoning_effort` values from config are passed as `effort` in `output_config`
- [ ] `thinking` blocks appear in DEBUG logs (via `display: "summarized"`)
- [ ] All unit tests pass: `make test-fast`
- [ ] `make lint` passes with no new warnings
- [ ] `OPENAI_API_KEY` pipeline run still works unchanged
