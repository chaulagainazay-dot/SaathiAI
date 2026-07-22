# OpenMontage Security Assessment for SaathiOS

**Date:** 2026-07-10  
**Status:** Stage 1 (static analysis only, no penetration testing)  
**Scope:** Identify risks before M5.2 integration  

---

## Risk Summary

| Risk | Severity | Status | Mitigation |
|------|----------|--------|-----------|
| API key exposure in logs | HIGH | ⚠️ FOUND | Implement log scrubbing (Stage 2) |
| Path traversal | MEDIUM | ✅ MITIGATED | Path canonicalization implemented |
| Credential in .env | LOW | ✅ MITIGATED | .env in .gitignore |
| Code injection via YAML | LOW | ✅ MITIGATED | yaml.safe_load() used |
| Dependency vulnerabilities | MEDIUM | ⚠️ UNKNOWN | Add pip-audit to CI/CD (Stage 2) |
| Multi-tenant isolation | N/A | ✅ N/A | Single-user design; no multi-tenant in M5.1 |

---

## Detailed Findings

### 1. Logging & API Key Exposure ⚠️ HIGH

**Finding:** OpenMontage tool execution may log API request/response bodies.

**Risk:** Sensitive data (auth headers, credentials) could appear in checkpoint logs or backlot server logs.

**Evidence:**
- tools/cost_tracker.py logs only cost (safe)
- tools/video_compose.py doesn't explicitly redact responses
- tools/image_gen tools may log provider responses

**Mitigation (Stage 2):**
```python
class LogScrubber:
    """Redact sensitive data from logs"""
    
    SECRET_PATTERNS = [
        r"Authorization:\s*Bearer\s+\S+",
        r"api[_-]?key[\"']?\s*[:=]\s*[\"']?\S+",
        r"api[_-]?key[\"']?\s*[:=]\s*\S+",
        r"secret[\"']?\s*[:=]\s*[\"']?\S+",
        r"password[\"']?\s*[:=]\s*[\"']?\S+",
        r"token[\"']?\s*[:=]\s*[\"']?\S+",
    ]
    
    @staticmethod
    def scrub(text: str) -> str:
        """Replace secrets with ***REDACTED***"""
        for pattern in LogScrubber.SECRET_PATTERNS:
            text = re.sub(pattern, "***REDACTED***", text, flags=re.IGNORECASE)
        return text
```

**SaathiOS Action:** Add log scrubber middleware in ExecutionGateway before persistence.

---

### 2. Path Traversal ✅ LOW (Mitigated)

**Finding:** OpenMontage uses Path.resolve() for path canonicalization.

**Status:** Safe. No user input in path construction within core libs.

**Evidence:**
- lib/paths.py defines PROJECTS_DIR, REPO_ROOT once
- All path operations use Path.resolve() (normalized absolute paths)
- backlot/state.py uses iterdir() + filtering, no string concatenation

**Residual Risk:** If SaathiOS passes user-controlled project_id to OpenMontage API, validation needed.

**Recommendation:** Validate project_id format (UUID format) before calling OpenMontage.

```python
def validate_project_id(project_id: str) -> bool:
    """Ensure project_id is safe"""
    import re
    # UUID v4 format
    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", 
                         project_id, re.IGNORECASE))
```

---

### 3. Credential Storage ✅ LOW (Mitigated)

**Finding:** API keys stored in .env file (not in code).

**Status:** Safe. Standard practice.

**Evidence:**
- .env in .gitignore (never committed)
- service-account JSON files in .gitignore
- No hardcoded secrets (grep verified)

**SaathiOS Integration:**
- Store OpenMontage .env outside SaathiOS repo
- Load at service startup, not in code
- Consider secrets manager (Vault, 1Password) for production

---

### 4. YAML Injection ✅ LOW (Mitigated)

**Finding:** Pipeline manifests loaded via yaml.safe_load().

**Status:** Safe. safe_load() prevents code injection.

**Evidence:**
- lib/pipeline_loader.py uses yaml.safe_load()
- No yaml.load() (unsafe) found

**Risk:** If user can upload custom pipeline YAML, validate schema first.

**Recommendation:** Only load pipelines from repo; don't accept user-uploaded YAMLs.

---

### 5. JSON Schema Validation ✅ MEDIUM

**Finding:** Artifacts validated against JSON Schema before checkpoint write.

**Status:** Good. Prevents malformed data from propagating.

**Evidence:**
- lib/checkpoint.py uses jsonschema.validate()
- schemas/artifacts/*.schema.json enforce structure

**Consideration:** Schema validation doesn't protect against semantic attacks (e.g., price injection, SQL in metadata strings).

**Recommendation (Stage 2):** Add semantic validation layer.

```python
def validate_artifact_semantics(artifact: Dict, artifact_type: str) -> List[str]:
    """Validate semantic constraints"""
    errors = []
    
    if artifact_type == "cost_log":
        # Ensure costs are reasonable (< $100 per entry)
        for entry in artifact.get("entries", []):
            if entry.get("actual_usd", 0) > 100:
                errors.append(f"Cost suspiciously high: ${entry['actual_usd']}")
    
    return errors
```

---

### 6. Dependency Vulnerabilities ⚠️ MEDIUM

**Finding:** No automated dependency scanning observed in CI/CD.

**Risk:** Known CVEs in transitive dependencies could be present.

**Recommendation (Stage 2):** Add pip-audit to CI/CD.

```bash
# .github/workflows/security.yaml
- name: Audit Python dependencies
  run: pip-audit requirements.txt --desc
```

**OpenMontage Dependencies (Sample Risk):**
- Pillow (image processing): Monitor for DoS via malformed images
- requests (HTTP): Monitor for cert validation bypasses
- pydantic (validation): Generally well-maintained

---

### 7. Credential Expiry ⚠️ MEDIUM

**Finding:** No built-in credential expiry check.

**Risk:** Expired API keys fail silently; pipelines error at tool execution time.

**Recommendation (Stage 2):** Implement pre-flight credential validation.

```python
class CredentialValidator:
    """Check credentials before pipeline"""
    
    async def validate_credentials(self, config: OpenMontageConfig) -> List[str]:
        """
        Returns list of expired/invalid credentials.
        Raises OpenMontageExecutionDisabled for Stage 1.
        """
        raise OpenMontageExecutionDisabled(
            "OpenMontage execution is unavailable during Stage 1."
        )
```

---

### 8. Service Account Key Rotation ⚠️ LOW

**Finding:** Service account keys (GOOGLE_APPLICATION_CREDENTIALS) stored as files.

**Risk:** Key compromise exposes all GCP resources.

**Mitigation:**
- Rotate keys annually
- Use short-lived tokens when possible
- Monitor GCP Cloud Audit logs for unauthorized access

**Recommendation (M5.3):** Use GCP Workload Identity for kubernetes deployments (eliminates key files).

---

### 9. Approval Workflow Bypass ✅ MEDIUM

**Finding:** Approval decisions stored in checkpoints; no cryptographic signature.

**Risk:** Technically, approval could be forged (checkpoint file edited).

**Status:** Acceptable for M5.1 (single-user, local storage).

**Mitigation:**
- Approval stored in checkpoint (checkpoint_name.json)
- Backlot board reads checkpoints (read-only watcher)
- Local file permissions protect from tampering

**Recommendation (M5.2):** Sign checkpoints with user key for audit trail.

---

### 10. Workspace Isolation ✅ LOW

**Finding:** projects/<id>/ directory model provides workspace isolation.

**Status:** Safe for single-user. No cross-project leakage.

**Evidence:**
- Artifacts project-scoped
- Tool invocations stateless
- backlot/state.py reads by iterdir() + filtering

**Limitation:** No access control (single-user only). OS file permissions are sole protection.

**Recommendation (M5.2+):** Add access control layer if multi-user support added.

---

## Threat Model: SaathiOS Integration

```
Actor: Ajay (trusted)
  └─→ SaathiOS (trusted)
      └─→ OpenMontage (trusted, but AGPL)
          └─→ External Providers (untrusted)
              └─→ Google APIs
              └─→ OpenAI APIs
              └─→ Runway APIs
              └─→ fal.ai
```

### Threat: Provider API Compromise

**Scenario:** Attacker gains OpenAI API key access.

**Impact:** Attacker can run image generation at Ajay's expense.

**Mitigation:**
- Store keys in .env (not in code)
- Implement cost governance (approval threshold)
- Monitor cost_log.json for anomalies
- Set provider API spend limits (if supported)

### Threat: Checkpoint Tampering

**Scenario:** Attacker modifies checkpoint to inject malicious instructions.

**Impact:** Next stage reads corrupted artifact; pipeline fails.

**Mitigation (M5.1):**
- Local file permissions (OS-level)
- Validate schema before use
- Checkpoints immutable once written

**Mitigation (M5.2+):**
- Sign checkpoints with actor key
- Audit trail for all modifications

---

## Security Checklist for M5.2

- [ ] Implement log scrubber for API responses
- [ ] Add pre-flight credential validation
- [ ] Add pip-audit to CI/CD
- [ ] Validate project_id format before API calls
- [ ] Add semantic validation for artifacts
- [ ] Implement checkpoint signing
- [ ] Monitor cost_log.json for anomalies
- [ ] Add provider API rate limit tracking
- [ ] Document credential rotation policy
- [ ] Add health check for provider APIs

---

## No Penetration Testing

**Scope Limitation:** Stage 1 is static analysis only. No:
- Runtime attacks (buffer overflow, race conditions)
- Exploit development
- Penetration testing against external providers
- Fuzzing

**When to conduct PT:** Post-M5.1, before production deployment of character-animation.

---

**Assessment Completed:** 2026-07-10  
**Severity: HIGH finding:** 1 (log exposure)  
**Severity: MEDIUM findings:** 3 (dependency audit, credential expiry, checkpoint signing)  
**Ready for M5.2:** Yes, with mitigations implemented

