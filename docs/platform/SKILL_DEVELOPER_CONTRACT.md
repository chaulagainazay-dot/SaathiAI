# Skill Developer Contract (M118)

Skills are **policy-bound, versioned capability packages**. They are not prompts,
shell scripts, permission grants, or tool authorities.

## Authoring

1. Place a package under `saathi/platform/skills/packages/<package_id>/`.
2. Include `skill.json` (schema `skill.manifest.v1`), `README.md`, optional `CONTRACT.md`.
3. Allowed files: `.json`, `.md`, `.txt`, `.yaml` — no executables.
4. Declare capabilities from the known set; declare tools only from registered safe tools.
5. Set `entrypoint_type` to `declarative`, `adapter_bound`, or `orchestration_template`.
6. Set `production_posture` to `not_authorized`.
7. Set `network_requirements` to `none` or `loopback`.
8. Never declare forbidden permissions (`unrestricted_shell`, `direct_tool_execution`, …).

## Validation

```bash
# Via API (authenticated)
POST /api/v1/platform/skills/validate  {"package_id":"repo_audit"}

# CLI scaffold (no remote URLs)
python -m saathi.platform.skills.cli validate repo_audit
```

## Execution

Skills execute only through:

```
SkillRuntime.execute
  → (optional) Fleet lease
  → PlatformAgentRuntime
  → ExecutionGateway
  → Approval Center when required
```

Manifests **cannot** grant RBAC, mint approvals, or invoke tools directly.

## Lifecycle

DISCOVERED → VALID → REGISTERED/DISABLED → ENABLED → (UPGRADING|QUARANTINED|REVOKED)

Disable before uninstall. Upgrade keeps prior version for rollback.
