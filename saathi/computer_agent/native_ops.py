"""M17.2 native macOS operations — registered as M15 connector tools.

The `macos` connector exposes native operations that route through the SAME
ExecutionEngine → ExecutionGateway → risk/approval path. Read/identity ops (L0/L1)
run LIVE via the canonical MacDriver; actuation ops (L2+) are gated by
Accessibility permission + an interactive session and honestly return
permission_blocked / environment_blocked. No native API is called outside the
driver boundary.
"""
from __future__ import annotations

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import adapters as A
from saathi.connectors.platform.models import (
    ConnectorDef, ToolDef, RiskClass, MutationClass, ToolResult, _now_iso,
)
from saathi.computer_agent.macos_driver import MacDriver, available

_REGISTERED = False

# native ops that genuinely run without Accessibility (LIVE where OS permits)
_LIVE_READ = {"inspect_applications", "active_application", "verify_identity"}


class MacAdapter(A.Adapter):
    name = "macos"

    def __init__(self):
        self.driver = MacDriver()

    def available(self) -> bool:
        return available().get("available", False)

    def health(self) -> dict:
        from saathi.computer_agent.macos_permissions import summary
        return {"status": "live" if self.available() else "dependency_blocked",
                "adapter": "macos", "permissions": summary()}

    def execute(self, *, tool, account_id, args, secret_getter=None) -> ToolResult:
        base = dict(connector_id=tool.connector_id, tool_id=tool.tool_id,
                    capability_id=tool.capability_id, started_at=_now_iso(),
                    provenance={"adapter": "macos", "driver": "canonical"})
        op = tool.capability_id
        d = self.driver
        try:
            if op == "inspect_applications":
                r = d.list_applications()
            elif op == "active_application":
                r = d.active_application()
            elif op == "verify_identity":
                r = d.verify_app_identity(bundle_id=args.get("bundle_id", ""),
                                          pid=int(args.get("pid", 0)))
            elif op == "ax_tree":
                r = d.ax_tree(bundle_id=args.get("bundle_id", "com.apple.finder"))
            elif op == "screenshot":
                r = d.screenshot(args.get("path", ""))
            elif op in ("finder_create_folder", "finder_rename", "finder_move",
                        "textedit_create", "textedit_save", "activate_application",
                        "menu_select", "type_text"):
                # actuation — needs Accessibility + GUI session
                r = d.activate_application(bundle_id=args.get("bundle_id", "com.apple.finder")) \
                    if op == "activate_application" else \
                    d.ax_tree(bundle_id=args.get("bundle_id", "com.apple.finder"))
                # map to the actuation gate honestly
                if r.status in ("permission_blocked", "environment_blocked"):
                    return ToolResult(status="blocked", completed_at=_now_iso(),
                                      errors=[{"class": "policy_denied",
                                               "message": f"{op}: {r.status} ({r.data.get('reason','')})"}],
                                      data={"native": r.data, "native_status": r.status}, **base)
                return ToolResult(status="uncertain", completed_at=_now_iso(),
                                  data={"native": r.data,
                                        "verification": {"verified": False,
                                                         "note": "actuation not confirmed"}}, **base)
            else:
                return ToolResult(status="failed", completed_at=_now_iso(),
                                  errors=[{"class": "unsupported_operation",
                                           "message": op}], **base)
            # read/identity ops
            status = {"success": "success",
                      "permission_blocked": "blocked",
                      "environment_blocked": "blocked",
                      "failed": "failed"}.get(r.status, "failed")
            return ToolResult(status=status, completed_at=_now_iso(),
                              data={"native": r.data, "native_status": r.status},
                              evidence=[{"driver": "canonical", "op": op,
                                         "native_status": r.status}], **base)
        except Exception as e:
            return ToolResult(status="failed", completed_at=_now_iso(),
                              errors=[{"class": "internal_error", "message": str(e)[:180]}], **base)


def register(force: bool = False) -> None:
    global _REGISTERED
    if _REGISTERED and not force:
        return
    if not R.get_connector("macos"):
        R.register_connector(ConnectorDef(
            connector_id="macos", provider="computer", display_name="macOS Desktop",
            category="computer", local=True, risk_ceiling=RiskClass.HIGH_IMPACT,
            integration_status="deterministic-adapter-tested"), MacAdapter())
        def t(cap, name, risk, mut=MutationClass.NONE, verify=False, idem=True):
            return ToolDef(tool_id=f"macos.{cap}", connector_id="macos",
                           capability_id=cap, name=name, risk_class=risk,
                           mutation_class=mut, idempotent=idem, deterministic_adapter=True,
                           rate_limit_bucket="macos", input_schema={"require_verification": verify})
        # LIVE reads (no Accessibility needed)
        R.register_tool(t("inspect_applications", "List applications", RiskClass.LOCAL_READ))
        R.register_tool(t("active_application", "Active application", RiskClass.LOCAL_READ))
        R.register_tool(t("verify_identity", "Verify app identity", RiskClass.LOCAL_READ))
        R.register_tool(t("ax_tree", "Accessibility tree", RiskClass.LOCAL_READ))
        R.register_tool(t("screenshot", "Screen capture", RiskClass.LOCAL_READ))
        # actuation (gated)
        R.register_tool(t("activate_application", "Activate app", RiskClass.REVERSIBLE_MUTATION,
                          mut=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(t("finder_create_folder", "Finder create folder", RiskClass.REVERSIBLE_MUTATION,
                          mut=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(t("finder_rename", "Finder rename", RiskClass.REVERSIBLE_MUTATION,
                          mut=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(t("finder_move", "Finder move", RiskClass.REVERSIBLE_MUTATION,
                          mut=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(t("textedit_create", "TextEdit create", RiskClass.REVERSIBLE_MUTATION,
                          mut=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(t("textedit_save", "TextEdit save", RiskClass.REVERSIBLE_MUTATION,
                          mut=MutationClass.REVERSIBLE, verify=True, idem=False))
    _REGISTERED = True


register()
