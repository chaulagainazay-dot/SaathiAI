# REPLAY_CERTIFICATION

Scenario **S10** (automated):

1. Create fund + fill + mark on durable SQLite path
2. Capture state + state_hash
3. New process / new service instance same DB
4. `replay()` → identical public state + identical hash

Lot IDs stable from fill identity. Event order = seq ASC.

