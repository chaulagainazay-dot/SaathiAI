# Deterministic workflow evaluation

`saathi.evaluation.workflows` contains five offline scenarios:

1. fixture-repository repair;
2. synthetic IELTSAlert manual-payment verification;
3. local browser-fixture recovery;
4. synthetic canteen reconciliation;
5. Baadar content production stopped before publication.

Run:

```bash
.venv/bin/python scripts/run_priority_evaluations.py
```

The resulting score is a deterministic contract-gate score, not a claim about
general model intelligence. No production service, payment service, browser
destination, or publishing destination is contacted.
