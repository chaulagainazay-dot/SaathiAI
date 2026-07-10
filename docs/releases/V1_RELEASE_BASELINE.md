# SaathiOS v1.0 — Release Baseline (Phase 0)

**Captured:** 2026-07-10
**Role:** Release Lead / Principal Architect / Security / QA
**Rule enforced:** A capability is complete only when it works through the real UI on real data with loading/empty/error states, auth, responsive layout, tests, a passing smoke test, and an auditable result. Code existing ≠ complete.

---

## 1. Git state (preserved, nothing reset)

| Item | Value |
|------|-------|
| Repo | monorepo — `saathi/` (FastAPI backend) + `saathi-os/` (Next.js 15 frontend) + `client/` (legacy frontend) |
| Branch | `milestone/m7-security-engine` |
| HEAD | `d1736ede64a0322b0ce17b99b1372f7f6da515a2` |
| Working tree | **clean** (`git status --short` empty) |
| Remotes | `origin` github.com/chaulagainazay-dot/SaathiAI · `hf` huggingface Baadar/baadar-ai |

Recent commits (top 5):
```
d1736ed feat: ExecutionGateway adapters + orchestrators + integration (end-to-end wiring)
26d5a1c feat: ExecutionGateway foundation + third-party integrations discovery
ceb1317 feat(execution): finalize production-ready ToolIntent contract
066b433 feat(phase3.1): deep immutability to prevent authorization bypass
1e683ee fix(phase3.1): production readiness audit & fixes
```

**Rollback point:** `d1736ed` (current clean HEAD). Any RC work must branch from here, not mutate it.

## 2. Backups taken

Scratchpad `v1_backup/` (41 MB):
- `data_20260710_143332/` — all 12 SQLite DBs (`saathi.db`, `baadar*.db`, `content_*.db`, `revenue.db`, `coach.db`, `platform_memory.db`, backups)
- `storage_20260710_143332/` — `storage.db`
- `dotenv.backup` — `.env`

## 3. Secrets exposure (SECURITY — must fix before public release)

| Finding | Location | Severity |
|---------|----------|----------|
| HuggingFace push token embedded in git remote URL | `git remote -v` (`hf` remote) | **HIGH** — token in plaintext, printed by tooling |
| Firebase admin service-account key committed | `firebase-admin.json` (repo root) | **HIGH** |
| `.env` present in repo root | `./.env` | verify `.gitignore` coverage |
| `secrets/saathi-os/.env.backup` | tracked path | verify not in git index |

Action: rotate HF token, move firebase-admin.json to secret store, confirm `.gitignore` and `git ls-files` don't track secrets. **Not done in Phase 0 (inspection only).**

## 4. Backend startup smoke — PASS

- Entrypoint `saathi.server:app` imports clean.
- **296 total routes / 291 API routes.**
- Boots under uvicorn on 127.0.0.1:8799.
- `/docs` → 200. `/api/health` → 401 (auth middleware active — expected).
- Deprecation warnings: `@app.on_event` (FastAPI lifespan), starlette TestClient httpx — non-blocking.

## 5. Backend test suite — 3 COLLECTION ERRORS + 9 FAILURES

Runner: `.venv/bin/python -m pytest tests/` (py3.12, pytest 9.1.1, fastapi 0.138.1). 116 test files.

**Collection errors (import-time, block the file entirely):**
| File | Cause |
|------|-------|
| `tests/test_execution.py` | `ImportError: cannot import name 'ExecutionIntent' from 'saathi.execution'` |
| `tests/test_trade_journal.py` | same — imports `ExecutionIntent` |
| `tests/test_m5_explainability.py` | same family |

Root cause: `saathi/execution/__init__.py` is **empty**. The `feat: ExecutionGateway` commits added `toolintent.py`/`gateway.py` etc. but never exported symbols, and renamed `ExecutionIntent`→`ToolIntent` without updating dependents. **Regression introduced by the ExecutionGateway work.**

**Result excluding the 3 un-collectable files: 832 passed, 9 failed, 1 skipped (6m37s).**

Failures:
| Test | Symptom |
|------|---------|
| `test_infra_events.py` ×4 (model_router_emits_selected, fallback_then_failure, browser started/finished, escalated_on_block) | `AttributeError: module 'saathi.events.bus' has no attribute 'subscribe'` |
| `test_eventstream.py::test_real_published_event_reaches_stream` | event bus API drift (same root) |
| `test_bff.py::test_payload_has_full_contract` | `assert 2 == 3` — contract shape drift |
| `test_bff.py::test_dream_pct_tracks_revenue` | `assert 1.0 < 0.01` — metric calc drift |
| `test_ai_lab.py::test_studio_tracks_prompt_only_with_default_gen` | studio tracking |
| `test_client_intake.py::test_studio_run_tags_project` | AttributeError |

Two clusters: **(a) event bus `subscribe()` removed/renamed** (5 tests), **(b) BFF/studio contract drift** (4 tests).

## 6. Frontend production build — PASS

`npm run build` (Next.js 15.5.20) succeeds. **37 routes** compiled (30 static ○, 7 dynamic ƒ). Shared JS 102 kB. No type/lint errors blocking build. Dev server serves localhost:3000; all 10 primary routes verified rendering with zero console errors (prior smoke this session; earlier ChunkLoadError was stale webpack cache, cleared by rebuild).

## 7. Baseline gate summary

| Gate | Status |
|------|--------|
| Git preserved + rollback point | ✅ |
| DB/secret backup | ✅ |
| Backend import/startup | ✅ |
| Backend tests | ❌ 3 collection errors + 9 failures |
| Frontend build | ✅ |
| Frontend runtime smoke (10 routes) | ✅ |
| Secrets clean | ❌ HF token + firebase key exposed |

**Baseline verdict: NOT release-ready.** Test collection is broken and the execution layer central to Phases 5–7 is dead code (see V1_CAPABILITY_AUDIT.md).
