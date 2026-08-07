# M51 Platform Intake Audit

## M50 CI baseline

```text
classification: M50_CI_GREEN
run: https://github.com/chaulagainazay-dot/SaathiAI/actions/runs/30011097364
critical-regressions: pass
full-suite: pass
HEAD: 154a247b26f466a8eb3019265ac50a2568745a14
```

## Surface inventory

| Surface | File | Auth | Membership | Workspace | Permission | Approval | Audit | UI | Tests |
|---|---|---|---|---|---|---|---|---|---|
| PlatformStore | store.py | n/a | n/a | n/a | n/a | n/a | yes | n/a | yes |
| PlatformService | service.py + alpha.py | session | yes | yes | yes | yes | yes | via API | yes |
| API /platform/* | api.py | token | yes | yes | yes | yes | yes | /platform | yes |
| AgentBinding | agent_binding.py | token only | yes | yes | RUNTIME_EXECUTE | optional | yes | agent/execute | yes |
| AgentExecutor legacy | saathi/agent.py | speaker | no platform | no | governance | legacy | partial | chat | residual |
| gateway_exec | agent_runtime | run context | no platform | no | m49 | m49 | m49 | n/a | residual |
| MissionStore legacy | missions/store.py | none | none | none | n/a | n/a | n/a | /missions | residual links |

## Unknown platform execution entry points

None remaining for **supported private-alpha path**. Residual AgentExecutor uses legacy execute_tool with M49 disposition gates (not a second gateway).
