# M25 Validation

## Closeout repair (embedding isolation)

Root cause of suite regressions after Ollama install: `select_provider("auto")`
chose `OllamaEmbedder` when the daemon answered `/api/tags` even though the
embedding model (`nomic-embed-text`) was **not** installed. Embeddings were not
persisted; retrieval fell back to keyword-only. Deterministic memory tests
expect stored hybrid vectors.

**Fixes (no nomic-embed-text pull):**

* Tests inject `LocalDeterministicEmbedder` explicitly.
* Production `auto` requires Ollama **embedding model present** (readiness).
* Explicit `select_provider("ollama")` fails with `embedding_model_missing`.
* Dual evidence: historical PASS preserved separately from latest observation.

## Focused

```bash
.venv/bin/python -m pytest tests/test_memory_engine.py -q
.venv/bin/python -m pytest tests/test_m25_live_provider_certification.py -q
```

## Live

```bash
ollama stop qwen2.5:1.5b
.venv/bin/python -m saathi.inference.live_cert_m25 discover
.venv/bin/python -m saathi.inference.live_cert_m25
.venv/bin/python -m saathi.inference.runtime_gate --explain
```

## Evidence files

* `docs/evidence/m25/LATEST_ENVIRONMENT_OBSERVATION.json`
* `docs/evidence/m25/LAST_SUCCESSFUL_LIVE_CERTIFICATION.json`
* `docs/evidence/m25/LIVE_CERT_EVIDENCE.json` (combined)
* `docs/evidence/m25/cert/full_suite_evidence.json`
* `docs/evidence/m25/cert/secret_scan_evidence.json`
* `docs/evidence/m25/cert/critical_check_evidence.json`
* `docs/evidence/m25/cert/certification_package.json`

## Package certification

```bash
.venv/bin/python -m saathi.inference.cert_evidence record-package --from-log /tmp/pytest.log
.venv/bin/python -m saathi.inference.cert_evidence status
.venv/bin/python -m saathi.inference.runtime_gate --json
# expect production_certified=true when all package + live mandatory checks PASS
```

## Invariants

```text
production_certified = true only when all mandatory gates PASS and evidence fresh
cloud fallback = disabled
Trading Guardian = UNCHANGED / UNENGAGED
```
