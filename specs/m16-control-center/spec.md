# M16 — Unified Control Center (Spec)
Constitution v1.0. ONE command/observation layer over the canonical subsystems
(connectors, security red-team, ops release gates, event bus, live-validation).
NOT an execution engine: never calls providers, never writes subsystem stores,
never bypasses ExecutionGateway. Mutations are action descriptors pointing at
canonical APIs. Bounded aggregation degrades honestly on partial failure; every
cell carries source + freshness. Owner-scoped throughout. Live browser/
authenticated-workflow verification = environment-blocked. See traceability.json.
