# Model Inventory and Resource Baseline

**Milestone:** M370
**Modules:** `saathi/agentdev/model_inventory.py` · `saathi/agentdev/host_probe.py`
**Command:** `qualification inventory` · `qualification baseline`
**Classification:** `deterministic`

Before any model can be evaluated, two questions have to be answered from the
machine rather than from memory: what is actually installed, and what can this
host actually run.

## 1. What the inventory reads

Three read-only Ollama endpoints on loopback:

| Endpoint | What it gives |
|---|---|
| `/api/tags` | Every installed model: name, tag, digest, on-disk size |
| `/api/ps` | Which models are resident right now |
| `/api/show` | Family, parameter size, quantisation, context length |

No other endpoint is called. There is no `/api/pull`, no `/api/delete`, no
`/api/create` and no `/api/copy` anywhere in the package — a model cannot be
downloaded or removed by anything in this range, by construction rather than by
policy.

Each installed model produces a record:

| Field | Source |
|---|---|
| `name`, `tag` | `/api/tags` |
| `digest` | `/api/tags` — the identity a result is pinned to |
| `size_bytes` | `/api/tags` |
| `family`, `parameter_size`, `quantization`, `context_length` | `/api/show` |
| `running` | `/api/ps` |
| `eligibility` | Derived from size against the host ceiling |
| `exclusion_reason` | Stated in full when eligibility is not `eligible` |

Duplicate digests and missing digests are reported rather than deduplicated, so
two tags pointing at one blob cannot silently become two evaluations.

## 2. What the host probe measures

`host_probe.py` runs three frozen argv probes:

```
/usr/sbin/sysctl -n vm.swapusage
/usr/bin/vm_stat
/usr/bin/memory_pressure
```

Every argv is a constant in `PROBES`. Nothing is constructed, formatted or
interpolated at call time, no probe takes a parameter, `shell=False` always, and
every probe is read-only. A probe that fails returns `available: False` with the
reason and never raises into the caller.

The module is not on the model path. No model output reaches it, and no model
path module imports it.

Measured per baseline: physical memory, reclaimable memory, memory pressure,
swap total/used/free, page statistics, free disk, load average, and the set of
resident models.

## 3. Eligibility is about this machine, never about quality

The size ceiling is a fraction of *physical* RAM, not of free RAM. On unified
memory a model competes with every other process for one pool, so a ceiling
based on free memory would move every time something else opened.

On the certifying host — Apple M2, 8 GiB unified memory — the ceiling is 4.0
GiB, and the reading was:

| Model | Size | Eligibility |
|---|---|---|
| `qwen2.5:1.5b` | 0.92 GiB | eligible |
| `qwen2.5-coder:3b` | 1.8 GiB | eligible |
| `qwen3:4b` | 2.33 GiB | eligible |
| `qwen3:8b` | 4.87 GiB | resource_unsuitable_on_current_host |
| `gemma4:e2b` | 6.67 GiB | resource_unsuitable_on_current_host |

`resource_unsuitable_on_current_host` says the host could not load it. It says
nothing whatever about the model. The same model on a 32 GiB machine would be
eligible with no change to this repository, which is why the exclusion reason is
recorded in full rather than as a flag.

## 4. Nothing is silently skipped

A model that is installed appears in the inventory. A model that is eligible but
never measured appears in the qualification matrix as `EVALUATION_INCOMPLETE`
with the reason. A model excluded by the host appears as `RESOURCE_UNSUITABLE`.

A missing row would read as "nothing to report" when the truth is "never
measured", and those are not the same sentence.

## 5. Evidence

- `docs/evidence/m369_m376/MODEL_INVENTORY.json`
- `docs/evidence/m369_m376/RESOURCE_MEASUREMENTS.json`

## Limitations

- One reading of one host at one moment. Eligibility is not a property of a
  model.
- `peak_process_memory` is this process since start, not current usage.
- The one-model ceiling is schema-validated and operator-observed. No component
  in this package spawns a model process, so none enforces the ceiling at the
  operating-system level.
