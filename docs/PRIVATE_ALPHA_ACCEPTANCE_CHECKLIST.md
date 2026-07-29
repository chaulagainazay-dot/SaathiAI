**Production authorized: false.** Local-only private alpha.

# Private Alpha Acceptance Checklist

- [x] Release manifest with production_authorized=false
- [x] Compatibility matrix (primary machine class only)
- [x] Prepare / doctor / init (idempotent, no secrets)
- [x] Lifecycle via saathi-local (localhost, ownership-safe)
- [x] Versioned config + migration + rollback
- [x] Local upgrade fixtures only (no remote auto-update)
- [x] Full-system backup integrity
- [x] Restore dry-run + isolated restore
- [x] Destructive restore approval-gated
- [x] DR drill passed
- [x] Automations disabled by default
- [x] Bounded execution via Mission Runtime path markers + PlanValidator + Gateway + Approval
- [x] No self-approval / shell / gateway bypass
- [x] Synthetic operator validation (HCG/IELTS/search/Yeti)
- [x] Support bundle privacy-safe
- [x] Incident playbooks
- [x] Certification gate
- [ ] Browser full E2E (run `npm run cert:m165` when services available)
- [x] Production **not** authorized

## Operator sign-off (human)

- [ ] Owner completed first-run on machine
- [ ] Backup destination confirmed
- [ ] Sample HCG shift exercised
- [ ] Sample IELTS practice exercised
- [ ] Support bundle exported and inspected
