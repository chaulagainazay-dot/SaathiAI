# M52 Security Review

| Control | Result |
|---|---|
| Token-trusted user/org/workspace | enforced |
| Persisted session revalidation | enforced on every dispatch |
| Revoked/expired session | rejected |
| Missing/suspended membership | rejected |
| Stale role | rejected |
| Organization/workspace/project/mission isolation | enforced |
| Mission without project | rejected |
| Agent binding mismatch | rejected |
| Client identity/role/authority spoof fields | ignored |
| Manifest authority | code-owned; unknown fails closed |
| Approval org/workspace/tool binding | enforced |
| Optional approval project/mission binding | enforced when present |
| Approval expiry/revocation/rejection/replay | rejected |
| Approval single use | consumed before dispatch attempt |
| Platform lifecycle terminal immutability | enforced |
| Restart mutation replay | prohibited after recorded dispatch |
| Gateway sole registered-tool authority | enforced |
| Direct adapter/ToolExecutionService API calls | absent |
| Connector mutation | dry-run only |
| Financial execution | prohibited; adapter not invoked |
| Trading Guardian | unengaged, advisory-only |

## Audit data

Structured events cover request, accepted/rejected context, approval required or
accepted/rejected, queue/lifecycle, dispatch, gateway accept/deny,
cancellation, timeout, recovery, completion, and failure. Arguments and raw
tokens are not written to platform audit events. Gateway event payload bodies
are not persisted; only the bounded event name and execution identifier are
recorded.

## Accepted limitations

- Single-host SQLite coordination; no distributed guarantee.
- Runtime binding currently recognizes the built-in `platform-agent`; there is
  no external multi-agent binding administration API.
- Recovery never auto-replays a recorded dispatch, which can require manual
  reconciliation of an uncertain read or mutation.
- Existing non-platform subsystems remain separately governed and were not
  redesigned.
