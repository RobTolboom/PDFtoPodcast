# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | yes       |

## Reporting a vulnerability

Do **not** open public GitHub issues for security reports. Instead:

1. Email the maintainer privately (see repository contact) or use GitHub's "Report a vulnerability" workflow.
2. Include a clear description, reproduction steps, potential impact, and suggested fixes if known.
3. Provide encrypted communication if sensitive data is involved.

### Response targets
- Initial acknowledgement: within 48 hours
- Status update: within 7 days
- Fix timeline (goal, depending on severity)
  - Critical: 1-3 days
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: next scheduled release

### Disclosure process
- We work with reporters to validate the issue and agree on next steps.
- Fixes are developed and tested privately.
- Once a patch is ready we will release an update, publish an advisory, and credit the reporter unless anonymity is requested.

## Security considerations

### Data privacy
- PDFs are uploaded directly to the configured LLM providers (currently OpenAI and Anthropic).
- The application itself is self-hosted; no PDFs or outputs are transmitted back to Licensor.
- Customers are responsible for complying with local regulations (GDPR, HIPAA, etc.) and provider terms before processing sensitive data.
- Consider redacting or anonymising patient data prior to use.

### API keys
- Store keys in `.env` (gitignored) and never commit them.
- Rotate keys periodically and use separate keys per environment.
- Avoid exporting keys in shell history; prefer `.env` loaded via `python-dotenv`.

### Dependencies
- Dependencies are pinned in `requirements.txt` / `requirements-dev.txt`.
- Run `pip-audit` or similar tools to check for known vulnerabilities:
  ```bash
  pip install pip-audit
  pip-audit
  ```
- Review dependency updates in pull requests before upgrading production environments.

### File handling
- Default upload cap is 10 MB (configurable via environment variables; provider hard limit is 32 MB). Large PDFs should be split or compressed before processing.
- Temporary outputs live in `tmp/`; clean up or secure this directory as it may contain sensitive extracted data (`make clean-all`).
- Ensure appropriate filesystem permissions (e.g., restrict `tmp/` access on shared systems).

## Known risks and mitigations

| Risk | Mitigation |
|------|------------|
| LLM provider exposure | Use providers' zero-retention modes where available; review provider policies regularly; consider future local-model options for highly sensitive data. |
| Prompt injection from PDFs | Prompts enforce strict schema outputs; schema validation rejects malformed responses; continue reviewing prompts for robustness. |
| Schema validation bypass | Schemas are version-controlled and bundled; validators are tested via the unit suite; avoid executing user-provided schemas. |
| API key leakage | `.env` is gitignored; documentation emphasises safe handling; consider pre-commit hooks to block secrets. |

For additional operational practices, consult `README.md`, `CONTRIBUTING.md`, and provider documentation.
