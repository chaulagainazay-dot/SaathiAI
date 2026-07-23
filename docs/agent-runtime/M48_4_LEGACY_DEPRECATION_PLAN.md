# M48.4 — Legacy Deprecation Plan

| component | replacement | status | removal prerequisite |
|---|---|---|---|
| Direct M8 send-only agent path | run_agent wrap | WRAPPED | none for wrap |
| skip_contract production use | start_agent_run | BLOCKED | already blocked |
| IELTS agents | future | DEFERRED | domain isolation review |
| EngineeringOrchestrator | optional façade | DEFERRED | M48.5+ |
