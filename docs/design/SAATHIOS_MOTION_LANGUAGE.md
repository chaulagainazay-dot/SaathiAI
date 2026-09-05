# SAATHIOS_MOTION_LANGUAGE

All motion optional under `prefers-reduced-motion: reduce` → **instant state swap**.

| State | Purpose | Duration | Easing | Reduced motion |
| --- | --- | --- | --- | --- |
| LISTENING | Voice active cue | 1.2–1.8s loop | ease-in-out | static badge |
| THINKING | System working | 0.9–1.4s loop | linear opacity | spinner off / text only |
| SPEAKING | TTS output | 0.8–1.2s loop | ease-in-out | static |
| MISSION_START | Context enter | 180–280ms | ease-out | none |
| MISSION_COMPLETE | Closure | 200–300ms | ease-out | none |
| APPROVAL_REQUIRED | Attention | 400ms fade | ease-out | badge only |
| RISK_WARNING | Soft limit | 250ms | ease-out | color+text |
| RISK_BLOCK | Hard limit | 200ms | ease-out | color+text, no shake |
| SYSTEM_DEGRADED | Health | 300ms | ease-out | badge |
| CONTEXT_SWITCH | Mode change | 150–220ms | ease-in-out | instant |

## Forbidden

- Screen shake for money
- Infinite particle fields
- GSAP on buttons/forms
- Three.js ambient scenes in Command
