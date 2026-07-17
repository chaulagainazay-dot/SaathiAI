# M25 — Local Provider Environment Audit

**Host:** Apple M2, arm64, 8 GB unified memory  
**Date:** 2026-07-17  
**Starting HEAD:** `e9571f3`  
**Policy:** read-only discovery; no install, no service start, no model pull  

## Discovery commands (executed)

| Check | Result |
|-------|--------|
| `command -v ollama` | empty (not on PATH) |
| `/usr/local/bin/ollama` | **broken symlink** → `/Applications/Ollama.app/Contents/Resources/ollama` (target missing) |
| `/Applications/Ollama.app` | **absent** |
| `ollama --version` | unavailable |
| `curl http://127.0.0.1:11434` | connection refused |
| `launchctl` `com.ajay.ollama` | LaunchAgent present, **not running** (`active count = 0`) |
| `brew list ollama` | not installed via brew list |
| `~/.ollama` | exists; **no model manifests**; cache only (~4 KB) |
| `SAATHI_*` env | none set |
| `OLLAMA_*` env | none set |

## Hardware

| Metric | Value |
|--------|-------|
| Architecture | arm64 (Apple M2) |
| Total memory | 8.0 GB |
| Available memory | ~1.41 GB |
| Memory safety margin | 2.0 GB |
| Memory gate | **FAIL** (pressure) |
| Free disk | ~69 GB |
| Recommended max model | ≤3B |

## Configured endpoint

| Item | Value |
|------|-------|
| Endpoint | `http://127.0.0.1:11434` |
| Source | `InferenceSettings.ollama_base_url` default |
| Allowlisted | yes (`127.0.0.1`, `localhost`, `::1`) |
| Auth mode | none (local) |

## Certification blockers

1. `ollama_broken_symlink` — binary path exists but Ollama.app missing  
2. `ollama_binary_absent_or_unusable`  
3. `ollama_runtime_unreachable` — port 11434 closed  
4. `no_installed_models_observed`  
5. `memory_pressure` — available RAM below safety margin  

## Operator permission boundary

| Action | Performed? |
|--------|------------|
| Install Ollama | **No** (forbidden) |
| Start LaunchAgent / `ollama serve` | **No** (no documented M25 start permission) |
| Pull models | **No** (forbidden) |
| Enable cloud | **No** |

## Models

| Model | Status |
|-------|--------|
| (none) | No installed generation models discovered |

## Secondary CLI evidence

Not used as certification path. Full-path binary unusable due to broken symlink.

## Verdict impact

Live local provider path **cannot** be certified on this host until operator repairs Ollama install, starts the service, installs an approved ≤3B model, and frees memory.

```text
M25 BLOCKED — LIVE LOCAL PROVIDER ENVIRONMENT UNAVAILABLE
```
