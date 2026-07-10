# OpenMontage AGPL-3.0 License Analysis

**Date:** 2026-07-10  
**License:** AGPL-3.0 with Network Server Clause  
**Scope:** SaathiOS integration compliance assessment  

---

## License Summary

**OpenMontage is AGPL-3.0 licensed.** Core library code (lib/ + tools/) is subject to copyleft. If you modify OpenMontage, modifications must be shared under AGPL.

**Network Server Clause** (AGPLv3 §13): If users can remotely interact with OpenMontage (via HTTP API or web interface), modified source must be available to those users.

---

## What Is AGPL-3.0?

| Aspect | Detail |
|--------|--------|
| **Type** | Copyleft open-source license |
| **Applies To** | Library + tool code (lib/, tools/) |
| **Trigger** | Modifications to source code |
| **Requirement** | Modified source must be AGPL-licensed and shared |
| **Network Clause** | If software runs on server (users interact remotely), source must be available to users |

---

## Scope: What Falls Under AGPL

### ✅ AGPL-Licensed (Copyleft Applies)

**Library Code (lib/)**
- checkpoint.py (state persistence)
- env_loader.py (credential loading)
- pipeline_loader.py (manifest parsing)
- config_model.py (Pydantic models)
- paths.py (path canonicalization)
- checkpoint schema validation

**Tool Code (tools/)**
- All 128 tool implementations
- base_tool.py (interface)
- cost_tracker.py (budget lifecycle)
- video_compose.py (render orchestration)
- All provider-specific tools (google_tts, sora_video, etc.)

**Backlot Server (backlot/)**
- FastAPI app
- State watcher (SSE feed)
- Project API
- Media serving

### ⚠️ AGPL-Licensed If Modified

**Custom Tools**
- If you inherit from BaseTool, your custom tool is AGPL-licensed
- If pipeline declares `extensions.custom_tools: true`, agents can create tools → falls under AGPL

**Modified Manifests or Schemas**
- If you fork and modify pipeline_defs/ or schemas/, those modifications are AGPL-licensed
- But project artifacts (scene_plan.json, render_report.json) are user data, NOT covered by AGPL

### ❓ Not Clearly Covered (Verify with Legal Counsel)

**Markdown Skills (skills/)**
- Instructions (Markdown) may not be "software" in AGPL's sense
- Likely permissive, but verify with legal counsel

**Custom Playbooks & Styles**
- User-created playbooks (JSON/YAML describing visual style) are data, not code
- Likely NOT covered by AGPL

**Project Outputs (Videos, Assets)**
- Rendered videos, scene plans, asset manifests = user data
- NOT covered by AGPL

---

## SaathiOS Integration: Three Scenarios

### Scenario 1: Embed as HTTP Service (Recommended)

**What You Do:**
- Don't modify OpenMontage code
- Run OpenMontage as separate service (HTTP API)
- SaathiOS calls OpenMontage API (no direct code linking)

**AGPL Impact:**
- ✅ **NO copyleft trigger** — Calling an unmodified AGPL service doesn't infect your code
- ✅ OpenMontage remains AGPL, SaathiOS code is unaffected
- ✅ No source-sharing requirement for SaathiOS

**Example:**
```python
# SaathiOS (any license)
response = requests.post(
    "http://openmontage-service/api/v1/character-animation/execute",
    json={"pipeline": "character-animation", ...}
)
video_url = response.json()["video_url"]
```

**Backlot Board:** If you run Backlot as a service without modifications, no new AGPL obligations.

### Scenario 2: Fork + Modify (Requires AGPL Compliance)

**What You Do:**
- Clone OpenMontage
- Modify lib/ or tools/ (e.g., custom cost model, new provider integration)
- Embed modified code in SaathiOS (Python library import)

**AGPL Impact:**
- ❌ **Copyleft triggered** — Modified code falls under AGPL
- ❌ All modifications must be AGPL-licensed
- ❌ If users access via network (web API), they must have access to modified source
- ❌ Your SaathiOS repository must be AGPL-licensed (if linked)

**Requirement:**
```
All modifications to lib/, tools/, backlot/ → AGPL-licensed
Publish source on GitHub (or equivalent)
Make source available to end users
```

### Scenario 3: Vendor + Never Modify (Permissive)

**What You Do:**
- Include unmodified OpenMontage as dependency (pip install openmontage)
- Never modify source code
- Link to official GitHub repo in documentation

**AGPL Impact:**
- ✅ **No new copyleft obligations** — Unmodified code remains AGPL
- ✅ Your code can be any license (proprietary, permissive, etc.)
- ✅ BUT if you run as network service, comply with network clause

**Requirement:**
- Credit + link to OpenMontage GitHub in docs
- No source-sharing obligation (code is unmodified)
- If you expose via API, ensure users know where to get source (GitHub link)

---

## Network Server Clause (AGPLv3 §13)

**Applies When:** OpenMontage runs on a network server, and users interact remotely.

**Examples That Trigger:**
- ✅ Backlot web UI (HTTP) → users access via browser
- ✅ REST API endpoint (HTTP) → users call via API
- ✅ WebSocket real-time updates (HTTP) → users subscribe to changes

**Examples That Don't Trigger:**
- ❌ Local CLI tool (no remote users)
- ❌ Python library imported by other code (no remote interaction)
- ❌ Batch processing daemon (no user interaction layer)

**Requirement If Triggered:**
- Modified source must be available to users
- Can be via download link, git repository, or API endpoint

**For SaathiOS:**
- If you embed Backlot board in SaathiOS, users accessing it via HTTP → comply with network clause
- If you run OpenMontage as internal service (no user-facing HTTP) → no network clause trigger

---

## SaathiOS Recommendation: Scenario 1 (Embed as Service)

**Rationale:**
- ✅ Cleanest separation of concerns
- ✅ No AGPL copyleft risk
- ✅ OpenMontage can be updated independently
- ✅ SaathiOS license unrestricted
- ✅ Easy to replace OpenMontage with alternative later

**Implementation:**
1. Run OpenMontage as separate Python service (FastAPI app)
2. SaathiOS calls via HTTP API
3. SaathiOS never imports lib/ or tools/ code directly
4. No modifications to OpenMontage source
5. Document credit + GitHub link

---

## What Must Be Shared (If You Modify)

| Item | AGPL? | Reason |
|------|-------|--------|
| Modified lib/*.py | YES | Library code, copyleft applies |
| Modified tools/*.py | YES | Tool code, copyleft applies |
| Modified backlot/*.py | YES | Server code, network clause applies |
| Modified pipeline_defs/*.yaml | YES | Derivative of AGPL code |
| Custom BaseTool subclass | YES | Inherits from AGPL base class |
| Custom skill (Markdown) | UNCLEAR | Likely not "software", verify with legal |
| Project artifacts (JSON) | NO | User data, not covered by AGPL |
| Rendered videos | NO | Output, not source code |

---

## What Can Be Proprietary

- SaathiOS code (if using Scenario 1 or 3)
- Custom ExecutionGateway adapter
- Custom skills and playbooks (Markdown/JSON)
- Project data (scene plans, render reports, videos)
- Baadar integration code (if not modifying OpenMontage)

---

## Compliance Checklist

### If Scenario 1 (Embed as Service)

- [ ] Run unmodified OpenMontage as separate service
- [ ] SaathiOS calls via HTTP only
- [ ] Document credit + GitHub link in README.md
- [ ] No modifications to OpenMontage source
- [ ] SaathiOS license: unrestricted (proprietary, permissive, etc.)

### If Scenario 2 (Fork + Modify)

- [ ] All modifications to lib/, tools/, backlot/ are AGPL-licensed
- [ ] Modified code published on GitHub (or equivalent)
- [ ] Source available to end users (download link, API endpoint, etc.)
- [ ] SaathiOS repository itself must be AGPL-licensed
- [ ] Document all modifications clearly

### If Scenario 3 (Vendor Unmodified)

- [ ] Never modify OpenMontage source code
- [ ] Include full AGPL license text in distribution
- [ ] Document credit + GitHub link
- [ ] If running as network service, ensure source availability to users

---

## Edge Cases & Clarifications

### Q: Can SaathiOS use OpenMontage output?

**A:** Yes. Project artifacts (videos, scene plans, cost logs) are user data, not covered by AGPL.

### Q: Can I modify OpenMontage for internal use?

**A:** Yes, but if you use it as a network service, users must have access to modified source. If internal-only (no network exposure), no sharing required, but it's still AGPL-licensed code.

### Q: Can I write custom tools without AGPL?

**A:** Not if they inherit from BaseTool. Custom tools fall under AGPL copyleft.

### Q: Can I use OpenMontage output in proprietary products?

**A:** Yes. Output (videos, data) is user data, not covered by AGPL.

### Q: What if I link to OpenMontage code from my code?

**A:** Linking/importing triggers copyleft. Your code must be AGPL-licensed.

---

## Legal Disclaimer

This analysis is informational. Consult a lawyer licensed in your jurisdiction for binding legal advice.

---

**Analysis Date:** 2026-07-10  
**Recommended Approach:** Scenario 1 (Embed as Service)  
**SaathiOS License:** Unrestricted (if using Scenario 1)
