"""M49.3 additional migrations, allowlisted commands, and connector dry-run actions."""
from __future__ import annotations

from typing import Any

from saathi.tool_runtime.command_manifest import (
    CommandManifestError,
    run_allowlisted_command,
)
from saathi.tool_runtime.context import BoundedToolContext
from saathi.tool_runtime.contracts import (
    IdempotencyPolicy,
    RetryPolicy,
    TimeoutPolicy,
    ToolApprovalRequirement,
    ToolAuthorityClass,
    ToolAvailability,
    ToolCancellationSupport,
    ToolIdempotencyClass,
    ToolManifest,
    ToolRetryClass,
    ToolSecretPolicy,
    ToolSideEffectClass,
)


def _safe_call(fn, *args, **kwargs):
    try:
        out = fn(*args, **kwargs)
        return out if isinstance(out, dict) else {"value": out}
    except Exception as exc:
        return {"error_type": type(exc).__name__, "ok": False}


# ── Additional read-only migrations ───────────────────────────────────────


def list_projects_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.tools import projects

        out = projects.list_projects()
        if not isinstance(out, dict):
            out = {"projects": out if isinstance(out, list) else []}
    except Exception:
        out = {"projects": []}
    # redact paths somewhat
    projects_list = out.get("projects") or out.get("items") or []
    if not isinstance(projects_list, list):
        projects_list = []
    safe = []
    for p in projects_list[:50]:
        if isinstance(p, dict):
            safe.append(
                {
                    k: p[k]
                    for k in list(p)[:8]
                    if k.lower() not in ("token", "password", "secret")
                }
            )
        else:
            safe.append({"name": str(p)[:120]})
    return {
        "data": {"projects": safe, "count": len(safe), "fixture": False},
        "side_effect_confirmed": True,
    }


def list_reminders_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.tools import calendar as cal

        out = cal.list_reminders()
        items = out if isinstance(out, list) else (out.get("reminders") if isinstance(out, dict) else [])
        if not isinstance(items, list):
            items = []
    except Exception:
        items = []
    safe = []
    for r in items[:30]:
        if isinstance(r, dict):
            safe.append({k: r[k] for k in list(r)[:6]})
        else:
            safe.append({"title": str(r)[:200]})
    return {
        "data": {"reminders": safe, "count": len(safe)},
        "side_effect_confirmed": True,
    }


def list_social_connections_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.tools import content

        out = content.list_connections()
        if not isinstance(out, dict):
            out = {"connections": out if isinstance(out, list) else []}
    except Exception:
        out = {"connections": []}
    conns = out.get("connections") or out.get("platforms") or []
    if not isinstance(conns, list):
        conns = []
    safe = []
    for c in conns[:20]:
        if isinstance(c, dict):
            safe.append(
                {
                    k: c[k]
                    for k in list(c)[:6]
                    if "token" not in k.lower() and "secret" not in k.lower()
                }
            )
        else:
            safe.append({"name": str(c)[:80]})
    return {
        "data": {"connections": safe, "count": len(safe)},
        "side_effect_confirmed": True,
    }


def list_blueprints_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.tools import n8n_tools

        out = n8n_tools.list_blueprints()
        if not isinstance(out, dict):
            out = {"blueprints": out if isinstance(out, list) else []}
    except Exception:
        out = {"blueprints": []}
    bps = out.get("blueprints") or out.get("items") or []
    if not isinstance(bps, list):
        bps = []
    safe = []
    for b in bps[:40]:
        if isinstance(b, dict):
            safe.append({k: b[k] for k in list(b)[:6] if "token" not in k.lower()})
        else:
            safe.append({"name": str(b)[:120]})
    return {
        "data": {"blueprints": safe, "count": len(safe)},
        "side_effect_confirmed": True,
    }


def performance_report_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi import analytics

        out = analytics.performance_report()
        if not isinstance(out, dict):
            out = {"report": str(out)[:2000]}
    except Exception as exc:
        out = {"status": "degraded", "error_type": type(exc).__name__}
    cleaned = {
        k: v
        for k, v in out.items()
        if "token" not in k.lower() and "key" not in k.lower() and "secret" not in k.lower()
    }
    return {
        "data": {"report": cleaned, "source": "saathi.analytics.performance_report"},
        "side_effect_confirmed": True,
    }


def todays_events_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.tools import calendar as cal

        # prefer todays_events if present
        if hasattr(cal, "todays_events"):
            out = cal.todays_events()
        elif hasattr(cal, "list_events"):
            out = cal.list_events()
        else:
            out = {"events": []}
        if not isinstance(out, dict):
            out = {"events": out if isinstance(out, list) else []}
    except Exception:
        out = {"events": []}
    events = out.get("events") or []
    if not isinstance(events, list):
        events = []
    safe = []
    for e in events[:30]:
        if isinstance(e, dict):
            safe.append({k: e[k] for k in list(e)[:6]})
        else:
            safe.append({"title": str(e)[:200]})
    return {
        "data": {"events": safe, "count": len(safe)},
        "side_effect_confirmed": True,
    }


# ── Allowlisted command tool ──────────────────────────────────────────────


def allowlisted_command_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    command_id = str(args.get("command_id") or "")
    timeout_sec = args.get("timeout_sec")
    try:
        res = run_allowlisted_command(
            command_id,
            timeout_sec=float(timeout_sec) if timeout_sec is not None else None,
            cancel_check=ctx.should_cancel,
            grace_sec=0.5,
        )
    except CommandManifestError as exc:
        return {"error": f"{exc.code}: {exc.message}"}
    if res.cancellation_confirmed:
        return {
            "cancelled": True,
            "data": res.to_dict(),
            "side_effect_confirmed": True,
        }
    if res.timeout_detected:
        return {
            "timeout": True,
            "data": res.to_dict(),
            "side_effect_confirmed": True,
        }
    if not res.ok:
        return {
            "error": "command_failed",
            "data": {
                "command_id": command_id,
                "exit_code": res.exit_code,
                "stderr": res.stderr[:500],
                "cancel_state": res.cancel_state,
            },
        }
    return {
        "data": {
            "command_id": command_id,
            "stdout": res.stdout.strip()[:2000],
            "exit_code": res.exit_code,
            "cancel_state": res.cancel_state,
            "duration_ms": res.duration_ms,
            "shell": False,
        },
        "side_effect_confirmed": True,
    }


# ── Connector dry-run + extended action catalog ───────────────────────────


def _dry_run_preview(
    *,
    connector: str,
    action: str,
    args: dict,
    authority: str,
    side_effect: str,
    approval_required: bool,
    idempotency_required: bool,
) -> dict:
    return {
        "validated_action": f"{connector}.{action}",
        "validated_arguments": {
            k: v
            for k, v in args.items()
            if k.lower()
            not in (
                "access_token",
                "refresh_token",
                "password",
                "cookie",
                "authorization",
                "api_key",
                "private_key",
            )
        },
        "resolved_authority": authority,
        "required_approval": approval_required,
        "target_connector": connector,
        "expected_side_effect_class": side_effect,
        "idempotency_requirement": idempotency_required,
        "safe_preview": f"DRY_RUN: would perform {connector}.{action}",
        "network_performed": False,
        "mutation_performed": False,
        "execution_mode": "DRY_RUN_ONLY",
        "fixture": True,
    }


def gmail_read_message_fake(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    mid = str(args.get("message_id") or "msg_fake_0")[:80]
    return {
        "data": {
            "message_id": mid,
            "subject": "[fixture] read message",
            "from": "noreply@example.test",
            "body_preview": "fixture body — no live gmail",
            "fixture": True,
            "connector": "gmail",
            "action": "read_message",
            "network_performed": False,
        },
        "side_effect_confirmed": True,
    }


def gmail_create_draft_dry_run(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    preview = _dry_run_preview(
        connector="gmail",
        action="create_draft",
        args=args,
        authority="EXTERNAL_MUTATION",
        side_effect="EXTERNAL_REVERSIBLE",
        approval_required=True,
        idempotency_required=True,
    )
    preview["to"] = str(args.get("to") or "")[:120]
    preview["subject"] = str(args.get("subject") or "")[:200]
    preview["draft_created"] = False
    return {"data": preview, "side_effect_confirmed": True}


def gmail_send_message_dry_run(args: dict, ctx: BoundedToolContext) -> dict:
    """Replaces live-send risk — always dry-run."""
    ctx.raise_if_cancelled()
    preview = _dry_run_preview(
        connector="gmail",
        action="send_message",
        args=args,
        authority="EXTERNAL_MUTATION",
        side_effect="EXTERNAL_IRREVERSIBLE",
        approval_required=True,
        idempotency_required=True,
    )
    preview["queued"] = False
    preview["sent"] = False
    preview["stub"] = True
    preview["to_domain"] = "example.test"
    preview["note"] = "M49.3 dry-run only — live send prohibited"
    return {"data": preview, "side_effect_confirmed": True}


def gcal_read_event_fake(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    eid = str(args.get("event_id") or "evt_fake_1")[:80]
    return {
        "data": {
            "event_id": eid,
            "title": "Fixture event",
            "when": "today",
            "fixture": True,
            "connector": "gcal",
            "action": "read_event",
            "network_performed": False,
        },
        "side_effect_confirmed": True,
    }


def gcal_create_event_dry_run(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    preview = _dry_run_preview(
        connector="gcal",
        action="create_event",
        args=args,
        authority="EXTERNAL_MUTATION",
        side_effect="EXTERNAL_REVERSIBLE",
        approval_required=True,
        idempotency_required=True,
    )
    preview["event_created"] = False
    preview["title"] = str(args.get("title") or "")[:200]
    return {"data": preview, "side_effect_confirmed": True}


def github_read_repository_fake(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    repo = str(args.get("repo") or "example/repo")[:120]
    return {
        "data": {
            "repo": repo,
            "default_branch": "main",
            "fixture": True,
            "connector": "github",
            "action": "read_repository",
            "network_performed": False,
        },
        "side_effect_confirmed": True,
    }


def github_read_pull_request_fake(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    repo = str(args.get("repo") or "example/repo")[:120]
    number = int(args.get("number") or 1)
    return {
        "data": {
            "repo": repo,
            "number": number,
            "title": "[fixture] pull request",
            "state": "open",
            "fixture": True,
            "connector": "github",
            "action": "read_pull_request",
            "network_performed": False,
        },
        "side_effect_confirmed": True,
    }


def github_create_issue_dry_run(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    preview = _dry_run_preview(
        connector="github",
        action="create_issue",
        args=args,
        authority="EXTERNAL_MUTATION",
        side_effect="EXTERNAL_REVERSIBLE",
        approval_required=True,
        idempotency_required=True,
    )
    preview["issue_created"] = False
    preview["title"] = str(args.get("title") or "")[:200]
    return {"data": preview, "side_effect_confirmed": True}


def browser_inspect_page_deferred(args: dict, ctx: BoundedToolContext) -> dict:
    """Discovery-safe read-only stub — no live browser."""
    ctx.raise_if_cancelled()
    return {
        "data": {
            "url": str(args.get("url") or "")[:300],
            "fixture": True,
            "connector": "browser",
            "action": "inspect_page",
            "network_performed": False,
            "mutation_performed": False,
            "note": "M49.3 browser inspect is fixture-only; live browser deferred",
        },
        "side_effect_confirmed": True,
    }


def m49_3_manifests() -> list[tuple[ToolManifest, Any]]:
    out: list[tuple[ToolManifest, Any]] = []

    def ro(
        tool_id: str,
        display: str,
        desc: str,
        caps: tuple[str, ...],
        adapter,
        input_schema: dict,
        output_schema: dict,
        domain: str = "saathi.tools",
    ):
        return ToolManifest(
            tool_id=tool_id,
            version="1.0.0",
            display_name=display,
            description=desc,
            domain=domain,
            capabilities=caps,
            authority_class=ToolAuthorityClass.READ_ONLY,
            side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
            approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
            secret_policy=ToolSecretPolicy.NO_SECRET
            if domain != "connectors"
            else ToolSecretPolicy.BROKERED_CLIENT_ONLY,
            input_schema=input_schema,
            output_schema=output_schema,
            cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
            timeout_policy=TimeoutPolicy(default_sec=15, max_sec=60),
            idempotency_policy=IdempotencyPolicy(
                klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT
            ),
        )

    out.append(
        (
            ro(
                "m49.list_projects",
                "List projects",
                "Read-only registered projects list",
                ("read", "projects", "list_projects"),
                list_projects_adapter,
                {"type": "object", "properties": {}, "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {
                        "projects": {"type": "array"},
                        "count": {"type": "integer"},
                        "fixture": {"type": "boolean"},
                    },
                    "required": ["projects", "count"],
                },
            ),
            list_projects_adapter,
        )
    )
    out.append(
        (
            ro(
                "m49.list_reminders",
                "List reminders",
                "Read-only reminders list",
                ("read", "reminders", "list_reminders"),
                list_reminders_adapter,
                {"type": "object", "properties": {}, "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {
                        "reminders": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                    "required": ["reminders", "count"],
                },
            ),
            list_reminders_adapter,
        )
    )
    out.append(
        (
            ro(
                "m49.list_social_connections",
                "List social connections",
                "Read-only social connection list",
                ("read", "social", "list_social_connections"),
                list_social_connections_adapter,
                {"type": "object", "properties": {}, "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {
                        "connections": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                    "required": ["connections", "count"],
                },
            ),
            list_social_connections_adapter,
        )
    )
    out.append(
        (
            ro(
                "m49.list_blueprints",
                "List n8n blueprints",
                "Read-only blueprint list (no trigger)",
                ("read", "n8n", "list_blueprints"),
                list_blueprints_adapter,
                {"type": "object", "properties": {}, "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {
                        "blueprints": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                    "required": ["blueprints", "count"],
                },
            ),
            list_blueprints_adapter,
        )
    )
    out.append(
        (
            ro(
                "m49.performance_report",
                "Performance report",
                "Read-only analytics performance report",
                ("read", "analytics", "performance_report"),
                performance_report_adapter,
                {"type": "object", "properties": {}, "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {
                        "report": {"type": "object"},
                        "source": {"type": "string"},
                    },
                    "required": ["report", "source"],
                },
            ),
            performance_report_adapter,
        )
    )
    out.append(
        (
            ro(
                "m49.todays_events",
                "Today's events",
                "Read-only today's calendar events",
                ("read", "calendar", "todays_events"),
                todays_events_adapter,
                {"type": "object", "properties": {}, "additionalProperties": False},
                {
                    "type": "object",
                    "properties": {
                        "events": {"type": "array"},
                        "count": {"type": "integer"},
                    },
                    "required": ["events", "count"],
                },
            ),
            todays_events_adapter,
        )
    )

    # Allowlisted command
    cmd_m = ToolManifest(
        tool_id="m49.allowlisted_command",
        version="1.0.0",
        display_name="Allowlisted command",
        description="Execute a code-owned allowlisted command (no freeform shell)",
        domain="tool_runtime",
        capabilities=("diag", "subprocess", "allowlisted_command"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {
                "command_id": {
                    "type": "string",
                    "enum": [
                        "uname",
                        "python_version",
                        "echo_ok",
                        "pwd",
                        "git_status",
                        "git_rev_parse_head",
                        "ls_data_files",
                    ],
                },
                "timeout_sec": {"type": "number"},
            },
            "required": ["command_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "command_id": {"type": "string"},
                "stdout": {"type": "string"},
                "exit_code": {"type": "integer"},
                "cancel_state": {"type": "string"},
                "duration_ms": {"type": "number"},
                "shell": {"type": "boolean"},
            },
            "required": ["command_id", "stdout", "exit_code", "shell"],
        },
        timeout_policy=TimeoutPolicy(default_sec=10, max_sec=30, grace_sec=0.5),
        cancellation_support=ToolCancellationSupport.HARD_CANCEL_SUPPORTED,
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT
        ),
    )
    out.append((cmd_m, allowlisted_command_adapter))

    # Connector actions
    gmail_read = ToolManifest(
        tool_id="m49.connector.gmail.read_message",
        version="1.0.0",
        display_name="Gmail read message (fixture)",
        description="Read-only gmail message fixture",
        domain="connectors",
        capabilities=("read", "gmail.read_message"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {"message_id": {"type": "string"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "message_id": {"type": "string"},
                "subject": {"type": "string"},
                "from": {"type": "string"},
                "body_preview": {"type": "string"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
                "network_performed": {"type": "boolean"},
            },
            "required": ["message_id", "fixture", "connector", "action"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    out.append((gmail_read, gmail_read_message_fake))

    gmail_draft = ToolManifest(
        tool_id="m49.connector.gmail.create_draft",
        version="1.0.0",
        display_name="Gmail create draft (dry-run)",
        description="External mutation dry-run — never creates live draft",
        domain="connectors",
        capabilities=("write", "gmail.create_draft"),
        authority_class=ToolAuthorityClass.EXTERNAL_MUTATION,
        side_effect_class=ToolSideEffectClass.EXTERNAL_REVERSIBLE,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "validated_action": {"type": "string"},
                "network_performed": {"type": "boolean"},
                "mutation_performed": {"type": "boolean"},
                "execution_mode": {"type": "string"},
                "draft_created": {"type": "boolean"},
            },
            "required": [
                "validated_action",
                "network_performed",
                "mutation_performed",
                "execution_mode",
            ],
        },
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED, require_key=True
        ),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )
    out.append((gmail_draft, gmail_create_draft_dry_run))

    # gmail.send_message remains registered in migrated.py (M49.2) with M49.3 dry-run body

    gcal_read = ToolManifest(
        tool_id="m49.connector.gcal.read_event",
        version="1.0.0",
        display_name="Calendar read event (fixture)",
        description="Read-only calendar event fixture",
        domain="connectors",
        capabilities=("read", "gcal.read_event"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "title": {"type": "string"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
                "network_performed": {"type": "boolean"},
            },
            "required": ["event_id", "fixture", "connector", "action"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    out.append((gcal_read, gcal_read_event_fake))

    gcal_create = ToolManifest(
        tool_id="m49.connector.gcal.create_event",
        version="1.0.0",
        display_name="Calendar create event (dry-run)",
        description="External mutation dry-run — never creates live event",
        domain="connectors",
        capabilities=("write", "gcal.create_event"),
        authority_class=ToolAuthorityClass.EXTERNAL_MUTATION,
        side_effect_class=ToolSideEffectClass.EXTERNAL_REVERSIBLE,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "when": {"type": "string"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "validated_action": {"type": "string"},
                "network_performed": {"type": "boolean"},
                "mutation_performed": {"type": "boolean"},
                "execution_mode": {"type": "string"},
                "event_created": {"type": "boolean"},
            },
            "required": [
                "validated_action",
                "network_performed",
                "mutation_performed",
                "execution_mode",
            ],
        },
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED, require_key=True
        ),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )
    out.append((gcal_create, gcal_create_event_dry_run))

    gh_repo = ToolManifest(
        tool_id="m49.connector.github.read_repository",
        version="1.0.0",
        display_name="GitHub read repository (fixture)",
        description="Read-only repository fixture — no live GitHub mutation",
        domain="connectors",
        capabilities=("read", "github.read_repository"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {"repo": {"type": "string"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "default_branch": {"type": "string"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
                "network_performed": {"type": "boolean"},
            },
            "required": ["repo", "fixture", "connector", "action"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    out.append((gh_repo, github_read_repository_fake))

    gh_pr = ToolManifest(
        tool_id="m49.connector.github.read_pull_request",
        version="1.0.0",
        display_name="GitHub read PR (fixture)",
        description="Read-only pull request fixture",
        domain="connectors",
        capabilities=("read", "github.read_pull_request"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "number": {"type": "integer"},
                "title": {"type": "string"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
                "network_performed": {"type": "boolean"},
            },
            "required": ["repo", "number", "fixture", "connector", "action"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    out.append((gh_pr, github_read_pull_request_fake))

    gh_issue = ToolManifest(
        tool_id="m49.connector.github.create_issue",
        version="1.0.0",
        display_name="GitHub create issue (dry-run)",
        description="External mutation dry-run — never creates live issues",
        domain="connectors",
        capabilities=("write", "github.create_issue"),
        authority_class=ToolAuthorityClass.EXTERNAL_MUTATION,
        side_effect_class=ToolSideEffectClass.EXTERNAL_REVERSIBLE,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "repo": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["repo", "title"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "validated_action": {"type": "string"},
                "network_performed": {"type": "boolean"},
                "mutation_performed": {"type": "boolean"},
                "execution_mode": {"type": "string"},
                "issue_created": {"type": "boolean"},
            },
            "required": [
                "validated_action",
                "network_performed",
                "mutation_performed",
                "execution_mode",
            ],
        },
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED, require_key=True
        ),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )
    out.append((gh_issue, github_create_issue_dry_run))

    browser = ToolManifest(
        tool_id="m49.connector.browser.inspect_page",
        version="1.0.0",
        display_name="Browser inspect (fixture)",
        description="Read-only page inspect fixture — live browser deferred",
        domain="connectors",
        capabilities=("read", "browser.inspect_page"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
                "network_performed": {"type": "boolean"},
                "mutation_performed": {"type": "boolean"},
            },
            "required": ["fixture", "connector", "action", "network_performed"],
        },
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )
    out.append((browser, browser_inspect_page_deferred))

    # Financial advisory (allowed) vs execution (prohibited already in builtins)
    fin_adv = ToolManifest(
        tool_id="m49.financial_advisory_stub",
        version="1.0.0",
        display_name="Financial advisory (read/analysis)",
        description="Advisory-only market/portfolio analysis stub — no order execution",
        domain="finance",
        capabilities=("read", "financial_advisory"),
        authority_class=ToolAuthorityClass.FINANCIAL_ADVISORY,
        side_effect_class=ToolSideEffectClass.FINANCIAL_ADVISORY,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}, "question": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "advisory": {"type": "string"},
                "live_execution": {"type": "boolean"},
                "paper_only": {"type": "boolean"},
            },
            "required": ["symbol", "advisory", "live_execution", "paper_only"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT
        ),
    )

    def financial_advisory_adapter(args: dict, ctx: BoundedToolContext) -> dict:
        ctx.raise_if_cancelled()
        sym = str(args.get("symbol") or "").upper()[:16]
        return {
            "data": {
                "symbol": sym,
                "advisory": f"Advisory analysis only for {sym}; no order placed.",
                "live_execution": False,
                "paper_only": True,
            },
            "side_effect_confirmed": True,
        }

    out.append((fin_adv, financial_advisory_adapter))

    return out


# Extend legacy name map for M49.3
LEGACY_NAME_MAP_M49_3: dict[str, str] = {
    "list_projects": "m49.list_projects",
    "list_reminders": "m49.list_reminders",
    "list_social_connections": "m49.list_social_connections",
    "list_blueprints": "m49.list_blueprints",
    "performance_report": "m49.performance_report",
    "todays_events": "m49.todays_events",
    "check_email": "m49.connector.gmail.search_messages",
    "send_email": "m49.connector.gmail.send_message",
}
