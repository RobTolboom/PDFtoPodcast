# GitHub Actions Workflows

This folder houses the automation that keeps the repository healthy and assists reviewers.

## Workflows
| File | Trigger | Highlights |
| --- | --- | --- |
| `ci.yml` | Pushes and pull requests targeting `main` or `develop`. | Runs formatting (`black`), linting (`ruff`), type checks (`mypy`), a multi-OS/pyversion test matrix, coverage upload, schema validation, and security scanning. Most optional jobs currently use `continue-on-error` while coverage and full integration tests mature. |
| `claude-code-review.yml` | PR open/sync events. | Invokes the `anthropics/claude-code-action` to leave automated review comments guided by `CLAUDE.md`. Requires the `CLAUDE_CODE_OAUTH_TOKEN` secret. |
| `claude.yml` | Comments or issues mentioning `@claude`. | On-demand assistant that runs Claude Code with optional extra permissions to read CI results when triaging feedback. |

## Editing Tips
- Reuse setup steps via composite actions or `uses:` blocks to minimise drift across jobs.
- Keep secrets requested in the workflow documented in `README2.md` or the PR to help operators provision them.
- When tightening `continue-on-error` flags, coordinate with owners of the affected checks to avoid blocking contributors unexpectedly.
- Test changes using `workflow_dispatch` or branch filters to validate new behaviour before enabling for all PRs.
