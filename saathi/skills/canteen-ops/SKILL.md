---
name: canteen-ops
description: HCG canteen rules, staff, revenue targets, and daily ops patterns. Load when Ajay asks about canteen data, staff, sales, credit, or HCGMS.
triggers: [canteen, hcg, hcgms, sajana, yabesh, hasina, aayush, nishant, revenue, sales, credit, report, hygiene, checklist, npr, daily summary]
---

# Canteen Ops Skill — Hamro Chamena Griha (HCG)

## Location & context
- Sushma Koirala Memorial Hospital canteen, Kathmandu
- System: HCGMS (Next.js + Supabase PWA)
- Goal: run without Ajay once he goes abroad

## Revenue targets
- **Daily target:** NPR 30,000
- **Baseline actual:** ~NPR 22,000
- **Credit limit per account:** NPR 3,000
- Alert Ajay if daily sales < NPR 20,000 or any credit account > NPR 2,800

## Staff schedule
| Name | Role | Shift |
|------|------|-------|
| Sajana (Ajay's wife) | Counter + credit management | Day |
| Yabesh | Kitchen | Day |
| Hasina | Service | Day |
| Aayush | Service | Day |
| AjayG | Early duty | 5:30am |
| Nishant | Snacks + evening | Evening |

## Daily reporting checklist
Every staff member should submit:
- [ ] Opening stock count
- [ ] Sales figure for shift
- [ ] Credit transactions (who paid, who owes)
- [ ] Hygiene checklist (kitchen + counter)
- [ ] Incident notes (if any)

## Credit account rules
- Max NPR 3,000 per account
- Weekly settlement expected
- If account > NPR 2,500: alert Ajay + Sajana
- If account > NPR 3,000: stop credit, cash only

## Morning briefing format (7am)
1. Yesterday's total sales vs NPR 30,000 target
2. Any credit accounts over limit
3. Missing reports from previous day
4. Today's calendar / special events at hospital

## Evening summary format (9pm)
1. Today's total sales (amount + % of target)
2. Top items sold
3. Credit accounts updated
4. Staff attendance issues
5. Action needed by Ajay (if any)

## HCGMS data access
Use canteen tools: `canteen.query("sales_today")`, `canteen.query("credit_alerts")`, etc.
If Supabase not connected, tell Ajay honestly and ask him to check HCGMS directly.
