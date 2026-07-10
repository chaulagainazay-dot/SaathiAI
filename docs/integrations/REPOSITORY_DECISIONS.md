# Third-Party Repository Integration Decisions

**Date:** 2026-07-10  
**Status:** In progress (OpenMontage complete, OpenJarvis + claude-video discovery active)

---

## Decision Matrix

| Repository | Purpose | Classification | Status | Priority | Next Step | Notes |
|---|---|---|---|---|---|---|
| **OpenMontage** | Character animation (Mr. Yeti) | WRAP | ✅ Complete | Very High | Phase 3.2: ExecutionGateway wiring | AGPL licensed; legal review required before commercial; HTTP adapter recommended |
| **OpenJarvis** | Local AI runtime + orchestration | WRAP | ✅ Complete | Very High | Phase 1: Prototype (4 weeks) | Apache 2.0 (permissive); 60-70% of pipeline infrastructure present; M5.1 launch 2026-09-15 |
| **claude-video** | Fast social content generation | WRAP | ✅ Complete | High | Phase 1: Baadar automation (weeks 1-4) | MIT licensed; Option C (dual-backend) approved; daily videos ($0.01-0.30, <45min) |
| **Ruflo** | Development orchestration | WRAP | 📅 Planned (defer) | Medium | Stage 3 (after Phase 3.2) | Agent swarms, task decomposition; development-harness only |
| **notebooklm-py** | Research + content gen | WRAP | 📅 Planned (defer) | Medium | Stage 3 (after Phase 3.2) | PIELTS research connector; data-policy restrictions required |
| **9Router** | Model routing sidecar | WRAP | 📅 Planned (defer) | Medium | Stage 3 (after Phase 3.2) | Development-only; cannot replace ModelRouter for production |

---

## OpenMontage Status

**License:** AGPL-3.0 + network server clause  
**Architecture:** Instruction-driven (YAML pipelines + Markdown skills)  
**Character-Animation Pipeline:** 10 stages, rigged animation, deterministic rendering (HyperFrames)  
**Blockers:** None  
**Risk:** Legal review needed before commercial deployment  
**Recommendation:** Proceed with Stage 2 contracts, await ExecutionGateway

---

## OpenJarvis (Discovery Complete)

**License:** Apache 2.0 (permissive, no copyleft)  
**Role:** Local AI runtime adapter + orchestration framework  
**Key Features:** Ollama integration, skill system, event-driven orchestration, memory backends, scheduling  
**Architecture Fit:** 60-70% of animation pipeline infrastructure already present  
**Recommendation:** ✅ PROCEED with Phase 1 prototype  
**Timeline:** 4 months to production (M5.1 readiness)  
**Critical Adaptation:** Extend OllamaEngine for custom animation endpoints (Wav2Lip, Runway, ComfyUI)  
**Documents:** OPENJARVIS_DISCOVERY.md (24 pages), INTEGRATION_SUMMARY.json  

---

## claude-video (Discovery Complete)

**License:** MIT (permissive, no copyleft)  
**Role:** Fast social content generation (Baadar daily automation)  
**Comparison to OpenMontage:** Complementary, not replacement  
**Architecture Decision:** ✅ Option C (Hybrid dual-backend)  
**Usage:**
- **Claude Toolkit:** Quick content (15-45 min, $0.01-0.30)
- **OpenMontage:** Production campaigns (2-4 hours, $0.50-2.00)
**Abstraction:** VideoProductionBackend with ToolIntent routing (mode='quick'|'production')  
**Documents:** CLAUDE_VIDEO_DISCOVERY.md (25 pages), CLAUDE_VIDEO_ARCHITECTURE.md (15 pages), CLAUDE_VIDEO_CAPABILITY_MATRIX.md (50+ rows), ADR-CLAUDE-VIDEO-ADAPTER.md

---

## Deferred Repositories (Decision dates TBD)

- **Ruflo**: Development orchestration (defer until Phase 3.2 stable)
- **notebooklm-py**: Research connector (defer until Phase 3.2 stable)
- **9Router**: Model routing sidecar (defer until Phase 3.2 stable)

---

## Architecture Constraints (Non-Negotiable)

All third-party code must flow through:

```
Planner
  ↓
ToolIntent
  ↓
ExecutionGateway
  ↓
Authorization
  ↓
Approval
  ↓
Credential Lease
  ↓
Connector/Runtime
  ↓
Sanitized Result
  ↓
Evidence + Timeline
```

No bypasses. No direct provider calls. No credential access outside ExecutionGateway abstraction.

---

**Last Updated:** 2026-07-10  
**Next Review:** When OpenJarvis + claude-video discovery complete
