# M15.1 Research
- Auth model: server middleware trusts local callers, requires X-Saathi-Token
  remote; request.state.user_id read by _user(); ownership enforced per row
  (same as CEO/chat/voice routers). Reused verbatim.
- Legacy connector surface: server.py @app /api/v1/connectors/{providers,accounts,
  execute} + saathi/connectors/ (accounts/manager) + adapters/telegram (real Bot
  API). New /api/v1/connectors/* is canonical; legacy kept as shim, execute path
  to be delegated. Recorded in migration.py MIGRATIONS.
- gstack: an optional external Claude/Codex development workflow and review
  toolkit. It is not a Spec Kit implementation, connector runtime, or SaathiOS
  production dependency.
