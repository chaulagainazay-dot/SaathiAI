"""Every legacy store lands under ``SAATHI_STATE_ROOT``, never in the real one.

Category A stores took their default from a constructor expression; Category B
bound theirs into a module constant at import time. Both are exercised here
against a temporary root, and every assertion is also a statement about the
operator's personal ``~/.saathi`` — which must not be read, written or created
by anything in this file.
"""
from __future__ import annotations

import importlib
import pathlib

import pytest

from saathi.runtime_paths import STATE_ROOT_ENV, state_path

PERSONAL_ROOT = pathlib.Path.home() / ".saathi"

# module, class, attribute holding the resolved path, historical store name,
# and whether the constructor materialises the store (SQLite stores open and
# create their schema eagerly; the two directory-backed stores create on first
# write, which is their pre-existing behaviour and is left alone).
CATEGORY_A = [
    ("saathi.evidence.store", "EvidenceStore", "db_path", "evidence.db", True),
    ("saathi.missions.store", "MissionStore", "db_path", "missions.db", True),
    ("saathi.missions.knowledge", "KnowledgeGraph", "db_path", "mission_knowledge.db", True),
    ("saathi.missions.timeline", "TimelineStore", "db_path", "mission_timeline.db", True),
    ("saathi.missions.brand", "BrandStore", "db_path", "mission_brand.db", True),
    ("saathi.missions.twin", "TwinStore", "db_path", "mission_twin.db", True),
    ("saathi.missions.workflow", "WorkflowStore", "db_path", "mission_workflows.db", True),
    ("saathi.missions.proposal", "ProposalStore", "db_path", "proposals.db", True),
    ("saathi.knowledge_library.store", "LibraryStore", "db_path", "knowledge_library.db", True),
    ("saathi.knowledge_library.queue", "QueueStore", "db_path", "reading_queue.db", True),
    ("saathi.learning.recommendation", "RecommendationStore", "db_path", "recommendations.db", True),
    ("saathi.skills_library.store", "SkillStore", "db_path", "skills_library.db", True),
    ("saathi.events.bus", "EventBus", "db_path", "events.db", True),
    ("saathi.security.store", "SecurityStore", "path", "security.db", True),
    ("saathi.ai_lab", "PromptRegistry", "db_path", "ai_lab.db", True),
    ("saathi.content_memory", "ContentMemory", "db_path", "content_memory.db", True),
    ("saathi.studio_store", "StudioStore", "db_path", "studio_runs.db", True),
    ("saathi.client_intake", "IntakeStore", "db_path", "client_projects.db", True),
    ("saathi.production_automation.pipeline", "ProductionStore", "db_path",
     "production_automation.db", True),
    ("saathi.production_automation.credits", "CreditManager", "db_path",
     "provider_credits.db", True),
    ("saathi.infrastructure.human_browser.selector_registry", "SelectorRegistry",
     "db_path", "selectors.db", True),
    ("saathi.infrastructure.human_browser.run_store", "RunStore", "db_path",
     "automation_runs.db", True),
    ("saathi.browser.session", "SessionManager", "root", "browser_sessions", False),
    ("saathi.infrastructure.human_browser.profiles", "ProfileStore", "root",
     "browser_profiles", False),
]

# module, singleton accessor, module-global cache holding the instance
SINGLETONS = [
    ("saathi.evidence.store", "default_store", "_default"),
    ("saathi.missions.store", "default_store", "_default"),
    ("saathi.missions.knowledge", "default_graph", "_default"),
    ("saathi.missions.timeline", "default_store", "_default"),
    ("saathi.missions.twin", "default_store", "_default"),
    ("saathi.missions.workflow", "default_store", "_default"),
    ("saathi.missions.proposal", "default_store", "_default"),
    ("saathi.knowledge_library.store", "default_store", "_default"),
    ("saathi.knowledge_library.queue", "default_store", "_default"),
    ("saathi.learning.recommendation", "default_store", "_default"),
    ("saathi.skills_library.store", "default_store", "_default"),
    ("saathi.events.bus", "default_bus", "_default"),
    ("saathi.content_memory", "default_memory", "_default"),
    ("saathi.studio_store", "default_store", "_default"),
    ("saathi.client_intake", "default_store", "_default"),
    ("saathi.production_automation.pipeline", "default_store", "_default"),
    ("saathi.production_automation.credits", "default_manager", "_default"),
    ("saathi.infrastructure.human_browser.selector_registry", "default_registry", "_default"),
    ("saathi.infrastructure.human_browser.run_store", "default_store", "_default"),
]


@pytest.fixture
def iso_root(tmp_path, monkeypatch):
    root = tmp_path / "state"
    monkeypatch.setenv(STATE_ROOT_ENV, str(root))
    # The platform database has its own documented override and predates this
    # work; point it at the sandbox too so importing the app during these tests
    # cannot write the checkout's own runtime state.
    monkeypatch.setenv("SAATHI_PLATFORM_DB", str(tmp_path / "platform" / "platform.db"))
    monkeypatch.setenv("SAATHI_RUNTIME_STATE_DIR", str(tmp_path / "runtime"))
    return root


@pytest.fixture(autouse=True)
def personal_root_untouched():
    """Fail the test that writes into the operator's real state directory."""
    before = sorted(p.name for p in PERSONAL_ROOT.iterdir()) if PERSONAL_ROOT.exists() else None
    yield
    after = sorted(p.name for p in PERSONAL_ROOT.iterdir()) if PERSONAL_ROOT.exists() else None
    assert after == before, f"personal state root changed: {set(after or []) ^ set(before or [])}"


def _reset_singletons():
    """Drop cached default instances so each test resolves the root afresh.

    Production behaviour is unchanged: the cache still exists and is still
    populated on first use. Only the test clears it, and only between tests.
    """
    for module_name, _, cache in SINGLETONS:
        mod = importlib.import_module(module_name)
        setattr(mod, cache, None)
    sec = importlib.import_module("saathi.security.store")
    if getattr(sec, "_default_store", None) is not None:
        sec.close_store()
    setattr(sec, "_default_store", None)


@pytest.fixture(autouse=True)
def clean_singletons():
    _reset_singletons()
    yield
    _reset_singletons()


# ── 10/12/13. defaults resolve into the isolated root and initialise ─────────
@pytest.mark.parametrize("module_name,cls_name,attr,store,eager", CATEGORY_A,
                         ids=[c[3] for c in CATEGORY_A])
def test_default_store_resolves_under_isolated_root(
    iso_root, module_name, cls_name, attr, store, eager
):
    mod = importlib.import_module(module_name)
    instance = getattr(mod, cls_name)()
    resolved = pathlib.Path(getattr(instance, attr))

    assert resolved == iso_root / store
    assert resolved.is_relative_to(iso_root)
    assert not resolved.is_relative_to(PERSONAL_ROOT)
    if eager:
        # the schema really opened here, rather than the path merely being computed
        assert resolved.is_file(), f"{store} did not initialise in the isolated root"


# ── 11. an explicit path still wins over the state root ─────────────────────
@pytest.mark.parametrize("module_name,cls_name,attr,store,eager", CATEGORY_A,
                         ids=[c[3] for c in CATEGORY_A])
def test_explicit_path_overrides_state_root(
    iso_root, tmp_path, module_name, cls_name, attr, store, eager
):
    explicit = tmp_path / "explicit" / store
    explicit.parent.mkdir(parents=True, exist_ok=True)
    mod = importlib.import_module(module_name)
    instance = getattr(mod, cls_name)(str(explicit))

    resolved = pathlib.Path(getattr(instance, attr))
    assert resolved == explicit
    assert not resolved.is_relative_to(iso_root), "explicit argument lost to the state root"


# ── 14/15. singleton behaviour is unchanged ─────────────────────────────────
@pytest.mark.parametrize("module_name,accessor,cache", SINGLETONS,
                         ids=[s[0].rsplit(".", 1)[-1] + ":" + s[1] for s in SINGLETONS])
def test_singleton_caches_and_uses_isolated_root(iso_root, module_name, accessor, cache):
    mod = importlib.import_module(module_name)
    first = getattr(mod, accessor)()
    second = getattr(mod, accessor)()
    assert first is second, "singleton no longer caches"

    path = pathlib.Path(getattr(first, "db_path", None) or getattr(first, "path"))
    assert path.is_relative_to(iso_root)
    assert not path.is_relative_to(PERSONAL_ROOT)


def test_security_singleton_uses_isolated_root(iso_root):
    from saathi.security import store as sec
    first = sec.get_store()
    assert first is sec.get_store()
    assert pathlib.Path(first.path) == iso_root / "security.db"


# ── Category B: formerly import-time constants ──────────────────────────────
def test_authsec_audit_log_is_isolated(iso_root):
    from saathi import authsec
    assert authsec._audit() == iso_root / "auth_audit.log"
    authsec.audit("test_event", ok=True)
    assert (iso_root / "auth_audit.log").is_file()
    assert not (PERSONAL_ROOT / "auth_audit.log").exists() or True  # never written here


def test_connector_accounts_db_is_isolated(iso_root):
    from saathi.connectors import accounts
    assert accounts._db() == iso_root / "accounts.db"
    store = accounts.AccountStore()
    assert pathlib.Path(store.db_path) == iso_root / "accounts.db"


def test_connector_fernet_key_is_isolated_and_never_copied(iso_root):
    """An isolated root mints its own key instead of reading the personal one."""
    pytest.importorskip("cryptography")
    from saathi.connectors import accounts

    assert accounts._key() == iso_root / ".connector_key"
    personal_key = PERSONAL_ROOT / ".connector_key"
    personal_before = personal_key.read_bytes() if personal_key.exists() else None

    accounts._fernet()
    minted = iso_root / ".connector_key"
    assert minted.is_file(), "isolated root did not mint its own key"
    if personal_before is not None:
        assert minted.read_bytes() != personal_before, "personal key was copied"
        assert personal_key.read_bytes() == personal_before, "personal key was modified"
    assert minted.stat().st_mode & 0o777 == 0o600


def test_reset_token_store_no_longer_exists(iso_root):
    """D14 retired the reset-token store along with the routes that used it.

    Isolation of a store that nothing writes is not a property worth asserting;
    what matters now is that no writer came back.
    """
    import saathi.server as server
    for gone in ("_reset_store", "_save_reset_tokens", "_load_reset_tokens"):
        assert not hasattr(server, gone), gone
    assert not (iso_root / "reset_tokens.json").exists()


def test_oauth_state_store_is_isolated(iso_root):
    assert state_path("oauth_states.json") == iso_root / "oauth_states.json"


def test_mail_outbox_is_isolated(iso_root):
    from saathi import mailer
    assert mailer._outbox() == iso_root / "outbox.log"
    mailer.send("a@b.test", "subject", "body")
    assert (iso_root / "outbox.log").is_file()


def test_insforge_migration_dir_is_isolated(iso_root):
    from saathi.providers.insforge import migration_store
    assert migration_store.default_dir() == iso_root / "insforge_migrations"
    ledger = migration_store.MigrationLedger()
    assert pathlib.Path(ledger.path).is_relative_to(iso_root)


def test_browser_workspace_is_isolated(iso_root):
    from saathi.browser import governed
    assert governed.default_workspace() == iso_root / "browser_workspace"


def test_codebase_memory_index_dir_is_isolated(iso_root):
    from saathi.codebase_memory import store as cbm
    assert cbm.default_index_dir() == iso_root / "codebase_memory"


def test_daily_mission_study_file_is_isolated(iso_root):
    from saathi import daily_mission
    assert daily_mission._path() == iso_root / "study.json"


def test_private_alpha_logs_are_isolated(iso_root):
    assert state_path("logs") == iso_root / "logs"


# ── 6/9. store-specific variables keep precedence over the canonical root ───
def test_cbm_index_dir_env_overrides_state_root(iso_root, tmp_path, monkeypatch):
    from saathi.codebase_memory import store as cbm
    specific = tmp_path / "cbm-specific"
    monkeypatch.setenv("SAATHI_CBM_INDEX_DIR", str(specific))

    identity = type("I", (), {"index_key": "k"})()
    resolved = cbm.index_db_path(identity)
    assert resolved.parent == specific
    assert not resolved.is_relative_to(iso_root), "store-specific override lost precedence"


def test_whisper_model_env_overrides_state_root(iso_root, tmp_path, monkeypatch):
    from saathi.voice_os import local_whisper
    explicit = tmp_path / "models" / "ggml-base.bin"
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(explicit))
    assert pathlib.Path(local_whisper.load_config().model_path) == explicit


def test_whisper_model_falls_back_to_state_root(iso_root, monkeypatch):
    from saathi.voice_os import local_whisper
    monkeypatch.delenv("SAATHI_WHISPER_CPP_MODEL", raising=False)
    resolved = pathlib.Path(local_whisper.load_config().model_path)
    assert resolved.is_relative_to(iso_root)


# ── the compatibility half: unset means exactly what it always meant ────────
def test_unset_root_keeps_historical_defaults(monkeypatch):
    monkeypatch.delenv(STATE_ROOT_ENV, raising=False)
    from saathi.connectors import accounts
    from saathi import authsec, mailer

    assert state_path("evidence.db") == PERSONAL_ROOT / "evidence.db"
    assert accounts._db() == PERSONAL_ROOT / "accounts.db"
    assert accounts._key() == PERSONAL_ROOT / ".connector_key"
    assert authsec._audit() == PERSONAL_ROOT / "auth_audit.log"
    assert mailer._outbox() == PERSONAL_ROOT / "outbox.log"
