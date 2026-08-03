# M361B private webhook feasibility decision

Conclusion: `LIVE_WEBHOOK_VALIDATION_SHOULD_BE_DEFERRED`

The pinned upstream documentation states that a webhook URL must be publicly
accessible and that all event types are delivered. It does not document delivery
to a private overlay address. The default SaathiOS rule remains
`DENY_PUBLIC_EXPOSURE`.

| Option | Technically feasible | Documentation evidence | Public/third-party/cost | Residual risk | Owner approval | M365 suitability |
| --- | --- | --- | --- | --- | --- | --- |
| No webhook in M361–M364 | yes | REST/schema work is independent of webhook delivery | none | live delivery remains untested | explicit deferral approval | recommended |
| Temporary authenticated relay | plausible, not verified for this design | upstream documents public HTTPS delivery and HMAC, not a SaathiOS relay architecture | public exposure and commonly a third-party service/cost | endpoint discovery, relay trust, teardown, broad event payloads | separate public-exposure, security, cost, and teardown approval | possible only as a later exception |
| Private tunnel/overlay | insufficient evidence | no upstream evidence that the sender can route to a private overlay address | may require third-party control plane | route reachability and sender identity unproven | required | not currently suitable |
| Self-generated contract tests | yes and already offline-tested | validates the local verifier contract, not Twenty delivery | none | cannot prove upstream emission/retry semantics | no runtime approval needed for fixture tests | suitable for contract/security evidence only |

The offline verifier can test signatures, timestamp freshness, payload bounds,
event allowlisting, redaction, tenant scoping, and observation-only behavior.
Its replay set is in-process, so durable replay across restart is not yet proven.
These are `INTEGRATION_CONTRACT_VALIDATION` and `SECURITY_CONTROL_VALIDATION`,
not `LIVE_DELIVERY_VALIDATION`.

Recommended sequence: approve no webhook for M361–M364, then make a separate
M365 decision after the private runtime, durable replay design, and teardown plan
are proven. A public relay must never expose dashboards, databases, SaathiOS
control routes, credentials, or execution surfaces.

The invariants remain `VERIFIED_EVENTS_TO_OBSERVATIONS_ONLY` and
`NO_DIRECT_EXECUTION`.
