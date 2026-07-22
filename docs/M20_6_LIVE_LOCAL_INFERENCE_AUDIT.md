# M20.6 — Live Local Inference Audit

**Date:** 2026-07-16  
**Starting HEAD:** `fb7eaea` (M20.5)  
**Host:** Apple M2, 8 GB unified memory  
**Rollback:** starting HEAD above  

---

## Intake snapshot

| Check | Result |
|-------|--------|
| Root | `/Users/macbookpro/SaathiAI` |
| Branch | `milestone/m7-security-engine` |
| Sync | `0/0` with origin at intake |
| Worktree | clean |
| M20.5 present | yes (`fb7eaea`) |
| Exclusive ownership | this Grok session; no overlapping writers on `saathi/inference/` |
| Available memory | ~1.3 GB free (below safety margin 2.0 GB) |
| Free disk | ~73 GB |

---

## 5.1 Engine inventory

| Engine ID | Binary/service | Version | Installed? | Running? | Health | Local-only | Canonical adapter | Classification |
|-----------|----------------|---------|------------|----------|--------|------------|-------------------|----------------|
| ollama | `/usr/local/bin/ollama` → Ollama.app | n/a | **broken symlink** (Ollama.app missing) | no | GET `/api/tags` fails | yes when live | `saathi.inference.adapters.ollama.OllamaEngine` | `UNAVAILABLE` |
| ollama residual | `~/Library/Application Support/Ollama/` | n/a | support dir present; no app | stale `ollama.pid` possible | n/a | n/a | n/a | `INSTALLED_UNCERTIFIED` residue only |
| llama.cpp | not found | — | no | no | — | — | none | `UNAVAILABLE` |
| MLX | not found | — | no | no | — | — | none | `UNAVAILABLE` |
| OpenJarvis process | not installed | — | no | no | — | — | concepts only M20.1 | `UNSUPPORTED` as runtime |
| FakeEngine | test only | — | yes (code) | n/a | mock | yes | `adapters/fake.py` | `TEST_ONLY` |

**Required action:** Operator must install Ollama.app (or repair binary) and pull a ≤3B model **manually** before live cert can pass. SaathiOS must not auto-install.

---

## 5.2 Installed model inventory

| Model ID | Engine | Installed? | Digest | Resource-safe candidate? | Disposition |
|----------|--------|------------|--------|--------------------------|-------------|
| *(none discovered)* | ollama | no | — | — | **No candidates** |

`~/.ollama/` contains only `cache/model-recommendations.json` (cloud recommendations) — **not** local model weights. Recommendations include cloud-only entries (`glm-5.2:cloud`, etc.) — **out of scope / forbidden for M20.6**.

---

## 5.3 Execution-path inventory

| Entry | Caller | Rollout default | ModelRouter | Canonical path | Direct engine? | Remediation |
|-------|--------|-----------------|-------------|----------------|----------------|-------------|
| `cheap_ask` | `tools/cheap_llm.py` | `legacy` | via compat when opted-in | M20.2 when mode ≠ legacy | **no** (M20.3) | keep legacy default |
| `prose_clean` | `tools/prose.py` | `legacy` | via compat | M20.2 when opted-in | **no** | keep legacy default |
| `llm.generate` | many | n/a | yes | cloud/local callers | default path | **not migrated** |
| chat engine | `chat/engine.py` | n/a | yes | llm.generate | no local cert | **KEEP_LEGACY** |
| M20.6 cert CLI | `inference/certification.py` | cert-only | yes via gateway_path | **required** | forbidden | implement suite |
| shell `ollama run` | operator only | n/a | n/a | bypass | yes if used | **not used by cert** |

---

## 5.4 Resource-control inventory

| Control | Implementation | Enforced? | Limit | Notes |
|---------|----------------|-----------|-------|-------|
| Prompt size | `InferenceSettings.max_prompt_chars` + request validation | yes on governed path | 16k default | caller bounds lower (M20.3) |
| Output tokens | `max_output_tokens` | yes | 1024 global / 512–1024 caller | |
| Timeout | request + settings | yes | 60s / caller 45–60s | |
| Concurrency | `BoundedSemaphore` max 1 | yes | 1 | |
| Memory gate | `min_available_memory_gb` | yes | 1.5 GB | host currently fails (~1.3 GB) |
| Cancel | process stop on sessions; gen cancel limited | partial | — | cert tests cancel API |
| Model unload | not automatic | n/a | — | deferred |
| Download | never | yes | 0 | M20.6 policy |

---

## 5.5 Privacy and security inventory

| Risk | Control | Status |
|------|---------|--------|
| Prompt in logs | compat/ledger redaction; cert evidence stores hashes only | OK by design |
| Cloud escape | `local_only=True`, cloud fallback default off | OK |
| Tool use | `tool_use_permitted=False` | OK |
| Secret prompts in corpus | synthetic only | OK |
| TG crossover | no trade paths in inference | OK |
| Broken ollama symlink | discovery must not claim healthy | OK |

---

## 5.6 Certification-gap inventory

| Requirement | Existing | Missing | Blocking? |
|-------------|----------|---------|-----------|
| Discover installed engines | hardware + live_validation | full cert discovery report | no (infra exists) |
| Discover installed models | Ollama list_models | none available | **yes for live pass** |
| Real governed generation | gateway_path | needs live engine+model | **yes** |
| Quality corpus | none | cert corpus | implement |
| Cancel/timeout live | partial | need live | blocked env |
| Resource certification | hardware profile | peak RSS under load | blocked env |
| Caller-ready verdict | rollout | live scores | blocked env |

---

## Disposition

```text
LIVE CERTIFICATION: BLOCKED — NO APPROVED INSTALLED SMALL MODEL AVAILABLE
(+ broken Ollama binary; memory pressure)
```

Infrastructure for certification is implemented in this milestone so that when an operator installs a ≤3B model and restores Ollama, the same suite can produce a pass/fail report without code changes beyond env flags.

### Operator unblocking steps (manual — not performed by agent)

1. Install Ollama.app from upstream (or repair `/usr/local/bin/ollama`).  
2. Manually `ollama pull qwen2.5:1.5b` or `qwen2.5:3b` (operator choice; not automated).  
3. Free memory (close heavy apps) until available ≥ 2.5 GB.  
4. Re-run: `python -m saathi.inference.certification run`  
5. Review `docs/M20_6_LIVE_CERT_RESULT.json` if written under `data/`.
