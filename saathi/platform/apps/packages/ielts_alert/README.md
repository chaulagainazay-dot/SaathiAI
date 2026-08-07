# IELTSAlert

First-party IELTS preparation and exam-readiness application for SaathiOS.

Runs through the Universal Application Runtime (`saathi.ielts_alert`).

## Product surface

- Learner profile & Academic / General Training goals
- Diagnostic assessment
- Personalized study plans (deterministic validation)
- Speaking / Writing / Reading / Listening practice
- Mock tests
- Exam readiness dashboard
- Yeti grounded coaching (read-only)
- Backup / restore (restore approval-gated)

## Scoring posture

Local deterministic heuristics and fixture answer keys only.

- Estimates are **not** official IELTS scores
- Rubric and scoring versions preserved
- Text-only speaking does **not** claim acoustic pronunciation analysis
- No live Gemini / OpenAI / Firebase in this package

## UI

- Product: `/apps/ielts`
- Classic workspace: `/ielts`
