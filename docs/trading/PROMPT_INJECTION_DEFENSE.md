# M62.3 — Prompt-Injection Defense

Every research document is untrusted data. Source text can never override system
instructions, platform policy, tool permissions, tenant boundaries, approval rules, or
execution authority. `analysis.detect_injection` flags HIGH-risk patterns (ignore
instructions / execute trade / place order / approve request / reveal-secret / send
credentials / change policy) → InjectionState.BLOCKED; softer patterns → SUSPECTED.
A BLOCKED source is quality PROMPT_INJECTION_SUSPECTED, is audited as rejected, and is
NEVER extracted from — so injected instructions cannot become claims, choose tools, or
trigger execution. Suspicious content is preserved as evidence but marked. Adversarial
fixture: INJECTION_SOURCE.
