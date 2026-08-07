**Production authorized: false.** Local-only private alpha.

# Private Alpha Security

## Posture

- Localhost-only binds
- Production not authorized
- Public exposure not authorized
- Fail-closed process ownership
- Secret-shaped config rejection
- Support-bundle privacy scan
- Automations cannot approve themselves
- ExecutionGateway / PlanValidator / Approval Center not bypassable by automations
- Trading Guardian unchanged

## Explicitly tested classes

Anonymous/invalid/revoked sessions (existing platform tests), viewer mutation
denials, cross-tenant isolation, approval and gateway bypass attempts,
automation self-approval, shell/public-network actions, stale PID ownership,
backup corruption/wrong-version, support-bundle secret leak, public listener
regression.

## Operator duties

- Keep services on 127.0.0.1
- Own backups
- Do not paste secrets into config
- Do not enable public tunnels for private alpha
