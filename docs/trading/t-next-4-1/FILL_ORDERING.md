# Fill Ordering

Paper fills retain immutable `fill_id`, `order_id`, event and receipt times,
and a per-order sequence. Duplicate events are idempotent. A future external
adapter must reject sequence regression, gaps, and duplicate sequence values;
the current paper adapter does not silently reorder facts.
