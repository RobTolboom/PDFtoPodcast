# Product Roadmap

Strategic development plan for PDFtoPodcast. *Status: planning* (March 2025)

## Current version (1.0.0)
- Initial public release: classification -> extraction -> validation/correction pipeline
- Streamlit UI and CLI parity
- Support for six publication types via schema-driven prompts
- Dual validation with best-iteration selection and tmp/ output audit trail

## Current focus (Q2 2025)
| Initiative | Goal | Notes |
|------------|------|-------|
| Appraisal summary | Provide LLM-assisted assessments of study quality (risk of bias, strengths, limitations). | Requires prompt extensions, schema updates for appraisal metadata, and validation scoring adjustments. |
| Full narrative report | Generate a structured written report combining metadata, extraction highlights, appraisal findings, and narrative summary. | Builds on new appraisal outputs; evaluate export formats (PDF/Markdown) and templating. |
| Podcast episode | Produce an audio-friendly script (intro, study overview, key findings, implications) and optionally TTS. | Leverages narrative report; evaluate TTS integration options and UX (download vs. playback). |

Milestones for these initiatives will be tracked in the repo (features/ directory) and CHANGELOG once delivered.

## Backlog ideas (unordered)
- Batch processing / queue support
- Additional export formats (CSV, Markdown, PDF)
- REST API / automation hooks
- Reference manager integration (Zotero, Mendeley)
- Local/offline LLM support for sensitive data
- Enhanced figure/table extraction workflows

Community feedback influences priority. See guidance below to propose new items.

## Contributing to the roadmap
1. **GitHub Issues** - file feature requests with use cases and desired outcomes.
2. **GitHub Discussions** - comment on roadmap threads, vote on priorities, share workflows.
3. **Pull requests** - submit implementations or proof-of-concept prototypes; link to the relevant issue.
4. **Feature planning notes** - for larger contributions, add a markdown plan under `features/` describing scope, tasks, and risks.

## Prioritisation criteria
| Criterion | Description |
|-----------|-------------|
| User impact | How many users benefit and how strongly it improves their workflow. |
| Effort | Engineering/design time required and complexity. |
| Strategic fit | Alignment with long-term positioning (clinical research workflow enablement). |
| Dependencies | Whether the item unlocks or blocks other roadmap goals. |

## Release cadence (target)
- Patch releases (1.0.x): bug fixes and documentation updates as needed.
- Minor releases (1.x.0): ship when a major focus item reaches MVP (e.g., appraisal report).
- Major releases (x.0.0): reserved for substantial platform changes or breakpoints.

Upcoming planned milestones (tentative):
- v1.1 - appraisal summary enhancements
- v1.2 - full written report exports
- v1.3 - podcast script/TTS workflow

## Past milestones
- January 2025 - v1.0.0: launch of core extraction pipeline, validation loop, Streamlit UI, and multi-provider support.

This roadmap is a living document and will be revised as feedback and priorities evolve. Submit ideas via GitHub Issues or Discussions.
