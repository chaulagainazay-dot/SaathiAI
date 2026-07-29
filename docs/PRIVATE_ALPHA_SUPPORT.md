**Production authorized: false.** Local-only private alpha.

# Private Alpha Support

## Support bundle

```bash
bin/saathi-alpha support-bundle
```

Writes a privacy-filtered archive under `data/alpha/support/`.

Includes: release manifest, redacted config, doctor summary, lifecycle contract,
bounded redacted logs, known limitations.

## Doctor

```bash
bin/saathi-alpha doctor
```

## Boundaries

- Private-alpha support only
- Owner-managed machine
- No guaranteed uptime
- No production SLA
