# MILESTONE_CONTAINMENT_MATRIX

Legend: **IN** = tip SHA is ancestor of recommended baseline `e1738d7deec5`. **OUT** = not contained.

| Family | Branch / tip | Contained in recommended baseline? | Notes |
| --- | --- | --- | --- |
| master | `67efcb3cd5ca` | IN | UI foundation only relative to product tip |
| M47 UI/UX | saathios-ui-ux / master | IN | PR #2 merged |
| M48 | m48-agent-runtime-baseline | IN | |
| M49.1–4 | m49* | IN | Tool runtime / gateway |
| M50–M53 | m50…m53 | IN | Platform foundation + agent runtime + ops |
| M54–M61 | m54…m61 | IN | Spatial UI / workflows / persistence absorbed before m304 |
| M166–M303 TG | various milestone/m* | IN | Verified via m304 ancestry |
| M304–M311 | market observation | IN | |
| M312–M319 | connectivity governance | IN | |
| M320–M327 | provider contracts | IN | mock only |
| M328–M335 | production readiness | IN | |
| M336–M343 | private alpha readiness | IN | LOOP_STATE certified_with_limitations |
| UI recovery | fix/saathios-ui-recovery | IN | |
| Full E2E | fix/…-full-e2e… | IN | local tip ahead of origin; contained |
| Private-alpha excellence | improve/… | IN | voice settings surface |
| M344–M359 agentdev | m344 local tip | IN | |
| M369–M376 | local model qualification | IN | |
| M377–M385 | AgentHarness design | IN | |
| FM-C1/C2 | docs freeze/reconcile | IN | |
| FM-I1–I6.2 | harness implementation | IN | tip == recommended |
| M17 concurrency | fix/m17-… | **OUT** | only on m344-remote merge tip |
| M360 Twenty | evaluation/twenty-… | **OUT** | diverged from m312 |
| m344-remote merge tip | origin/m344-m351 | **OUT** (as tip) | reverse also false — diverged after m369 |

## Containment scores (how many mapped tips are ancestors of this tip)

Top: `fm-i6.2-memory` **55**, then fm-i6.2-ollama 54 … m344-remote 45, private-alpha 41, m336 38, m312 35.

## Unpublished predecessor problem

PRs #12–#14 and #18–#22 assume bases that are themselves not on `master`. GitHub “mergeable” does **not** mean the base is published. Integrating to master requires either stacking all unpublished bases or an authorized tip integration.
