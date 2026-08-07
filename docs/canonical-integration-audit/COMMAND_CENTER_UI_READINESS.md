# COMMAND_CENTER_UI_READINESS

**Strongest UI-containing tip:** recommended baseline (includes private-alpha excellence + UI recovery + M47 foundation).  
**UI app:** `saathi-os/` (Next-style app router).

## Surfaces inventory

| Surface | State |
| --- | --- |
| Application shell | Present (`Shell.jsx`) with module discovery/guards |
| Canonical navigation / module registry | Present (`lib/modules/registry.js`, guards, drift) |
| Home attention spine | Present (`lib/attention.js`) |
| Command center `/command` | Present (route inventory: IMPLEMENTED_AND_WORKING) |
| Chat | Present |
| Mission control / missions | Present (incl. mission voice subroutes) |
| Approvals | Route present; may show intentional availability gate |
| Agent operations | Agentdev console on m344+; `/agents` route present |
| Trading / investment UI | Present (trading lib, TG ops routes, paper portfolio screens in evidence) |
| Model/provider health | Partial (platform health, inference consoles, voice health) |
| Monitoring | Partial (control center facets, ops dashboards read-only) |
| Voice UI | Settings + docks + chat control (see voice inventory) |
| Mobile UI | `MobileSaathi`, `MobileMic`, quick sheets |
| Settings | General + `/settings/voice` |
| Legacy routes | Soft redirects / parity map M47.4; some intentional gates |

## Route truth (E2E inventory heritage)

From `docs/e2e-functional-audit/ROUTE_INVENTORY.json` (129 static routes):

- **123** IMPLEMENTED_AND_WORKING  
- **6** INTENTIONALLY_UNAVAILABLE (explicit gates), e.g. `/`, `/approvals`, `/ceo`, `/control` in that snapshot  

Note: inventory was captured on private-alpha chain; still contained in baseline.

## Completeness assessment

| Question | Answer |
| --- | --- |
| Most complete UI branch? | **Recommended baseline** (superset of UI recovery + private-alpha voice settings) |
| Backend capabilities without UI? | Harness/local-model ops, some agentdev evidence consoles, deep TG research lab surfaces may be API-heavy |
| Duplicate/stale routes? | Legacy `/voice` enrollment vs `/settings/voice`; multiple control entry points historically |
| Operational state truthful? | UI recovery work focused on truthful bootstrap phases for module routes |
| Authority / approval / evidence visible? | Partially — approvals, attention spine, evidence docs exist; not a single unified “authority timeline” product |
| Voice state synced with tool actions? | Partial — interruption repair improved output/mic sync; tool governance visibility incomplete |

## Next bounded UI milestone (no redesign)

**UI-NEXT-1 — Command composition, not redesign:**  
Wire existing read models into `/command` and Home attention: (1) authority flags strip (live trading false, providers disabled), (2) approval queue, (3) agent/harness session health, (4) voice session state, (5) TG paper portfolio snapshot. Remove or clearly mark legacy enrollment route. No visual redesign system rewrite.
