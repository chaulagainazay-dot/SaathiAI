# FULL_SUITE_REPORT

Local (Python 3.12, `pip install -e .`, after repair):

```text
7393 passed, 8 skipped, 0 failed
in 1031.50s (0:17:11)
```

Command:

```bash
PYTHONPATH=. python3.12 -m pytest tests/ -q -p no:cacheprovider
```
