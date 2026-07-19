# M39 — Live Multi-Session Results

## Status

**NOT_EXERCISED**

## Design (ready)

- Max concurrent sessions: **2**
- Separate SecretHandle, lease, session ID, correlation ID per session
- No plaintext in coordinator state
- Independent call accounting; aggregate budget default **6**
- Cleanup of one session does not invalidate the other mid-flight
- Both end `CLEANED` or safe terminal
- Duplicate cleanup idempotent
- Preferred sequential overlapping lifecycle if simultaneous live calls unsafe

## Offline fixture

Offline multi-session exercise **passed** (not live evidence).
