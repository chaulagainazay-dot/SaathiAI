# M22 Security & Privacy

## Credential isolation

* Provider API keys read only in allowlisted config/adapter modules.
* M22 facades (`llm.py`, `agent.py`, `research.py`) must not call `getenv` for provider keys.
* Missing credentials map to `MISCONFIGURED` — values never logged.
* Release rule `caller_credential_read` scans M22 inference facades.

## Telemetry

* Preflight and model events strip prompt/output/api_key fields.
* Opik/trace defaults suppress raw content unless `SAATHI_TRACE_RAW_LLM=1` (forbidden in production posture).

## Research

* Privacy classification remains `public_web`.
* Grounding errors return exception type names only.

## Trading Guardian

```text
UNCHANGED
UNENGAGED
LIVE TRADING NOT AUTHORIZED
```
