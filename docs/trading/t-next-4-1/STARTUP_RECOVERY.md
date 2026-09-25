# Startup Recovery

Service construction scans submission attempts, ambiguous OMS/intents, and
pending canonical-ledger posts. Any finding produces
`STARTUP_RECONCILIATION_REQUIRED`; submissions remain blocked until explicit
reconciliation is recorded.
