# Failure matrix

Offline tests cover heartbeat staleness, disconnect/reconnect exhaustion, bounded overflow, snapshot validation, duplicate/regressing/gapped sequence behavior, and clean fail-closed states. DNS/TLS/socket transport failures are represented by the existing provider result boundary; live validation remains environment-blocked.
