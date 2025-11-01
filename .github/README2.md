# GitHub Operations Directory

Automation, templates, and repository configuration that govern collaboration live here.

## Structure
| Path | Purpose |
| --- | --- |
| `PULL_REQUEST_TEMPLATE.md` | Standardises PR summaries, testing evidence, and security sign-off before review. |
| `ISSUE_TEMPLATE/` | Markdown issue templates that pre-apply labels and collect reproduction data. |
| `workflows/` | GitHub Actions defining CI, schema bundling, and automation with Claude-based reviews. |

## Maintenance Guidelines
- Keep template copy aligned with `CONTRIBUTING.md` so expectations match across documentation and tooling.
- When editing workflow permissions or secrets, document the rationale in the associated PR and confirm least-privilege scopes.
- Exercise workflow updates by triggering them on a draft branch (using `workflow_dispatch` or temporary branch filters) before merging to `main`.
- Prefer composite or reusable workflows when adding new jobs to avoid duplicating setup steps.

## Related Artefacts
- `DEVELOPMENT.md` – onboarding and local tooling expectations.
- `SECURITY.md` – vulnerability handling and disclosure policy.
- `ROADMAP.md` & `features/` – context for upcoming automation changes.
