"""M15.3 canonical scope + permission engine.

One evaluator answers "may this exact operation run?" before execution. Scope
matching is EXACT (no fuzzy/prefix matching). Returns a structured, actionable
explanation with a stable reason_code. This does NOT replace the engine's
ownership/approval/gateway checks — it is an additional pre-execution gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from saathi.connectors.platform import registry as R
from saathi.connectors.platform.models import RiskClass, MANUAL_ONLY


# stable reason codes (safe to surface to users)
R_OK = "ALLOWED"
R_CONNECTOR_UNKNOWN = "CONNECTOR_UNKNOWN"
R_OP_UNKNOWN = "OPERATION_UNKNOWN"
R_OP_UNSUPPORTED = "CONNECTOR_OPERATION_UNSUPPORTED"
R_SCOPE_MISSING = "CONNECTOR_SCOPE_MISSING"
R_ACCOUNT_INACTIVE = "ACCOUNT_INACTIVE"
R_ACCOUNT_REVOKED = "ACCOUNT_REVOKED"
R_CONNECTOR_DISABLED = "CONNECTOR_DISABLED"
R_RISK_CEILING = "RISK_CEILING_EXCEEDED"
R_ENV_NOT_PERMITTED = "ENVIRONMENT_NOT_PERMITTED"
R_AGENT_FORBIDDEN = "AGENT_OPERATION_FORBIDDEN"
R_MANUAL_ONLY = "MANUAL_ONLY_RISK4"


@dataclass
class ScopeDecision:
    allowed: bool
    reason_code: str
    required_scopes: list = field(default_factory=list)
    granted_scopes: list = field(default_factory=list)
    user_action: str = ""
    risk: int = 0

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "reason_code": self.reason_code,
                "required_scopes": self.required_scopes,
                "granted_scopes": self.granted_scopes,
                "user_action": self.user_action, "risk": self.risk}


# per-operation required provider scopes (exact). Extends the tool registry;
# absent → no provider scope required (local/no-auth ops).
OPERATION_SCOPES: dict[str, list[str]] = {
    "gmail.search_email": ["gmail.readonly"],
    "gmail.read_email": ["gmail.readonly"],
    "gmail.draft_email": ["gmail.compose"],
    "gmail.send_email": ["gmail.send"],
    "gmail.reply_email": ["gmail.send"],
    "gcal.list_calendar_events": ["calendar.events.readonly"],
    "gcal.create_calendar_event": ["calendar.events"],
    "gcal.cancel_calendar_event": ["calendar.events"],
    "gcontacts.search_contacts": ["contacts.readonly"],
    "github.list_issues": ["repo:read"],
    "github.inspect_repository": ["repo:read"],
    "github.create_issue": ["repo:write"],
    "github.create_branch": ["repo:write"],
    "github.open_pull_request": ["repo:write"],
    "github.push_branch": ["repo:write"],
    "telegram.send_message": ["bot:send"],
    "telegram.send_notification": ["bot:send"],
    "studio_publish.publish_video": ["publish:video"],
    "deploy.deploy_to_staging": ["deploy:staging"],
    "deploy.deploy_to_production": ["deploy:production"],
}


def required_scopes(tool_id: str) -> list[str]:
    return list(OPERATION_SCOPES.get(tool_id, []))


def evaluate(*, tool_id: str, account: dict | None, actor_type: str = "user",
             environment: str = "staging", allowed_environments=None) -> ScopeDecision:
    """Full pre-execution permission evaluation. `account` is the store row
    (or None for local no-auth). granted scopes come from account metadata."""
    tool = R.get_tool(tool_id)
    if tool is None:
        return ScopeDecision(False, R_OP_UNKNOWN, user_action="Unknown operation.")
    conn = R.get_connector(tool.connector_id)
    if conn is None:
        return ScopeDecision(False, R_CONNECTOR_UNKNOWN)
    risk = int(tool.risk_class)

    if not conn.local:
        if account is None:
            return ScopeDecision(False, R_ACCOUNT_INACTIVE, risk=risk,
                                 user_action="Connect an account for this connector.")
        st = account.get("state", "")
        if st in ("revoked", "unauthorized"):
            return ScopeDecision(False, R_ACCOUNT_REVOKED, risk=risk,
                                 user_action="Reconnect the account.")
        if not account.get("enabled", 1) or st in ("disabled",):
            return ScopeDecision(False, R_ACCOUNT_INACTIVE, risk=risk,
                                 user_action="Enable the account.")
        # EXACT scope match
        req = required_scopes(tool_id)
        granted = account.get("granted_scopes") or []
        if isinstance(granted, str):
            import json
            try:
                granted = json.loads(granted)
            except Exception:
                granted = [granted]
        # Scope enforcement applies to accounts that TRACK scopes (real OAuth/
        # token accounts populate granted_scopes at connect time). An account
        # with no tracked scopes is a local/deterministic account — scope
        # enforcement is not applicable, other gates (ownership/approval/risk)
        # still apply. When scopes ARE tracked, matching is EXACT.
        if granted:
            missing = [s for s in req if s not in granted]
            if missing:
                return ScopeDecision(False, R_SCOPE_MISSING, required_scopes=req,
                                     granted_scopes=list(granted), risk=risk,
                                     user_action="Reconnect the account with the required permission.")

    if allowed_environments and environment not in allowed_environments:
        return ScopeDecision(False, R_ENV_NOT_PERMITTED, risk=risk,
                             user_action=f"Operation not permitted in {environment}.")
    if risk > int(conn.risk_ceiling):
        return ScopeDecision(False, R_RISK_CEILING, risk=risk,
                             user_action="Operation risk exceeds connector ceiling.")
    if actor_type == "agent" and risk >= int(MANUAL_ONLY):
        return ScopeDecision(False, R_MANUAL_ONLY, risk=risk,
                             user_action="Risk-4 action is manual-only; a user must perform it.")
    return ScopeDecision(True, R_OK, required_scopes=required_scopes(tool_id), risk=risk)
