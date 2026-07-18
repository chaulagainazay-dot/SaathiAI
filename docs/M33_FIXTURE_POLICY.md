# M33 — External Fixture Policy

**Milestone:** M33 — Official Read-Only External Provider Pilot
**Scope:** governs every external-response fixture committed to the repository.
**Enforced by:** `saathi/connectors/providers/external/fixtures.py` (fail-closed at load time).

Raw provider responses are **never** committed. Only small, sanitized, deterministic,
provenance-bearing fixtures are permitted, and every load re-runs the M31 leak scanner.

---

## 1. Hard requirements

A committed fixture is admissible only if **all** hold:

- **Sanitized** — no credentials, cookies, tokens, authorization material, or personal data.
  Sensitive material is stripped via `_strip_sensitive` (M32 normalization) before commit.
- **Deterministic** — no unstable identifiers or timestamps. The following keys are stripped
  on sanitization: `request_id`, `x-request-id`, `x-github-request-id`, `timestamp`, `date`,
  `etag`, `last-modified`, `trace_id`, `correlation_id`, `server_time`.
- **Bounded** — at most `MAX_FIXTURE_BYTES = 64 KiB` on disk. Oversized fixtures are rejected
  (`fixture_too_large`).
- **Parseable** — valid UTF-8 JSON (`fixture_unparseable` otherwise).
- **Provenance-bearing** — must carry `provider_id`, `operation`, `capture_method`, and `body`.
  A missing field is rejected (`fixture_missing_provenance`).
- **Leak-clean** — `load_fixture` calls `assert_fixture_clean` (M31 `assert_clean`); any
  secret-shaped content fails the load closed (`LeakDetected`).

## 2. Provenance schema (`m33.external_fixture.v1`)

| Field | Meaning |
|-------|---------|
| `schema` | `m33.external_fixture.v1` |
| `provider_id` | canonical provider id (e.g. `github_meta`) |
| `operation` | declared read-only operation (e.g. `get_meta`) |
| `capture_method` | how the fixture body was produced |
| `official_documentation_reference` | first-party doc URL the fixture is derived from |
| `privacy_safe` | must be `true` |
| `body` | the sanitized, canonical response body |

## 3. Capture method for `github_meta`

The committed fixture (`saathi/connectors/providers/external/fixtures/github_meta/get_meta.success.json`)
uses `capture_method = synthesized_from_public_documentation_sanitized`: a representative,
truncated subset of the public GitHub `/meta` response, synthesized from official
documentation. It contains only **public infrastructure CIDR ranges** and boolean/enum flags —
no credentials, cookies, tokens, personal data, request ids, or timestamps. No live response
was captured or committed.

## 4. Enforcement evidence

- `docs/evidence/m33/fixture_sanitization_results.json` records: `raw_response_committed: false`,
  `bounded: true`, empty `leak_scan_findings`, and the fixture provenance.
- The evidence is regenerated deterministically by `scripts/m33_generate_evidence.py`.

## 5. Offline-first testing

Focused M33 tests are fixture-backed and never touch the network: transport, DNS, and TLS
are injected (`testkit.py`). Live external verification is operator-only and is **not**
exercised in CI (recorded as `NOT EXERCISED`). See `docs/M33_FINAL_REPORT.md`.
