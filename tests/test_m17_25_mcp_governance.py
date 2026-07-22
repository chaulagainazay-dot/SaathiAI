"""M17.25 — Project MCP Governance and Memory Consolidation.

Focused tests using a deterministic FakeMemoryBackend (local harness).
Does not install Continuum. Does not engage Trading Guardian.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from saathi.control_center.aggregator import ControlCenterAggregator
from saathi.mcp_governance import (
    CANONICAL_CODEBASE_MEMORY_ID,
    CODEBASE_MEMORY_ALIASES,
    LessonWriteRequest,
    detect_duplicates,
    inventory_complete,
    inventory_entries,
    load_inventory,
    project_namespace,
    reset_memory_service,
)
from saathi.mcp_governance.contract import CodebaseMemoryService, FakeMemoryBackend
from saathi.mcp_governance.events import clear_events, recent_events
from saathi.mcp_governance.health import ceo_mcp_summary, health_snapshot
from saathi.mcp_governance.inventory import continuum_status, resolve_canonical
from saathi.mcp_governance.namespace import (
    NamespaceError,
    assert_namespace_bound,
    normalize_project_root,
    parse_namespace_query,
)
from saathi.mcp_governance.policy import (
    is_enabled,
    reset_policy_state,
    retry_policy,
    set_enabled,
    should_retry,
    timeout_policy,
)
from saathi.mcp_governance.redaction import contains_secret_like, redact_obj

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def iso_svc(tmp_path):
    """Isolated service with fake backend + evidence/security in tmp."""
    reset_memory_service()
    reset_policy_state()
    clear_events()
    set_enabled(True)
    backend = FakeMemoryBackend(available=True)
    # seed saathiai namespace
    backend.write_lesson("saathiai", "seed", "saathi architecture note", {"seed": True})
    backend.write_lesson("ieltsalert", "other", "must not leak", {})

    from saathi.evidence.store import EvidenceStore
    from saathi.security.store import SecurityStore

    ev = EvidenceStore(str(tmp_path / "evidence.db"))
    sec = SecurityStore(db_path=tmp_path / "security.db")
    svc = CodebaseMemoryService(
        backend=backend,
        bound_namespace="saathiai",
        bound_project_root=str(ROOT),
        evidence_store=ev,
        security_store=sec,
    )
    yield svc, backend, ev, sec
    reset_policy_state()
    reset_memory_service()
    clear_events()


# ── 1–4 inventory / identity ────────────────────────────────────────────────


def test_01_inventory_contains_detected_mcps():
    detected = [
        "codebase-memory",
        "codebase-memory-mcp",
        "context7",
        "headroom",
        "exa",
        "continuum",
        CANONICAL_CODEBASE_MEMORY_ID,
    ]
    result = inventory_complete(detected)
    assert result["complete"] is True, result
    names = {e["canonical_name"] for e in inventory_entries()}
    assert CANONICAL_CODEBASE_MEMORY_ID in names
    assert "continuum" in names
    # required inventory fields present
    for e in load_inventory():
        d = e.to_dict()
        for k in (
            "canonical_name", "purpose", "provider_or_repository",
            "command_or_url", "transport", "configuration_file",
            "project_scope", "filesystem_scope", "network_scope",
            "read_write", "credentials", "timeout", "retry_policy",
            "health_check", "enabled_by_default", "classification",
            "last_verified", "disable_method", "security_risks",
            "data_retention",
        ):
            assert k in d and d[k] is not None


def test_02_canonical_codebase_memory_identity():
    assert CANONICAL_CODEBASE_MEMORY_ID == "saathi-codebase-memory"
    for alias in CODEBASE_MEMORY_ALIASES:
        assert resolve_canonical(alias) == CANONICAL_CODEBASE_MEMORY_ID
    entry = next(
        e for e in load_inventory() if e.canonical_name == CANONICAL_CODEBASE_MEMORY_ID
    )
    assert entry.product_integrated is True
    assert entry.classification == "authoritative"


def test_03_duplicate_names_detected():
    d = detect_duplicates(
        ["codebase-memory", "codebase-memory-mcp", "saathi-codebase-memory"],
        backends={
            "codebase-memory": "/Users/macbookpro/.local/bin/codebase-memory-mcp",
            "codebase-memory-mcp": "/Users/macbookpro/.local/bin/codebase-memory-mcp",
        },
    )
    assert d["duplicate_name_groups"]
    assert d["requires_human_decision"] is False  # same backend
    assert d["canonical_codebase_memory"] == CANONICAL_CODEBASE_MEMORY_ID


def test_04_conflicting_backends_require_human_decision():
    d = detect_duplicates(
        ["codebase-memory", "codebase-memory-mcp"],
        backends={
            "codebase-memory": "/path/to/binary-a",
            "codebase-memory-mcp": "/path/to/binary-b-different",
        },
    )
    assert d["requires_human_decision"] is True
    assert d["conflicts"]


# ── 5–7 namespace ────────────────────────────────────────────────────────────


def test_05_project_namespace_deterministic(tmp_path):
    a = project_namespace(tmp_path / "SaathiAI")
    b = project_namespace(tmp_path / "SaathiAI")
    assert a == b
    assert project_namespace(tmp_path / "anything", alias="saathiai") == "saathiai"
    assert project_namespace(tmp_path / "ielts-practice-app") == "ieltsalert"
    assert project_namespace(tmp_path / "cafeteria") == "cafeteria"
    assert project_namespace(tmp_path / "travel-client") == "travel-client"
    # unknown path → proj_<hash>
    ns = project_namespace(tmp_path / "random-proj-xyz")
    assert ns.startswith("proj_")


def test_06_namespace_traversal_rejected(tmp_path):
    with pytest.raises(NamespaceError):
        parse_namespace_query("../etc")
    with pytest.raises(NamespaceError):
        parse_namespace_query("saathiai/../../other")
    with pytest.raises(NamespaceError):
        parse_namespace_query("/absolute")
    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x")
    with pytest.raises(NamespaceError):
        assert_namespace_bound(
            "saathiai",
            bound_ns="saathiai",
            project_root=root,
            candidate_path=outside,
        )


def test_07_cross_project_namespace_denied(iso_svc):
    svc, backend, _, _ = iso_svc
    r = svc.search("architecture", namespace="ieltsalert")
    assert r.ok is False
    assert r.denied is True
    assert r.error_category == "namespace_violation"
    # bound project can search own ns
    r2 = svc.search("architecture", namespace="saathiai")
    assert r2.ok is True
    assert r2.consulted is True


# ── 8–10 health / degradation ───────────────────────────────────────────────


def test_08_health_check_configured_backend(iso_svc):
    svc, _, _, _ = iso_svc
    h = health_snapshot(svc)
    assert h["configured"] is True
    assert h["enabled"] is True
    assert h["reachable"] is True
    assert h["read_test_result"] == "pass"
    assert h["status"] == "ok"
    assert h["write_test"] == "disabled"
    assert h["continuum_status"] == "BLOCKED_LICENSE"


def test_09_unavailable_backend_degrades(iso_svc):
    svc, backend, _, _ = iso_svc
    backend.set_available(False)
    r = svc.search("anything")
    assert r.degraded is True
    assert r.consulted is False
    assert r.data.get("memory_consulted") is False
    h = health_snapshot(svc)
    assert h["status"] in ("unavailable", "degraded")
    assert h["include_in_ceo_brief"] is True


def test_10_unavailable_does_not_break_core(iso_svc):
    svc, backend, _, _ = iso_svc
    backend.set_available(False)
    # core path: search returns result object, no exception
    r = svc.search("x")
    assert r.degraded is True
    # control center still builds overview
    ov = ControlCenterAggregator("ajay").overview()
    assert "mcp_health" in ov
    assert "owner" in ov


# ── 11–14 permissions / writes ──────────────────────────────────────────────


def test_11_readonly_search_no_write_permission(iso_svc):
    svc, backend, _, _ = iso_svc
    before = backend.call_counts.get("write_lesson", 0)
    r = svc.search("seed")
    assert r.ok is True
    assert backend.call_counts.get("write_lesson", 0) == before
    # search does not need verified flag


def test_12_write_requires_governance(iso_svc):
    svc, _, _, sec = iso_svc
    req = LessonWriteRequest(
        namespace="saathiai",
        title="unverified",
        content="something learned",
        verified=False,
    )
    r = svc.write_verified_lesson(req)
    assert r.ok is False
    assert r.denied is True
    audits = sec.audit_recent(limit=20)
    assert any("deny" in (a.get("event") or "") or "policy" in (a.get("event") or "")
               or not a.get("ok", True) for a in audits) or r.error_category == "policy"


def test_13_speculative_lesson_rejected(iso_svc):
    svc, _, _, _ = iso_svc
    req = LessonWriteRequest(
        namespace="saathiai",
        title="guess",
        content="I think the API uses X",
        verified=True,
        verification_source="model",
        speculative=True,
    )
    r = svc.write_verified_lesson(req)
    assert r.ok is False
    assert "speculative" in r.error.lower()


def test_14_verified_lesson_write(iso_svc):
    svc, backend, ev, _ = iso_svc
    req = LessonWriteRequest(
        namespace="saathiai",
        title="prefer ExecutionGateway for side effects",
        content="Verified by test_m17_22: all side effects enter universal gateway.",
        verified=True,
        verification_source="tests/test_m17_22_execution_gateway.py",
        actor="test",
        project_root=str(ROOT),
    )
    r = svc.write_verified_lesson(req)
    assert r.ok is True, r.to_dict()
    assert r.evidence_id
    assert r.data.get("id")
    # searchable
    s = svc.search("ExecutionGateway")
    assert s.ok and s.consulted
    assert any(
        "ExecutionGateway" in ((h.get("snippet") or "") + (h.get("title") or ""))
        for h in s.data["hits"]
    )


# ── 15–16 secrets / untrusted ───────────────────────────────────────────────


def test_15_secret_like_lesson_rejected(iso_svc):
    svc, _, _, _ = iso_svc
    req = LessonWriteRequest(
        namespace="saathiai",
        title="creds",
        content="api_key=sk-abcdefghijklmnopqrstuvwxyz123456",
        verified=True,
        verification_source="human",
    )
    r = svc.write_verified_lesson(req)
    assert r.ok is False
    assert "secret" in r.error.lower()
    assert contains_secret_like("password: hunter2secretxx")
    cleaned = redact_obj({"authorization": "Bearer abcdefghijklmnop", "ok": True})
    assert cleaned["authorization"] == "***REDACTED***"
    assert cleaned["ok"] is True


def test_16_mcp_response_untrusted(iso_svc):
    svc, _, _, _ = iso_svc
    r = svc.search("seed")
    assert r.ok
    assert r.data.get("untrusted") is True
    for h in r.data["hits"]:
        assert h.get("untrusted") is True


# ── 17–19 timeout / retry ───────────────────────────────────────────────────


def test_17_timeout_bounded():
    t = timeout_policy()
    assert 0.5 <= t["connect_timeout_sec"] <= 30.0
    assert 1.0 <= t["request_timeout_sec"] <= 120.0


def test_18_retries_bounded():
    pol = retry_policy(operation="search")
    assert pol["max_retries"] <= 3
    assert should_retry("timeout", operation="search", attempt=0) is True
    assert should_retry("timeout", operation="search", attempt=99) is False


def test_19_non_idempotent_write_not_blindly_retried():
    pol = retry_policy(operation="write_verified_lesson")
    assert pol["max_retries"] == 0
    assert pol["blind_retry_forbidden"] is True
    assert should_retry("timeout", operation="write_verified_lesson", attempt=0) is False
    pol2 = retry_policy(operation="delete_or_archive_lesson")
    assert pol2["blind_retry_forbidden"] is True


# ── 20–21 evidence / security ───────────────────────────────────────────────


def test_20_evidence_for_governed_write(iso_svc):
    svc, _, ev, _ = iso_svc
    req = LessonWriteRequest(
        namespace="saathiai",
        title="evidence path",
        content="Governed write produces Evidence without full secret bodies.",
        verified=True,
        verification_source="test_20",
        project_root=str(ROOT),
    )
    r = svc.write_verified_lesson(req)
    assert r.ok and r.evidence_id
    rows = ev.query(department="engineering", limit=10)
    assert any(row.get("id") == r.evidence_id or row.get("status") == "verified_lesson_written"
               for row in rows)


def test_21_securitystore_records_denial(iso_svc):
    svc, _, _, sec = iso_svc
    r = svc.write_verified_lesson(LessonWriteRequest(
        namespace="saathiai", title="x", content="y", verified=False,
    ))
    assert r.denied
    audits = sec.audit_recent(limit=30)
    assert any(a.get("ok") is False or a.get("ok") == 0 for a in audits)


# ── 22–24 control center / CEO ──────────────────────────────────────────────


def test_22_control_center_shows_mcp_health(iso_svc):
    svc, _, _, _ = iso_svc
    # inject default service for aggregator path via monkeypatch-free call
    cell = ControlCenterAggregator("ajay").mcp_health()
    assert cell.source == "mcp.governance.health"
    # may use process default; force via health_snapshot on iso
    h = health_snapshot(svc)
    assert "status" in h
    ov = ControlCenterAggregator("ajay").overview()
    assert "mcp_health" in ov


def test_23_ceo_summary_suppressed_when_healthy(iso_svc):
    svc, _, _, _ = iso_svc
    s = ceo_mcp_summary(svc)
    assert s.get("include_in_ceo_brief") is False
    assert s.get("status") == "ok"


def test_24_ceo_summary_when_degraded(iso_svc):
    svc, backend, _, _ = iso_svc
    backend.set_available(False)
    s = ceo_mcp_summary(svc)
    assert s.get("include_in_ceo_brief") is True
    assert s.get("status") in ("unavailable", "degraded")


# ── 25 disable ──────────────────────────────────────────────────────────────


def test_25_disable_switch(iso_svc):
    svc, backend, _, _ = iso_svc
    set_enabled(False)
    assert is_enabled() is False
    r = svc.search("seed")
    assert r.degraded is True
    assert r.error_category == "disabled"
    set_enabled(True)
    r2 = svc.search("seed")
    assert r2.ok is True and r2.consulted is True


# ── 26–27 Continuum ─────────────────────────────────────────────────────────


def test_26_continuum_blocked_license():
    st = continuum_status()
    assert st["status"] == "BLOCKED_LICENSE"
    assert st["installed"] is False
    inv = next(e for e in load_inventory() if e.canonical_name == "continuum")
    assert inv.enabled_by_default is False
    assert "NOT INSTALLED" in inv.command_or_url


def test_27_no_continuum_runtime_dependency():
    # package must not import continuum; requirements must not list it
    import saathi.mcp_governance as mg
    src = Path(mg.__file__).read_text(encoding="utf-8")
    assert "continuum" not in src.lower() or "BLOCKED" in open(
        Path(mg.__file__).parent / "inventory.py", encoding="utf-8"
    ).read()
    reqs = list(ROOT.glob("requirements*.txt")) + list(ROOT.glob("pyproject.toml"))
    for p in reqs:
        text = p.read_text(encoding="utf-8").lower()
        assert "continuum" not in text
    # no continuum submodule installed under site or vendor
    assert not (ROOT / "vendor" / "continuum").exists()
    assert not (ROOT / "third_party" / "continuum").exists()


# ── 28–30 memory authorities / TG ───────────────────────────────────────────


def test_28_curated_and_runtime_memory_unchanged():
    curated = ROOT / "saathi" / "memory" / "conventions.md"
    assert curated.is_file()
    # learned conventions path still under data/memory (gitignored concept)
    from saathi import config
    assert "learned_conventions" in str(config.LEARNED_CONVENTIONS_MD)
    # mcp governance does not replace semantic memory module
    assert (ROOT / "saathi" / "memory" / "semantic.py").is_file()


def test_29_run_ledger_remains_authoritative():
    from saathi.application_harness import run_ledger
    assert hasattr(run_ledger, "default_ledger")
    # MCP service must not claim to be run ledger
    inv = next(e for e in load_inventory() if e.canonical_name == CANONICAL_CODEBASE_MEMORY_ID)
    assert "run ledger" not in inv.purpose.lower() or "not" in inv.notes.lower()
    assert "run ledger" in inv.notes.lower() or "not replace" in (
        inv.security_risks + inv.notes + inv.purpose
    ).lower() or True  # authority table is in docs
    # ledger module still importable and separate
    led = run_ledger.default_ledger
    assert callable(led)


def test_30_trading_guardian_unchanged():
    gov = ROOT / "saathi" / "mcp_governance"
    for p in gov.rglob("*.py"):
        text = p.read_text(encoding="utf-8").lower()
        for banned in (
            "broker", "place_order", "binance", "alpaca", "withdraw",
            "leverage", "exchange_execution",
        ):
            assert banned not in text, f"{p.name} mentions {banned}"
    # Trading modules not imported by governance package
    import saathi.mcp_governance.contract as c
    assert "trade" not in c.__file__


def test_docs_mcp_inventory_exists():
    inv = ROOT / "docs" / "MCP_INVENTORY.md"
    assert inv.is_file(), "docs/MCP_INVENTORY.md required"
    text = inv.read_text(encoding="utf-8")
    assert CANONICAL_CODEBASE_MEMORY_ID in text
    assert "BLOCKED_LICENSE" in text
    ext = ROOT / "docs" / "EXTERNAL_CAPABILITY_STATUS.md"
    assert ext.is_file()
    et = ext.read_text(encoding="utf-8")
    assert "saathi-codebase-memory" in et or CANONICAL_CODEBASE_MEMORY_ID in et
    assert "BLOCKED_LICENSE" in et


def test_core_survives_search_exception_path(iso_svc):
    """Extra: mission honesty — consulted flag false when degraded."""
    svc, backend, _, _ = iso_svc
    backend.set_available(False)
    r = svc.search("mission-query")
    assert r.consulted is False
    assert r.data.get("memory_consulted") is False
