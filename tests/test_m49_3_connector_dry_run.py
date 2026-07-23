"""M49.3 connector dry-run gates — no live mutation."""
from __future__ import annotations

import time

from saathi.tool_runtime.contracts import ToolApprovalReference, ToolExecutionRequest
from saathi.tool_runtime.durable_idempotency import DurableIdempotencyStore
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.tool_runtime.service import ToolExecutionService


def _svc(tmp_path):
    return ToolExecutionService(
        registry=reset_registry_for_tests(),
        idempotency=DurableIdempotencyStore(tmp_path / "i.db"),
    )


def _ap(tool_id: str, side: str, action: str = "", connector: str = ""):
    return ToolApprovalReference(
        approval_id="ap",
        tool_id=tool_id,
        capability="write",
        action=action,
        connector=connector,
        run_id="r",
        side_effect_class=side,
        authority="EXTERNAL_MUTATION",
        expires_at=time.time() + 999,
    )


def test_gmail_send_dry_run_never_sends(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.send_message",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=_ap(
                "m49.connector.gmail.send_message",
                "EXTERNAL_IRREVERSIBLE",
                "send_message",
                "gmail",
            ),
            idempotency_key="dry1",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["sent"] is False
    assert r.data["network_performed"] is False
    assert r.data["mutation_performed"] is False
    assert r.data.get("execution_mode") == "DRY_RUN_ONLY"


def test_gmail_create_draft_dry_run(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gmail.create_draft",
            arguments={"to": "a@example.test", "subject": "s", "body": "b"},
            approval_reference=_ap(
                "m49.connector.gmail.create_draft",
                "EXTERNAL_REVERSIBLE",
                "create_draft",
                "gmail",
            ),
            idempotency_key="dry2",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["draft_created"] is False
    assert r.data["network_performed"] is False
    assert r.data["mutation_performed"] is False


def test_gcal_create_event_dry_run(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.gcal.create_event",
            arguments={"title": "Meet"},
            approval_reference=_ap(
                "m49.connector.gcal.create_event",
                "EXTERNAL_REVERSIBLE",
                "create_event",
                "gcal",
            ),
            idempotency_key="dry3",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["event_created"] is False
    assert r.data["network_performed"] is False


def test_github_create_issue_dry_run(tmp_path):
    svc = _svc(tmp_path)
    r = svc.execute_tool(
        ToolExecutionRequest(
            run_id="r",
            tool_id="m49.connector.github.create_issue",
            arguments={"repo": "ex/repo", "title": "bug"},
            approval_reference=_ap(
                "m49.connector.github.create_issue",
                "EXTERNAL_REVERSIBLE",
                "create_issue",
                "github",
            ),
            idempotency_key="dry4",
            capability="write",
        )
    )
    assert r.ok
    assert r.data["issue_created"] is False
    assert r.data["mutation_performed"] is False


def test_dry_run_idempotency_replay(tmp_path):
    svc = _svc(tmp_path)
    req = ToolExecutionRequest(
        run_id="r",
        tool_id="m49.connector.gmail.create_draft",
        arguments={"to": "a@example.test", "subject": "s", "body": "b"},
        approval_reference=_ap(
            "m49.connector.gmail.create_draft",
            "EXTERNAL_REVERSIBLE",
            "create_draft",
            "gmail",
        ),
        idempotency_key="dry-replay",
        capability="write",
    )
    r1 = svc.execute_tool(req)
    r2 = svc.execute_tool(req)
    assert r1.ok and r2.ok
    assert r1.data["mutation_performed"] is False
    assert r2.data["mutation_performed"] is False
