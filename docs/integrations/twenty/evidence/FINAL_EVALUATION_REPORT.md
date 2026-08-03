# Twenty CRM evaluation — final report

## Terminal verdict

`TWENTY_SETUP_BLOCKED_BY_RESOURCE_CONSTRAINTS`

An isolated sandbox configuration and fixture-only read boundary are prepared,
but no Twenty runtime was installed or started. Docker/Compose are absent and the
8 GB host exhibited high compression/swap pressure. Therefore this result is not
`TWENTY_SANDBOX_READY_NO_SAATHIOS_INTEGRATION` and not
`TWENTY_READ_ONLY_INTEGRATION_READY_WITH_LIMITATIONS`.

## Environment and isolation

- Original SaathiOS: `/Users/macbookpro/SaathiAI`, branch
  `milestone/m312-m319-connectivity-governance`, SHA
  `6639ca730ece11bce160a55a237fcaff8df3058c`.
- Isolated worktree: `/Users/macbookpro/SaathiAI-twenty-readonly`, branch
  `evaluation/twenty-readonly-sandbox`, starting SHA above.
- Twenty audit clone: `/Users/macbookpro/dev-toolkits/twenty`, `main`, SHA
  `37f1fe17ab48269384cffb774f82f096abe3863a`.
- Sandbox config: `/Users/macbookpro/dev-toolkits/twenty-saathios-sandbox`.
- Runtime: Node 26.4.0, npm 11.17.0, pnpm 11.5.0; Yarn/Corepack unavailable.
- Docker/Compose: not installed. PostgreSQL/Redis processes: not detected.
- Existing ports preserved: SaathiOS/Next.js on 3000, 8765, and 8766. Planned
  Twenty port 3020 was free and never bound.

Twenty remains outside SaathiOS. No core or enterprise source was copied. The
upstream clone is clean and unmodified. The original dirty SaathiOS worktree was
not staged, reset, stashed, cleaned, or overwritten.

## Delivered artifacts

The external sandbox includes placeholder-only environment configuration, a
localhost/internal-network Compose topology, fixed prefixed names, guarded
start/stop/status/log/reset scripts, a synthetic-data policy/model, operator
instructions, and machine-readable audit evidence. No `.env`, generated secret,
container, image, network, volume, database, dump, or log was created.

SaathiOS includes a source-inspected but live-unvalidated read contract:

- `TwentyConfig`, request/response/page/scope/status/health contracts;
- injected `TwentyTransport` protocol and deterministic `FixtureTransport`;
- list/retrieve for Company, Person, Opportunity, and Task fixtures;
- metadata/schema GET contracts;
- canonical `ConnectorManifest` composition, OFF/SHADOW and READ only;
- scope/provenance mapping and fail-closed error normalization;
- HMAC/timestamp/replay/allowlist/size/redaction webhook verifier;
- explicit write rejection and no direct webhook execution.

There is no concrete HTTP transport and no raw secret resolution. The package
cannot connect to Twenty on its own.

## Validation

- Focused adapter/webhook: 19 passed, 0 failed (final rerun 0.11 s).
- Existing connector governance: 315 passed, 0 failed (17.74 s).
- Full backend: 5,785 passed, 1 skipped, 9 failed (1,007.09 s). Failures were
  outside the Twenty package and tied to isolated-worktree prerequisites/live
  browser/private-alpha/release-readiness gates. They were not changed to obtain
  a pass.
- Python compile, shell syntax, JSON syntax, static YAML parse, diff check,
  no-network-import scan, and targeted secret scan: pass.
- Container/health/UI/login/API/GraphQL/OAuth/webhook-delivery/custom-object/
  persistence/backup/restore/runtime memory/disk validation: not run.
- Upstream clone footprint: about 468 MB; sandbox config: about 48 KB; image and
  persistent data footprints are unknown because no pull occurred.

The full-suite run generated changes in five pre-existing evidence files inside
the new clean worktree. Those exact test artifacts were restored to the starting
commit before the integration commit. No user work was discarded.

## Safety and authority

No production, customer, hospital, supplier, patient, employee, or financial data
was used. No real credential, API key, OAuth client, account, email provider,
public endpoint, DNS, unrestricted outbound action, CRM write, delete, autonomous
write authority, Trading Guardian change, approval change, Execution Gateway
change, deployment, publication, or push occurred.

## Limitations and next milestone

Twenty image availability/digest, Apple Silicon compatibility, startup health,
local setup/login, exact generated workspace schemas, API authentication, role
scoping, pagination semantics, webhook delivery, custom object installation,
migrations, restart persistence, backup/restore, upgrade, and resource consumption
remain unverified.

Recommended next milestone:
`TWENTY_READ_ONLY_PROVIDER_CONNECTIVITY_AND_SCHEMA_VALIDATION`. It should begin
only after the owner approves a container runtime or private development host and
should validate exact GET contracts against synthetic data while preserving the
existing registry, credential-reference, tenant, audit, and execution boundaries.
