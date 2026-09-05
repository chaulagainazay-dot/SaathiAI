# MOTION_TECH_DECISION — UI-NEXT-3.1

## Primary

```text
CSS_SUFFICIENT
```

Canonical tokens: `saathi-os/styles/motion-tokens.css`  
Applied via production `/command` CSS (`command-hybrid.css`).

## Runtime libraries

| Library | Decision | Reason |
| --- | --- | --- |
| CSS / design tokens | **INTEGRATE** | All voice, risk, mode, proposal, evidence emphasis |
| Web Animations API | **NOT_REQUIRED** | No cancelable multi-step choreography beyond CSS |
| GSAP | **GSAP_RUNTIME_DEFERRED** | No multi-panel timeline choreography needed at ship |
| Lottie | **LOTTIE_RUNTIME_DEFERRED** | No high-quality local Saathi/Yeti state asset |
| Three.js | **THREE_JS_DEFERRED** | Forbidden on Command; no WebGL dashboard |
| framer-motion | **NOT ADDED to /command** | Present as app dep for other surfaces; not used here |

## Acceptable future GSAP triggers

Only if proven CSS-insufficient:

- multi-panel synchronized evidence/mission timeline reverse scrub
- complex cancelable coordinated transitions across 3+ panels

Until then GSAP must not enter the production `/command` path.
