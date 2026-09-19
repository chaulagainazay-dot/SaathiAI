"""SaathiOS AI Company — organization foundation tests.

Covers: charter schema/membership/uniqueness, authority boundaries (no execution,
no forbidden capabilities, no executor binding, no trading-path imports),
status lifecycle, real-state derivation (UNKNOWN/UNAVAILABLE/stale honesty),
missions + delegation + events, API auth/serialization/redaction.
All stores are temp files; no real user data is read or written.
"""
from __future__ import annotations

import ast
import sqlite3
import time
from pathlib import Path

import pytest

ORG_DIR = Path(__file__).resolve().parent.parent / "saathi" / "organization"


# ── fixtures ────────────────────────────────────────────────────────────────
def _seed_platform(path: Path, *, bars_per_symbol: int = 1, positions: bool = True) -> None:
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE paper_accounts(id TEXT, org_id TEXT, workspace_id TEXT, project_id TEXT, name TEXT,
      base_currency TEXT, starting_cash TEXT, current_cash TEXT, reserved_cash TEXT, realized_pnl TEXT,
      status TEXT, environment TEXT, halt_reason TEXT, created_by TEXT, created_at REAL,
      updated_at REAL, version INTEGER);
    CREATE TABLE paper_positions(org_id TEXT, account_id TEXT, symbol TEXT, quantity TEXT,
      reserved_quantity TEXT, avg_cost TEXT, realized_pnl TEXT);
    CREATE TABLE md_bars(org_id TEXT, provider TEXT, instrument TEXT, timeframe TEXT, start_epoch REAL,
      end_epoch REAL, open REAL, high REAL, low REAL, close REAL, volume REAL, source_epoch REAL,
      ingest_epoch REAL, quality TEXT, raw_hash TEXT);
    CREATE TABLE md_instruments(id TEXT);
    """)
    c.execute("INSERT INTO paper_accounts VALUES('pacc_1','o','w','','Paper A','USD','10000','8000',"
              "'0','0','ACTIVE','PAPER','','u',0,0,1)")
    if positions:
        c.execute("INSERT INTO paper_positions VALUES('o','pacc_1','AAPL','10','0','200','0')")
    now = time.time()
    for sym, o, cl in (("NABIL", 550, 552), ("NIMB", 186, 185), ("SCB", 647, 648)):
        for i in range(bars_per_symbol):
            c.execute("INSERT INTO md_bars VALUES('o','p',?, '1d',?,?,?,?,?,?,?,0,0,'VALID','h')",
                      (f"NEPSE:{sym}", now - 86400 * (i + 1), now - 3600 - 86400 * i, o, cl + 1, o - 1, cl, 1000))
    c.commit()
    c.close()


@pytest.fixture
def org_env(tmp_path, monkeypatch):
    plat = tmp_path / "platform.db"
    _seed_platform(plat)
    monkeypatch.setenv("SAATHI_PLATFORM_DB", str(plat))
    monkeypatch.setenv("SAATHI_ORG_DB", str(tmp_path / "org.db"))
    monkeypatch.setenv("SAATHI_ORG_STEP_PACING_SEC", "0")
    import saathi.agent_runtime.store as ar_store
    monkeypatch.setattr(ar_store, "DB_PATH", tmp_path / "agent_runtime.db")
    from saathi.evidence import store as ev_store
    ev = ev_store.EvidenceStore(str(tmp_path / "evidence.db"))
    monkeypatch.setattr(ev_store, "default_store", lambda: ev)
    from saathi.organization import system_status
    system_status._cache.update(at=0.0, value=None)
    return tmp_path


# ── charter ─────────────────────────────────────────────────────────────────
def test_charter_loads_and_ids_are_unique():
    from saathi.organization.charter import ROLES, OFFICES, FLOORS, load_charter
    ch = load_charter()
    assert len(ch.roles) == len(ROLES) and len({r.role_id for r in ROLES}) == len(ROLES)
    assert len({o.office_id for o in OFFICES}) == len(OFFICES)
    assert len({f.number for f in FLOORS}) == len(FLOORS)


def test_required_departments_and_offices_exist():
    from saathi.organization.charter import load_charter
    ch = load_charter()
    for o in ("owner", "ceo", "board", "cio", "crypto", "nepse", "portfolio", "risk",
              "committee", "research_hq", "dev", "security", "finance", "assistant"):
        assert o in ch.offices, o
    assert ch.roles["exec.saathi"].office_id == "ceo"
    assert ch.owner["in_agent_hierarchy"] is False


def test_every_office_lead_is_a_member_and_offices_have_members():
    from saathi.organization.charter import load_charter
    ch = load_charter()
    for o in ch.offices.values():
        members = [r.role_id for r in ch.members(o.office_id)]
        if o.office_id == "owner":
            assert members == []          # the owner is not an agent
            continue
        assert members, o.office_id
        assert o.lead_role_id in members, o.office_id


def test_membership_and_floor_department_consistency():
    from saathi.organization.charter import load_charter
    ch = load_charter()
    for r in ch.roles.values():
        assert r.office_id in ch.offices
    for o in ch.offices.values():
        assert ch.floors[o.floor_id].department_id == o.department_id


def test_validator_rejects_bad_charters():
    from saathi.organization import charter as C
    from saathi.organization.models import RuntimeBinding
    import dataclasses
    dup = C.ROLES + (C.ROLES[0],)
    assert any("duplicate role" in e for e in C.validate(C.DEPARTMENTS, C.FLOORS, C.OFFICES, dup, C.AUTHORITY_CHAIN))
    bad_exec = C.ROLES + (dataclasses.replace(C.ROLES[1], role_id="x.exec",
                                             binding=RuntimeBinding("agent_runtime", "executor")),)
    assert any("executor" in e for e in C.validate(C.DEPARTMENTS, C.FLOORS, C.OFFICES, bad_exec, C.AUTHORITY_CHAIN))
    bad_cap = C.ROLES + (dataclasses.replace(C.ROLES[1], role_id="x.cap",
                                            capabilities=("trading_execution",)),)
    assert any("forbidden" in e for e in C.validate(C.DEPARTMENTS, C.FLOORS, C.OFFICES, bad_cap, C.AUTHORITY_CHAIN))
    bad_office = C.ROLES + (dataclasses.replace(C.ROLES[1], role_id="x.o", office_id="nowhere"),)
    assert any("unknown office" in e for e in C.validate(C.DEPARTMENTS, C.FLOORS, C.OFFICES, bad_office, C.AUTHORITY_CHAIN))


def test_bindings_reference_real_runtime_identities():
    from saathi.agent_runtime import registry
    from saathi.platform.mission_runtime.models import AgentType
    from saathi.organization.charter import load_charter
    for r in load_charter().roles.values():
        if r.binding.kind == "agent_runtime":
            assert registry.get(r.binding.ref) is not None
            assert r.binding.ref != "executor"
        if r.binding.kind == "mission_agent":
            assert r.binding.ref in {a.value for a in AgentType}


# ── authority boundaries ────────────────────────────────────────────────────
def test_no_role_has_execution_authority_or_forbidden_capability():
    from saathi.organization.charter import load_charter
    from saathi.organization.models import FORBIDDEN_CAPABILITIES
    for r in load_charter().roles.values():
        assert r.execution_authority == "NONE"
        assert not FORBIDDEN_CAPABILITIES.intersection(r.capabilities)
        assert r.to_public()["execution_authority"] == "NONE"


def test_forbidden_set_covers_platform_forbidden_all():
    from saathi.platform.orchestration.roles import FORBIDDEN_ALL
    from saathi.organization.models import FORBIDDEN_CAPABILITIES
    assert FORBIDDEN_ALL <= FORBIDDEN_CAPABILITIES


@pytest.mark.parametrize("rid", ["exec.saathi", "inv.fund_manager", "ic.chair", "crypto.lead",
                                 "crypto.technical", "nepse.lead", "nepse.company", "research.web"])
def test_named_roles_never_have_broker_or_gateway_authority(rid):
    from saathi.organization.charter import load_charter
    r = load_charter().roles[rid]
    pub = r.to_public()
    assert pub["execution_authority"] == "NONE"
    joined = " ".join(pub["can"]).lower()
    for word in ("order", "execute", "gateway", "approve", "withdraw"):
        assert word not in joined, (rid, word)


def test_financial_roles_state_financial_prohibitions():
    from saathi.organization.charter import load_charter
    fin = [r for r in load_charter().roles.values() if r.financial]
    assert len(fin) > 40
    for r in fin:
        cannot = " ".join(r.cannot())
        assert "ExecutionGateway" in cannot and "orders" in cannot and "Trading Guardian" in cannot


def test_organization_package_never_imports_execution_paths():
    """Static proof: no org module imports order/gateway/broker execution code."""
    forbidden = ("saathi.execution.gateway", "execution_tool", "submit_via_gateway",
                 "saathi.execution.trade", "broker", "paper_activation", "paper_trading.orchestration",
                 "paper_trading.service")
    forbidden_calls = ("submit_order", "place_order", "execute_registered_tool", "cancel_order")
    for py in ORG_DIR.glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", "") or ""
                names = [a.name for a in node.names]
                for f in forbidden:
                    assert f not in mod and not any(f in n for n in names), (py.name, mod, names)
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_calls, (py.name, node.attr)
            if isinstance(node, ast.Name):
                assert node.id not in forbidden_calls, (py.name, node.id)


def test_executor_agent_is_not_mapped_to_any_role():
    from saathi.organization.charter import AGENT_RUNTIME_ROLE
    assert "executor" not in AGENT_RUNTIME_ROLE


def test_existing_trading_boundaries_still_hold():
    """The chain the organization defers to still refuses LLM authority."""
    from saathi.platform.tg.service import default_tg_service
    from saathi.platform.trading_guardian import safety_posture
    p = default_tg_service().posture()
    assert p["paper_only"] is True and p["live_trading_authorized"] is False
    assert p["llm_boundary"]["may_approve"] is False
    assert safety_posture()["LIVE_EXECUTION"] == "DISABLED"


# ── lifecycle ───────────────────────────────────────────────────────────────
def test_status_lifecycle_transitions():
    from saathi.organization.models import AgentStatus as S, can_transition, \
        validate_status_transition, IllegalStatusTransition
    assert can_transition(S.IDLE, S.ASSIGNED)
    assert can_transition(S.ASSIGNED, S.ANALYZING)
    assert can_transition(S.ANALYZING, S.WAITING)
    assert can_transition(S.WAITING, S.ANALYZING)
    assert can_transition(S.ANALYZING, S.COMPLETE)
    assert can_transition(S.REVIEWING, S.AWAITING_EVIDENCE)
    assert not can_transition(S.COMPLETE, S.BLOCKED)
    assert not can_transition(S.IDLE, S.COMPLETE)
    assert not can_transition(S.ERROR, S.COMPLETE)
    with pytest.raises(IllegalStatusTransition):
        validate_status_transition(S.OFFLINE, S.WORKING)


def test_every_status_has_an_outgoing_path_back_to_idle_or_work():
    from saathi.organization.models import AgentStatus as S, can_transition
    for s in S:
        assert any(can_transition(s, d) for d in (S.IDLE, S.ASSIGNED, S.UNKNOWN)), s


# ── real state ──────────────────────────────────────────────────────────────
def test_idle_snapshot_is_truthful(org_env):
    from saathi.organization.state import company_snapshot
    snap = company_snapshot()
    m = snap["metrics"]
    assert m["total"] == len(snap["roles"])
    assert m["active"] == 0 and m["errors"] == 0
    by = {r["role_id"]: r for r in snap["roles"]}
    assert by["crypto.onchain"]["status"] == "UNAVAILABLE" and by["crypto.onchain"]["reason"]
    assert by["personal.email"]["status"] in ("UNAVAILABLE", "UNKNOWN")
    assert "not connected" in by["personal.email"]["reason"].lower() or \
        by["personal.email"]["status"] == "UNKNOWN"
    assert by["exec.saathi"]["status"] == "IDLE"
    assert {s["system_id"] for s in snap["authority_chain"]} == {
        "portfolio_construction", "portfolio_risk", "trading_guardian", "approval", "execution_gateway"}


def test_unreadable_runtime_store_yields_unknown_not_idle(org_env, monkeypatch):
    from saathi.organization import state
    monkeypatch.setattr(state, "_m10_activity", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    states, sources = state.role_states()
    assert sources["agent_runtime"]["ok"] is False
    assert states["eng.coding"]["status"] == "UNKNOWN"
    assert states["research.web"]["status"] == "UNKNOWN"


def test_running_m10_turn_maps_to_role_activity(org_env, monkeypatch):
    from saathi.organization import state
    now = time.time()
    monkeypatch.setattr(state, "_m10_activity", lambda: {
        "ok": True, "pending": [],
        "running": [{"agent": "builder", "run_id": "r1", "created_at": now, "objective": "fix x",
                     "run_state": "running", "updated_at": now},
                    {"agent": "reviewer", "run_id": "r2", "created_at": now - 90000, "objective": "old",
                     "run_state": "running", "updated_at": now - 90000}]})
    states, _ = state.role_states(now)
    assert states["eng.coding"]["status"] == "WORKING"
    assert states["eng.coding"]["activity"]["run_id"] == "r1"
    assert states["eng.code_review"]["status"] == "WAITING"
    assert "stale" in states["eng.code_review"]["reason"]


def test_stale_pending_tasks_are_ignored(org_env, monkeypatch):
    from saathi.organization import state
    now = time.time()
    monkeypatch.setattr(state, "_m10_activity", lambda: {"ok": True, "running": [], "pending": [
        {"agent": "builder", "run_id": "old", "objective": "implement x", "updated_at": now - 10 * 86400}]})
    states, sources = state.role_states(now)
    assert states["eng.coding"]["status"] == "IDLE"
    assert sources["agent_runtime"]["stale_pending_ignored"] == 1


def test_owner_desk_counts_real_rows_and_unknown_is_none(org_env, monkeypatch, tmp_path):
    from saathi.organization.state import owner_desk
    d = owner_desk("ajay")
    assert d["paper_accounts"] == 1 and d["paper_positions"] == 1
    assert d["pending_platform_approvals"] is None  # seeded db has no approvals table → unknown
    monkeypatch.setenv("SAATHI_PLATFORM_DB", str(tmp_path / "absent.db"))
    assert owner_desk("ajay")["paper_accounts"] is None


# ── missions ────────────────────────────────────────────────────────────────
def test_templates_are_valid_and_rooted_at_saathi():
    from saathi.organization.missions import validate_templates
    assert validate_templates() == []


def test_objective_routing():
    from saathi.organization.missions import route_objective, MissionError
    assert route_objective("analyze my portfolio risks").template_id == "portfolio_review"
    assert route_objective("research NEPSE banking stocks for swing").template_id == "nepse_swing_research"
    with pytest.raises(MissionError):
        route_objective("bake a cake")


def test_portfolio_mission_runs_with_real_reads_and_honest_gaps(org_env):
    from saathi.organization.missions import MissionRunner, delegation_tree
    r = MissionRunner(pacing_sec=0)
    m = r.create(objective="", template_id="portfolio_review", created_by="test")
    m = r.run_sync(m["id"])
    assert m["status"] in ("COMPLETE", "COMPLETE_WITH_GAPS")
    assert m["report"]["authorizes_execution"] is False and m["report"]["llm_used"] is False
    steps = {s["role_id"]: s for s in r.store.steps(m["id"])}
    assert steps["pm.manager"]["status"] == "COMPLETE"
    assert steps["crypto.technical"]["status"] == "AWAITING_EVIDENCE"   # no crypto bars seeded
    assert steps["crypto.technical"]["reason"]
    assert steps["risk.stress"]["status"] == "AWAITING_EVIDENCE"
    chair = steps["ic.chair"]["output"]["data"]
    assert chair["authorizes_execution"] is False
    assert "NOT invoked" in chair["committee_engine"]
    assert all(s["output"].get("llm_used") is False for s in steps.values())
    tree = delegation_tree(r.store, m["id"])["tree"]
    assert tree["role_id"] == "owner"
    saathi = tree["children"][0]
    assert saathi["role_id"] == "exec.saathi"
    assert "inv.fund_manager" in [c["role_id"] for c in saathi["children"]]


def test_swing_mission_reports_insufficient_history(org_env):
    from saathi.organization.missions import MissionRunner
    r = MissionRunner(pacing_sec=0)
    m = r.run_sync(r.create(objective="nepse banking swing", created_by="t")["id"])
    steps = {s["role_id"]: s for s in r.store.steps(m["id"])}
    assert steps["nepse.swing"]["status"] == "AWAITING_EVIDENCE"
    assert "≥ 20" in steps["nepse.swing"]["reason"]
    assert steps["nepse.sector"]["status"] == "AWAITING_EVIDENCE"
    assert steps["nepse.technical"]["status"] == "COMPLETE"


def test_missing_platform_store_is_not_fabricated(org_env, monkeypatch, tmp_path):
    monkeypatch.setenv("SAATHI_PLATFORM_DB", str(tmp_path / "absent.db"))
    from saathi.organization.probes import run_probe
    assert run_probe("paper_portfolio", {})["status"] == "awaiting_evidence"
    assert run_probe("nepse_market_snapshot", {})["status"] == "awaiting_evidence"


def test_probe_exceptions_become_error_not_success():
    from saathi.organization import probes
    probes.PROBES["_boom"] = lambda ctx: 1 / 0
    try:
        out = probes.run_probe("_boom", {})
        assert out["status"] == "error" and out["gaps"]
    finally:
        probes.PROBES.pop("_boom")


def test_mission_is_visible_in_role_state_while_running(org_env):
    from saathi.organization.missions import MissionRunner
    from saathi.organization.state import role_states
    from saathi.organization.store import default_store
    r = MissionRunner(pacing_sec=0)
    m = r.create(objective="", template_id="company_health", created_by="t")
    st = default_store()
    st.set_mission(m["id"], status="RUNNING")
    step = [s for s in st.steps(m["id"]) if s["role_id"] == "eng.monitoring"][0]
    st.set_step(step["id"], status="RESEARCHING", started=True)
    states, _ = role_states()
    assert states["eng.monitoring"]["status"] == "RESEARCHING"
    assert states["eng.monitoring"]["activity"]["mission_id"] == m["id"]


def test_concurrency_is_bounded_to_one_mission(org_env):
    from saathi.organization import missions as M
    r = M.MissionRunner(pacing_sec=0)
    m = r.create(objective="", template_id="company_health", created_by="t")
    assert M._slots.acquire(blocking=False)
    try:
        with pytest.raises(M.MissionError) as ei:
            r.start_async(m["id"])
        assert ei.value.status == 409
    finally:
        M._slots.release()


def test_bus_events_carry_ids_only(org_env):
    from saathi.events import bus
    from saathi.organization.missions import MissionRunner
    seen = []
    handler = lambda ev: seen.append(ev)  # noqa: E731
    bus.subscribe("*", handler)
    try:
        r = MissionRunner(pacing_sec=0)
        r.run_sync(r.create(objective="", template_id="company_health", created_by="t")["id"])
    finally:
        try:
            bus._subs["*"].remove(handler)
        except Exception:
            pass
    org = [e for e in seen if getattr(e, "name", "").startswith("org.")]
    names = {e.name for e in org}
    assert {"org.mission.created", "org.agent.started", "org.mission.delegated",
            "org.agent.output_created", "org.mission.completed"} <= names
    for e in org:
        assert set(e.payload) <= {"mission_id", "step_id", "role_id", "status"}


# ── API ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def api(org_env, monkeypatch):
    import saathi.server as svr
    from fastapi.testclient import TestClient
    monkeypatch.setattr(svr, "ACCESS_TOKEN", "org-test-token")
    return TestClient(svr.app), {"x-saathi-token": "org-test-token"}


def test_api_requires_auth(api):
    client, _ = api
    assert client.get("/api/v1/organization/company").status_code == 401
    assert client.post("/api/v1/organization/missions", json={"template_id": "company_health"}).status_code == 401


def test_api_company_snapshot_serializes(api):
    client, h = api
    r = client.get("/api/v1/organization/company", headers=h)
    assert r.status_code == 200
    d = r.json()
    assert d["metrics"]["total"] == len(d["roles"]) > 100
    assert all(x["execution_authority"] == "NONE" for x in d["roles"])
    assert {"floors", "offices", "authority_chain", "today_focus", "sources"} <= set(d)


def test_api_role_and_office_detail(api):
    client, h = api
    r = client.get("/api/v1/organization/roles/inv.fund_manager", headers=h).json()
    assert r["role"]["execution_authority"] == "NONE" and r["role"]["cannot"]
    assert client.get("/api/v1/organization/roles/nope", headers=h).status_code == 404
    o = client.get("/api/v1/organization/offices/crypto", headers=h).json()
    assert o["lead"] == "crypto.lead" and len(o["members"]) == 15


def test_api_mission_lifecycle(api):
    client, h = api
    r = client.post("/api/v1/organization/missions", headers=h,
                    json={"objective": "check system health"})
    assert r.status_code == 200, r.text
    mid = r.json()["mission"]["id"]
    for _ in range(100):
        m = client.get(f"/api/v1/organization/missions/{mid}", headers=h).json()
        if m["mission"]["status"] not in ("CREATED", "RUNNING"):
            break
        time.sleep(0.05)
    assert m["mission"]["status"] in ("COMPLETE", "COMPLETE_WITH_GAPS")
    assert m["tree"]["children"][0]["role_id"] == "exec.saathi"
    assert m["events"]
    bad = client.post("/api/v1/organization/missions", headers=h, json={"objective": "bake a cake"})
    assert bad.status_code == 400 and bad.json()["error"] == "NO_TEMPLATE"


def test_api_evidence_by_id_validates_and_redacts(api, org_env):
    client, h = api
    assert client.get("/api/v1/organization/evidence/..%2f", headers=h).status_code in (400, 404)
    assert client.get("/api/v1/organization/evidence/abcdef12", headers=h).status_code == 404


def test_event_stream_is_not_transformable_by_proxies():
    """The single-origin Next proxy gzip-buffers SSE unless the response forbids
    transformation; without this header browsers receive no live events."""
    src = (Path(__file__).resolve().parent.parent / "saathi" / "server.py").read_text()
    block = src[src.index('@app.get("/api/events/stream")'):][:600]
    assert "no-transform" in block


def test_redaction():
    from saathi.organization.api import redact
    out = redact({"api_key": "x", "nested": [{"session_id": "s", "authority": "ADVISE",
                                              "authorizes_execution": False}]})
    assert out["api_key"] == "[REDACTED]"
    assert out["nested"][0]["session_id"] == "[REDACTED]"
    assert out["nested"][0]["authority"] == "ADVISE"
    assert out["nested"][0]["authorizes_execution"] is False


# ── standing duties / operations loop ───────────────────────────────────────
@pytest.fixture
def ops_env(org_env, monkeypatch):
    monkeypatch.setenv("SAATHI_ORG_DATA_ROOT", str(org_env / "data"))
    monkeypatch.setenv("SAATHI_ORG_OPERATIONS", "0")
    (org_env / "data").mkdir(exist_ok=True)
    from saathi.organization.operations import OperationsLoop
    OperationsLoop._req_cache = (0.0, {})
    return org_env


def test_every_role_has_a_standing_duty():
    from saathi.organization.charter import load_charter
    from saathi.organization.duties import DUTIES
    roles = set(load_charter().roles)
    assert set(DUTIES) == roles, sorted(roles ^ set(DUTIES))


def _hash_tree(root):
    import hashlib
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(root).rglob("*")) if p.is_file() and not p.name.startswith("org")}


def test_all_duties_are_read_only_and_never_raise(ops_env):
    from saathi.organization.duties import DUTIES, run_duty
    before = _hash_tree(ops_env)
    results = {rid: run_duty(d, {"recent": {}}) for rid, d in DUTIES.items()}
    after = _hash_tree(ops_env)
    assert before == after, "a duty modified a data file"
    for rid, out in results.items():
        assert out["status"] in ("complete", "awaiting_evidence", "error"), rid
        assert out["llm_used"] is False
        if out["status"] != "complete":
            assert out["gaps"], f"{rid} must say why it could not complete"


def test_operations_run_once_records_and_emits_id_only_events(ops_env):
    from saathi.events import bus
    from saathi.organization.operations import OperationsLoop
    from saathi.organization.store import default_store
    seen = []
    handler = lambda ev: seen.append(ev)  # noqa: E731
    bus.subscribe("*", handler)
    try:
        loop = OperationsLoop(tick_sec=0, visible_sec=0)
        first = loop.run_once()
    finally:
        bus._subs["*"].remove(handler)
    assert first and first["status"] in ("COMPLETE", "AWAITING_EVIDENCE", "ERROR")
    d = default_store().duties()[first["role_id"]]
    assert d["finished_at"] > 0 and d["next_due_at"] > d["finished_at"] and d["runs"] == 1
    org = [e for e in seen if e.name.startswith("org.duty.")]
    assert {e.name for e in org} == {"org.duty.started", "org.duty.completed"}
    for e in org:
        assert set(e.payload) <= {"role_id", "status"}


def test_first_pass_runs_specialists_before_digests(ops_env):
    from saathi.organization.operations import OperationsLoop
    loop = OperationsLoop(tick_sec=0, visible_sec=0)
    order = []
    for _ in range(200):
        r = loop.run_once()
        if r is None:
            break
        order.append(r["role_id"])
    assert "nepse.technical" in order and "nepse.lead" in order
    assert order.index("nepse.technical") < order.index("nepse.lead")
    assert order.index("pm.manager") < order.index("inv.fund_manager")
    assert loop.run_once() is None           # nothing due immediately after a full pass


def test_owner_missions_take_the_single_slot_first(ops_env):
    from saathi.organization import missions as M
    from saathi.organization.operations import OperationsLoop
    loop = OperationsLoop(tick_sec=0, visible_sec=0)
    assert M._slots.acquire(blocking=False)
    try:
        assert loop.run_once() is None
    finally:
        M._slots.release()


def test_owner_pause_is_persisted_and_respected(ops_env):
    from saathi.organization.operations import OperationsLoop
    loop = OperationsLoop(tick_sec=0, visible_sec=0)
    st = loop.set_running(False)
    assert st["owner_setting"] == "paused" and st["running"] is False
    assert OperationsLoop(tick_sec=0).enabled_by_owner is False
    loop._stop.set()
    assert loop.start_if_enabled() is False     # env SAATHI_ORG_OPERATIONS=0 also blocks


def test_duty_state_drives_role_status(ops_env):
    from saathi.organization.state import role_states, DUTY_RECENT_SEC
    from saathi.organization.store import default_store
    st = default_store()
    st.duty_start("eng.debugging", "Scan backend error log")
    with st._conn() as c:
        c.execute("UPDATE org_duty SET status='ANALYZING' WHERE role_id='eng.debugging'")
    assert role_states()[0]["eng.debugging"]["status"] == "ANALYZING"
    st.duty_finish("eng.debugging", status="COMPLETE", reason="", output={"summary": "ok"},
                   next_due_at=time.time() + 600)
    assert role_states()[0]["eng.debugging"]["status"] == "COMPLETE"
    later = time.time() + DUTY_RECENT_SEC + 5
    s = role_states(later)[0]["eng.debugging"]
    assert s["status"] == "IDLE" and s["activity"]["source"] == "duty"
    st.duty_start("pm.correlation", "Correlation")
    st.duty_finish("pm.correlation", status="AWAITING_EVIDENCE", reason="No return series",
                   output={}, next_due_at=time.time() + 600)
    s = role_states(later)[0]["pm.correlation"]
    assert s["status"] == "AWAITING_EVIDENCE" and s["reason"] == "No return series"


def test_interrupted_duty_is_not_left_working(ops_env):
    from saathi.organization.store import default_store
    st = default_store()
    st.duty_start("eng.cto", "Engineering digest")
    assert st.reset_running_duties() == 1
    assert st.duties()["eng.cto"]["status"] == "IDLE"


def test_api_operations_requires_auth_and_toggles(api, ops_env):
    client, h = api
    assert client.get("/api/v1/organization/operations").status_code == 401
    assert client.post("/api/v1/organization/operations", json={"running": False}).status_code == 401
    r = client.post("/api/v1/organization/operations", headers=h, json={"running": False})
    assert r.status_code == 200 and r.json()["owner_setting"] == "paused"
    snap = client.get("/api/v1/organization/company", headers=h).json()
    assert snap["operations"]["running"] is False and snap["operations"]["llm_used"] is False
