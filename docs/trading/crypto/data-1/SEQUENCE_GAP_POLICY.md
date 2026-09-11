# Sequence and gap policy

Contiguous update IDs are accepted. Duplicate and regressing IDs are surfaced. A gap marks the stream `GAPPED` and requires a fresh snapshot/resynchronization before resume. Queue overflow is `DROPPED_BACKPRESSURE` with degraded quality, never silent loss.
