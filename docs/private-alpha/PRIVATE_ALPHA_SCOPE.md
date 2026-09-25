# SaathiOS Private Alpha — Scope

**Release** `0.1.0-private-alpha.1` · **Channel** `private-alpha` · **Maximum state**
`PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY`

Private alpha is **not** a public launch. It is a bounded, local, invite-only
evaluation of SaathiOS on a single machine. This document is the contract: what
is in scope, who may use it, and what it explicitly will not do. The
machine-readable form is
[`m336_m343_evidence/M338_PRIVATE_ALPHA_CONTRACT.json`](m336_m343_evidence/M338_PRIVATE_ALPHA_CONTRACT.json).

---

## 1. Audience — invite only

| Who | How they get in | What they can do |
| --- | --- | --- |
| **Owner** | Bootstrapped once at first run. One per installation. | Everything an operator can do, plus owner-required approvals and invitations. |
| **Approved internal operator** | Owner provisions them into an organization and workspace. | Create and run allowed missions; request approvals. |
| **Invited tester** | Owner issues a single-use invite bound to an email. Scoped to one organization and one workspace. | Usually viewer or operator; exactly what their role grants and nothing more. |

**Nobody else.** There is no anonymous access and no public sign-up.
`PUBLIC_REGISTRATION_AUTHORIZED=false`. Enabling registration later requires a
separate, explicitly authorized milestone — it is never a side effect of this
one, and automation may never flip it.

## 2. Environment

- **Single host, single machine.** No multi-host, no device sync.
- **Localhost only.** Backend on `127.0.0.1:8765`, frontend on `localhost:3000`.
  No `0.0.0.0` bind, no tunnel, no DNS record, no public deployment.
- **Supported host:** macOS on arm64, Python 3.11/3.12, Node ≥ 18, 5 GB free
  disk, 8 GB memory recommended.
- **Your data stays on your machine.** `data/platform/platform.db` and
  `data/alpha/*` are local files. Nothing is uploaded. There is no cloud backup,
  no cloud monitoring, and no external telemetry.

## 3. What the system will do

The certified private-alpha journey, end to end:

1. Operator starts SaathiOS locally and opens `http://localhost:3000`.
2. A user is invited or provisioned by the owner.
3. The user authenticates. Invalid credentials fail closed.
4. Organization and workspace context is established and bound to the session.
5. The user enters an existing project or creates an allowed one.
6. The user creates a mission.
7. The mission is validated.
8. The required approval is requested.
9. **A human** approves or rejects. The LLM never approves.
10. The approved mission executes through local deterministic tools and mock
    providers only.
11. Progress is observable while it runs.
12. Output and evidence are recorded.
13. The mission can be cancelled.
14. A failure can be diagnosed.
15. A session can be revoked.
16. The audit trail can be inspected.
17. Backup and recovery evidence can be generated.
18. The user signs out.

Certification evidence:
[`M339_PRIVATE_ALPHA_E2E_JOURNEY.json`](m336_m343_evidence/M339_PRIVATE_ALPHA_E2E_JOURNEY.json).

## 4. What the system will **not** do

- No public sign-up, no public production deployment.
- No real-money operations. No broker or exchange connection. No live trading.
  No paper execution through an external provider.
- No real trading, broker or paid-provider credentials are requested, accepted
  or stored. No account, balance or position is ever read.
- No order is submitted, modified or cancelled.
- No automatic approval, and no self-approval where maker-checker applies.
- No unrestricted filesystem access, network access, or tool execution. Every
  tool runs through the ExecutionGateway.
- No claim of general autonomy without limits.
- No guaranteed uptime or SLA. No email, SMS or push alerting.
- No public application marketplace. No paid AI provider activation at first run.

### Authority locks

Every one of these is `false` and is asserted by the test suite, the browser
certification and the security scan:

```
REAL_CONNECTIVITY_AUTHORIZED       BROKER_CONNECTIVITY_AUTHORIZED
CREDENTIAL_PROVISIONING_AUTHORIZED CREDENTIAL_VALIDATION_AUTHORIZED
OAUTH_AUTHORIZED                   ACCOUNT_ACCESS_AUTHORIZED
BALANCE_READ_AUTHORIZED            POSITION_READ_AUTHORIZED
ORDER_SUBMISSION_AUTHORIZED        ORDER_EXECUTION_AUTHORIZED
CANARY_ACTIVATION_AUTHORIZED       LIVE_TRADING_AUTHORIZED
AUTOMATED_INVESTMENT_AUTHORITY     PUBLIC_PRODUCTION_AUTHORIZED
PUBLIC_REGISTRATION_AUTHORIZED
```

## 5. What the assistant may and may not do

**May:** guide onboarding, explain permissions, draft missions, explain why an
approval is needed, summarise progress, explain failures, prepare diagnostic
summaries and release checklists, draft incident summaries.

**May not:** invite users, approve users, grant roles, approve its own missions,
bypass approvals, change workspace scope, restore revoked sessions, mark owner
review complete, deploy, publish, connect providers, access accounts, execute
orders, or authorize live trading.

## 6. Interface disclosure

The interface must state plainly that this is a private alpha, must show its
limitations, and must never present a control that does not exist. There is no
public-registration control, no broker-connectivity control, no credential
input, no account access, no order-execution control and no live-trading
control.

Platform status wording describes **local platform health only**. It must never
read as broker connectivity, live market access, account connection, execution
readiness or live trading. See
[`M340_PRIVATE_ALPHA_UX_READINESS.json`](m336_m343_evidence/M340_PRIVATE_ALPHA_UX_READINESS.json).

## 7. Release governance

A private-alpha release is **not automatic**. It requires:

- a passing release gate,
- a passing full backend and frontend suite,
- browser certification against real Chromium,
- clean-clone certification,
- the release, rollback, incident and tester-support runbooks, and
- **explicit human owner review**, which automation may never mark as complete.

`OWNER_REVIEW_REQUIRED` · `PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC` ·
`PUBLIC_PRODUCTION_NOT_AUTHORIZED`

---

**Private-alpha readiness does not authorize public production deployment.**
