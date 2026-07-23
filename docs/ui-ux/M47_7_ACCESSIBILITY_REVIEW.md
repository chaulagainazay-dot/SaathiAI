# M47.7 — Accessibility Review

**Date:** 2026-07-23  
**Scope:** high-traffic shell + modified Chat/Copilot surfaces  
**Claim:** **not** full WCAG certification

## Automated / harness checks

| Check | Result |
|---|---|
| `main` landmark present | ✅ |
| Page-level heading (`h1` count ≥ 1 on Home) | ✅ (sample: 2) |
| Unlabeled icon buttons (empty name + no aria-label) | ✅ 0 on Home sample |
| Keyboard: ⌘K, Esc, `]`, g-h/c/p/m/a | ✅ |
| Copilot close control `aria-label="Close Ask Saathi"` | ✅ (source) |
| Stop control `aria-label="Stop streaming"` | ✅ (source) |
| ConfirmDialog on Approvals (M47.3 safety tests) | ✅ unit |

## Focus / dismiss

| Behavior | Result |
|---|---|
| Esc closes command palette | ✅ |
| Esc closes Copilot | ✅ |
| Focus enters close control when Copilot opens | ✅ (source `useEffect`) |
| Dialog focus return | covered by unit safety; not re-audited full AT suite |

## Mobile

| Check | Result |
|---|---|
| Phone: mobile tabs visible, sidebar hidden | ✅ responsive gate |
| Desktop: sidebar visible | ✅ |

## Verdict

```text
PASS_WITH_LIMITATIONS
```

### Limitations

- No axe-core / full WCAG 2.2 AA run.
- Color contrast not instrumented.
- Screen-reader full walkthrough not performed.
- Nested interactive controls not exhaustively scanned beyond Home sample.
