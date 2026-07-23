# M49.3 Connector Approval Scope

Approval is bound to: connector, action, tool_id, tool_version, capability, run_id, mission_id, actor, authority, side-effect class, target_resource, expiry, revocation.

## Rules

- Approval for `gmail.create_draft` does not authorize `gmail.send_message`
- Approval for one target does not authorize another when `target_resource` is set
- Expired / revoked approvals fail closed
- Revalidation occurs immediately before adapter invocation

## CLI

```bash
python -m saathi.agent_runtime.cli tools audit-approvals
```
