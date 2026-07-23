# M49.1 Bypass Review

| Vector | Mitigation |
|---|---|
| Direct adapter call | adapters not exported as public execute API |
| User tool registration | trusted=False blocked |
| Authority override | not accepted on request |
| Unknown tool success | rejected TOOL_NOT_FOUND |
| skip_contract style | no skip on ToolExecutionService |
| API/CLI generic execute | CLI tools diagnostics read-only only |

Remaining: saathi.tools voice path deferred (documented).
