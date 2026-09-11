# ACCESSIBILITY_AUTOMATION_REPORT

Tool: axe-core WCAG 2A/2AA scoped to `.dl-root`.

| Page | Critical | Serious | Total |
| --- | ---: | ---: | ---: |
| command-desktop-healthy | 0 | 0 | 0 |
| command-recon-required | 0 | 0 | 0 |
| investments-desktop | 0 | 0 | 0 |

## Gate

```text
0 CRITICAL
0 SERIOUS
```

## Notes

- Production shell contrast (#6c7a96 on #182031) is **out of design-lab scope**; shell hidden via `body:has(.dl-root)` during lab view.
- Root `meta viewport maximum-scale=1` remains app-wide moderate issue (not design-lab).
- Full SR manual pass not completed (limitation).

