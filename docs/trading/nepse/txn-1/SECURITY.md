# Untrusted File Security

Transaction exports are `UNTRUSTED_DATA`. The importer accepts in-memory UTF-8
or UTF-8-with-BOM CSV/TSV only. It never opens a supplied path and never invokes
a spreadsheet application.

Default hard limits are:

| Limit | Value |
|---|---:|
| File size | 5 MiB |
| Non-blank data rows | 50,000 |
| Columns per row | 64 |
| Characters per cell | 4,096 |

The byte bound is checked before decoding. CSV records are streamed after that
bound; no unbounded input is converted into an in-memory row matrix. Exceeding
any bound raises `FILE_LIMIT_EXCEEDED` and returns no partial proposal.

Other fail-closed controls:

- strict UTF-8 decoding; embedded nulls are rejected;
- only comma or tab delimiters are accepted;
- blank, duplicate, formula-prefixed, or ambiguously mapped headers fail;
- structural cells beginning with `=`, `+`, `-`, or `@` are rejected before
  normalization; numeric formula text cannot parse as `Decimal`;
- source-file provenance is a bounded non-path label, so traversal components
  are rejected;
- non-finite numbers, excessive magnitude, and excessive scale are rejected;
- raw rejected rows are represented by SHA-256 references, not copied into
  error detail;
- malformed delimited input raises a typed whole-file refusal.

The package contains no provider transport or dynamic import surface.
