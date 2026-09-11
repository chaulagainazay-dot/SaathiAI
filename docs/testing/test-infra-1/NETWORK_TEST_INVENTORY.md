# Network Test Inventory

## Method

```bash
grep -rln "import httpx\|import requests\|import urllib\|import aiohttp\|import socket\|websocket" tests/
grep -rhoE "https?://[a-zA-Z0-9.-]+" tests/ | sort | uniq -c | sort -rn
```

## Files importing a network library (12)

`test_connector_drivers.py` · `test_m33_external_provider_runtime.py` ·
`test_m18_3_insforge_provider.py` · `test_m328_m335_production_readiness.py` ·
`test_m320_m327_provider_contracts.py` · `test_failure_injection.py` ·
`test_m355_agentdev_model_adapter.py` · `test_browser_service.py` ·
`test_human_browser.py` · `test_m21_4_runtime_consolidation.py` ·
`test_browser_session.py` · `test_connectors.py`

Importing a network library is not the same as reaching the network. Every
external-looking host referenced in the suite is either a deliberately invalid
sentinel or a loopback address:

| Host pattern | Count | Nature |
|---|---|---|
| `http://x`, `https://x`, `http://a.com` | 27 | URL-parsing fixtures |
| `https://youtu.be`, `https://youtube.com` | 23 | string fixtures, not fetched |
| `https://github.com`, `https://api.github.com` | 23 | connector metadata fixtures |
| `https://acme.com`, `http://evil.example`, `https://evil.test`, `https://evil.com`, `https://example.invalid` | 25 | SSRF / allowlist negative tests |
| `http://169.254.169.254` | 6 | cloud metadata endpoint — **SSRF denial tests**, must never be reachable |
| `http://127.0.0.1:7130` | 4 | InsForge fixtures, loopback with nothing listening |

## Tests that actively block the network

Three files monkeypatch the socket layer to *prove* code fails closed rather than
egressing:

| File | Patch |
|---|---|
| `test_m33_external_provider_runtime.py:91-92` | `socket.getaddrinfo` and `socket.socket` → raise |
| `test_m320_m327_provider_contracts.py:794` | `socket.socket` → blocked |
| `test_m328_m335_production_readiness.py:735-736` | `socket.socket.connect`, `socket.create_connection` → refuse |

All use pytest's `monkeypatch`, which is undone at teardown. None leaked — they
were checked as hang suspects and cleared (they also collect *after* the hang
point, so they could not have caused it).

## Confirmed: the hang involved no network at all

`lsof -nP -p <pid>` against the live stalled interpreter returned **zero** TCP or
UDP entries. A direct `httpx` GET to the configured InsForge URL fails in 0.05 s.
See `ROOT_CAUSE.md`.

## Changes made

`tests/test_m18_4_insforge_migration.py` now injects an `httpx.MockTransport`
into `InsForgeProvider`, so the migration tests never attempt a socket connection
even to loopback. This was begun by earlier uncommitted work in the tree and is
retained: it is correct, it removes 4 loopback connection attempts per run, and
it makes the file independent of whether anything happens to be bound to port
7130.

`tests/test_m80_conversation_service.py::test_real_ollama_generation_when_available`
is marked `external` — it probes a local Ollama service and runs only when one is
present.

## Assessment

The offline suite has **no dependency on external network availability**. What
network-shaped code exists is either mocked, loopback-only, or a negative test
asserting that egress is refused.
