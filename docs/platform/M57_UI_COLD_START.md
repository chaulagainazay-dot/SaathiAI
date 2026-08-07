# M57 Operator Console Cold-Start Hardening

Fixes the first-load `/platform/ops` experience where, during initial Next.js
route compilation, concurrent cross-origin fetches could transiently fail and
show empty cards or a temporary error banner.

## Implementation (`saathi-os/app/platform/ops/page.jsx`)
- Explicit **loading state** (`ops-loading` → "Loading operator console…").
- `loadWithRetry`: each data endpoint retries up to 4 times with bounded backoff
  (400/800/1200 ms).
- **Transient vs real**: `Failed to fetch`/`NetworkError`/`load failed` are treated
  as cold-start races — retried quietly, and only surfaced as a soft "Console
  notice" if still failing after retries. Non-transient errors (e.g. 401/403) are
  shown immediately.
- Genuine errors remain visible **after** retries are exhausted; the fatal
  "Console error" is reserved for real failures.
- `Promise.allSettled` isolates each card so one slow endpoint never blanks the
  console, avoiding duplicate request storms. Authentication and CORS behavior are
  unchanged.

## Result
```
Cold first load:  Loading → data populated
Not:              Empty cards → misleading fatal error
```
