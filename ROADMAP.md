# Product Roadmap

Strategic development plan for PDFtoPodcast.

**Status:** Planning Phase
**Last Updated:** January 2025

---

## Current Version: 1.0.0 ✅

### Implemented Features

- ✅ Four-step extraction pipeline (Classification → Extraction → Validation → Correction)
- ✅ Multi-provider LLM support (OpenAI GPT-5, Claude Opus/Sonnet)
- ✅ Direct PDF upload with vision analysis
- ✅ Dual validation strategy (schema + conditional LLM)
- ✅ Support for 6 publication types
- ✅ **Streamlit web interface** for easy interaction
- ✅ Command-line interface for automation
- ✅ JSON Schema-based structured outputs
- ✅ PDF filename-based file management
- ✅ Rich CLI with progress indicators
- ✅ Breakpoint system for development

---

## Planned Features

> **Note:** This roadmap is under active planning. Features and priorities may change based on:
> - User feedback and requests
> - Technical feasibility
> - Resource availability
> - Strategic priorities

### Ideas Under Consideration

**User Experience:**
- [ ] Batch processing (multiple PDFs at once)
- [ ] Export to additional formats (CSV, Excel, Markdown)
- [ ] PDF annotation (highlight extracted sections)
- [ ] Custom schema builder UI

**Performance & Quality:**
- [ ] Result caching system (opt-in)
- [ ] Multi-language support
- [ ] Figure/chart OCR extraction
- [ ] Confidence scores per field

**Integration:**
- [ ] RESTful API server
- [ ] Database storage option
- [ ] Integration with reference managers (Zotero, Mendeley)
- [ ] Export formats for systematic review tools

**Technical:**
- [ ] Additional LLM providers (Gemini, local models)
- [ ] Automated testing suite
- [ ] Performance benchmarking
- [ ] Token usage optimization

---

## How to Influence the Roadmap

We welcome input from the community:

### 1. **GitHub Issues**
Open a feature request with:
- Clear use case description
- Expected behavior
- Why it would be valuable
- Any implementation ideas

### 2. **GitHub Discussions**
- Discuss ideas and priorities
- Vote on existing proposals
- Share your workflow and needs

### 3. **Pull Requests**
- Contribute implementations
- Improve existing features
- Add documentation

### 4. **Direct Feedback**
- Open an issue describing your workflow
- Share what features would help most
- Prioritize from the list above

---

## Decision Framework

Features are prioritized based on:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| User Impact | 40% | How many users benefit? |
| Effort | 30% | Development time required |
| Strategic Value | 20% | Aligns with long-term vision? |
| Dependencies | 10% | Blocks other features? |

---

## Release Cadence

- **Patch releases** (1.0.x): Bug fixes, minor improvements - as needed
- **Minor releases** (1.x.0): New features, backward compatible - when ready
- **Major releases** (x.0.0): Breaking changes, major features - yearly

---

## Get Involved

Want to help shape the future of PDFtoPodcast?

1. ⭐ Star the repository
2. 💬 Join discussions on GitHub
3. 🐛 Report bugs and suggest features
4. 🔧 Contribute code improvements
5. 📖 Improve documentation

**Repository:** https://github.com/RobTolboom/PDFtoPodcast
**Issues:** https://github.com/RobTolboom/PDFtoPodcast/issues
**Discussions:** https://github.com/RobTolboom/PDFtoPodcast/discussions

---

## Past Milestones

### Version 1.0.0 (January 2025) ✅
- Initial release with core extraction pipeline
- Web interface and CLI
- Multi-provider LLM support
- Dual validation system
- 6 publication types supported

---

**This roadmap is a living document and will be updated as the project evolves.**

_Have ideas? Open an issue or discussion on GitHub!_
