# AUTHORITY_AUDIT — UI-NEXT-3.1

Confirmed for Production Hybrid Command motion work:

```text
ZERO_LIVE_TRADING_AUTHORITY
ZERO_FRONTEND_LEDGER_AUTHORITY
ZERO_FRONTEND_RISK_AUTHORITY
ZERO_FRONTEND_CONSTRUCTION_AUTHORITY
ZERO_VOICE_FINANCIAL_AUTHORIZATION
ZERO_AUTO_APPROVAL
ZERO_TG_WEAKENING
ZERO_EG_BYPASS
```

## Evidence

- Motion is presentation-only (CSS + pure helpers in `command-motion.js`)
- Performance panel is T-NEXT-4 read-contract pass-through
- Proposal lifecycle never green-executes; APPROVED remains warn attention
- Voice is consumer/sim of VoiceSession vocabulary — no second audio owner
- Fixtures require explicit `?fixture=` query; production default non-demo
- No TG / EG / ledger write paths introduced

## Explicit non-actions

- Did not modify or merge PR #43
- Did not add GSAP / Lottie / Three.js runtime
- Did not invent frontend financial calculations
- Did not create new VoiceSession states
