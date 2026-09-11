# Quality mapping

Use existing MD-1 quality/provenance and NEPSE calendar. Valid observations map to `FRESH`/`DELAYED`; age beyond a documented threshold to `STALE`; malformed/non-positive values to `INVALID`; disagreements retain provenance as `CONFLICTING`; missing open-session observations are `GAPPED`. Closed sessions are not stale by default; unknown holidays never imply open state.
