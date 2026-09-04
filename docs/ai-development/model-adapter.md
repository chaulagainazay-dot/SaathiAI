# Local Reasoning Adapter

**Milestone:** M355
**Module:** `saathi/agentdev/model_adapter.py`
**Commands:** `model capabilities` · `model health` · `model verify`
**Provider:** Ollama, loopback only
**Model:** `qwen3:4b`

One local model, behind an interface that gives it nothing else. This is the
only place in `agentdev` that talks to a model.

---

## 1. What the adapter offers

Nine capabilities, and no tenth:

`load` · `health_check` · `send_prompt` · `receive_response` ·
`record_metadata` · `timeout` · `cancel` · `retry` · `resource_measurement`

## 2. What it denies, and how

| Denied | Mechanism | Classification |
|---|---|---|
| Non-loopback network | `assert_loopback()` runs at construction and refuses anything but `127.0.0.1`, `localhost` or `::1`, before a socket exists | `technically_enforced` |
| Credentials | The only header ever constructed is `Content-Type`. No code path builds an `Authorization` header | `technically_enforced` |
| Tool invocation | `tools`, `functions`, `tool_choice`, `function_call` are in `FORBIDDEN_OPTION_KEYS` and refused | `technically_enforced` |
| Shell access | The module imports no `subprocess`, `os`, `shutil`, `pathlib`, `socket`, `ctypes`, `pty` or `shlex` — asserted against the parsed import list, not a substring of the prose | `technically_enforced` |
| Filesystem writes | Same import check; the adapter reads and writes no file | `technically_enforced` |
| Provider fallback | Neither adapter class can construct the other; a failed call returns a failure with the configured model name and empty text | `technically_enforced` |
| Paid API calls | Follows from the loopback check — no public host is reachable | `technically_enforced` |

A model that emitted `rm -rf /` would produce a string. Nothing in this module
can execute one, and nothing hands the string to anything that could.

## 3. No fallback, on purpose

If the configured adapter is unhealthy, the call fails and says why. Answering
from a second model would make every recorded result unattributable, which is
worse than an error — the whole point of M356 is knowing *which* model did what.

`ScriptedAdapter` exists so the test suite can exercise every path on a machine
with no daemon. It is chosen explicitly, never substituted, and every response
records the adapter that produced it.

## 4. Metadata, and the measured/estimated distinction

Ollama reports `prompt_eval_count` and `eval_count`. When present they are
recorded with `source: measured`. When absent the adapter falls back to
characters÷4 and records `source: estimated` with a note saying so. The
distinction is carried into every report rather than smoothed away.

Memory is reported twice, with different meanings:

- `peak_memory_growth_bytes` — growth in **this process's** peak RSS across the call. Small, because the model does not live here.
- `health().resident_models` — what the **provider daemon** is holding, which is the number that matters on an 8 GB host.

## 5. Determinism is requested, not guaranteed

`temperature: 0` and `seed: 1` are the defaults, and `think: false` suppresses
reasoning traces because this layer evaluates the answer it is given. Two runs
of the same prompt are therefore comparable. They are not guaranteed identical:
a provider may vary output across versions, quantisations or hardware. The
capability report says this in its own `limitation` field.

## 6. Measured on the development host

Apple Silicon, 8 GB RAM, `qwen3:4b`, one model resident:

| | |
|---|---|
| Model on disk | 2.5 GB |
| Model resident | 2.95 GiB, 100% GPU |
| Load (already resident) | ~300 ms |
| Latency, 8-token reply | ~1.1 s |
| Latency, 96-token JSON reply | ~5.6 s |
| Latency, 96-token prose reply | ~8.1 s |
| Throughput | 7–11 tokens/second |
| Adapter process peak RSS | 29 MiB |

Full report: `docs/evidence/m352_m359/ADAPTER_VERIFICATION.json`.

One behavioural observation worth carrying into M356: asked to *reply with
exactly one word*, `qwen3:4b` spent its whole 8-token budget on a preamble
("Hmm, the user wants me to reply") and never emitted the word. In JSON mode it
returned well-formed JSON on the first attempt. That difference is data, not a
defect, and M356 scores it rather than working around it.

## 7. What this does not establish

- **Nothing about output quality.** Three calls establish that the path works and what it cost here.
- **Nothing about another model, host or day.** Every number above is one host at one moment.
- **No sandbox around the provider.** The adapter cannot reach a shell; the Ollama daemon is an ordinary process on the machine and this milestone does not confine it.
- **No concurrency guarantee.** One model instance is the declared ceiling; nothing in this module enforces it.
