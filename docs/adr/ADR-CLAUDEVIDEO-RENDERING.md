# ADR: claude-video Rendering Integration vs. OpenMontage

**Date:** 2026-07-10  
**Status:** DISCOVERY IN PROGRESS (awaiting claude-video discovery agent completion)  
**Context:** Character-animation pipeline for Mr. Yeti; video generation provider comparison  

---

## Problem

Two video-generation frameworks under consideration:

1. **OpenMontage** (AGPL-3.0)
   - 10-stage character-animation pipeline
   - Rigged character animation + pose libraries
   - Deterministic HyperFrames rendering
   - 35 providers, always-free tier

2. **claude-video** (TBD license)
   - Likely specialized for video generation
   - Provider integration (to be discovered)
   - Determinism properties (to be discovered)
   - Feature set (to be discovered)

**Question:** Is claude-video a better integration point than OpenMontage for Mr. Yeti character animation?

---

## Comparison Dimensions (TBD)

Discovery will address:
- Character rigging and animation capabilities
- Rendering determinism and reproducibility
- Provider integration breadth
- Licensing and commercial terms
- Maintenance and stability
- Performance and resource requirements
- Architecture alignment with SaathiOS
- Custom playbook support (brand consistency)

---

## Decision: OPTION C (APPROVED)

**Hybrid dual-backend architecture** with VideoProductionBackend abstraction.

**Why Option C is optimal:**
- Complementary strengths: Claude fast + pragmatic, OpenMontage sophisticated + governed
- Dual use cases: Baadar daily automation (15-45 min) + Mr. Yeti campaigns (2-4 hours)
- Balanced complexity: Claude simple (direct skills), OpenMontage abstracted (HTTP adapter)
- Extensibility: Add 3rd backend later without changing SaathiOS
- Risk mitigation: Dual-system reduces vendor lock-in
- No single system sufficient: Claude lacks rigging/approval gates; OpenMontage overkill for daily

---

## Architecture

```
ToolIntent (mode='quick'|'production')
    ↓
ExecutionGateway
    ↓
VideoProductionBackend
    ├→ mode='quick' + low cost → Claude Video Toolkit Adapter
    ├→ mode='production' + character='yeti' → OpenMontage HTTP Adapter
    └→ ToolIntent.approval_required=true → OpenMontage (mandatory)
    ↓
Sanitized Result + Evidence
```

---

## Phase Implementation

**Phase 1 (Weeks 1-4): Claude Video Toolkit**
- Daily Baadar automation
- Product demos
- Social clips (TikTok, Instagram, YouTube Shorts)
- Target: 3+ videos/day, <$0.30 cost, <45 min turnaround
- Launch: 2026-08-10

**Phase 2 (Weeks 5-12): OpenMontage Integration**
- Production Mr. Yeti campaigns
- Approval workflow (proposal → script → scene_plan → publish)
- Budget tracking + cost reconciliation
- Target: 1-2 videos/week, professional quality, <$2.00 cost
- Launch: 2026-09-10

**Phase 3 (Weeks 13-16): Unified VideoProductionBackend**
- Single ToolIntent entry point
- Dual adapter routing
- Unified analytics
- Launch: 2026-09-15

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Baadar daily videos | 3+ per day |
| Baadar cost per video | <$0.30 |
| Baadar turnaround | <45 minutes |
| Mr. Yeti campaign frequency | 1-2 per week |
| Mr. Yeti cost per video | <$2.00 |
| Mr. Yeti turnaround | 2-4 hours (incl. approvals) |
| System uptime | 99.5% |
| Human approval SLA | 1 hour |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Claude API rate limit | Queue + backoff + fallback to batch |
| OpenMontage HTTP timeout | Health check + fallback to manual execution |
| Provider incompatibility | Compatibility matrix + pre-flight validation |
| Approval workflow delay | Async notification + escalation if >1 hour |
| Cost overrun | Budget caps per mode + alerts at 80% spend |

---

**Status:** ✅ APPROVED FOR IMPLEMENTATION  
**Documents:** CLAUDE_VIDEO_DISCOVERY.md, CLAUDE_VIDEO_ARCHITECTURE.md, CLAUDE_VIDEO_CAPABILITY_MATRIX.md  
**Next:** Begin Phase 1 implementation (2026-07-15)
