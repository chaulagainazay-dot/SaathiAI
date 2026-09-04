---
title: SaathiOS
emoji: 🏔️
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: true
---

# SaathiOS

SaathiOS is the product: one local operating environment for Central Command,
conversation and voice, agent work, governed intelligence, applications, and
paper-only trading research.

SaathiAI is the internal intelligence layer inside SaathiOS. The existing
`saathi` Python namespace, inference adapters, model router, memory, and agent
modules retain their technical names to preserve compatibility; they are not a
separate application or product.

## Canonical local runtime

The primary experience is SaathiOS Central Command:

`http://127.0.0.1:3000`

```bash
cd /path/to/saathios
./bin/saathi-local doctor
./bin/saathi-local start
```

Useful lifecycle commands:

```bash
./bin/saathi-local status
./bin/saathi-local open
./bin/saathi-local logs
./bin/saathi-local stop
```

The launcher owns exactly one loopback FastAPI backend on
`127.0.0.1:8765` and one Next.js frontend on `127.0.0.1:3000`. It refuses
to kill or silently reuse a process from another checkout. The historical
`scripts/start_local.sh` entrypoint delegates to this same manager.

One-time setup:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd saathi-os
npm install
```

Configuration belongs in an untracked `.env` created from `.env.example`.
Never commit credentials. Local model use is optional; SaathiOS does not
download models or enable paid providers automatically.

## Canonical architecture

- Product shell and Central Command: `saathi-os/`
- Conversation and voice runtime: `saathi/platform/conversation` and
  `saathi/platform/voice/runtime`
- SaathiAI intelligence: `saathi/inference`, `saathi/model_router.py`,
  `saathi/memory`
- Agent work: `saathi/agent_runtime` and
  `saathi/platform/mission_runtime`
- External action boundary: `saathi.execution.ExecutionGateway`
- Trading safety: `saathi.platform.trading_guardian` and
  `saathi.platform.tg`
- Audit and evidence: `saathi/audit`, `saathi/evidence`, and
  `saathi/security`

The full provenance and ownership record is in
`docs/architecture/SAATHIOS_CANONICAL_UNIFICATION.md`.

## Safety posture

- Trading is paper/advisory by default; live broker connectivity is not
  activated.
- Models and agents may propose work but cannot approve or execute side effects.
- External writes must pass authenticated policy, approval, ExecutionGateway,
  and audit boundaries.
- Voice has one SaathiOS command capture owner; settings microphone checks are
  explicit transient diagnostics.
- Runtime state, secrets, databases, caches, model weights, and browser profiles
  stay outside Git.

The Hugging Face metadata above is retained for compatibility with the existing
remote. That hosted surface is not the canonical local SaathiOS runtime.
