# M60 — Agent / Binding Selection

Inside mission planning. Reads real `GET /agent-bindings`.

`agentSelectionBlockers(binding, {workspaceId, requiredCapability})` returns the
reasons a binding cannot be selected — inactive, revoked/invalid, cross-workspace,
or missing the required capability. `isAgentSelectable()` is the boolean gate; the
radio control is disabled with the reason shown. No silent fallback to another agent.

Terminology is truthful: records are labelled agent **bindings** (runtime
identities), advisory vs execution-capable by ceiling — never rebranded as
autonomous agents.
