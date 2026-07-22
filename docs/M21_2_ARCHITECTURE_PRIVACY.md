# M21.2 — Architecture and Privacy

## Target flow

```text
caller → InferenceRequest → contract validation → caller policy
→ capability filter → availability → cost/privacy
→ kill + circuit → deterministic provider decision
→ ModelRouter → provider attempt → typed failure
→ retry/failover decision → privacy-safe evidence
```

## Authorities preserved

* **ModelRouter** — model selection (not replaced)
* **ExecutionGateway / governed path** — execution
* **provider_policy** — extended, not duplicated as second registry
* **No second inference gateway**

## Privacy

Sensitivity: public | internal | confidential | sensitive (+ restricted label in decision mapping).

Rules:

* local_only cannot select cloud
* confidential/sensitive/restricted cannot cloud-process
* unknown privacy → fail closed via mismatch
* failover cannot weaken privacy
* telemetry: no raw prompt/output/credentials
* production_certified remains **false**

## Trading Guardian

UNCHANGED / UNENGAGED / LIVE TRADING NOT AUTHORIZED
