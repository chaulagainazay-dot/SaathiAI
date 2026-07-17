# M25 Live Certification Guide

## Run

```bash
python -m saathi.inference.live_cert_m25 discover
python -m saathi.inference.live_cert_m25
python -m saathi.inference.live_cert_m25 --json
python -m saathi.inference.runtime_gate
```

## Operator unlock path (manual — not performed by M25)

1. Repair/install Ollama.app so `/usr/local/bin/ollama` resolves.  
2. Start service: approved local method only (e.g. LaunchAgent / app).  
3. Manually pull a small model, e.g. `qwen2.5:1.5b` (operator action).  
4. Free memory ≥ ~2.5 GB available.  
5. Re-run `python -m saathi.inference.live_cert_m25`.  
6. Confirm evidence `live=true` and gates PASS before considering production certification.

## Evidence location

* `docs/evidence/m25/LIVE_CERT_EVIDENCE.json`  
* `docs/evidence/m25/LIVE_CERT_SUMMARY.md`  

Privacy-safe: no raw prompts/outputs/secrets.
