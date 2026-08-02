"""Regression tests for the SaathiOS full end-to-end functional audit.

Each test pins a defect that was reproducible through the running platform API
before repair. Test ids match docs/e2e-functional-audit/BASELINE_DEFECTS.json.
"""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.service import reset_platform_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests


@pytest.fixture()
def plat(tmp_path):
    reset_registry_for_tests()
    return reset_platform_for_tests(tmp_path / "e2e.db")


def _owner_ctx(plat):
    plat.bootstrap_owner(email="owner@local", name="Owner")
    token = plat.login(email="owner@local")["token"]
    return token, plat.require_context(token)


def _project(plat, ctx, name="E2E Project"):
    return plat.create_project(ctx, name=name)


# ── DEFECT-001 ────────────────────────────────────────────────────────────────
# Re-submitting a mission key that already exists in the organization raised
# sqlite3.IntegrityError straight out of the store. FastAPI turned that into a
# bare HTTP 500 with a stack trace in the server log and no usable message for
# the operator, so duplicate-submission prevention was not observable in the UI.


def test_duplicate_mission_key_raises_conflict_not_integrity_error(plat):
    _token, ctx = _owner_ctx(plat)
    proj = _project(plat, ctx)
    plat.create_mission(ctx, proj["project_id"], "dup-key", "First")

    with pytest.raises(PlatformContextError) as excinfo:
        plat.create_mission(ctx, proj["project_id"], "dup-key", "Second")

    assert excinfo.value.code == "MISSION_KEY_EXISTS"
    assert "already exists" in excinfo.value.message


def test_duplicate_mission_key_does_not_create_a_second_mission(plat):
    _token, ctx = _owner_ctx(plat)
    proj = _project(plat, ctx)
    plat.create_mission(ctx, proj["project_id"], "dup-key", "First")
    with pytest.raises(PlatformContextError):
        plat.create_mission(ctx, proj["project_id"], "dup-key", "Second")

    missions = plat.store.list_missions(project_id=proj["project_id"])
    assert [m.key for m in missions] == ["dup-key"]


def test_distinct_mission_keys_still_create_missions(plat):
    _token, ctx = _owner_ctx(plat)
    proj = _project(plat, ctx)
    a = plat.create_mission(ctx, proj["project_id"], "key-a", "A")
    b = plat.create_mission(ctx, proj["project_id"], "key-b", "B")
    assert a["mission_id"] != b["mission_id"]


def test_mission_key_exists_maps_to_http_409():
    from saathi.platform.api import _err

    exc = _err(PlatformContextError("MISSION_KEY_EXISTS", "mission key already exists"))
    assert exc.status_code == 409


# ── DEFECT-002 ────────────────────────────────────────────────────────────────
# request_approval stored any caller-supplied authority / side_effect_class /
# capability verbatim. The gateway matches those against the tool manifest
# exactly, so a contradictory request was accepted, routed to a human, approved,
# and only then rejected at dispatch as an unattributed "approval invalid".


def test_approval_rejects_side_effect_class_the_tool_cannot_satisfy(plat):
    _token, ctx = _owner_ctx(plat)
    with pytest.raises(PlatformContextError) as excinfo:
        plat.request_approval(
            ctx,
            tool_id="m49.local_note_write",
            action="write",
            capability="write",
            authority="LOCAL_MUTATION",
            side_effect_class="LOCAL_IRREVERSIBLE",  # manifest says LOCAL_REVERSIBLE
        )
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert "side_effect_class" in excinfo.value.message
    assert "LOCAL_REVERSIBLE" in excinfo.value.message


def test_approval_rejects_capability_the_tool_does_not_declare(plat):
    _token, ctx = _owner_ctx(plat)
    with pytest.raises(PlatformContextError) as excinfo:
        plat.request_approval(
            ctx, tool_id="m49.local_note_write", capability="delete_everything"
        )
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert "capability" in excinfo.value.message


def test_approval_rejects_authority_the_tool_does_not_declare(plat):
    _token, ctx = _owner_ctx(plat)
    with pytest.raises(PlatformContextError) as excinfo:
        plat.request_approval(
            ctx, tool_id="m49.local_note_write", authority="EXTERNAL_MUTATION"
        )
    assert excinfo.value.code == "VALIDATION_FAILED"
    assert "authority" in excinfo.value.message


def test_unsatisfiable_approval_is_never_persisted(plat):
    _token, ctx = _owner_ctx(plat)
    with pytest.raises(PlatformContextError):
        plat.request_approval(
            ctx,
            tool_id="m49.local_note_write",
            capability="write",
            side_effect_class="LOCAL_IRREVERSIBLE",
        )
    assert plat.inbox(ctx, status="pending") == []


def test_manifest_consistent_approval_is_still_accepted(plat):
    _token, ctx = _owner_ctx(plat)
    rec = plat.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        action="write",
        capability="write",
        authority="LOCAL_MUTATION",
        side_effect_class="LOCAL_REVERSIBLE",
    )
    assert rec.approval_id


def test_partially_specified_approval_scope_is_still_accepted(plat):
    """Omitted fields keep the previous permissive behaviour."""
    _token, ctx = _owner_ctx(plat)
    rec = plat.request_approval(ctx, tool_id="m49.local_note_write", capability="write")
    assert rec.approval_id


def test_unregistered_tool_id_keeps_permissive_request_behaviour(plat):
    """Dynamic connector grants have no manifest; they validate at dispatch."""
    _token, ctx = _owner_ctx(plat)
    rec = plat.request_approval(
        ctx,
        tool_id="m49.connector.github.issue_create",
        capability="write",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        authority="EXTERNAL_MUTATION",
    )
    assert rec.approval_id


# ── DEFECT-005 ────────────────────────────────────────────────────────────────
# POST /api/v1/platform/auth/login with only {"email": ...} routed to the M50
# passwordless compatibility path and issued a full session for that user —
# including owner. The rendered /platform console had no password field at all,
# so the login gate could be walked straight through from the UI with nothing
# but a known invitee address. RBAC and workspace isolation were both moot.

_STRONG_PASSWORD = "e2e-Recovery-Passphrase-9!"


def _secure_owner(plat):
    return plat.bootstrap_owner_secure(
        email="owner@local", name="Owner", password=_STRONG_PASSWORD
    )


def test_passwordless_login_is_refused_for_a_credentialed_account(plat):
    _secure_owner(plat)
    with pytest.raises(PlatformContextError) as excinfo:
        plat.login(email="owner@local")
    assert excinfo.value.code == "AUTH_FAILED"


def test_passwordless_refusal_does_not_reveal_why(plat):
    """The message must not distinguish 'no such user' from 'needs a password'."""
    _secure_owner(plat)
    with pytest.raises(PlatformContextError) as credentialed:
        plat.login(email="owner@local")
    with pytest.raises(PlatformContextError) as unknown:
        plat.login(email="nobody@local")
    assert credentialed.value.code == unknown.value.code == "AUTH_FAILED"


def test_correct_password_still_authenticates(plat):
    _secure_owner(plat)
    result = plat.authenticate_login(email="owner@local", password=_STRONG_PASSWORD)
    assert result["token"]
    assert result["session"]["role"] == "owner"


def test_wrong_password_is_rejected(plat):
    _secure_owner(plat)
    with pytest.raises(PlatformContextError) as excinfo:
        plat.authenticate_login(email="owner@local", password="not-the-password")
    assert excinfo.value.code == "AUTH_FAILED"


def test_empty_password_is_rejected_for_a_credentialed_account(plat):
    _secure_owner(plat)
    with pytest.raises(PlatformContextError):
        plat.authenticate_login(email="owner@local", password="")


def test_m50_accounts_without_a_credential_keep_the_passwordless_path(plat):
    """Backward compatibility: accounts provisioned before credentials existed."""
    plat.bootstrap_owner(email="legacy@local", name="Legacy Owner")
    result = plat.login(email="legacy@local")
    assert result["token"]


def test_setting_a_password_closes_the_passwordless_path_for_that_account(plat):
    plat.bootstrap_owner(email="legacy@local", name="Legacy Owner")
    token = plat.login(email="legacy@local")["token"]
    ctx = plat.require_context(token)

    plat.store.set_password_hash(ctx.user_id, "scrypt$placeholder$hash")

    with pytest.raises(PlatformContextError) as excinfo:
        plat.login(email="legacy@local")
    assert excinfo.value.code == "AUTH_FAILED"


def test_refused_passwordless_login_is_audited(plat):
    _secure_owner(plat)
    with pytest.raises(PlatformContextError):
        plat.login(email="owner@local")
    events = [row for row in plat.store.list_audit(limit=50)
              if row.get("event") == "auth.login_failed"]
    assert events, "a refused login must leave an audit record"


# ── Journey invariant: the repaired approval path still executes end to end ───


def test_approved_local_mutation_still_executes_to_completion(plat):
    token, ctx = _owner_ctx(plat)
    proj = _project(plat, ctx)
    mission = plat.create_mission(ctx, proj["project_id"], "journey", "Journey")

    rec = plat.request_approval(
        ctx,
        tool_id="m49.local_note_write",
        action="write",
        capability="write",
        authority="LOCAL_MUTATION",
        side_effect_class="LOCAL_REVERSIBLE",
    )
    plat.decide_approval(ctx, rec.approval_id, approve=True, reason="e2e")

    from saathi.platform.runtime import PlatformAgentRuntime

    result = PlatformAgentRuntime(plat).execute_token(
        token=token,
        tool_id="m49.local_note_write",
        arguments={"key": "journey", "value": "certified"},
        capability="write",
        approval_id=rec.approval_id,
        project_id=proj["project_id"],
        mission_id=mission["mission_id"],
        idempotency_key="journey-1",
    )
    assert result.ok is True
    assert result.data.get("written") is True
