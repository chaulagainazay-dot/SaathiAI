# M49.1 Tool Manifest Contract

Code-owned `ToolManifest` in `saathi/tool_runtime/contracts.py`.

Required fields: tool_id, version, display_name, description, domain, capabilities,
authority_class, side_effect_class, approval_requirement, secret_policy,
input_schema, output_schema, timeout_policy, retry_policy, idempotency_policy,
cancellation_support, evidence_policy, redaction_policy, enabled, availability.

Unknown authority/side-effect/cancellation/idempotency **cannot register**.
Financial execution requires PROHIBITED approval + availability.
Callers cannot supply or override authority.
