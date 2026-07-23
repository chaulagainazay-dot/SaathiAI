"""M49.2 migrated / wrapped tools — safe waves only (fixtures for connectors)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.tool_runtime.context import BoundedToolContext, ToolCancelledError
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
from saathi.tool_runtime.subprocess_exec import run_bounded

ROOT = Path(__file__).resolve().parent.parent.parent.parent
ARTIFACT_DIR = ROOT / "data" / "tool_runtime" / "artifacts"
FILES_DIR = ROOT / "data" / "files"


# ── Wave A: read-only local ───────────────────────────────────────────────


def system_health_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.health import health_check

        data = health_check()
        if not isinstance(data, dict):
            data = {"status": "ok", "raw": str(data)[:500]}
    except Exception as exc:
        data = {"status": "degraded", "error_type": type(exc).__name__}
    # strip any secret-looking keys
    data = {k: v for k, v in data.items() if "token" not in k.lower() and "key" not in k.lower()}
    return {"data": {"health": data, "source": "saathi.health.health_check"}, "side_effect_confirmed": True}


def my_files_list_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(FILES_DIR.iterdir()):
        if p.is_file():
            items.append({"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)})
        if len(items) >= 100:
            break
    return {
        "data": {"files": items, "count": len(items), "root": "data/files"},
        "side_effect_confirmed": True,
    }


def list_open_tasks_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    try:
        from saathi.tools.notes import manage_tasks

        out = manage_tasks("list")
        tasks = out.get("open_tasks") if isinstance(out, dict) else []
        if not isinstance(tasks, list):
            tasks = []
    except Exception:
        tasks = []
    # normalize to simple list of dicts/strings
    safe = []
    for t in tasks[:50]:
        if isinstance(t, dict):
            safe.append({k: t[k] for k in list(t)[:6] if k not in ("password", "token")})
        else:
            safe.append({"title": str(t)[:200]})
    return {"data": {"open_tasks": safe, "count": len(safe)}, "side_effect_confirmed": True}


# ── Wave B: reversible local mutation + subprocess diag ───────────────────


def local_artifact_write_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    name = str(args.get("name", "")).replace("/", "_").replace("..", "")[:64]
    content = str(args.get("content", ""))[:4000]
    if not name:
        return {"error": "name required"}
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / name
    path.write_text(content, encoding="utf-8")
    ctx.evidence("artifact_write", {"name": name, "bytes": len(content.encode())})
    return {
        "data": {
            "written": True,
            "name": name,
            "bytes": len(content.encode()),
            "path_hint": "data/tool_runtime/artifacts",
        },
        "side_effect_confirmed": True,
    }


def subprocess_diag_adapter(args: dict, ctx: BoundedToolContext) -> dict:
    """Safe diagnostic: only allowlisted argv templates (no freeform shell)."""
    ctx.raise_if_cancelled()
    kind = str(args.get("kind", "uname"))
    allow = {
        "uname": ["uname", "-a"],
        "python_version": ["python3", "-c", "import sys; print(sys.version.split()[0])"],
        "echo_ok": ["echo", "m49.2-ok"],
    }
    argv = allow.get(kind)
    if not argv:
        return {"error": f"kind not allowlisted: {kind}"}
    res = run_bounded(
        argv,
        timeout_sec=min(float(args.get("timeout_sec") or 5), 10),
        cancel_check=ctx.should_cancel,
        grace_sec=0.5,
        allow_kill=True,
    )
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
            "error": "subprocess_failed",
            "data": {
                "exit_code": res.exit_code,
                "stderr": res.stderr[:500],
                "cancel_state": res.cancel_state,
            },
        }
    return {
        "data": {
            "kind": kind,
            "stdout": res.stdout.strip()[:2000],
            "exit_code": res.exit_code,
            "cancel_state": res.cancel_state,
            "duration_ms": res.duration_ms,
        },
        "side_effect_confirmed": True,
    }


# ── Wave C: connector fakes (read-only + mutation stub) ───────────────────


def gmail_search_fake(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    q = str(args.get("query", "is:unread"))[:200]
    limit = int(args.get("limit") or 5)
    limit = max(1, min(limit, 20))
    # fixture-only; no network
    messages = [
        {
            "id": f"msg_fake_{i}",
            "subject": f"[fixture] result {i} for {q[:40]}",
            "from": "noreply@example.test",
            "snippet": "fixture message — no live gmail",
        }
        for i in range(min(limit, 3))
    ]
    return {
        "data": {
            "messages": messages,
            "count": len(messages),
            "fixture": True,
            "connector": "gmail",
            "action": "search_messages",
        },
        "side_effect_confirmed": True,
    }


def gcal_list_fake(args: dict, ctx: BoundedToolContext) -> dict:
    ctx.raise_if_cancelled()
    days = int(args.get("days") or 1)
    events = [
        {
            "id": "evt_fake_1",
            "title": "Fixture calendar block",
            "when": "today",
            "days_window": days,
        }
    ]
    return {
        "data": {
            "events": events,
            "count": 1,
            "fixture": True,
            "connector": "gcal",
            "action": "list_events",
        },
        "side_effect_confirmed": True,
    }


def gmail_send_stub(args: dict, ctx: BoundedToolContext) -> dict:
    """Approval-gated external mutation stub — never sends email."""
    ctx.raise_if_cancelled()
    # Even if invoked, do not perform network I/O
    return {
        "data": {
            "queued": False,
            "sent": False,
            "stub": True,
            "to_domain": "example.test",
            "note": "M49.2 stub — live send prohibited in this milestone",
        },
        "side_effect_confirmed": True,
    }


def migrated_manifests() -> list[tuple[ToolManifest, Any]]:
    health = ToolManifest(
        tool_id="m49.system_health",
        version="1.0.0",
        display_name="System health (migrated)",
        description="Read-only system health via saathi.health.health_check",
        domain="saathi.tools",
        capabilities=("read", "health", "system_health"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {
                "health": {"type": "object"},
                "source": {"type": "string"},
            },
            "required": ["health", "source"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
        timeout_policy=TimeoutPolicy(default_sec=15, max_sec=60),
        idempotency_policy=IdempotencyPolicy(klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT),
    )
    files = ToolManifest(
        tool_id="m49.my_files_list",
        version="1.0.0",
        display_name="List uploaded files",
        description="List files in data/files (read-only)",
        domain="saathi.tools",
        capabilities=("read", "files", "my_files"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {
                "files": {"type": "array"},
                "count": {"type": "integer"},
                "root": {"type": "string"},
            },
            "required": ["files", "count"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    tasks = ToolManifest(
        tool_id="m49.list_open_tasks",
        version="1.0.0",
        display_name="List open tasks",
        description="Read-only open tasks list",
        domain="saathi.tools",
        capabilities=("read", "tasks", "manage_tasks"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        output_schema={
            "type": "object",
            "properties": {
                "open_tasks": {"type": "array"},
                "count": {"type": "integer"},
            },
            "required": ["open_tasks", "count"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    artifact = ToolManifest(
        tool_id="m49.local_artifact_write",
        version="1.0.0",
        display_name="Local artifact write",
        description="Write reversible artifact under data/tool_runtime/artifacts",
        domain="saathi.tools",
        capabilities=("write", "artifact"),
        authority_class=ToolAuthorityClass.LOCAL_MUTATION,
        side_effect_class=ToolSideEffectClass.LOCAL_REVERSIBLE,
        approval_requirement=ToolApprovalRequirement.EXPLICIT_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "maxLength": 64},
                "content": {"type": "string", "maxLength": 4000},
            },
            "required": ["name", "content"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "written": {"type": "boolean"},
                "name": {"type": "string"},
                "bytes": {"type": "integer"},
                "path_hint": {"type": "string"},
            },
            "required": ["written", "name", "bytes"],
        },
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED, require_key=True
        ),
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    sub = ToolManifest(
        tool_id="m49.subprocess_diag",
        version="1.0.0",
        display_name="Subprocess diagnostic",
        description="Allowlisted read-only subprocess diagnostics with cancel/timeout",
        domain="tool_runtime",
        capabilities=("diag", "subprocess"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["uname", "python_version", "echo_ok"]},
                "timeout_sec": {"type": "number"},
            },
            "required": ["kind"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "stdout": {"type": "string"},
                "exit_code": {"type": "integer"},
                "cancel_state": {"type": "string"},
                "duration_ms": {"type": "number"},
            },
            "required": ["kind", "stdout", "exit_code"],
        },
        timeout_policy=TimeoutPolicy(default_sec=5, max_sec=10, grace_sec=0.5),
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    gmail_search = ToolManifest(
        tool_id="m49.connector.gmail.search_messages",
        version="1.0.0",
        display_name="Gmail search (fixture)",
        description="Read-only Gmail search via fixture adapter — no live network",
        domain="connectors",
        capabilities=("read", "gmail.search_messages"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 200},
                "limit": {"type": "integer"},
            },
            "required": [],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "messages": {"type": "array"},
                "count": {"type": "integer"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
            },
            "required": ["messages", "count", "fixture"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
        idempotency_policy=IdempotencyPolicy(klass=ToolIdempotencyClass.NATURALLY_IDEMPOTENT),
    )
    gcal = ToolManifest(
        tool_id="m49.connector.gcal.list_events",
        version="1.0.0",
        display_name="Calendar list (fixture)",
        description="Read-only calendar list fixture — no live network",
        domain="connectors",
        capabilities=("read", "gcal.list_events"),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.BROKERED_CLIENT_ONLY,
        input_schema={
            "type": "object",
            "properties": {"days": {"type": "integer"}},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "events": {"type": "array"},
                "count": {"type": "integer"},
                "fixture": {"type": "boolean"},
                "connector": {"type": "string"},
                "action": {"type": "string"},
            },
            "required": ["events", "count", "fixture"],
        },
        cancellation_support=ToolCancellationSupport.COOPERATIVE_CANCEL_SUPPORTED,
    )
    gmail_send = ToolManifest(
        tool_id="m49.connector.gmail.send_message",
        version="1.0.0",
        display_name="Gmail send (stub)",
        description="External mutation stub — requires approval; never sends live",
        domain="connectors",
        capabilities=("write", "gmail.send_message"),
        authority_class=ToolAuthorityClass.EXTERNAL_MUTATION,
        side_effect_class=ToolSideEffectClass.EXTERNAL_IRREVERSIBLE,
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
                "queued": {"type": "boolean"},
                "sent": {"type": "boolean"},
                "stub": {"type": "boolean"},
                "to_domain": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["sent", "stub"],
        },
        idempotency_policy=IdempotencyPolicy(
            klass=ToolIdempotencyClass.IDEMPOTENCY_KEY_REQUIRED, require_key=True
        ),
        retry_policy=RetryPolicy(max_attempts=1, retry_class=ToolRetryClass.NEVER),
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )

    return [
        (health, system_health_adapter),
        (files, my_files_list_adapter),
        (tasks, list_open_tasks_adapter),
        (artifact, local_artifact_write_adapter),
        (sub, subprocess_diag_adapter),
        (gmail_search, gmail_search_fake),
        (gcal, gcal_list_fake),
        (gmail_send, gmail_send_stub),
    ]


# Legacy name aliases for compatibility bridge
LEGACY_NAME_MAP = {
    "system_health": "m49.system_health",
    "my_files": "m49.my_files_list",  # list-only path
    "manage_tasks": "m49.list_open_tasks",  # list-only via action=list
}
