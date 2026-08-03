# Twenty repository audit for SaathiOS

Audit date: 2026-08-03 (Asia/Kathmandu)

## Decision

`ISOLATED_SANDBOX_EVALUATION_ALLOWED_WITH_RUNTIME_BLOCKER`

The architecture and licence permit a separately deployed Twenty service linked
through published application interfaces. Installation and live validation are
blocked on this host because Docker/Compose are absent and the 8 GB Mac showed
heavy memory pressure. The upstream source was not modified.

## Audited source

- Path: `/Users/macbookpro/dev-toolkits/twenty`
- Remote: `https://github.com/twentyhq/twenty.git`
- Branch: `main`
- Commit: `37f1fe17ab48269384cffb774f82f096abe3863a`
- Commit time: `2026-08-03T11:49:08+02:00`
- Declared monorepo version: `2.27.0`
- Runtime manifest: Node `^24.5.0`, Yarn `4.13.0`
- Local Node: `26.4.0`; local Yarn/Corepack: unavailable

The clone is depth-one and exists only as an upstream audit copy.

## Licence boundary

The root licence says the repository is mostly AGPLv3, with a Twenty Application
Exception for works that interact only through published REST/GraphQL APIs,
webhooks, application manifests/configuration, logic functions, front components,
or published SDKs and do not incorporate or modify Twenty source.

The package manifests/license files identify `twenty-sdk`, `twenty-client-sdk`,
`create-twenty-app`, `twenty-shared`, `twenty-ui`, and apps under
`packages/twenty-apps` as MIT areas. The audit found 303 source files carrying
`/* @license Enterprise */` across server/front; those commercial-license areas
must not be copied or assumed available under AGPL/MIT.

SaathiOS therefore uses only a separately deployed service boundary. No Twenty
core, enterprise source, generated server code, or SDK source was copied into
SaathiOS. This is an engineering boundary report, not legal advice.

## Actual self-host architecture

The official `packages/twenty-docker/docker-compose.yml` defines:

- `twentycrm/twenty:${TAG:-latest}` server on container/host port 3000;
- a second image instance running `yarn worker:prod`;
- PostgreSQL 16 with a persistent database volume;
- Redis with `noeviction` policy;
- a persistent local-storage volume shared by server and worker;
- `/healthz` health checking for the server;
- automatic restart and startup database migrations (worker disables duplicates).

Local storage is the default; S3-compatible configuration is optional. The
official guide states a 2 GB minimum, but the full server+worker+database+Redis
stack plus Docker VM overhead competes with active SaathiOS/Next.js services.
On this 8 GB host, forcing it while memory is already compressed/swapping is not
accepted. Upstream clone disk usage was 470 MB; container-image and persistent
data impact remain unmeasured because no image was pulled.

## Interfaces and authentication

- Core records: REST `/rest/` and GraphQL `/graphql/`.
- Metadata/schema: REST `/rest/metadata/` and GraphQL `/metadata/`.
- Schemas are generated per workspace, so exact record contracts require a live
  synthetic workspace and its generated API documentation.
- API authentication uses bearer API keys which can inherit a Twenty role.
- OAuth 2.0 supports authorization-code + PKCE and client credentials, including
  RFC 7591 dynamic registration and a discovery endpoint.
- Webhooks cover create/update/delete for standard and custom records. Source code
  emits timestamp, signature, and nonce headers; HMAC-SHA256 signs
  `{timestamp}:{JSON payload}`.
- Custom objects/fields use stable universal identifiers via app definitions or
  the Metadata API. App manifests, roles, logic functions, and front components
  are supported extension surfaces.

No API key, OAuth client, user account, workspace, webhook, custom object, or app
was created during this mission. The adapter's endpoint shapes are fixtures based
on source documentation and are not live-contract certified.

## Operations

- Health: public guarded `GET /healthz`, confirmed in controller source and Compose.
- Migrations: server runs required migrations on startup; `upgrade:status` reports
  instance/workspace state.
- Backup: upstream documents `pg_dumpall`; restore uses `psql` into PostgreSQL.
- Upgrade: back up, stop Compose, change tag, restart; cross-version support begins
  at v1.23, with older instances upgraded incrementally.
- Secret storage: current upstream requires `ENCRYPTION_KEY` for new installs and
  encrypts OAuth tokens/application variables/signing keys/TOTP/config secrets.

These operational procedures were inspected, not executed.

## Threat and compatibility findings

- API keys and OAuth scopes can grant broad read/write access; a future milestone
  must use a role limited to read operations and a credential reference.
- Metadata endpoints can mutate schema and are not safe merely because they expose
  metadata; the initial adapter performs GET only.
- Webhooks are outbound from Twenty and need a reachable receiver in practice.
  No public endpoint is created here; a local fixture verifier only is implemented.
- Twenty's generated workspace schema makes static assumptions fragile; live schema
  discovery and validation are mandatory before enabling a transport.
- Enterprise row-level permission code exists. No entitlement or availability is
  assumed; SaathiOS tenant scope remains independently enforced.
- A published image digest and Apple Silicon runtime behavior remain unverified.
