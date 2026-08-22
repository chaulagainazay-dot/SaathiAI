"""Source invariant: no writable store may hardcode the personal state root.

The isolation repair rewrote every legacy ``Path.home() / ".saathi" / X`` into
``saathi.runtime_paths.state_path(X)``. That repair is only worth as much as its
resistance to the next patch, so this module re-derives the property from the
source tree on every run instead of trusting a count recorded once.

Two independent halves:

``test_every_known_store_routes_through_state_path``
    the positive half — each store in ``STORE_INVENTORY`` is still wired to the
    canonical resolver in the module that owns it.

``test_no_hardcoded_state_root_in_production_source``
    the negative half — no *new* module reintroduces a hardcoded root by any of
    the spellings the original code used.

The scanner works on the AST rather than on raw text. Comments never reach the
AST at all, docstrings are ordinary string statements, and a string only counts
when it is actually handed to something that builds a path — which is what
separates ``Path(os.path.expanduser("~/.saathi/study.json"))`` (a real store)
from ``"staging.saathi.local"`` (a hostname) or a ``print()`` describing a shell
command to the operator. ``test_scanner_fixtures`` pins that discrimination.
"""
from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Every legacy writable store, mapped to the module that owns its default path.
# Adding a store here without wiring it to state_path() fails the positive half;
# adding one to the source without listing it here fails nothing on its own, so
# the negative half is what actually guards the tree.
STORE_INVENTORY: dict[str, str] = {
    # ── Category A: constructor defaults ──────────────────────────────────────
    "evidence.db": "saathi/evidence/store.py",
    "missions.db": "saathi/missions/store.py",
    "mission_knowledge.db": "saathi/missions/knowledge.py",
    "mission_timeline.db": "saathi/missions/timeline.py",
    "mission_brand.db": "saathi/missions/brand.py",
    "mission_twin.db": "saathi/missions/twin.py",
    "mission_workflows.db": "saathi/missions/workflow.py",
    "proposals.db": "saathi/missions/proposal.py",
    "knowledge_library.db": "saathi/knowledge_library/store.py",
    "reading_queue.db": "saathi/knowledge_library/queue.py",
    "recommendations.db": "saathi/learning/recommendation.py",
    "skills_library.db": "saathi/skills_library/store.py",
    "events.db": "saathi/events/bus.py",
    "security.db": "saathi/security/store.py",
    "ai_lab.db": "saathi/ai_lab.py",
    "content_memory.db": "saathi/content_memory.py",
    "studio_runs.db": "saathi/studio_store.py",
    "client_projects.db": "saathi/client_intake.py",
    "production_automation.db": "saathi/production_automation/pipeline.py",
    "provider_credits.db": "saathi/production_automation/credits.py",
    "selectors.db": "saathi/infrastructure/human_browser/selector_registry.py",
    "automation_runs.db": "saathi/infrastructure/human_browser/run_store.py",
    "browser_sessions": "saathi/browser/session.py",
    "browser_profiles": "saathi/infrastructure/human_browser/profiles.py",
    # ── Category B: formerly bound at import time ─────────────────────────────
    "auth_audit.log": "saathi/authsec.py",
    "accounts.db": "saathi/connectors/accounts.py",
    ".connector_key": "saathi/connectors/accounts.py",
    "reset_tokens.json": "saathi/server.py",
    "outbox.log": "saathi/mailer.py",
    "insforge_migrations": "saathi/providers/insforge/migration_store.py",
    "browser_workspace": "saathi/browser/governed.py",
    "codebase_memory": "saathi/codebase_memory/store.py",
    # ── Other writable paths resolved per call ────────────────────────────────
    "oauth_states.json": "saathi/server.py",
    "study.json": "saathi/daily_mission.py",
    "logs": "saathi/platform/private_alpha/support.py",
    "sessions.json": "saathi/security/store.py",
    "passkeys.json": "saathi/security/store.py",
    "stt-models": "saathi/voice_os/local_whisper.py",
}

# Directories of importable production source. Tests and fixtures are excluded:
# a test is *supposed* to be able to name the personal root in order to assert
# that nothing touches it.
SOURCE_DIRS = ("saathi", "scripts", "tools")

# Standalone operator tooling for the speech-training corpora. These are not
# imported by the backend, so they cannot affect its isolation, and they address
# a corpus of recordings that deliberately lives outside any validation root —
# repointing them is a separate change with its own consent question. They are
# pinned rather than skipped so the set can only shrink: a *new* hardcoded path,
# here or anywhere else under SOURCE_DIRS, still fails the invariant.
KNOWN_UNISOLATED = {
    "tools/voice-stt-bench/benchmark_codeswitch.py",
    "tools/voice-stt-bench/benchmark_specialized_nepali.py",
    "tools/voice-stt-bench/benchmark_whisper_vs_omni.py",
    "tools/voice-stt-bench/complete_owner_corpus.py",
    "tools/voice-stt-bench/owner_record_tool.py",
    "tools/voice-stt-data/scripts/assign_prompts.py",
    "tools/voice-stt-data/scripts/build_splits.py",
    "tools/voice-stt-data/scripts/campaign_progress.py",
    "tools/voice-stt-data/scripts/campaign_session.py",
    "tools/voice-stt-data/scripts/contamination_check.py",
    "tools/voice-stt-data/scripts/dataset_stats.py",
    "tools/voice-stt-data/scripts/freeze_dataset.py",
    "tools/voice-stt-data/scripts/hash_dedupe.py",
    "tools/voice-stt-data/scripts/participant_recorder.py",
    "tools/voice-stt-data/scripts/qa_clips.py",
    "tools/voice-stt-data/scripts/training_authorization_gate.py",
    "tools/voice-stt-data/scripts/verify_transcript.py",
    "tools/voice-stt-train/scripts/prove_ct2_plumbing.py"
}

# The one module allowed to name the historical default — it defines it.
RESOLVER_MODULE = "saathi/runtime_paths.py"

# Calls that turn a string into a filesystem path.
_PATH_BUILDERS = {
    "Path", "PurePath", "PosixPath", "open",
    "expanduser", "expandvars", "join", "makedirs", "mkdir",
}

# Distinct directory, tracked in the repository rather than under the state root.
_AGENT_STATE = ".saathi-agent-state"


def _is_state_dir_string(text: str) -> bool:
    """True when a literal denotes the personal state directory as a path.

    Requires a separator so ``"staging.saathi.local"`` (a hostname) and a bare
    ``".saathi"`` used as a registry key are both excluded, and skips the
    unrelated repository-local agent-state directory.
    """
    if _AGENT_STATE in text:
        return False
    return "~/.saathi" in text or "/.saathi/" in text or text.endswith("/.saathi")


def _is_state_dir_operand(node: ast.AST) -> bool:
    """True for the right-hand side of ``Path.home() / <here>``.

    Both spellings occur in the tree: a bare ``".saathi"`` followed by further
    ``/`` operands, and a single combined ``".saathi/stt-models/x"``. Matching
    only the first would let the combined form through silently.
    """
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False
    text = node.value
    if _AGENT_STATE in text:
        return False
    return text == ".saathi" or text.startswith(".saathi/")


def _callee_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _is_path_home_call(node: ast.AST) -> bool:
    """Match ``Path.home()`` / ``pathlib.Path.home()``."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "home"
        and _callee_name(node.func.value) in {"Path", "PurePath", "PosixPath"}
    )


class _Scanner(ast.NodeVisitor):
    """Collects hardcoded-root and import-time-binding violations."""

    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.violations: list[tuple[int, str]] = []
        self._depth = 0  # >0 means inside a function body

    # ── scope tracking: only module/class level is "import time" ─────────────
    def visit_FunctionDef(self, node):  # noqa: N802
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815
    visit_Lambda = visit_FunctionDef  # noqa: N815

    def _flag(self, node: ast.AST, why: str) -> None:
        self.violations.append((getattr(node, "lineno", 0), why))

    # ── V1: Path.home() / ".saathi" ──────────────────────────────────────────
    def visit_BinOp(self, node):  # noqa: N802
        if isinstance(node.op, ast.Div):
            if _is_path_home_call(node.left) and _is_state_dir_operand(node.right):
                self._flag(node, 'Path.home() / ".saathi..." — use state_path()')
        self.generic_visit(node)

    # ── V2/V3: a state-root string handed to a path builder ──────────────────
    def visit_Call(self, node):  # noqa: N802
        if _callee_name(node.func) in _PATH_BUILDERS:
            for arg in node.args:
                for sub in ast.walk(arg):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                            and _is_state_dir_string(sub.value):
                        self._flag(node, f"{_callee_name(node.func)}({sub.value!r}) "
                                         "— use state_path()")
                    # f-string segment, e.g. f"{Path.home()}/.saathi/x.db"
                    if isinstance(sub, ast.JoinedStr):
                        joined = "".join(
                            p.value for p in sub.values
                            if isinstance(p, ast.Constant) and isinstance(p.value, str)
                        )
                        if _is_state_dir_string(joined):
                            self._flag(node, "f-string state path — use state_path()")
        # ── V4: state root frozen into a module/class-level constant ─────────
        if self._depth == 0 and _callee_name(node.func) in {"state_path", "state_root"}:
            self._flag(node, f"{_callee_name(node.func)}() called at import time — "
                             "resolve it inside the function that uses it")
        self.generic_visit(node)


def scan_source(source: str, relpath: str = "<memory>") -> list[tuple[int, str]]:
    """Return ``(lineno, reason)`` for every hardcoded/import-time state path."""
    scanner = _Scanner(relpath)
    scanner.visit(ast.parse(source))
    return scanner.violations


def _production_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for d in SOURCE_DIRS:
        for p in sorted((REPO_ROOT / d).rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            files.append(p)
    return files


# ── the invariant ────────────────────────────────────────────────────────────
def _violations() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in _production_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel == RESOLVER_MODULE:
            continue
        try:
            hits = scan_source(path.read_text(errors="replace"), rel)
        except SyntaxError:  # a tool targeting a different interpreter
            continue
        if hits:
            found[rel] = [f"{rel}:{n}: {w}" for n, w in hits]
    return found


def test_no_hardcoded_state_root_in_production_source():
    """No module may name the personal state root directly, bar the pinned set."""
    found = _violations()
    new = sorted(k for k in found if k not in KNOWN_UNISOLATED)
    assert not new, (
        "hardcoded or import-time state paths reintroduced:\n  "
        + "\n  ".join(line for k in new for line in found[k])
        + "\n\nRoute the store through saathi.runtime_paths.state_path()."
    )


def test_the_pinned_exception_set_only_shrinks():
    """A pinned file that was fixed (or deleted) must leave the set."""
    found = _violations()
    stale = sorted(k for k in KNOWN_UNISOLATED if k not in found)
    assert not stale, (
        "these no longer hardcode a state path — remove them from "
        "KNOWN_UNISOLATED:\n  " + "\n  ".join(stale)
    )


def test_the_backend_package_has_no_exceptions():
    """Whatever is tolerated in tooling, `saathi/` itself must be clean."""
    offenders = sorted(k for k in _violations() if k.startswith("saathi/"))
    assert not offenders, offenders


def test_every_known_store_routes_through_state_path():
    """Each inventoried store still resolves through the canonical resolver."""
    missing: list[str] = []
    for store, owner in sorted(STORE_INVENTORY.items()):
        src = (REPO_ROOT / owner).read_text()
        if f'state_path("{store}")' not in src:
            missing.append(f"{owner} no longer calls state_path({store!r})")
    assert not missing, "\n".join(missing)


def test_inventory_owners_exist():
    """A store may not point at a module that has been moved or deleted."""
    for store, owner in sorted(STORE_INVENTORY.items()):
        assert (REPO_ROOT / owner).is_file(), f"{store}: missing owner {owner}"


# ── fixtures: the scanner must catch code and ignore prose ───────────────────
CAUGHT = {
    "path_home_div": 'from pathlib import Path\nDB = Path.home() / ".saathi" / "x.db"\n',
    "path_home_div_combined": 'from pathlib import Path\n'
                              'M = Path.home() / ".saathi/stt-models/v2/model.bin"\n',
    "path_home_div_combined_dir": 'from pathlib import Path\n'
                                  'C = Path.home() / ".saathi/stt-product-corpus"\n',
    "expanduser": 'import os\np = os.path.expanduser("~/.saathi/study.json")\n',
    "path_expanduser_nested": 'from pathlib import Path\nimport os\n'
                              'p = Path(os.path.expanduser("~/.saathi/x.db"))\n',
    "open_literal": 'f = open("/home/me/.saathi/outbox.log", "a")\n',
    "join_literal": 'import os\np = os.path.join("~/.saathi/logs", "backend.log")\n',
    "fstring": 'from pathlib import Path\np = Path(f"{Path.home()}/.saathi/x.db")\n',
    "import_time_state_path": (
        'from saathi.runtime_paths import state_path\nDB = state_path("x.db")\n'
    ),
    "import_time_state_root": (
        'from saathi.runtime_paths import state_root\nROOT = state_root()\n'
    ),
    "class_level_binding": (
        'from saathi.runtime_paths import state_path\n'
        'class S:\n    DB = state_path("x.db")\n'
    ),
}

IGNORED = {
    "module_docstring": '"""Stores SQLite at ~/.saathi/evidence.db by default."""\nX = 1\n',
    "comment": '# Reset tokens live in ~/.saathi/reset_tokens.json with a TTL.\nX = 1\n',
    "inline_comment": 'X = 1  # migrated away from ~/.saathi/x.db\n',
    "hostname": 'HOSTS = ["staging.saathi.local", "saathi.local"]\n',
    "hostname_in_path_call": 'from pathlib import Path\np = Path("/etc/staging.saathi.local")\n',
    "agent_state_dir": 'from pathlib import Path\nD = Path(".saathi-agent-state") / "SESSION"\n',
    "agent_state_via_home": 'from pathlib import Path\n'
                            'D = Path.home() / ".saathi-agent-state" / "SESSION"\n',
    "registry_literal": 'PROTECTED = [(".saathi", "saathi_user_state")]\n',
    "operator_hint_print": 'print("  --user-data-dir=\\"$HOME/.saathi/chrome-cdp\\"")\n',
    "url": 'URL = "https://saathi.local/.saathi/docs"\n',
    "regex_literal": 'import re\nR = re.compile(r"(\\.saathi-agent-state/SESSION)")\n',
    "lazy_accessor": (
        'from saathi.runtime_paths import state_path\n'
        'def _db():\n    return state_path("x.db")\n'
    ),
    "constructor_default": (
        'from pathlib import Path\nfrom saathi.runtime_paths import state_path\n'
        'class S:\n'
        '    def __init__(self, db_path=None):\n'
        '        self.db_path = Path(db_path) if db_path else state_path("x.db")\n'
    ),
}


def test_scanner_catches_executable_state_paths():
    """Every spelling the repaired code used must still be detected."""
    for name, src in sorted(CAUGHT.items()):
        assert scan_source(src, name), f"scanner MISSED {name}:\n{src}"


def test_scanner_ignores_prose_and_unrelated_literals():
    """Documentation, hostnames and the agent-state dir are not violations."""
    for name, src in sorted(IGNORED.items()):
        found = scan_source(src, name)
        assert not found, f"scanner FALSELY flagged {name}: {found}\n{src}"


def test_scanner_detects_a_regression_in_a_real_store():
    """Reverting one real store to the old pattern must fail the invariant."""
    src = (REPO_ROOT / "saathi/evidence/store.py").read_text()
    assert not scan_source(src, "evidence"), "store is already dirty"
    reverted = src.replace(
        'state_path("evidence.db")', '(Path.home() / ".saathi" / "evidence.db")'
    )
    assert reverted != src, "pattern not found — update this test"
    assert scan_source(reverted, "evidence"), "invariant would not catch a revert"
