# SaathiAI Documentation Changelog

All significant changes to the SaathiAI engineering specification are recorded here.

## [Unreleased]

## [v1.2] — 2026-07-02
### Added
- `docs/SES/v1.0/SES-000A_DOCUMENT_STANDARD.md` — governing meta-document for the entire SaathiAI Engineering Specification (SES). Defines: mandatory header block, document governance sections, 15-section chapter template, writing conventions, naming standards, diagram conventions, Platform-First Design Principle, 10 Engineering Values, Repository Integration Standard, ADR format and lifecycle, versioning strategy, and review/approval workflow. All future SES documents must comply with this standard.
- `docs/SES/v1.0/` directory — canonical location for all Volume-1 SES documents
- `docs/decisions/` directory — canonical location for individual ADR files
- `docs/appendix/` directory — canonical location for Appendix A–G documents
### Changed
- SES naming formalized: SaathiAI Engineering Specification (SES), document IDs SES-000 through SES-020

## [v1.1] — 2026-07-02
### Added
- Versioned documentation structure (`docs/v1.0/`, `docs/v1.1/`)
- `CHANGELOG.md` and `DECISIONS.md` at docs root
- Appendix directory (`Appendix/`) for reference documents
- SaathiAI OS framing: HCG POS, pielts, HCG Live Signal, Travel as applications on the OS
- Full 13-chapter constitution format for `00_MASTER_ROADMAP.md`

### Changed
- `00_MASTER_ROADMAP.md` promoted from roadmap to **constitutional document**
- Product ecosystem expanded to include HCG Live Signal and Travel Platform
- Architecture reframed as OS layer, not single-application

## [v1.0] — 2026-07-02
### Added
- Initial `00_MASTER_ROADMAP.md` — first full survey of SaathiAI platform
- 60+ endpoint registry, 25+ scheduler jobs, 70+ tool modules
- BMA (Baadar Multi-Agent Architecture) — 4-phase loop, 7 sub-agents, 30 tests
- 3-tier memory system (Working, Episodic, Semantic)
- Scoring bug fix in pielts `scoring.js` (blank answer → no credit)

---

*Format: [Semantic version] — YYYY-MM-DD*
*Each entry: Added / Changed / Fixed / Removed / Security*
