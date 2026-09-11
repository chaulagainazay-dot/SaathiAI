# Model Resource Limits

**Milestone:** M370
**Modules:** `saathi/agentdev/model_inventory.py` · `saathi/agentdev/host_probe.py`
**Command:** `qualification baseline`
**Classification:** `schema_validated`

Evaluating local models on a laptop can make the laptop unusable. These are the
limits that stop that, and the honest description of how strongly each is
enforced.

## 1. The thresholds

| Threshold | Value on the certifying host | What it guards |
|---|---|---|
| `max_model_size_fraction_of_ram` | 0.5 (4.0 GiB of 8.0 GiB) | A model larger than half of physical memory is not loaded |
| `min_available_memory_mib` | 1024.0 | Reclaimable memory floor |
| `min_free_memory_percent` | 20 | Proportional floor, for when the absolute one is not enough |
| `min_free_swap_mib` | 512.0 | Swap headroom |
| `min_free_disk_gib` | 10.0 | Disk headroom |
| `max_resident_models` | 1 | One model at a time |
| `max_concurrent_evaluations` | 1 | One evaluation at a time |

The rationale is recorded with the numbers: Apple M2, 8 GiB unified memory,
single SSD. Unified memory means a model competes with every other process for
one pool, which is why the size ceiling is a fraction of *physical* RAM rather
than of free RAM — a ceiling based on free memory would move every time
something else opened a window.

## 2. When they are checked

Before every model is loaded, and again after it is unloaded. Both readings go
into `RESOURCE_MEASUREMENTS.json` with the full baseline behind them, so the
cost of a model is visible rather than inferred.

A breach before loading aborts that model. It is recorded as
`EVALUATION_INCOMPLETE` with the breach text, never dropped and never recorded
as a behavioural result.

A breach after unloading is recorded and does not retroactively invalidate the
run that produced it. It is a measurement of what the run cost.

## 3. What "enforced" honestly means here

| Control | Strength |
|---|---|
| Size ceiling | `technically_enforced` — an oversized model is never passed to an adapter |
| Pre-load resource check | `technically_enforced` — the run aborts |
| One resident model | `schema_validated` and operator-observed |
| One concurrent evaluation | `schema_validated` and operator-observed |

The last two matter to state precisely. No component in this package spawns a
model process, so no component can enforce a process ceiling at the operating
system level. The check reads `/api/ps` and refuses to proceed if another model
is resident. An operator who loads a second model in another terminal is not
prevented by this code — they are detected by it on the next check.

Claiming otherwise would be exactly the kind of overstatement the M369
terminology pin exists to catch.

## 4. An abort is not a verdict on the model

During the first M369–M376 run, `qwen2.5-coder:3b` tripped the one-resident-model
ceiling before loading — a previous model was still resident — and was recorded
as `EVALUATION_INCOMPLETE`. On a later run with the host quiet it loaded and was
evaluated in full.

Nothing about the model changed between those two runs. The machine did. That is
the whole reason `EVALUATION_INCOMPLETE` exists as a status separate from
`NOT_QUALIFIED`.

## 5. What this does not do

- It does not download a model. There is no `/api/pull` in the package.
- It does not delete a model. There is no `/api/delete` in the package.
- It does not kill a process. The only lifecycle verb used is `keep_alive: 0`,
  which asks the provider to drop a resident model.
- It does not change any system setting to make room.

## Evidence

- `docs/evidence/m369_m376/RESOURCE_MEASUREMENTS.json`
- `thresholds` and `baseline` in `docs/evidence/m369_m376/MODEL_INVENTORY.json`

## Limitations

- Every number describes one host at one moment.
- `peak_process_memory` is this process since start, not current usage;
  `total_memory` is physical, not available.
- A probe that fails returns `available: false` with a reason, so a missing
  measurement is visible rather than defaulted.
