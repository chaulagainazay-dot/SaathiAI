# M17.3 SaathiOS Harness Audit
Reusable: ExecutionGateway, risk/approval model (M15), circuit/rate (M15.3),
error taxonomy, event bus, Control Center, red-team harness, ffmpeg usage (M13
Studio). New (M17.3): application_harness package (models/trust/registry/
importer/resolver/adapter/output-verify/service + ffmpeg pilot). No parallel
execution engine — the ApplicationHarnessAdapter is the sole subprocess boundary
and callers reach it only via service.run_harness_action (ownership+trust+risk
gated). Direct-execution risk audited: no agent/chat/frontend path to the adapter.
