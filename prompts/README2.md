# Prompt Library

Prompt templates used by the pipeline live here. They are consumed through `src/prompts.py`, which selects the correct template based on schema metadata and orchestrator context.

## Files
| File | Usage |
| --- | --- |
| `Classification.txt` | Initial study-type detection and metadata extraction. |
| `Extraction-prompt-*.txt` | Specialised extraction prompts for each study design (editorials, observational, interventional, prediction, evidence synthesis). |
| `Extraction-correction.txt` | Iterative correction instructions invoked when validation fails. |
| `Extraction-validation.txt` | Semantic validation prompt that pairs with JSON Schema checks. |

## Authoring Guidelines
- Keep prompts succinct and reference schema field names exactly as defined in `schemas/`.
- Highlight constraints (e.g., units, enumerations) in bullet lists so the LLM can cross-check outputs.
- When updating prompts, update related tests or fixtures in `tests/fixtures/` to reflect new expectations.
- Note additions in `CHANGELOG.md` to track prompt drift across releases.
