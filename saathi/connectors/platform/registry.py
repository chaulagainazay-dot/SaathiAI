"""M15 connector registry — registration, versioning, capability/tool resolution.

Config-driven. Seeds the real SaathiOS-relevant connectors (local fs/git,
GitHub, Gmail, Calendar, Contacts, Telegram, browser, sqlite, deployment,
studio-publish) with honest integration-status labels. Adapters: deterministic
for tests + real-local where genuinely runnable; cloud/OAuth are contract-ready
and labeled environment-blocked.
"""
from __future__ import annotations

from saathi.connectors.platform.models import (
    ConnectorDef, ToolDef, RiskClass, MutationClass,
)
from saathi.connectors.platform.catalog import capability_risk
from saathi.connectors.platform import adapters as A

_CONNECTORS: dict[str, ConnectorDef] = {}
_TOOLS: dict[str, ToolDef] = {}
_ADAPTERS: dict[str, A.Adapter] = {}


def register_connector(defn: ConnectorDef, adapter: A.Adapter | None = None) -> None:
    if defn.connector_id in _CONNECTORS:
        raise ValueError(f"duplicate connector id: {defn.connector_id}")
    _CONNECTORS[defn.connector_id] = defn
    if adapter:
        _ADAPTERS[defn.connector_id] = adapter


def register_tool(tool: ToolDef) -> None:
    if tool.tool_id in _TOOLS:
        raise ValueError(f"duplicate tool id: {tool.tool_id}")
    _TOOLS[tool.tool_id] = tool
    conn = _CONNECTORS.get(tool.connector_id)
    if conn and tool.tool_id not in conn.tools:
        conn.tools.append(tool.tool_id)


def get_connector(cid: str) -> ConnectorDef | None:
    return _CONNECTORS.get(cid)


def get_tool(tid: str) -> ToolDef | None:
    return _TOOLS.get(tid)


def get_adapter(cid: str) -> A.Adapter | None:
    return _ADAPTERS.get(cid)


def all_connectors() -> list[ConnectorDef]:
    return list(_CONNECTORS.values())


def all_tools() -> list[ToolDef]:
    return list(_TOOLS.values())


def tools_for_capability(capability_id: str, *, enabled_only: bool = True) -> list[ToolDef]:
    return [t for t in _TOOLS.values()
            if t.capability_id == capability_id and (t.enabled or not enabled_only)]


def connectors_for_capability(capability_id: str) -> list[ConnectorDef]:
    return [c for c in _CONNECTORS.values() if capability_id in c.capabilities]


def default_tool_for_capability(capability_id: str) -> ToolDef | None:
    """Prefer a local/deterministic-available tool; else the first."""
    candidates = tools_for_capability(capability_id)
    for t in candidates:
        c = _CONNECTORS.get(t.connector_id)
        if c and c.local:
            return t
    return candidates[0] if candidates else None


def registry_health() -> dict:
    return {"connectors": len(_CONNECTORS), "tools": len(_TOOLS),
            "adapters": len(_ADAPTERS),
            "by_integration_status": _count("integration_status")}


def _count(attr: str) -> dict:
    out: dict = {}
    for c in _CONNECTORS.values():
        out[getattr(c, attr)] = out.get(getattr(c, attr), 0) + 1
    return out


def _tool(connector_id, capability_id, name, *, mutation=MutationClass.NONE,
          idempotent=True, deterministic=True, reversible=True):
    risk = capability_risk(capability_id)
    return ToolDef(
        tool_id=f"{connector_id}.{capability_id}", connector_id=connector_id,
        capability_id=capability_id, name=name, risk_class=risk,
        mutation_class=mutation, idempotent=idempotent, reversible=reversible,
        deterministic_adapter=deterministic, rate_limit_bucket=connector_id)


def _bootstrap() -> None:
    if _CONNECTORS:
        return

    # local filesystem (real-local)
    register_connector(ConnectorDef(
        connector_id="local_fs", provider="local", display_name="Local Filesystem",
        category="local", capabilities=["read_local_file", "inspect_disk"],
        auth_type="local", local=True, risk_ceiling=RiskClass.LOCAL_READ,
        integration_status="live-tested"), A.LocalFilesystemAdapter())
    register_tool(_tool("local_fs", "read_local_file", "Read local file"))
    register_tool(_tool("local_fs", "inspect_disk", "Inspect disk"))

    # local git (real-local, read-only)
    register_connector(ConnectorDef(
        connector_id="local_git", provider="git", display_name="Local Git",
        category="git", capabilities=["inspect_repository"], auth_type="local",
        local=True, risk_ceiling=RiskClass.EXTERNAL_READ,
        integration_status="live-tested"), A.LocalGitAdapter())
    register_tool(_tool("local_git", "inspect_repository", "Inspect repository"))

    det = A.DeterministicAdapter()

    # GitHub (deterministic-adapter-tested; live env-blocked without token)
    register_connector(ConnectorDef(
        connector_id="github", provider="github", display_name="GitHub",
        category="git", auth_type="token", local=False,
        capabilities=["inspect_repository", "list_issues", "create_issue",
                      "create_branch", "open_pull_request", "push_branch", "inspect_ci"],
        required_credentials=["GITHUB_TOKEN"], risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT,
        webhook_support=True, integration_status="deterministic-adapter-tested"), det)
    register_tool(_tool("github", "inspect_repository", "GitHub inspect repo"))
    register_tool(_tool("github", "list_issues", "GitHub list issues"))
    register_tool(_tool("github", "create_issue", "GitHub create issue",
                       mutation=MutationClass.REVERSIBLE))
    register_tool(_tool("github", "create_branch", "GitHub create branch",
                       mutation=MutationClass.REVERSIBLE))
    register_tool(_tool("github", "open_pull_request", "GitHub open PR",
                       mutation=MutationClass.REVERSIBLE, idempotent=False))
    register_tool(_tool("github", "push_branch", "GitHub push", idempotent=False,
                       mutation=MutationClass.IRREVERSIBLE, reversible=False))

    # Gmail
    register_connector(ConnectorDef(
        connector_id="gmail", provider="google", display_name="Gmail",
        category="communication", auth_type="oauth", local=False,
        capabilities=["search_email", "read_email", "draft_email", "reply_email", "send_email"],
        required_credentials=["GMAIL_OAUTH"], risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT,
        integration_status="environment-blocked"), det)
    for cap, nm, mut, idem in [("search_email", "search", MutationClass.NONE, True),
                               ("read_email", "read", MutationClass.NONE, True),
                               ("draft_email", "draft", MutationClass.REVERSIBLE, True),
                               ("send_email", "send", MutationClass.IRREVERSIBLE, False),
                               ("reply_email", "reply", MutationClass.IRREVERSIBLE, False)]:
        register_tool(_tool("gmail", cap, f"Gmail {nm}", mutation=mut, idempotent=idem,
                           reversible=(mut != MutationClass.IRREVERSIBLE)))

    # Google Calendar
    register_connector(ConnectorDef(
        connector_id="gcal", provider="google", display_name="Google Calendar",
        category="calendar", auth_type="oauth", local=False,
        capabilities=["list_calendar_events", "create_calendar_event",
                      "update_calendar_event", "cancel_calendar_event"],
        required_credentials=["GCAL_OAUTH"], risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT,
        integration_status="environment-blocked"), det)
    register_tool(_tool("gcal", "list_calendar_events", "List events"))
    register_tool(_tool("gcal", "create_calendar_event", "Create event",
                       mutation=MutationClass.REVERSIBLE, idempotent=False))
    register_tool(_tool("gcal", "cancel_calendar_event", "Cancel event",
                       mutation=MutationClass.REVERSIBLE, idempotent=False))

    # Google Contacts (read only)
    register_connector(ConnectorDef(
        connector_id="gcontacts", provider="google", display_name="Google Contacts",
        category="contacts", auth_type="oauth", local=False,
        capabilities=["search_contacts"], required_credentials=["GCONTACTS_OAUTH"],
        risk_ceiling=RiskClass.EXTERNAL_READ,
        integration_status="environment-blocked"), det)
    register_tool(_tool("gcontacts", "search_contacts", "Search contacts"))

    # Telegram
    register_connector(ConnectorDef(
        connector_id="telegram", provider="telegram", display_name="Telegram",
        category="communication", auth_type="token", local=False,
        capabilities=["send_message", "send_notification"],
        required_credentials=["TELEGRAM_BOT_TOKEN"], webhook_support=True,
        risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT,
        integration_status="environment-blocked"), det)
    register_tool(_tool("telegram", "send_message", "Telegram send", idempotent=False,
                       mutation=MutationClass.IRREVERSIBLE, reversible=False))
    register_tool(_tool("telegram", "send_notification", "Telegram notify", idempotent=False,
                       mutation=MutationClass.IRREVERSIBLE, reversible=False))

    # Browser (bounded, via existing browser service)
    register_connector(ConnectorDef(
        connector_id="browser", provider="browser", display_name="Browser",
        category="browser", auth_type="none", local=True,
        capabilities=["open_url", "extract_page", "capture_screenshot"],
        risk_ceiling=RiskClass.EXTERNAL_READ,
        integration_status="deterministic-adapter-tested"), det)
    register_tool(_tool("browser", "open_url", "Open URL"))
    register_tool(_tool("browser", "extract_page", "Extract page"))

    # SQLite (local db)
    register_connector(ConnectorDef(
        connector_id="sqlite", provider="sqlite", display_name="SQLite",
        category="database", auth_type="local", local=True,
        capabilities=["inspect_schema", "query_database"],
        risk_ceiling=RiskClass.EXTERNAL_READ,
        integration_status="deterministic-adapter-tested"), det)
    register_tool(_tool("sqlite", "inspect_schema", "Inspect schema"))
    register_tool(_tool("sqlite", "query_database", "Query database"))

    # Deployment (Vercel/Firebase/local — contract-ready)
    register_connector(ConnectorDef(
        connector_id="deploy", provider="multi", display_name="Deployment",
        category="deployment", auth_type="token", local=False,
        capabilities=["inspect_deployment", "deploy_to_staging",
                      "deploy_to_production", "rollback_deployment", "inspect_logs"],
        risk_ceiling=RiskClass.HIGH_IMPACT, integration_status="contract-ready"), det)
    register_tool(_tool("deploy", "inspect_deployment", "Inspect deployment"))
    register_tool(_tool("deploy", "deploy_to_staging", "Deploy staging", idempotent=False,
                       mutation=MutationClass.IRREVERSIBLE, reversible=False))
    register_tool(_tool("deploy", "deploy_to_production", "Deploy production", idempotent=False,
                       mutation=MutationClass.IRREVERSIBLE, reversible=False))

    # AI Studio publishing (reuses M13; dry-run only here)
    register_connector(ConnectorDef(
        connector_id="studio_publish", provider="social", display_name="Studio Publishing",
        category="content", auth_type="oauth", local=False,
        capabilities=["publish_video", "publish_post"],
        risk_ceiling=RiskClass.EXTERNAL_SIDE_EFFECT,
        integration_status="environment-blocked"), det)
    register_tool(_tool("studio_publish", "publish_video", "Publish video", idempotent=False,
                       mutation=MutationClass.IRREVERSIBLE, reversible=False))


_bootstrap()
