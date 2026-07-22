# M22 Release Check

## Command

```bash
.venv/bin/python -m saathi.inference.release_check
.venv/bin/python -m saathi.inference.release_check --explain
```

## New / tightened rules

| Rule | Purpose |
|------|---------|
| `facade_direct_provider_url` | llm/agent/research must not contain provider URLs |
| `facade_direct_sdk_import` | facades must not import openai/anthropic |
| `caller_credential_read` | M22 inference facades must not getenv provider keys |
| SDK allowlist | `llm.py`, `agent.py`, `research.py` removed |

## Failure behavior

Exit code 2 on any blocking finding. `production_certified` always false in report.
