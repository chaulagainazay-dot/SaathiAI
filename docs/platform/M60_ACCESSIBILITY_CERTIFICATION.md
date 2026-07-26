# M60 — Accessibility Automation

Verdict: **ACCESSIBILITY_AUTOMATION_PASSED_WITH_LIMITATIONS**

axe-core run (production cert) across onboarding, mission creation, mission plan,
approval preparation, action queue, evidence.

- **Critical violations: 0** (hard gate `accessibility_no_critical` PASS).
- **Serious violations: 6**, all pre-existing global app-shell chrome (TopBar
  "Local"/"Alerts" glyph contrast) inherited from M58/M59 — none on M60 surfaces.

Keyboard: accessible `WorkflowStepper` (step buttons, `aria-current="step"`),
labelled form fields, visible focus, Escape-closable palette/drawer, reduced-motion
support, status not by colour alone (`StatusPulse` + text). Onboarding, mission
creation, and approval preparation are keyboard-operable.

Limitation: automated axe checks are not a full WCAG audit.
