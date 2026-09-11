# Offline Suite Contract

## Canonical command

```bash
pytest tests -m "not browser and not live and not external and not network"
```

Run it with the checkout-local interpreter so the `conftest.py` import guard is
satisfied.

## Why a marker filter when the unfiltered suite now passes

After the fix, plain `pytest tests` completes: **7642 passed, 2 skipped, 667.63 s**.
The filter is not needed to *finish* — it is needed to make the run **deterministic
on a machine that has no browser, no Ollama, and no network**.

Several tests are written to self-skip when their dependency is absent
(`skip_no_browser`, "when available" Ollama probes). That works, but it means the
same command exercises a different set of tests on a developer laptop than in CI,
and a test that self-skips today can start *running* tomorrow because someone
happened to have Ollama up. The markers make the boundary explicit rather than
incidental.

## Markers

Declared in `pyproject.toml` under `[tool.pytest.ini_options]`:

| Marker | Meaning |
|---|---|
| `browser` | launches or requires a browser |
| `network` | may access a network endpoint |
| `live` | requires live external infrastructure |
| `external` | requires an external provider or service |
| `live_ollama` | requires a running local Ollama service |
| `integration` | local integration test, outside the bounded certification run |

## Guarantees of the offline suite

- No external network required
- No real provider API keys required
- No browser required
- No real broker, no live endpoint, no production capital
- Isolated security store — see below
- Deterministic completion, with a pytest summary line

## Security-store isolation (added by this mission)

`conftest.py` sets `SAATHI_SECURITY_DB` to a per-session temporary path when the
variable is unset. Without it, a test session opens dozens of connections against
the operator's real `~/.saathi/security.db`.

Two things follow from that, and both matter:

1. **Correctness.** Tests were mutating the developer's live security database —
   users, sessions, API tokens, audit log. That should never have been true.
2. **The hang.** Contention on that shared file is what deadlocked the suite.

`SecurityStore(db_path=...)` still wins when passed explicitly, and with neither
the argument nor the environment variable the historical `~/.saathi/security.db`
default is unchanged. Production behaviour is untouched.

## What this suite does **not** cover

- Browser / Playwright certification (`-m browser`)
- Live provider certification (`-m "live or external"`)
- `saathi-os` JavaScript tests (separate npm toolchain)

Run those explicitly and separately when their dependencies are present.

## CI suitability

The command is suitable for CI as-is. Two caveats worth knowing before wiring it
up:

- **Duration.** ~11 minutes unfiltered on an 8 GB Apple Silicon host. The slowest
  single test is 18.3 s; fifteen tests exceed 7 s. There is real headroom here,
  but reducing it was out of scope for this mission.
- **Serial only.** The suite has not been validated under `pytest-xdist`. Given
  that the bug just fixed was cross-test SQLite contention on a shared file,
  parallelising without first auditing every shared-path default would be
  premature.
