# M361B runtime architecture and supply-chain compatibility

Assessment time: `2026-08-03T13:07:51Z`

Image result: `IMAGE_DIGEST_SET_PARTIAL`

Dependency result: `DEPENDENCY_PINNING_PARTIAL`

Architecture result: `ARM64_COMPATIBILITY_SUPPORTED_BY_MANIFESTS`

Runtime recommendation: `HOST_ARCHITECTURE_DECISION_PENDING`

No image was pulled, built, or executed. Public Docker Hub tag metadata and the
pinned upstream source tree were inspected read-only.

## Proposed image set

| Component | Upstream reference | Candidate immutable pin | Manifest architecture | Classification | Limitation |
| --- | --- | --- | --- | --- | --- |
| Twenty server and worker | `twentycrm/twenty:${TAG:-latest}` | `twentycrm/twenty@sha256:3c5845fb485b57688bb90a202918038c2d4ce3b868c0dad8df3cf79e51c91dd9` (tag observed as `v2.26.0`) | linux/amd64 and linux/arm64 | `MULTI_ARCH_WITH_ARM64`; `VERSION_RELATIONSHIP_UNPROVEN` | No official Git tag at `v2.26.0` was found, and this image cannot be mapped to pinned main SHA `37f1fe17...` |
| PostgreSQL | `postgres:16` | `postgres@sha256:33f923b05f64ca54ac4401c01126a6b92afe839a0aa0a52bc5aeb5cc958e5f20` (tag observed as `16.14`) | linux/amd64, linux/arm64, others | `MULTI_ARCH_WITH_ARM64`; `VERIFIED_DIGEST` | Migration compatibility remains unexecuted |
| Redis | production Compose uses `redis`; dev Compose uses `redis:7` | `redis@sha256:6372db89351b00ba0ddca437ff49ce2ed4beed8a961a27d8259060c9603c240d` (candidate `7.2.15`) | linux/amd64, linux/arm64, others | `MULTI_ARCH_WITH_ARM64`; `VERIFIED_DIGEST` | Exact 7.2 selection is safer than mutable `redis`, but has not been runtime-validated with Twenty |
| Node build base | Dockerfile pins `node:24.18.0-alpine3.23` | `node@sha256:595398b0081eacda8e1c4c5b97b76cd1020e4d58a8ebcb4843b9bca1e79e7436` | linux/amd64, linux/arm64, linux/s390x | `MULTI_ARCH_WITH_ARM64`; `VERIFIED_DIGEST` | Needed only for a future source build, not the proposed prebuilt runtime |
| TLS terminator/proxy | not selected | none | unknown | `UNKNOWN`; `DIGEST_NOT_FOUND` | Required only if the selected private host cannot provide approved private TLS termination itself |

The server and worker use the same Twenty image. No separate worker image is
required. PostgreSQL and Redis are separate required services. No proxy image is
selected because the runtime host and its private TLS mechanism are owner fields.

## Architecture matrix

| Runtime path | Evidence | Emulation | Risk | Recommendation |
| --- | --- | --- | --- | --- |
| Apple Silicon / private ARM64 host | All three candidate runtime manifests publish linux/arm64 children; Dockerfile uses `TARGETARCH` for architecture-specific assets | none indicated by manifests | Native Node modules, migrations, worker behavior, and browser automation were not executed | Technically eligible for a bounded future validation; do not claim runtime compatibility yet |
| Private AMD64 host | All candidate runtime manifests publish linux/amd64 children | none | Same unexecuted runtime/migration risks | Technically eligible and broadest conventional ecosystem path |
| AMD64 image on ARM64 host | not required by current manifests | would require emulation | avoidable memory and performance cost | Do not select unless a later manifest loses ARM64 support and owner separately approves it |
| Source build | pinned Node base supports ARM64 and amd64; Dockerfile is `TARGETARCH` aware | none expected | Alpine packages, `aws-cli`, S6 downloads, and other build inputs are not all immutable | Not reproducible enough to replace the prebuilt-image plan |

Manifest availability is not a successful-run claim. Browser dependencies are
not required inside the Twenty service image for the planned external SaathiOS
verification. Native extensions, migrations, server/worker coordination, backup,
and actual resource use remain future runtime checks.

## Dependency and license assessment

- Pinned upstream source: `37f1fe17ab48269384cffb774f82f096abe3863a`.
- Root package manager: `yarn@4.13.0`; Node engine: `^24.5.0`; `yarn.lock` exists.
- Twenty Dockerfile base digest is immutable, but source-build `apk` packages and
  downloaded S6/bootstrap assets are not a fully captured immutable dependency set.
- Twenty source is primarily AGPLv3 with the Twenty Application Exception;
  marked enterprise files have separate commercial terms and named SDK packages
  have their recorded MIT terms.
- PostgreSQL is under the PostgreSQL License. The selected Redis 7.2 line is
  recorded under its BSD-3-Clause source terms. Node.js is MIT-licensed, with
  bundled dependencies retaining their own licenses.
- An approved update requires a new manifest capture, license review, architecture
  check, and owner acceptance. Rollback means returning to the exact approved
  digest, never a tag.

Because the application image-to-source relationship and host TLS component are
not pinned, the digest set is partial. Because migration compatibility and all
source-build inputs are not immutable, dependency pinning is partial.
