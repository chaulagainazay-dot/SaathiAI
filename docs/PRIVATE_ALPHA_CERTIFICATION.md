# Private Alpha Certification

## Gate

```bash
bin/saathi-alpha certify
# or: .venv/bin/python -m saathi.platform.private_alpha certify
```

## Required verdicts

| Surface | Verdict |
| --- | --- |
| Certification gate | `PRIVATE_ALPHA_READY_WITH_LIMITATIONS` |
| Browser journey | `SAATHIOS_PRIVATE_ALPHA_BROWSER_CERT_PASSED` |
| DR drill | `PRIVATE_ALPHA_DR_DRILL_PASSED` |
| Production | **NOT AUTHORIZED** |

## Evidence

- `docs/evidence/m157_m165/M165_PRIVATE_ALPHA_CERTIFICATION.json`
- `docs/evidence/m157_m165/browser/M165_BROWSER_CERT.json`
- Focused tests: `tests/test_m157_private_alpha.py`

## Acceptance meaning

Ready for **bounded local private alpha** on the certified Apple Silicon machine
class — not public launch, not production deployment.
