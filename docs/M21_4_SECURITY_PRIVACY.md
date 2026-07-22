# M21.4 — Security & Privacy

## Guarantees

* Runtime gate / release check / console readiness emit **no** raw prompts or outputs  
* No API keys, authorization headers, or exchange credentials in gate reports  
* Secret scan remains part of ops release gate (strong rules; tests/docs excluded for noisy placeholders)  
* Raw prompt logging flag (`SAATHI_LOG_RAW_PROMPTS`) fails production posture  
* Fake/test providers cannot become production-eligible  
* Unknown callers disabled / forbidden  
* Cloud fallback remains default-off  
* Trading Guardian: **UNCHANGED / UNENGAGED**  
* No exchange SDK imports under `saathi/inference/`  

## Secret scan

Use repository canonical path via `saathi.ops.release_gate` / `saathi.repair.secrets_scan`.

M21.4 does not weaken secret scanning.

## Live credentials

* No live cloud credentials added  
* No models downloaded  
* Ollama not installed by milestone (environment-blocked when absent)  
