# M20.8 Status Determination

**Date:** 2026-07-16  
**Determined during:** M20 finalization intake (pre-M20.9)  
**Repository HEAD at determination:** `947d267`

## Classification

```text
INTENTIONALLY_SKIPPED
```

## Evidence

| Source | Finding |
|--------|---------|
| Git history | No commit titled M20.8; no `docs/M20_8_*`; no `test_m20_8_*` |
| Roadmap | Series plan lists M20.8 as optional; not marked completed |
| Master loop | Status **planned** |
| Caller set | Only M20.3 selected callers: `cheap_ask`, `prose_clean` |
| Handoff after M20.7 | Next listed as M20.8 **or** operator live cert — operator chose finalization path |

## Reason for skip

M20.6 live local certification is **environment-blocked**. Expanding callers (M20.8) without a certified live local model adds rollout surface without live value. Series plan allows certifying the **implemented** caller set and proceeding to M20.9.

## What is certified instead

* Implemented opt-in callers: **exactly two** (`cheap_ask`, `prose_clean`) from M20.3  
* Default rollout: **legacy**  
* No additional callers adopted in finalization  

## Explicit non-claims

* M20.8 is **not** COMPLETE  
* No silent reclassification as done  
* Chat / voice / IELTS / directors / `_llm_helper` / TG remain non-adopted  

## Residual path (future)

A future series (M21+) may reopen bounded shadow adoption of 1–2 low-risk callers **after** live model certification or under explicit legacy/shadow-only policy.
