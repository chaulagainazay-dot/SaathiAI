# PERFORMANCE_BUDGET

| Budget | Target |
| --- | --- |
| Design-lab JS | no Three.js, no GSAP runtime |
| Ambient animation | CSS only, optional, reduced-motion off |
| Command production | no new animation deps |
| 8 GB host | prototype must not start GPU-heavy loops |
| Voice path | no animation on critical STT path |

Permanent GPU ambient motion: **forbidden**.

