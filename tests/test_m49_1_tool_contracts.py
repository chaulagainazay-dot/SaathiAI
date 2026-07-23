"""M49.1 — tool manifest, registry, and schema contracts."""
from __future__ import annotations

import pytest

from saathi.tool_runtime.contracts import (
    ToolApprovalRequirement,
    ToolAuthorityClass,
    ToolAvailability,
    ToolCancellationSupport,
    ToolIdempotencyClass,
    ToolManifest,
    ToolSecretPolicy,
    ToolSideEffectClass,
    TimeoutPolicy,
    validate_manifest,
)
from saathi.tool_runtime.registry import ToolRegistry, ToolRegistryError, reset_registry_for_tests
from saathi.tool_runtime.schema import validate_against_schema


def _min_manifest(**kw) -> ToolManifest:
    base = dict(
        tool_id="m49.test_tool",
        version="1.0.0",
        display_name="Test",
        description="t",
        domain="test",
        capabilities=("read",),
        authority_class=ToolAuthorityClass.READ_ONLY,
        side_effect_class=ToolSideEffectClass.NO_SIDE_EFFECT,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        secret_policy=ToolSecretPolicy.NO_SECRET,
        input_schema={"type": "object", "properties": {}},
        output_schema={"type": "object", "properties": {}},
        cancellation_support=ToolCancellationSupport.TIMEOUT_ONLY,
    )
    base.update(kw)
    return ToolManifest(**base)


def test_validate_manifest_rejects_unknown_authority():
    m = _min_manifest(authority_class=ToolAuthorityClass.UNKNOWN)
    assert any("authority" in e for e in validate_manifest(m))


def test_validate_manifest_rejects_unknown_side_effect():
    m = _min_manifest(side_effect_class=ToolSideEffectClass.UNKNOWN)
    assert any("side_effect" in e for e in validate_manifest(m))


def test_financial_must_be_prohibited():
    m = _min_manifest(
        tool_id="m49.fin",
        authority_class=ToolAuthorityClass.FINANCIAL_EXECUTION,
        side_effect_class=ToolSideEffectClass.FINANCIAL_EXECUTION,
        approval_requirement=ToolApprovalRequirement.NO_APPROVAL_REQUIRED,
        availability=ToolAvailability.ENABLED,
    )
    errs = validate_manifest(m)
    assert errs


def test_duplicate_registration_fails():
    reg = ToolRegistry(allow_dynamic=False)

    def adapter(a, c):
        return {"data": {}}

    m = _min_manifest()
    reg.register(m, adapter, trusted=True)
    with pytest.raises(ToolRegistryError) as ei:
        reg.register(m, adapter, trusted=True)
    assert "duplicate" in ei.value.message.lower()


def test_dynamic_registration_disabled():
    reg = ToolRegistry(allow_dynamic=False)

    def adapter(a, c):
        return {"data": {}}

    with pytest.raises(ToolRegistryError):
        reg.register(_min_manifest(), adapter, trusted=False)


def test_incomplete_manifest_rejected():
    reg = ToolRegistry()

    def adapter(a, c):
        return {"data": {}}

    m = _min_manifest(input_schema={})  # missing type
    with pytest.raises(ToolRegistryError):
        reg.register(m, adapter, trusted=True)


def test_schema_required_and_additional():
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }
    assert validate_against_schema({"text": "ok"}, schema) == []
    assert validate_against_schema({}, schema)
    assert validate_against_schema({"text": "ok", "x": 1}, schema)


def test_builtins_bootstrap_and_matrix():
    reg = reset_registry_for_tests()
    ids = {m.tool_id for m in reg.list_manifests(include_disabled=True)}
    assert "m49.echo_readonly" in ids
    assert "m49.financial_execution_stub" in ids
    matrix = reg.capability_matrix()
    assert any(r["authority_class"] == "FINANCIAL_EXECUTION" for r in matrix)
    assert reg.validate_all()["ok"] is True


def test_manifest_public_dict_no_adapter_leak():
    reg = reset_registry_for_tests()
    m = reg.get_manifest("m49.echo_readonly")
    d = m.to_public_dict()
    assert "adapter" not in d
    assert d["authority_class"] == "READ_ONLY"
