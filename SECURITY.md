# Security Policy

## Supported Versions

Currently supported versions for security updates:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

---

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow responsible disclosure:

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead:

1. **Email**: Send details to the maintainer via GitHub private security advisory
2. **GitHub Security Advisory**: Use the "Report a vulnerability" button in the Security tab
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if known)

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Depends on severity
  - Critical: 1-3 days
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Next scheduled release

### Disclosure Policy

- We will work with you to understand and validate the issue
- A fix will be developed and tested privately
- Once ready, we will:
  1. Release a patched version
  2. Publish a security advisory
  3. Credit you (unless you prefer anonymity)

---

## Security Considerations

### Data Privacy

**PDFs and Extracted Data:**
- PDFs are sent directly to LLM provider APIs (OpenAI/Anthropic)
- Data is subject to provider privacy policies
- No data is stored on our servers (this is local software)
- Users are responsible for their own data handling

**Recommendations:**
- Review LLM provider privacy policies before processing sensitive data
- Use local models for highly sensitive medical data (future feature)
- Ensure compliance with GDPR, HIPAA, or other regulations in your jurisdiction

### API Keys

**Sensitive Information:**
- API keys should NEVER be committed to version control
- Use `.env` files (gitignored by default)
- Rotate keys regularly
- Use separate keys for development and production

**Best Practices:**
```bash
# Good
cp .env.example .env
# Edit .env with your keys
# .env is in .gitignore

# Bad
export OPENAI_API_KEY=sk-... # In shell history
OPENAI_API_KEY=sk-...  # Hardcoded in code
```

### Dependencies

**Supply Chain Security:**
- All dependencies are from trusted sources (PyPI)
- Dependency versions are pinned in `requirements.txt`
- Regular updates for security patches
- Use `pip-audit` to scan for known vulnerabilities

```bash
# Check for vulnerabilities
pip install pip-audit
pip-audit
```

### File Handling

**PDF Processing:**
- Maximum file size enforced (32 MB)
- File validation before processing
- No arbitrary code execution from PDFs
- PDF parsing delegated to LLM providers

**Temporary Files:**
- Stored in `tmp/` directory
- User responsible for cleanup
- Contains extracted data (potentially sensitive)
- Not automatically encrypted

**Recommendations:**
- Delete `tmp/` contents after use: `make clean-all`
- Encrypt `tmp/` directory if storing sensitive data
- Use appropriate file permissions (chmod 600)

---

## Known Security Considerations

### 1. LLM Provider API Calls

**Risk:** Data sent to third-party APIs

**Mitigation:**
- Use provider terms of service
- Enable zero-retention policies where available
- Consider local models for sensitive data (roadmap item)

### 2. Prompt Injection

**Risk:** Malicious PDFs could contain adversarial prompts

**Mitigation:**
- Prompts use clear instruction structure
- Schema validation prevents malformed outputs
- No direct code execution from extracted data

### 3. JSON Schema Validation

**Risk:** Malformed schemas could bypass validation

**Mitigation:**
- Schemas are bundled and version-controlled
- JSON Schema validator is well-tested library
- No user-provided schemas in production use

### 4. Environment Variables

**Risk:** Accidental exposure of API keys

**Mitigation:**
- `.env` in `.gitignore`
- Pre-commit hooks block `.env` commits
- Clear documentation on key management

---

## Secure Development Practices

### Code Review

- All changes require review before merge
- Security-sensitive changes get extra scrutiny
- Automated security scanning in CI/CD (future)

### Testing

- Security test cases in test suite
- Input validation testing
- Error handling verification

### Dependencies

- Regular dependency updates
- Security-focused dependency scanning
- Minimal dependency tree

---

## Compliance

### Medical Data

This tool processes medical literature (published research), not patient data (PHI/PII).

**Important:**
- Do NOT process patient medical records
- Do NOT include patient identifiable information
- Published research papers are generally not covered by HIPAA

### GDPR

For EU users:
- No personal data collected by the software
- Data sent to LLM providers (see their GDPR compliance)
- Users control all data locally

### Responsible Use

This tool is for:
- ✅ Academic research
- ✅ Systematic reviews
- ✅ Medical literature analysis
- ✅ Evidence synthesis

This tool is NOT for:
- ❌ Patient record processing (use HIPAA-compliant tools)
- ❌ Automated medical diagnosis
- ❌ Clinical decision-making without human review

---

## Security Updates

Security updates are released as:
- **Patch versions** for critical issues (1.0.x)
- **Security advisories** published on GitHub
- **Changelog** entries marked with `[Security]`

Subscribe to:
- GitHub Security Advisories: Watch repository → Custom → Security alerts
- Releases: Watch repository → Releases only

---

## Security Best Practices for Users

### 1. Installation

```bash
# Use virtual environments
python -m venv .venv
source .venv/bin/activate

# Install from requirements.txt (pinned versions)
pip install -r requirements.txt

# Verify installation
pip list
```

### 2. Configuration

```bash
# Secure .env file
chmod 600 .env

# Never commit .env
git status  # Should not show .env
```

### 3. Running Pipeline

```bash
# Process test PDFs first
python run_pipeline.py test.pdf --max-pages 5

# Review extracted data
cat tmp/test-extraction.json | jq '.'

# Clean up sensitive data
make clean-all
```

### 4. API Key Rotation

```bash
# Regularly rotate keys
# 1. Generate new key from provider
# 2. Update .env
# 3. Test with sample PDF
# 4. Revoke old key
```

---

## Contact

For security concerns:
- **Private**: GitHub Security Advisories
- **General**: https://github.com/RobTolboom/PDFtoPodcast/issues

---

**This security policy is reviewed quarterly and updated as needed.**

Last updated: January 2025
