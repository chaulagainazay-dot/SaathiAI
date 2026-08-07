# M48.1 — Memory Boundaries

## Inventory

| Store | Path | Role |
|---|---|---|
| M9 MemoryEngine | `saathi/memory/engine/` | scoped namespaces, retrieve_for_chat |
| Chat history | chat tables / conversations | short-term conversation |
| Agent memory_scopes | AgentDefinition.memory_scopes | prefix allowlists |
| Delegation narrowing | policy.narrow_permissions | child ⊆ parent scopes |
| Evidence / artifacts | RunStore artifacts | run outputs |
| Code memory | codebase_memory / MCP | optional external |

## Rules

- Agents only read/write declared scopes  
- Delegation may narrow, never widen scopes  
- Secrets never stored in memory payloads as raw credentials  
- Provenance required for retrieval citations where implemented  
- M48.1 does not redesign memory; documents boundaries only  
- No personal secret harvesting in this milestone  
