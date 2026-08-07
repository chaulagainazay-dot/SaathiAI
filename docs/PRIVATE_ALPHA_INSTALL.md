# Private Alpha Installation

**Production authorized: false.** Local-only private alpha.

## Prerequisites (required)

- Apple Silicon Mac (certified class)
- macOS
- Python 3.11+ in repo `.venv`
- Node.js ≥ 18 and npm
- `curl`
- ≥ 5 GB free disk

## Optional

- Local Ollama or other local fixtures (not required)
- LaunchAgent login start (disabled by default)

## Prepare (idempotent)

```bash
bin/saathi-alpha prepare
# or: .venv/bin/python -m saathi.platform.private_alpha prepare
```

Prepare will:

1. Inspect OS/arch, Python, Node, npm
2. Check disk headroom and ports
3. Reject unsafe public-bind configuration
4. Create required directories under `data/`
5. Write release manifest and default alpha config
6. **Never** request API credentials or activate paid providers

## First-run

```bash
bin/saathi-alpha init --ack-local-only
```

You must acknowledge local-only posture. Optional owner bootstrap for automated
setup (tests/operators):

```bash
bin/saathi-alpha init --ack-local-only --email owner@local --password 'YourPassw0rd!'
```

First-run includes:

- local-only acknowledgement
- organization/workspace selection (via bootstrap)
- HCG / IELTSAlert demo options
- backup destination
- notification preferences
- voice/provider availability (disabled by default)
- explicit **production disabled** notice

## Start

```bash
bin/saathi-alpha start
bin/saathi-alpha open
```

Opens `http://localhost:3000` only when both backend and frontend are healthy.
