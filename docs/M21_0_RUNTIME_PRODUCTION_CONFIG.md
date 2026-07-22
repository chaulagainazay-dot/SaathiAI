# M21.0 — Runtime Production-Configuration Inventory and Provider Policy

**Status:** COMPLETE (deterministic-tested)
**Branch:** `milestone/m7-security-engine`
**Evidence tier:** `UNIT_TESTED` + `SOURCE_INSPECTED`
**Not claimed:** production certified, live model certified, full M21 consolidation

---

## 1. Objective

Formalize production-safe **configuration inventory**, **provider policy**, and **per-provider kill switches** as the first slice of platform M21 — without starting M21.1 (caller contract enforcement) or M22.

## 2. Scope

### In scope

* Residual LLM/inference **call-path inventory** (machine-readable)
* **Production config schema** + validator over `InferenceSettings`
* **Provider policy** table (local/cloud/compat/fake)
* **Kill-switch matrix** (`SAATHI_INFERENCE_KILL_ALL`, `SAATHI_PROVIDER_KILL_*`)
* Gateway path **respects** ollama / kill-all switches
* Console flag catalog + `prod-config` CLI
* Focused tests + operator docs

### Out of scope (deferred)

| Item | Milestone |
|------|-----------|
| Migrate residual chat / all callers | M21.1 |
| Live cost ceilings + availability probes | M21.2 |
| Critical Manifest / release-check hard gate | M21.3 |
| Voice / durable agents | M22 |
| Live Ollama model install | Environment (M20.6) |

## 3. Architecture (reuse only)

```text
ModelRouter              — sole selection authority (unchanged)
saathi.inference         — extended with path_inventory, provider_policy, prod_config
ExecutionGateway path    — gateway_path consults kill switches
m20_console              — flag catalog + prod-config read-only command
```

**No** second ModelRouter, inference package, ExecutionGateway, run ledger, or TG engagement.

## 4. Packages / modules

| Module | Role |
|--------|------|
| `saathi/inference/path_inventory.py` | Call-path inventory |
| `saathi/inference/provider_policy.py` | Provider policy + kills |
| `saathi/inference/prod_config.py` | Schema validation + CLI |
| `saathi/inference/gateway_path.py` | Kill-switch enforcement |
| `saathi/m20_console/flags.py` | Kill flag catalog |
| `saathi/m20_console/status.py` | `m21_0` facet on inference snapshot |
| `saathi/m20_console/cli.py` | `prod-config` command |

## 5. Kill switches

```bash
# Emergency — all providers via policy
export SAATHI_INFERENCE_KILL_ALL=1

# Per family
export SAATHI_PROVIDER_KILL_OLLAMA=1
export SAATHI_PROVIDER_KILL_ANTHROPIC=1
# … see python -m saathi.inference.prod_config disable

# Master inference still default-off
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED SAATHI_ALLOW_CLOUD_FALLBACK
```

Defaults: kill switches **off** (not killed). Cloud policy **disabled** unless `SAATHI_ALLOW_CLOUD_FALLBACK=1`.

## 6. Operator CLI

```bash
python -m saathi.inference.prod_config validate
python -m saathi.inference.prod_config inventory
python -m saathi.inference.prod_config policy
python -m saathi.inference.prod_config disable
python -m saathi.inference.prod_config bundle
python -m saathi.m20_console prod-config
```

## 7. Tests

```bash
python -m pytest tests/test_m21_0_production_config.py -q
```

## 8. Disable / rollback

* Unset kill / inference env vars (defaults already safe).
* Git: revert M21.0 commits on this branch.

## 9. Verdict form

```text
M21.0 COMPLETE — RUNTIME PRODUCTION-CONFIGURATION INVENTORY AND PROVIDER POLICY FORMALIZED
```

Limitations: residual chat path inventoried not migrated; live model still environment-blocked; not production certified.
