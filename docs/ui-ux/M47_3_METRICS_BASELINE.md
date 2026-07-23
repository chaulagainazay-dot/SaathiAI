# M47.3 Metrics Baseline

**Date:** 2026-07-22  
**HEAD:** `2c9f8c5c8120311cc549b28b951610fe39b3a35d`

## Commands

```bash
rg -c 'style=\{\{' saathi-os --glob '!node_modules' -g '*.{jsx,js}' | awk -F: '{s+=$2} END {print s}'
# primitive usage: files outside ui.jsx importing each symbol
rg -c 'aria-|role=' saathi-os --glob '!node_modules' -g '*.{jsx,js,css}' | awk -F: '{s+=$2} END {print s}'
```

## Measured baseline

| Metric | Count |
|---|---|
| `style={{` sites | **1635** (matches M47.2 ending) |
| Files using M1 state/badges outside `ui.jsx` | **11** |
| LoadingState files | 4 |
| EmptyState files | 5 |
| ErrorState files | 4 |
| BlockedState files | 2 |
| StatusBadge files | 10 |
| AuthorityBadge files | 9 |
| RiskBadge files | 2 |
| EnvironmentBadge files | 3 |
| EvidenceBadge files | 1 |
| aria/role attribute hits | **96** |
| Frontend test files (`*.test.js`) | **2** |

## Target deltas (M47.3)

| Metric | Target |
|---|---|
| Inline styles | **&lt; 1600** preferred; net reduction minimum |
| Primitive adoption on Home/Approvals/Command/Missions/Projects/Monitoring | required |
| Test files | + attention + approvals + dialogs |
| Frontend lint | deterministic non-interactive command |
