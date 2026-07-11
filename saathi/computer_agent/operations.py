"""M17 computer-agent operations — registered as M15 connector tools.

Desktop / browser / vision operations are ordinary connector tools so every
computer action flows through the SAME ExecutionEngine → ExecutionGateway →
risk/approval → evidence path. No new execution engine. Read ops are L0/L1;
click/type are L2; download/upload/send are L3 (approval); delete/purchase/
deploy/admin are L4 (manual-only). Mutating ops carry require_verification so the
adapter performs a post-action visual check (never assume success).
"""
from __future__ import annotations

import time

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import adapters as A
from saathi.connectors.platform.models import (
    ConnectorDef, ToolDef, RiskClass, MutationClass, ToolResult, _now_iso,
)
from saathi.computer_agent.providers import default_provider, provider_availability

_REGISTERED = False


class ComputerAdapter(A.Adapter):
    """Bridges connector execution to a computer provider. Deterministic by
    default (no real desktop). Mutating ops run a post-action verification."""
    name = "computer"

    def available(self) -> bool:
        return True

    def health(self) -> dict:
        return {"status": "deterministic", "adapter": "computer",
                "providers": provider_availability()}

    def execute(self, *, tool, account_id, args, secret_getter=None) -> ToolResult:
        started = _now_iso()
        surface = "browser" if tool.connector_id == "browser_agent" else "desktop"
        provider = default_provider(surface)
        base = dict(connector_id=tool.connector_id, tool_id=tool.tool_id,
                    capability_id=tool.capability_id, started_at=started,
                    provenance={"adapter": "computer", "provider": provider.name})
        op = tool.capability_id
        try:
            if op in _READ_OPS:
                screen = provider.perceive(fixture=args.get("_fixture", "login"))
                return ToolResult(status="success",
                                  data={"screen": screen.to_dict(),
                                        "element_count": len(screen.elements)},
                                  evidence=[{"provider": provider.name,
                                             "elements": len(screen.elements)}],
                                  completed_at=_now_iso(), **base)
            # mutating op → actuate then VERIFY (never assume success)
            act = provider.actuate(action=op, args=args)
            verification = self._verify(provider, op, args)
            status = "success" if verification["verified"] else "uncertain"
            return ToolResult(status=status,
                              data={"action": act, "verification": verification},
                              warnings=[] if verification["verified"]
                              else ["post-action verification did not confirm the result"],
                              evidence=[{"provider": provider.name, "verified": verification["verified"]}],
                              completed_at=_now_iso(), **base)
        except Exception as e:
            return ToolResult(status="failed", completed_at=_now_iso(),
                              errors=[{"class": "internal_error", "message": str(e)[:200]}],
                              **base)

    @staticmethod
    def _verify(provider, op, args) -> dict:
        """Post-action visual verification contract. Re-perceive and check the
        expected observable change. Deterministic here; a live provider re-reads
        the real screen."""
        screen = provider.perceive(fixture=args.get("_expect", "login"))
        expected_text = args.get("_expect_text", "")
        if expected_text:
            found = bool(screen.find(text=expected_text))
            return {"verified": found, "method": "text_appeared",
                    "expected": expected_text}
        # default: no error dialog present == verified
        return {"verified": not screen.error_present, "method": "no_error_dialog"}


# capability_id sets: reads never mutate
_READ_OPS = {
    "capture_screen", "ocr_text", "detect_elements", "inspect_window",
    "read_page", "detect_error", "detect_loading", "caption_image",
    "understand_document", "understand_chart",
}


def _tool(connector_id, cap, name, risk, *, mutation=MutationClass.NONE,
          verify=False, idempotent=True, reversible=True):
    return ToolDef(
        tool_id=f"{connector_id}.{cap}", connector_id=connector_id, capability_id=cap,
        name=name, risk_class=risk, mutation_class=mutation, idempotent=idempotent,
        reversible=reversible, deterministic_adapter=True,
        rate_limit_bucket=connector_id,
        input_schema={"require_verification": verify})


def register(force: bool = False) -> None:
    global _REGISTERED
    if _REGISTERED and not force:
        return
    adapter = ComputerAdapter()

    # ── vision connector (perception; read-only) ────────────────────────────
    if not R.get_connector("vision"):
        R.register_connector(ConnectorDef(
            connector_id="vision", provider="computer", display_name="Vision",
            category="computer", local=True, risk_ceiling=RiskClass.EXTERNAL_READ,
            integration_status="deterministic-adapter-tested"), adapter)
        for cap, nm in [("capture_screen", "Capture screen"), ("ocr_text", "OCR text"),
                        ("detect_elements", "Detect UI elements"),
                        ("caption_image", "Caption image"),
                        ("understand_document", "Understand document"),
                        ("understand_chart", "Understand chart"),
                        ("detect_error", "Detect error dialog"),
                        ("detect_loading", "Detect loading")]:
            R.register_tool(_tool("vision", cap, nm, RiskClass.LOCAL_READ))

    # ── desktop connector ───────────────────────────────────────────────────
    if not R.get_connector("desktop"):
        R.register_connector(ConnectorDef(
            connector_id="desktop", provider="computer", display_name="Desktop",
            category="computer", local=True, risk_ceiling=RiskClass.HIGH_IMPACT,
            integration_status="deterministic-adapter-tested"), adapter)
        R.register_tool(_tool("desktop", "inspect_window", "Inspect window", RiskClass.LOCAL_READ))
        R.register_tool(_tool("desktop", "click", "Click", RiskClass.REVERSIBLE_MUTATION,
                             mutation=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(_tool("desktop", "type_text", "Type text", RiskClass.REVERSIBLE_MUTATION,
                             mutation=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(_tool("desktop", "scroll", "Scroll", RiskClass.REVERSIBLE_MUTATION,
                             mutation=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(_tool("desktop", "file_upload", "Upload file", RiskClass.EXTERNAL_SIDE_EFFECT,
                             mutation=MutationClass.REVERSIBLE, verify=True, idempotent=False))
        R.register_tool(_tool("desktop", "delete_item", "Delete item", RiskClass.HIGH_IMPACT,
                             mutation=MutationClass.IRREVERSIBLE, verify=True,
                             idempotent=False, reversible=False))
        R.register_tool(_tool("desktop", "run_binary", "Run binary", RiskClass.HIGH_IMPACT,
                             mutation=MutationClass.IRREVERSIBLE, verify=True,
                             idempotent=False, reversible=False))

    # ── browser_agent connector (DOM+vision hybrid) ─────────────────────────
    if not R.get_connector("browser_agent"):
        R.register_connector(ConnectorDef(
            connector_id="browser_agent", provider="computer", display_name="Browser Agent",
            category="computer", local=True, risk_ceiling=RiskClass.HIGH_IMPACT,
            integration_status="deterministic-adapter-tested"), adapter)
        R.register_tool(_tool("browser_agent", "read_page", "Read page", RiskClass.EXTERNAL_READ))
        R.register_tool(_tool("browser_agent", "navigate", "Navigate", RiskClass.EXTERNAL_READ,
                             mutation=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(_tool("browser_agent", "click", "Click element", RiskClass.REVERSIBLE_MUTATION,
                             mutation=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(_tool("browser_agent", "fill_form", "Fill form", RiskClass.REVERSIBLE_MUTATION,
                             mutation=MutationClass.REVERSIBLE, verify=True))
        R.register_tool(_tool("browser_agent", "download", "Download file", RiskClass.EXTERNAL_SIDE_EFFECT,
                             mutation=MutationClass.REVERSIBLE, verify=True, idempotent=False))
        R.register_tool(_tool("browser_agent", "submit_purchase", "Submit purchase", RiskClass.HIGH_IMPACT,
                             mutation=MutationClass.IRREVERSIBLE, verify=True,
                             idempotent=False, reversible=False))
        R.register_tool(_tool("browser_agent", "send_message", "Send message", RiskClass.EXTERNAL_SIDE_EFFECT,
                             mutation=MutationClass.IRREVERSIBLE, verify=True,
                             idempotent=False, reversible=False))
    _REGISTERED = True


register()
