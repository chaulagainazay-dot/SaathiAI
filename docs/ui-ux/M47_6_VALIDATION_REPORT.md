# M47.6 — Validation Report

## Checks

```bash
cd ~/SaathiAI
python -m pytest tests/test_m47_6_cors_policy.py -q
cd saathi-os && npm test && npm run lint && npm run build
```

## Expected

| Check | Result |
|---|---|
| CORS unit tests | pass |
| Frontend unit tests | pass |
| Lint | pass |
| Build | pass |
| New soft redirects | none |
| Trading advisory | preserved |
| PR draft | preserved |

## Limitations

- Chat panel lacks team/voice/timeline (full /chat)  
- Control search not on Command  
- Finance API still unwired  
- Studio dual pages remain  
