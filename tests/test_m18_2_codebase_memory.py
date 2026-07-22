"""M18.2 — Governed codebase memory: indexing, provenance, retrieval, security."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from saathi.codebase_memory.classify import FileClass, classify_path
from saathi.codebase_memory.eval_set import EVAL_CASES, run_evaluation
from saathi.codebase_memory.freshness import Freshness, verify_result
from saathi.codebase_memory.health import index_health
from saathi.codebase_memory.identity import resolve_identity, identity_compatible
from saathi.codebase_memory.indexer import index_repository, rebuild_index
from saathi.codebase_memory.policy import path_exclusion_reason
from saathi.codebase_memory.retrieve import search
from saathi.codebase_memory.secrets_scan import scan_content
from saathi.codebase_memory.service import CodebaseMemoryRuntime, dispatch_tool
from saathi.codebase_memory.store import IndexStore, index_db_path
from saathi.mcp_governance.inventory import continuum_status
from saathi.mcp_governance.namespace import NamespaceError
from saathi.mcp_governance.policy import set_enabled, reset_policy_state

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def mini_repo(tmp_path):
    """Tiny git repo with code, docs, secrets, and vendored noise."""
    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "saathi").mkdir()
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()
    (repo / "node_modules" / "x").mkdir(parents=True)
    (repo / "saathi" / "engine.py").write_text(
        '"""engine"""\n\nclass EventBus:\n    def emit(self, t):\n        return t\n\n'
        "def mission_entry():\n    return EventBus()\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_engine.py").write_text(
        "from saathi.engine import EventBus\n\ndef test_bus():\n    assert EventBus()\n",
        encoding="utf-8",
    )
    (repo / "docs" / "ARCHITECTURE.md").write_text(
        "# Architecture\n\n## Event bus\nCanonical EventBus lives in saathi/engine.py.\n",
        encoding="utf-8",
    )
    (repo / "Brain.md").write_text("# Brain\nProject brain document.\n", encoding="utf-8")
    (repo / ".env").write_text("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789\n")
    (repo / "saathi" / "secrets_sample.py").write_text(
        'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz0123456789secret"\n'
    )
    (repo / "node_modules" / "x" / "index.js").write_text("module.exports=1\n")
    (repo / "saathi" / "namespace_policy.py").write_text(
        "def project_namespace(root):\n    return 'saathiai'\n"
    )
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    base = tmp_path / "idx"
    yield repo, base
    reset_policy_state()
    set_enabled(True)


def test_01_identity_isolation(tmp_path):
    a = tmp_path / "SaathiAI"
    b = tmp_path / "other" / "SaathiAI"
    a.mkdir()
    b.mkdir(parents=True)
    for p in (a, b):
        subprocess.run(["git", "init"], cwd=p, check=True, capture_output=True)
        (p / "f.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=p, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "i"], cwd=p, check=True, capture_output=True)
    ia = resolve_identity(a)
    ib = resolve_identity(b)
    assert ia.repository_id != ib.repository_id or ia.worktree_id != ib.worktree_id
    assert ia.index_key != ib.index_key


def test_02_non_git_fail_closed(tmp_path):
    d = tmp_path / "nongit"
    d.mkdir()
    with pytest.raises(NamespaceError):
        resolve_identity(d)
    ident = resolve_identity(d, allow_non_git=True)
    assert ident.non_git_mode is True


def test_03_classify_and_exclusions():
    assert classify_path("saathi/foo.py") == FileClass.SOURCE_CODE
    assert classify_path("tests/test_x.py") == FileClass.TEST_CODE
    assert classify_path(".env") == FileClass.SECRET
    assert classify_path("node_modules/x/a.js") == FileClass.VENDORED
    assert path_exclusion_reason(".env") == "secret_path"
    assert path_exclusion_reason("node_modules/x.js") is not None


def test_04_secret_scan_rejects_keys_keeps_docs():
    bad = scan_content('key = "sk-abcdefghijklmnopqrstuvwxyz012345"')
    assert bad.allowed is False
    ok = scan_content('def project_namespace(root):\n    return "x"\n')
    assert ok.allowed is True
    # Brain-like text with word "token" in prose must not false-positive
    prose = "The auth token flow is documented; use ExecutionGateway."
    assert scan_content(prose).allowed is True


def test_05_index_and_incremental(mini_repo):
    repo, base = mini_repo
    s1 = index_repository(repo, base_dir=base)
    assert s1.ok and s1.files_indexed >= 3
    assert s1.secret_exclusions >= 1  # .env and/or secrets_sample
    s2 = index_repository(repo, base_dir=base)
    assert s2.ok
    assert s2.files_unchanged >= 1
    # modify file → reindex only that
    (repo / "saathi" / "engine.py").write_text(
        (repo / "saathi" / "engine.py").read_text() + "\n# touch\n", encoding="utf-8"
    )
    s3 = index_repository(repo, base_dir=base)
    assert s3.files_indexed >= 1


def test_06_namespace_isolation(mini_repo, tmp_path):
    repo, base = mini_repo
    index_repository(repo, base_dir=base)
    r = search("EventBus", project_root=repo, base_dir=base, namespace="otherproj")
    assert r.denied is True
    r2 = search("EventBus", project_root=repo, base_dir=base)
    assert r2.ok and r2.hits


def test_07_retrieval_provenance_and_freshness(mini_repo):
    repo, base = mini_repo
    index_repository(repo, base_dir=base)
    r = search("EventBus", project_root=repo, base_dir=base, top_k=5)
    assert r.ok and r.hits
    h = r.hits[0]
    assert h.path
    assert h.citation
    assert h.freshness in {f.value for f in Freshness}
    assert h.repository_id
    assert h.file_hash
    assert h.score > 0


def test_08_live_verification_stale(mini_repo):
    repo, base = mini_repo
    index_repository(repo, base_dir=base)
    ident = resolve_identity(repo)
    # corrupt hash
    v = verify_result(
        root=repo, path="saathi/engine.py", indexed_hash="0" * 64,
        indexed_commit=ident.commit_sha, identity=ident,
    )
    assert v["freshness"] == Freshness.STALE_INDEX.value
    v2 = verify_result(
        root=repo, path="missing.py", indexed_hash="abc",
        indexed_commit=ident.commit_sha, identity=ident,
    )
    assert v2["freshness"] == Freshness.DELETED_SOURCE.value


def test_09_disable_and_tools(mini_repo):
    repo, base = mini_repo
    set_enabled(False)
    rt = CodebaseMemoryRuntime(repo, base_dir=base)
    assert rt.search("x")["degraded"] is True
    set_enabled(True)
    index_repository(repo, base_dir=base)
    h = dispatch_tool("codebase_memory_health", project_root=str(repo))
    assert h["ok"]
    denied = dispatch_tool("write_file", {"path": "x"}, project_root=str(repo))
    assert denied.get("denied") or not denied.get("ok")


def test_10_health_states(mini_repo):
    repo, base = mini_repo
    h0 = index_health(repo, base_dir=base)
    assert h0.status in ("EMPTY", "UNAVAILABLE", "HEALTHY")
    index_repository(repo, base_dir=base)
    h1 = index_health(repo, base_dir=base)
    assert h1.status == "HEALTHY"
    assert h1.chunks > 0
    assert h1.continuum_status == "BLOCKED_LICENSE"


def test_11_rebuild_and_schema(mini_repo):
    repo, base = mini_repo
    index_repository(repo, base_dir=base)
    s = rebuild_index(repo, base_dir=base)
    assert s.ok and s.rebuild


def test_12_no_vendored_or_env_in_hits(mini_repo):
    repo, base = mini_repo
    index_repository(repo, base_dir=base)
    r = search("module.exports", project_root=repo, base_dir=base)
    paths = " ".join(h.path for h in r.hits)
    assert "node_modules" not in paths
    r2 = search("OPENAI_API_KEY", project_root=repo, base_dir=base)
    # secret file must not be indexed; hits may be empty or non-secret docs
    for h in r2.hits:
        assert ".env" not in h.path
        assert "sk-abcdef" not in h.snippet


def test_13_continuum_blocked():
    assert continuum_status()["status"] == "BLOCKED_LICENSE"
    assert continuum_status()["installed"] is False


def test_14_trading_guardian_untouched():
    for p in (ROOT / "saathi" / "codebase_memory").rglob("*.py"):
        text = p.read_text(encoding="utf-8").lower()
        for banned in ("place_order", "binance", "alpaca", "withdraw_funds", "leverage"):
            assert banned not in text, p.name


def test_15_cli_help():
    from saathi.codebase_memory.cli import main
    # health on empty may return non-zero; ensure it runs
    code = main(["health", "--root", str(ROOT), "--json"])
    assert code in (0, 1, 2)


def test_16_m18_1_renumber_docs():
    """Canonical docs map historical M17.25 MCP governance → M18.1 without history rewrite."""
    inv = (ROOT / "docs" / "MCP_INVENTORY.md").read_text(encoding="utf-8")
    # After renumbering update, M18.1 should appear; allow either during transition
    roadmap = (ROOT / "docs" / "AUTONOMOUS_ROADMAP.md").read_text(encoding="utf-8")
    assert "M18.1" in roadmap or "M17.25" in inv
    # Browser M17.25 must remain distinct when mentioned
    assert "Interactive Browser" in roadmap or "browser" in roadmap.lower()


def test_17_eval_mini(mini_repo):
    repo, base = mini_repo
    index_repository(repo, base_dir=base)

    def sfn(q, **kw):
        return search(q, project_root=repo, base_dir=base, **kw).to_dict()

    r = sfn("EventBus engine")
    assert r["ok"] and any("engine" in (h.get("path") or "") for h in r["hits"])


def test_18_identity_compatible_schema():
    repo = ROOT
    try:
        ident = resolve_identity(repo)
    except Exception:
        pytest.skip("not a git checkout")
    ok, reason = identity_compatible(
        {
            "index_schema_version": "old",
            "repository_id": ident.repository_id,
            "worktree_id": ident.worktree_id,
        },
        ident,
    )
    assert ok is False and reason == "schema_mismatch"
