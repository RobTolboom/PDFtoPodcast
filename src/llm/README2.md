# LLM Provider Abstraction

This package wraps supported LLM providers and exposes a consistent interface for the pipeline.

## Key Modules
- **`base.py`** – Defines `BaseLLMProvider`, retry helpers, and shared error classes (`LLMError`, `LLMProviderError`).
- **`openai_provider.py`** – Implements Structured Output calls against the OpenAI Responses API, enforcing schema-compliant JSON.
- **`claude_provider.py`** – Implements Anthropic Claude calls with markdown-stripping, schema validation via `jsonschema`, and fallback parsing.
- **`__init__.py`** – Exposes `get_llm_provider`, convenience generation helpers, and reads runtime configuration from `src/config.py`.

## Implementation Notes
- Providers must honour the interfaces defined in `base.py` (`generate_text`, `generate_json_with_schema`, `supports_schema_generation`).
- Configuration defaults (model names, temperature, retries) are sourced from `LLMSettings` in `src/config.py`; override via dependency injection when testing.
- Surface provider-specific errors as `LLMProviderError` to keep pipeline exception handling consistent.
- Add dedicated unit tests under `tests/unit/test_llm_*` when introducing new providers or capabilities.
