# M52 Limitations

1. Platform execution coordination is single-host SQLite. Versioned transitions
   prevent ordinary local races but do not provide multi-host consensus.
2. A recorded dispatch interrupted by process loss is paused for manual review;
   it is never automatically replayed. This favors mutation safety over
   automatic completion.
3. `PlatformService.execute_tool`, `AgentExecutor`, and the M49 legacy bridge
   remain compatibility surfaces. They cannot bypass the M52/M49 authority
   boundaries described in the migration report.
4. The built-in platform binding supports one canonical `platform-agent`.
   Durable administrative registration of multiple agent identities is deferred.
5. Connector mutations remain deterministic dry-run fixtures. No live OAuth,
   credentials, email delivery, issue creation, deployment, or production
   connector activity is enabled.
6. Financial execution remains prohibited. Trading Guardian is unengaged and
   advisory-only.
7. CI, browser certification, distributed recovery, deployment, and production
   authorization are outside this local milestone.
8. The repository has no `CAPABILITY_MATRIX.md` or `HANDOFF.md` to update.
