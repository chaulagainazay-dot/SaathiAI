# M17 — Universal Computer Agent (Spec)
Constitution v1.0. SaathiOS operates desktop apps + browsers by registering
computer operations (vision/desktop/browser_agent) as M15 connector tools, so
every action flows through the SAME ExecutionEngine → ExecutionGateway → risk/
approval → evidence path. NO new execution engine, NO app-specific code. Canonical
UIElement perception model; provider abstraction (Playwright/CDP/accessibility/
OCR/vision) deterministic by default; live desktop control ENVIRONMENT-BLOCKED
(no installed+enabled provider here) and honestly reported. Mutating ops run a
post-action visual verification (never assume success); destructive ops
(delete/purchase/send/deploy) are risk-gated (L3 approval / L4 manual-only).
Replays sanitized (never passwords/OTP/secrets). See traceability.json.
