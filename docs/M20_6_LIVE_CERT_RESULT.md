# M20.6 Live Certification Result (this host)

**Live:** false  
**Status:** BLOCKED  
**Verdict:** `M20.6 BLOCKED — NO APPROVED INSTALLED SMALL MODEL OR LIVE LOCAL ENGINE AVAILABLE`

## Discovery

| Item | Result |
|------|--------|
| Ollama binary | unavailable / broken symlink to missing Ollama.app |
| Models installed | 0 |
| Free memory | ~1.3 GB (below safety margin) |
| Downloads performed | **0** |
| Cloud calls | **0** |

## Suite infrastructure

Certification suite `m20.6.cert.suite.v1` + corpus `m20.6.cert.corpus.v1` implemented and unit-tested with injected governed path (not labelled live).

## Caller defaults

| Caller | Default | Live certified? |
|--------|---------|-----------------|
| cheap_ask | legacy | **no** |
| prose_clean | legacy | **no** |
| chat / voice / directors / TG | unchanged | n/a |

## Operator path to COMPLETE

1. Install/repair Ollama.app  
2. Manually pull ≤3B model (e.g. `qwen2.5:1.5b`)  
3. Free memory ≥ ~2.5 GB  
4. `python -m saathi.inference.certification run`  
5. Re-evaluate verdict from report  

No automatic install/pull by SaathiOS.
