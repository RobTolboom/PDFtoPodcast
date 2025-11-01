# Issue Templates

The Markdown files in this folder power the repository's guided issue creation forms.

## Available Templates
- **`bug_report.md`** – Applies the `bug` label, enforces `[BUG]` titles, and prompts for environment metadata, reproduction steps, impacted schemas, and PDF snippets/logs.
- **`feature_request.md`** – Applies the `enhancement` label, prefixes titles with `[FEATURE]`, and gathers the problem statement, success criteria, personas, and willingness to contribute.

## Customisation Notes
- GitHub caches template front matter (`name`, `about`, `labels`, `title`). After editing those fields allow a few minutes for the issue chooser to refresh.
- Align checklists with `ROADMAP.md` and `CONTRIBUTING.md` so authors know which docs to review before submitting.
- Include default labels and concise descriptions when introducing new templates to keep triage dashboards filterable.
- Test experimental templates in a draft PR so maintainers can preview the chooser before merging.
