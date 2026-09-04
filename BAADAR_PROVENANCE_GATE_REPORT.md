# Baadar Provenance Gate Report

## Manifest

`AssetManifest` contains every required identity, source, generation, prompt,
input, licence, commercial-use, attribution, music/font/voice/character,
similarity, human-review, destination, and content-hash field. Source types
are original, generated, licensed, public domain, user provided, and unknown.

## Gate behavior

The gate fails closed for unknown source, missing licence, unclear commercial
use, missing attribution, unresolved media/font/voice/character rights,
unconfirmed user permission, incomplete similarity review, absent human
review/evidence, missing hash, duplicate hash, undeclared destination, missing
existing approval, or any real-publication request.

Approval and audit are injected existing SaathiOS authorities. The gate stores
neither approvals nor audit records and performs no publication. Its only
success status is `APPROVED_SIMULATION`.

## Test matrix

| Case | Expected/result |
|---|---|
| Original generated asset | approved simulation |
| Properly licensed asset | approved simulation |
| Public-domain asset | approved simulation |
| Missing licence | blocked |
| Unclear commercial use | blocked |
| Missing attribution | blocked |
| Duplicate asset hash | blocked |
| Unapproved character likeness | blocked |
| Unresolved music rights | blocked |
| Missing similarity/human-review evidence | blocked |
| Approval denial | blocked |
| Real publishing flag | blocked |

All focused provenance/provider/evaluation tests passed. Legal review remains
required for ambiguous licensing, fair use, territorial limits, publicity and
likeness rights, and substantive similarity. C2PA may later sign provenance;
it does not replace rights clearance.
