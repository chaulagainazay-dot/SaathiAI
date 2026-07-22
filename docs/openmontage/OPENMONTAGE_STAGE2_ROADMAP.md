# OpenMontage Stage 2 Implementation Roadmap

**Date:** 2026-07-10  
**Phase:** Stage 2 Detailed Integration Design  
**Duration:** 4-6 weeks (estimated)  
**Primary Target:** Character-animation for Mr. Yeti  

---

## Stage 2 Goals

1. **Executable integration:** OpenMontage HTTP service running, callable from SaathiOS
2. **Character-animation pipeline:** End-to-end video generation
3. **Determinism verification:** Same input → byte-identical video
4. **Cost tracking:** Finance layer sees OpenMontage costs
5. **Approval workflow:** SaathiOS dashboard or Backlot integration
6. **Production-ready:** Tested, documented, deployable

---

## Implementation Phases

### Phase 2A: Service Setup (Week 1)

**Task 2A.1: OpenMontage Service Containerization**
- [ ] Create Dockerfile for OpenMontage
- [ ] Define docker-compose.yml (OpenMontage + dependencies)
- [ ] Setup environment variable management
- [ ] Test local startup (http://localhost:8000)
- [ ] Document service setup

**Task 2A.2: HTTP API Wrapper**
- [ ] Build OpenMontageService class (contracts from Stage 1)
- [ ] Implement async HTTP client (httpx)
- [ ] Test all endpoints (create_project, get_status, get_checkpoint, approve, costs)
- [ ] Add request/response logging (with scrubbing)
- [ ] Add retry logic (backoff for transient failures)

**Task 2A.3: Config Loading**
- [ ] Load config from YAML + .env
- [ ] Implement ConfigValidator
- [ ] Add health check (service reachable, storage writable)
- [ ] Test config merge order (defaults < config.yaml < .env)

---

### Phase 2B: ExecutionGateway Adapter (Week 2)

**Task 2B.1: OpenMontageExecutionGateway**
- [ ] Implement execute() method (ToolIntent → OpenMontage project)
- [ ] Implement polling loop (wait_for_stage_complete)
- [ ] Implement approval submission (approve_checkpoint)
- [ ] Handle error cases (service unavailable, approval rejected)
- [ ] Test end-to-end: ToolIntent → project → checkpoint → approval → proceed

**Task 2B.2: ToolIntent ↔ OpenMontage Adapter**
- [ ] Map ToolIntent fields → OpenMontage project fields
- [ ] Convert parameters dict → scene_input
- [ ] Extract render_cost_usd from render_report, return to Finance
- [ ] Handle custom playbook (Mr. Yeti brand specs)

**Task 2B.3: Approval Workflow Integration**
- [ ] Create ApprovalRecord type in SaathiOS
- [ ] Implement approval UI (Backlot or SaathiOS dashboard)
- [ ] Test human approval gate (wait, approve, send-back)
- [ ] Implement send-back logic (agent re-runs stage)

---

### Phase 2C: Video Domain Model (Week 2)

**Task 2C.1: Database Schema**
- [ ] Create video_projects table
- [ ] Create scenes table
- [ ] Create video_assets table
- [ ] Create publish_records table
- [ ] Create character_branding table
- [ ] Run migrations

**Task 2C.2: Model Implementation**
- [ ] Implement VideoProject class (ORM)
- [ ] Implement VideoAsset class
- [ ] Implement PublishRecord class
- [ ] Add relationships (Mission ↔ VideoProject, VideoProject ↔ VideoAsset)
- [ ] Test CRUD operations

**Task 2C.3: API Endpoints**
- [ ] POST /api/v1/missions/{mission_id}/video-projects (create)
- [ ] GET /api/v1/video-projects/{project_id} (read)
- [ ] POST /api/v1/video-projects/{project_id}/invoke-pipeline (execute)
- [ ] GET /api/v1/video-projects/{project_id}/checkpoints/{stage} (read checkpoint)
- [ ] POST /api/v1/video-projects/{project_id}/approve (submit approval)
- [ ] GET /api/v1/video-projects/{project_id}/video-asset (read final video)

---

### Phase 2D: Cost Tracking (Week 2)

**Task 2D.1: Finance Integration**
- [ ] Expose OpenMontage cost_log.json via API
- [ ] Create CostAllocation model (mission → cost breakdown)
- [ ] Implement cost aggregation (per stage, per tool)
- [ ] Add cost tracking to SaathiOS Finance layer

**Task 2D.2: Budget Governance**
- [ ] Implement approval gate for costs > $0.50
- [ ] Implement budget cap enforcement
- [ ] Add cost warnings (SaathiOS notifies when approaching budget)
- [ ] Test budget override (user increases budget)

---

### Phase 2E: Error Handling (Week 3)

**Task 2E.1: ErrorHandler Implementation**
- [ ] Implement error classification (retriable vs. escalate)
- [ ] Implement automatic retry logic (backoff)
- [ ] Implement fallback provider selection (e.g., image gen: Google → Flux → OpenAI)
- [ ] Implement human escalation (create incident alert)

**Task 2E.2: Provider Fallback Chains**
- [ ] Image generation: Google Imagen → Flux → OpenAI
- [ ] Video generation: HyperFrames (local) → Runway → Sora
- [ ] TTS: Google → Piper → ElevenLabs
- [ ] Stock media: Pexels → Pixabay → Unsplash (always have fallback)

**Task 2E.3: Error Logging & Monitoring**
- [ ] Implement log scrubber (redact API keys)
- [ ] Add structured logging (error code, remediation)
- [ ] Send error alerts to Telegram (admin notification)
- [ ] Log all errors to audit trail (Finance layer)

---

### Phase 2F: Health Checks (Week 3)

**Task 2F.1: OpenMontageHealthMonitor**
- [ ] Implement GET /health endpoint polling
- [ ] Collect per-provider health (Google, OpenAI, Runway, etc.)
- [ ] Collect credential health (expiry check)
- [ ] Collect storage health (disk free, projects count)

**Task 2F.2: Health Dashboard**
- [ ] Create SaathiOS health widget (shows provider status)
- [ ] Add alerts for degradation (e.g., provider rate-limited)
- [ ] Add alerts for credentials expiring
- [ ] Implement background monitor (poll every 60s)

**Task 2F.3: Provider Status API**
- [ ] Expose provider health via SaathiOS API
- [ ] Allow manual provider enable/disable (if unhealthy)
- [ ] Track provider incidents (timestamp, error, resolved_at)

---

### Phase 2G: Testing & Determinism (Week 4)

**Task 2G.1: Integration Tests**
- [ ] Test character-animation pipeline end-to-end (invoke → render → complete)
- [ ] Test approval workflow (human decision → proceed)
- [ ] Test send-back (rejection → re-run)
- [ ] Test cost tracking (verify cost_log.json populated)

**Task 2G.2: Determinism Verification**
- [ ] Run same scene twice, verify identical output
- [ ] Compare MD5 hashes (must match)
- [ ] Verify video duration, resolution, codec match
- [ ] Document determinism guarantee

**Task 2G.3: Performance Tests**
- [ ] Measure pipeline latency (invoke → approval gate)
- [ ] Measure render time (typical 1min video: ~30-60s)
- [ ] Measure cost accuracy (estimate vs. actual)
- [ ] Profile memory usage

---

### Phase 2H: Mr. Yeti Branding (Week 4)

**Task 2H.1: Custom Playbook**
- [ ] Define Mr. Yeti visual style (colors, tone, character specs)
- [ ] Create custom playbook JSON
- [ ] Test brand consistency (verify generated character matches)
- [ ] Get design approval (Baadar brand team)

**Task 2H.2: Character Design Approval**
- [ ] Run character_design stage
- [ ] Review generated character (does it look like Mr. Yeti?)
- [ ] Send-back if needed (refine playbook)
- [ ] Approve final design

**Task 2H.3: Sample Video Renders**
- [ ] Generate 2-3 sample videos (proposal.sample, final renders)
- [ ] Verify determinism (re-render, compare)
- [ ] Test publication (YouTube upload test)

---

### Phase 2I: Deployment (Week 5)

**Task 2I.1: Local Environment**
- [ ] docker-compose up (both SaathiOS + OpenMontage)
- [ ] Verify services running
- [ ] Test full pipeline (create → execute → render → publish)
- [ ] Document local setup

**Task 2I.2: Cloud Deployment (Optional)**
- [ ] Push OpenMontage to container registry
- [ ] Deploy to Kubernetes or cloud VM
- [ ] Setup persistent storage (projects/ directory)
- [ ] Configure environment variables (API keys)
- [ ] Test cloud pipeline

**Task 2I.3: Monitoring & Alerting**
- [ ] Setup health check polling (Prometheus/Grafana optional)
- [ ] Setup error alerting (Telegram notifications)
- [ ] Setup cost tracking (daily report to Finance)
- [ ] Setup credential expiry alerts (admin email)

---

### Phase 2J: Documentation (Week 5-6)

**Task 2J.1: Operator Guide**
- [ ] Setup instructions (local + cloud)
- [ ] Troubleshooting guide (common errors + fixes)
- [ ] Runbook for manual operations (e.g., if service crashes)
- [ ] Cost monitoring guide (Finance team)

**Task 2J.2: Developer Guide**
- [ ] Architecture overview (SaathiOS ↔ OpenMontage)
- [ ] API documentation (all endpoints)
- [ ] Error codes + remediation
- [ ] Custom playbook guide (how to create brand specs)

**Task 2J.3: User Guide**
- [ ] How to create video project
- [ ] How to approve stages
- [ ] How to understand costs
- [ ] FAQ + troubleshooting

---

## Dependencies & Blockers

| Dependency | Status | Risk |
|------------|--------|------|
| Google APIs credentials (service account) | ⚠️ TBD | Need GCP project + keys |
| OpenAI API key | ✅ Available | Ready |
| Runway API key | ⚠️ TBD | Request access |
| Docker installation | ✅ Available | Ready |
| PostgreSQL database | ✅ Available | Ready |

**Blockers (None identified)**

---

## Success Criteria for Stage 2

- [ ] Character-animation pipeline: end-to-end working
- [ ] Determinism verified: 3 runs of same input produce identical videos
- [ ] Cost tracking: Finance layer sees per-project costs
- [ ] Approval workflow: 4 human approval gates functional (proposal, character design, scene plan, publish)
- [ ] Error handling: Automatic retry + fallback for transient failures
- [ ] Health checks: Provider status visible in SaathiOS dashboard
- [ ] Security: Log scrubber active, no API keys in logs
- [ ] Documentation: Operator + developer guides complete
- [ ] Tests: Integration tests passing, 80% code coverage minimum
- [ ] Performance: Full pipeline < 2 hours from invoke to final video

---

## Phase 3 (M5.2+) Enhancements

- [ ] Multiverse character variants (A/B test multiple Mr. Yetis)
- [ ] Parallel stage execution (speed up pipeline)
- [ ] Custom music generation (Suno integration)
- [ ] Video editing improvements (transitions, effects)
- [ ] Social media distribution (TikTok, Instagram auto-sync)
- [ ] Performance optimization (cache layer for repeated assets)

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Provider API failures | High | Med | Implement fallback chains |
| Credential expiry | Med | High | Pre-flight validation + alerts |
| Cost overruns | Low | High | Approval gates + budgets |
| Determinism issues | Low | Critical | Verification tests + checksums |
| Approval timeout | Low | Med | Max wait time + escalation |

---

## Resource Allocation

- **Frontend/API:** 30% (endpoints, error handling)
- **Backend/Integration:** 40% (ExecutionGateway, polling, cost tracking)
- **Testing/QA:** 20% (integration tests, determinism verification)
- **Documentation:** 10% (guides, runbooks)

**Estimated: 4-6 weeks, 1 developer + code review**

---

## Timeline

```
Week 1: Service setup + HTTP wrapper
Week 2: ExecutionGateway + Video model + Cost tracking
Week 3: Error handling + Health checks
Week 4: Testing + Mr. Yeti branding
Week 5: Deployment + Monitoring
Week 6: Documentation + Final QA

Production Deploy: ~2026-08-20
```

---

**Roadmap Status:** APPROVED  
**Start Date:** 2026-07-15 (pending user approval)  
**Owner:** SaathiOS Infrastructure Team  
**Reviewer:** Executive Intelligence (Baadar)

