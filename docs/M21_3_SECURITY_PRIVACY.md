# M21.3 Security & Privacy

## Logged (safe)

Request ID, caller ID, path ID, provider ID, model class, capability, input/output **sizes**, fingerprint prefix, failure category, kill/circuit state, latency, attempt count, adapter ID.

## Excluded

Raw prompts, chat messages, research source text, outputs, API keys, Authorization headers, private files, exchange credentials, full provider error bodies.

## Controls

* `legacy_facade` / `llm.generate` events strip prompt/output keys
* Default Opik trace suppresses raw content unless `SAATHI_TRACE_RAW_LLM=1`
* Research errors return exception type names, not bodies
* Release check flags `log_prompt=True` / `log_output=True` assignments

## Kill switches

```bash
export SAATHI_INFERENCE_KILL_ALL=1
export SAATHI_PROVIDER_KILL_OLLAMA=1   # example per-provider
```

## Trading Guardian

UNCHANGED / UNENGAGED / LIVE TRADING NOT AUTHORIZED. No trading inference callers enabled.
