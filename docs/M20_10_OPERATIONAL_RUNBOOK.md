# M20 Operational Runbook (Canonical)

## Purpose

Operate the M20 **pilot** engineering + inference platform safely on a development host.

**Not production.** Defaults off. Live local model may be unavailable.

---

## 1. Daily status

```bash
cd /Users/macbookpro/SaathiAI
python -m saathi.m20_console status
python -m saathi.m20_console domains
python -m saathi.engineering status
python -m saathi.inference.certification discover
```

Interpret:

* `posture: degraded` with `no_installed_local_models` / `memory_pressure` is expected on 8 GB without Ollama  
* `domains_isolated.merged_store: false` must remain true  
* `trading_guardian.engaged: false` must remain true  

---

## 2. Flags

```bash
python -m saathi.m20_console flags
python -m saathi.m20_console disable
```

| Area | Default |
|------|---------|
| Engineering orch/launch/writes/commits/pushes | **off** |
| Inference + gateway | **off** |
| Caller rollout | **legacy** |
| Cloud fallback | **off** |

---

## 3. Engineering sessions (read-only pilot)

```bash
# Only after intentional enable of SAATHI_ENG_ORCH_ENABLED + LAUNCH
python -m saathi.engineering backlog
python -m saathi.engineering select
python -m saathi.engineering control-center
python -m saathi.engineering approve-readonly ...   # when using claude_code
python -m saathi.engineering launch <item> --adapter mock
python -m saathi.engineering ledger
python -m saathi.engineering recover --dry-run
python -m saathi.engineering integrity
```

Never enable writes/commits/pushes for unattended loops.

---

## 4. Inference / certification

```bash
python -m saathi.inference.certification discover
python -m saathi.inference.certification run
```

* **No automatic model download**  
* COMPLETE live requires installed Ollama + ≤3B model + memory headroom  
* Callers stay legacy unless operator sets `SAATHI_INF_ROLLOUT_*` **and** enables inference flags  

---

## 5. Emergency disable

```bash
unset SAATHI_ENG_ORCH_ENABLED SAATHI_ENG_ORCH_LAUNCH \
      SAATHI_ENG_ORCH_WRITES SAATHI_ENG_ORCH_COMMITS SAATHI_ENG_ORCH_PUSHES
unset SAATHI_INFERENCE_ENABLED SAATHI_INFERENCE_GATEWAY_ENABLED \
      SAATHI_ALLOW_CLOUD_FALLBACK \
      SAATHI_INF_ROLLOUT SAATHI_INF_ROLLOUT_CHEAP_ASK SAATHI_INF_ROLLOUT_PROSE_CLEAN
python -m saathi.engineering stop <session_id> --force   # if any
```

---

## 6. Recovery

```bash
python -m saathi.engineering recover --dry-run
python -m saathi.engineering recover
python -m saathi.engineering resume-plan <session_id>
```

Resume plans **never** auto-launch agents.

---

## 7. Recertify after host change

See `docs/M20_10_CLOSURE.md` §6.

---

## 8. Prohibited

Merge/deploy/tag/force-push · auto model pull · cloud cert · TG use via M20 · global chat switch · secret logging of prompts  
