# M17.3 Harness Architecture
User/Agent → Capability Resolver → trust/compat/ownership → HarnessActionIntent →
risk/approval → service.run_harness_action → ApplicationHarnessAdapter (argv-only,
env-sanitized, file-root confined, output-capped, process-group cleanup) →
structured-output parser → INDEPENDENT verifier (ffprobe/magic-bytes/checksum/
XXE-safe/ZIP-slip-safe) → evidence → (event bus/memory/Control Center).
Resolution order: connector_api → trusted_harness → dom_cdp → accessibility →
ocr_vision → coordinate. Never fall from a trusted structured layer to GUI unless
unhealthy/incompatible/missing.
