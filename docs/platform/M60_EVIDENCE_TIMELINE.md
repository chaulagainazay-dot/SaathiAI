# M60 — Evidence Timeline

Route: `/platform/evidence`. `buildEvidenceTimeline()` aggregates authorized
lifecycle events (mission created, approval request/decision, execution start,
attention event) chronologically with evidence states (Available/Invalid/…). Filter
by kind. Governed export uses the existing `GET /runtime/export` (role-gated via
`canExportEvidence`); the manifest (kind, record count, content hash, production_data)
is shown. Secret-bearing logs are never rendered.
