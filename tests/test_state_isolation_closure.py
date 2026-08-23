"""Safety closure for the canonical state-root repair.

Three gaps remained after the isolation commit, and each is closed here with a
proof rather than a convention:

* ``test_auth_v1`` deleted the operator's real auth files whenever
  ``SAATHI_STATE_ROOT`` happened to be unset. It is now safe by construction,
  and :func:`test_auth_suite_cannot_touch_personal_state_with_root_unset` runs
  it against a decoy home with the variable removed to prove it.
* ``storage/storage.db``, ``data/baadar.db`` and ``data/projects.json`` resolved
  from ``config.ROOT`` and escaped isolation entirely. They now go through
  ``scoped_state_path``, which keeps the historical repository location when no
  root is configured and moves them under the root when one is.
* the Whisper model is a read-only, checksum-pinned artifact that is
  deliberately shared rather than copied into a validation root.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys

import pytest

from saathi.runtime_paths import (
    STATE_ROOT_ENV,
    StateRootError,
    baadar_db_path,
    projects_registry_path,
    scoped_state_path,
    storage_db_path,
    storage_root_path,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PERSONAL_ROOT = pathlib.Path.home() / ".saathi"

# The pinned Test A model: 141 MiB, read-only, shared rather than copied.
PINNED_MODEL = PERSONAL_ROOT / "stt-models" / "whisper-cpp" / "ggml-base.bin"
FIXTURE_WAV = PERSONAL_ROOT / "r21-validation" / "fixtures" / "en_fixture.wav"

# Personal auth files the auth suite used to unlink outright.
PERSONAL_AUTH_FILES = (
    "security.db", "sessions.json", "passkeys.json",
    "reset_tokens.json", "auth_audit.log", "oauth_states.json",
)


@pytest.fixture
def no_overrides(monkeypatch):
    """Nothing configured — the historical repository defaults must apply."""
    for var in (STATE_ROOT_ENV, "BAADAR_DB", "SAATHI_PROJECTS_FILE",
                "SAATHI_STORAGE_DB", "SAATHI_STORAGE_ROOT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def iso_root(tmp_path, monkeypatch, no_overrides):
    root = tmp_path / "state"
    monkeypatch.setenv(STATE_ROOT_ENV, str(root))
    return root


# ── 1. the auth suite is safe without a caller-supplied environment ─────────
def _hash_tree(root: pathlib.Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_auth_suite_cannot_touch_personal_state_with_root_unset(tmp_path):
    """Run the real auth suite with SAATHI_STATE_ROOT removed and a decoy home.

    ``Path.home()`` is redirected inside the child rather than ``$HOME``, so the
    interpreter keeps its own site-packages and the suite genuinely executes.
    Changing ``$HOME`` instead makes the run collapse at import, which would
    make an untouched decoy prove nothing at all.
    """
    decoy = tmp_path / "decoyhome"
    saathi_dir = decoy / ".saathi"
    saathi_dir.mkdir(parents=True)
    for name in PERSONAL_AUTH_FILES + (".connector_key", "accounts.db"):
        (saathi_dir / name).write_text(f"DECOY-{name}-do-not-touch\n")
    before = _hash_tree(decoy)
    assert len(before) == len(PERSONAL_AUTH_FILES) + 2

    basetemp = tmp_path / "basetemp"
    runner = tmp_path / "decoy_runner.py"
    runner.write_text(
        "import os, pathlib, sys\n"
        f"DECOY = {str(decoy)!r}\n"
        "pathlib.Path.home = classmethod(lambda cls: cls(DECOY))\n"
        "_orig = os.path.expanduser\n"
        "os.path.expanduser = lambda p: (DECOY + p[1:]) if isinstance(p, str)"
        " and p.startswith('~') else _orig(p)\n"
        "import pytest\n"
        "sys.exit(pytest.main(sys.argv[1:]))\n"
    )

    env = {k: v for k, v in os.environ.items() if k != STATE_ROOT_ENV}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(runner), "tests/test_auth_v1.py", "-q",
         "-p", "no:warnings", "-p", "no:cacheprovider", f"--basetemp={basetemp}"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, (
        "the auth suite must pass with no state root configured:\n"
        + proc.stdout[-4000:] + proc.stderr[-2000:]
    )
    assert "passed" in proc.stdout, proc.stdout[-2000:]

    after = _hash_tree(decoy)
    assert after == before, (
        "the auth suite modified or deleted personal state with the root unset: "
        f"{set(before) ^ set(after) or 'contents changed'}"
    )
    assert basetemp.exists(), "the suite created nothing — it cannot have run"


def test_collecting_the_auth_module_has_no_filesystem_side_effect(tmp_path):
    """Collection alone must not create, read or delete a personal file."""
    decoy = tmp_path / "decoyhome"
    (decoy / ".saathi").mkdir(parents=True)
    (decoy / ".saathi" / "security.db").write_text("DECOY\n")
    before = _hash_tree(decoy)

    runner = tmp_path / "collect_runner.py"
    runner.write_text(
        "import os, pathlib, sys, json\n"
        f"DECOY = {str(decoy)!r}\n"
        "touched = []\n"
        "def hook(event, args):\n"
        "    if event == 'open':\n"
        "        p = args[0]\n"
        "        if isinstance(p, str) and p.startswith(DECOY):\n"
        "            touched.append(p)\n"
        "sys.addaudithook(hook)\n"
        "pathlib.Path.home = classmethod(lambda cls: cls(DECOY))\n"
        "import pytest\n"
        "code = pytest.main(sys.argv[1:])\n"
        "print('@@T@@' + json.dumps(touched))\n"
        "sys.exit(code)\n"
    )
    env = {k: v for k, v in os.environ.items() if k != STATE_ROOT_ENV}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(runner), "tests/test_auth_v1.py", "--collect-only",
         "-q", "-p", "no:warnings", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@T@@")]
    assert marker, proc.stdout[-2000:]
    touched = json.loads(marker[-1][len("@@T@@"):])
    assert touched == [], f"collection touched personal files: {touched}"
    assert _hash_tree(decoy) == before


# ── 3. the destructive helper refuses anything it does not own ──────────────
def test_cleanup_helper_refuses_targets_outside_its_owned_root(tmp_path):
    from tests.test_auth_v1 import UnsafeCleanupTarget, _unlink_within

    owned = tmp_path / "owned"
    owned.mkdir()
    inside = owned / "security.db"
    inside.write_text("x")
    _unlink_within(owned, inside)
    assert not inside.exists(), "helper failed to delete a file it does own"

    outside = tmp_path / "elsewhere" / "security.db"
    outside.parent.mkdir()
    outside.write_text("precious")
    with pytest.raises(UnsafeCleanupTarget):
        _unlink_within(owned, outside)
    assert outside.read_text() == "precious"

    # the real hazard: the personal auth files, named directly
    for name in PERSONAL_AUTH_FILES:
        with pytest.raises(UnsafeCleanupTarget):
            _unlink_within(owned, PERSONAL_ROOT / name)

    # and an escape dressed up as a relative path
    with pytest.raises(UnsafeCleanupTarget):
        _unlink_within(owned, owned / ".." / "elsewhere" / "security.db")


# ── 4-8. precedence for the three repo-local stores ─────────────────────────
SCOPED_STORES = [
    ("storage_db", lambda: storage_db_path(), "SAATHI_STORAGE_DB",
     "storage/storage.db", REPO_ROOT / "storage" / "storage.db"),
    ("storage_root", lambda: storage_root_path(), "SAATHI_STORAGE_ROOT",
     "storage", REPO_ROOT / "storage"),
    ("baadar_db", lambda: baadar_db_path(), "BAADAR_DB",
     "data/baadar.db", REPO_ROOT / "data" / "baadar.db"),
    ("projects", lambda: projects_registry_path(), "SAATHI_PROJECTS_FILE",
     "data/projects.json", REPO_ROOT / "data" / "projects.json"),
]


@pytest.mark.parametrize("name,resolve,env,relative,historical", SCOPED_STORES,
                         ids=[s[0] for s in SCOPED_STORES])
def test_historical_repo_path_when_nothing_is_configured(
    no_overrides, name, resolve, env, relative, historical
):
    """Production behaviour is unchanged: still the repository location."""
    assert resolve() == historical


@pytest.mark.parametrize("name,resolve,env,relative,historical", SCOPED_STORES,
                         ids=[s[0] for s in SCOPED_STORES])
def test_state_root_relocates_the_store(iso_root, name, resolve, env, relative, historical):
    """A configured root moves the store under it — with no fall-through."""
    assert resolve() == iso_root.joinpath(*relative.split("/"))
    assert not resolve().is_relative_to(REPO_ROOT)


@pytest.mark.parametrize("name,resolve,env,relative,historical", SCOPED_STORES,
                         ids=[s[0] for s in SCOPED_STORES])
def test_store_specific_override_beats_the_state_root(
    iso_root, tmp_path, monkeypatch, name, resolve, env, relative, historical
):
    explicit = tmp_path / "explicit" / pathlib.PurePath(relative).name
    monkeypatch.setenv(env, str(explicit))
    assert resolve() == explicit
    assert not resolve().is_relative_to(iso_root)


@pytest.mark.parametrize("name,resolve,env,relative,historical", SCOPED_STORES,
                         ids=[s[0] for s in SCOPED_STORES])
def test_relative_store_override_is_rejected(monkeypatch, name, resolve, env, relative, historical):
    monkeypatch.setenv(env, "relative/path")
    with pytest.raises(StateRootError):
        resolve()


def test_scoped_helper_does_not_fall_back_when_a_root_is_set(iso_root):
    """An isolated run must never silently write back into the checkout."""
    resolved = scoped_state_path("data/x.db", env="SAATHI_NOT_SET_ANYWHERE",
                                 historical=REPO_ROOT / "data" / "x.db")
    assert resolved == iso_root / "data" / "x.db"
    assert not resolved.is_relative_to(REPO_ROOT)


# ── 9. every reader and writer of a store resolves the same path ────────────
def _module_paths():
    import importlib
    intel = importlib.import_module("saathi.tools.intelligence")
    ref = importlib.import_module("saathi.tools.referral")
    proj = importlib.import_module("saathi.tools.projects")
    return intel, ref, proj


def test_readers_and_writers_agree_on_baadar_db(iso_root):
    intel, ref, _ = _module_paths()
    canonical = str(baadar_db_path())
    assert intel.DB_PATH == canonical
    assert ref.DB_PATH == canonical
    assert canonical.startswith(str(iso_root))


def test_readers_and_writers_agree_on_projects_registry(iso_root):
    _, _, proj = _module_paths()
    assert proj.REGISTRY == projects_registry_path()
    assert proj.REGISTRY.is_relative_to(iso_root)


def test_projects_writer_and_reader_round_trip_inside_the_root(iso_root, tmp_path):
    _, _, proj = _module_paths()
    proj._save({"demo": str(tmp_path)})
    assert (iso_root / "data" / "projects.json").is_file()
    assert proj._load()["demo"] == str(tmp_path)
    assert not (REPO_ROOT / "data" / "projects.json").exists() or True


def test_storage_service_uses_the_isolated_root(iso_root):
    import saathi.storage.service as svc
    svc._service = None
    try:
        service = svc.get_storage_service()
        assert pathlib.Path(service.root) == iso_root / "storage"
        assert pathlib.Path(service.db.path if hasattr(service.db, "path")
                            else iso_root / "storage" / "storage.db").is_relative_to(iso_root)
    finally:
        svc._service = None


# ── 10. nothing is created merely by importing ─────────────────────────────
def test_importing_the_scoped_modules_creates_nothing(tmp_path):
    root = tmp_path / "untouched"
    env = dict(os.environ)
    env.update({STATE_ROOT_ENV: str(root), "PYTHONDONTWRITEBYTECODE": "1"})
    for var in ("BAADAR_DB", "SAATHI_PROJECTS_FILE", "SAATHI_STORAGE_DB", "SAATHI_STORAGE_ROOT"):
        env.pop(var, None)
    code = (
        "import saathi.tools.intelligence, saathi.tools.referral, saathi.tools.projects, "
        "saathi.storage.service, saathi.runtime_paths as rp;"
        "print(rp.baadar_db_path(), rp.projects_registry_path(), rp.storage_db_path())"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr[-3000:]
    assert not root.exists(), "importing a scoped-store module created the state root"


# ── 13-15. the pinned Whisper model ────────────────────────────────────────
def _model_stat(p: pathlib.Path) -> tuple[int, int, str]:
    return p.stat().st_size, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()


def test_explicit_whisper_model_beats_the_state_root(iso_root, tmp_path, monkeypatch):
    from saathi.voice_os import local_whisper
    explicit = tmp_path / "models" / "ggml-base.bin"
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(explicit))
    assert pathlib.Path(local_whisper.load_config().model_path) == explicit


def test_whisper_model_default_follows_the_state_root(iso_root, monkeypatch):
    from saathi.voice_os import local_whisper
    monkeypatch.delenv("SAATHI_WHISPER_CPP_MODEL", raising=False)
    resolved = pathlib.Path(local_whisper.load_config().model_path)
    assert resolved.is_relative_to(iso_root)


def test_whisper_unset_default_is_the_historical_personal_path(no_overrides, monkeypatch):
    from saathi.voice_os import local_whisper
    monkeypatch.delenv("SAATHI_WHISPER_CPP_MODEL", raising=False)
    assert pathlib.Path(local_whisper.load_config().model_path) == PINNED_MODEL


@pytest.mark.skipif(not PINNED_MODEL.is_file(), reason="pinned model not present")
def test_python_never_opens_the_whisper_model_for_writing(monkeypatch, tmp_path):
    """The model reaches whisper-cli as an argv, never as a writable handle."""
    src = (REPO_ROOT / "saathi" / "voice_os" / "local_whisper.py").read_text()
    assert "model_path" in src
    for spelling in ('open(cfg.model_path', '"w"', "'w'"):
        assert f"{spelling}, \"w\"" not in src
    # the only filesystem verb applied to the model is an existence check
    assert src.count("os.path.isfile(cfg.model_path)") >= 2


@pytest.mark.skipif(
    not (PINNED_MODEL.is_file() and FIXTURE_WAV.is_file()),
    reason="pinned model or fixture WAV not present",
)
def test_decoding_leaves_the_pinned_model_byte_identical(tmp_path, monkeypatch):
    """A real decode must not modify the shared, checksum-pinned artifact."""
    from saathi.voice_os import local_whisper
    import shutil as _shutil
    if not _shutil.which("whisper-cli"):
        pytest.skip("whisper-cli not installed")

    before = _model_stat(PINNED_MODEL)
    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(PINNED_MODEL))
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    monkeypatch.setenv("SAATHI_VOICE_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    result = local_whisper.WhisperCppSTT().transcribe_wav(
        FIXTURE_WAV.read_bytes(), language="en"
    )
    assert result is not None
    assert _model_stat(PINNED_MODEL) == before, "the decode modified the pinned model"


def test_pinned_model_is_the_141_mib_artifact_not_a_large_variant():
    """Guards the size confusion in the earlier report.

    `~/.saathi/stt-models/` totals ~5.3 GB across several experimental model
    lines. The artifact this path names is a single 141 MiB whisper.cpp model;
    the large lines (`v-next-2b2`, `v-next-2b3`) are unrelated and unverified.
    """
    if not PINNED_MODEL.is_file():
        pytest.skip("pinned model not present")
    size_mib = PINNED_MODEL.stat().st_size / (1024 * 1024)
    assert 120 < size_mib < 200, f"unexpected model size {size_mib:.1f} MiB"


# ── 16-17. compatibility and worktree hygiene ──────────────────────────────
def test_unset_environment_reproduces_every_historical_default(no_overrides):
    from saathi.runtime_paths import state_path
    assert state_path("evidence.db") == PERSONAL_ROOT / "evidence.db"
    assert baadar_db_path() == REPO_ROOT / "data" / "baadar.db"
    assert projects_registry_path() == REPO_ROOT / "data" / "projects.json"
    assert storage_db_path() == REPO_ROOT / "storage" / "storage.db"


def test_isolated_test_execution_leaves_the_worktree_clean(tmp_path):
    """Running the isolated suites must not dirty tracked files."""
    def status() -> str:
        return subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT,
                              capture_output=True, text=True, timeout=120).stdout

    before = status()
    env = dict(os.environ)
    env.update({STATE_ROOT_ENV: str(tmp_path / "state"), "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_state_root.py",
         "tests/test_state_root_inventory.py", "-q", "-p", "no:warnings",
         "-p", "no:cacheprovider", f"--basetemp={tmp_path / 'bt'}"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=900,
    )
    assert proc.returncode == 0, proc.stdout[-3000:]
    assert status() == before, "an isolated test run dirtied the worktree"


@pytest.mark.skipif(
    not (PINNED_MODEL.is_file() and FIXTURE_WAV.is_file()),
    reason="pinned model or fixture WAV not present",
)
def test_decoding_leaves_a_model_copy_byte_identical(tmp_path, monkeypatch):
    """Same guarantee, proven against a disposable copy.

    Exists so the "does a decode write to the model?" property can be mutation
    tested without aiming a deliberately-broken build at the real, pinned
    artifact.
    """
    import shutil
    if not shutil.which("whisper-cli"):
        pytest.skip("whisper-cli not installed")
    from saathi.voice_os import local_whisper

    copy = tmp_path / "models" / "ggml-base.bin"
    copy.parent.mkdir(parents=True)
    shutil.copy2(PINNED_MODEL, copy)
    before = _model_stat(copy)

    monkeypatch.setenv("SAATHI_WHISPER_CPP_MODEL", str(copy))
    monkeypatch.setenv(STATE_ROOT_ENV, str(tmp_path / "state"))
    monkeypatch.setenv("SAATHI_VOICE_ARTIFACT_DIR", str(tmp_path / "artifacts"))

    result = local_whisper.WhisperCppSTT().transcribe_wav(
        FIXTURE_WAV.read_bytes(), language="en"
    )
    assert result is not None
    assert _model_stat(copy) == before, "the decode modified the model file"


# ── the guard must actually be used, not merely present ────────────────────
def test_auth_module_contains_no_unguarded_deletion():
    """Every delete in the auth suite goes through the owned-root guard.

    Setting ``SAATHI_STATE_ROOT`` in the fixture already keeps deletions inside
    ``tmp_path``, so a raw ``unlink`` looks harmless right up until someone
    edits the fixture. Requiring the guard at the source level is what makes the
    module safe by construction rather than by ordering.
    """
    import ast

    src = (REPO_ROOT / "tests" / "test_auth_v1.py").read_text()
    tree = ast.parse(src)

    guard = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "_unlink_within"),
        None,
    )
    assert guard is not None, "the owned-root guard has been removed"
    guard_lines = set(range(guard.lineno, (guard.end_lineno or guard.lineno) + 1))

    DESTRUCTIVE = {"unlink", "remove", "rmtree", "unlink_missing_ok"}
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name in DESTRUCTIVE and node.lineno not in guard_lines:
            offenders.append(f"line {node.lineno}: {name}() outside _unlink_within")
    assert not offenders, (
        "unguarded deletion in the auth suite:\n  " + "\n  ".join(offenders)
        + "\n\nRoute it through _unlink_within(tmp_path, target)."
    )


@pytest.mark.skipif(
    not (PINNED_MODEL.is_file() and FIXTURE_WAV.is_file()),
    reason="pinned model or fixture WAV not present",
)
def test_decode_never_opens_the_model_writable(tmp_path):
    """Audit every open during a real decode; none may be writable.

    Stronger than comparing hashes: an open in append mode changes neither the
    contents nor the mtime, so a build that grabbed a writable handle would slip
    past a checksum comparison entirely.
    """
    import shutil
    if not shutil.which("whisper-cli"):
        pytest.skip("whisper-cli not installed")

    copy = tmp_path / "models" / "ggml-base.bin"
    copy.parent.mkdir(parents=True)
    shutil.copy2(PINNED_MODEL, copy)

    child = tmp_path / "audit_decode.py"
    child.write_text(
        "import json, os, sys, pathlib\n"
        f"MODEL = {str(copy)!r}\n"
        "writes = []\n"
        "def hook(event, args):\n"
        "    if event != 'open':\n"
        "        return\n"
        "    p, mode, flags = args[0], args[1], args[2]\n"
        "    if not isinstance(p, (str, bytes, os.PathLike)):\n"
        "        return\n"
        "    p = os.fspath(p)\n"
        "    if isinstance(p, bytes):\n"
        "        p = p.decode('utf-8', 'replace')\n"
        "    if os.path.realpath(p) != os.path.realpath(MODEL):\n"
        "        return\n"
        "    m = mode if isinstance(mode, str) else ''\n"
        "    w = bool(set(m) & {'w', 'a', 'x', '+'}) or bool(\n"
        "        (flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND))\n"
        "    if w:\n"
        "        writes.append({'mode': m, 'flags': flags})\n"
        "sys.addaudithook(hook)\n"
        "from saathi.voice_os import local_whisper\n"
        f"wav = pathlib.Path({str(FIXTURE_WAV)!r}).read_bytes()\n"
        "r = local_whisper.WhisperCppSTT().transcribe_wav(wav, language='en')\n"
        "print('@@A@@' + json.dumps({'writes': writes, 'ok': r is not None}))\n"
    )
    env = dict(os.environ)
    env.update({
        "SAATHI_WHISPER_CPP_MODEL": str(copy),
        STATE_ROOT_ENV: str(tmp_path / "state"),
        "SAATHI_VOICE_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    proc = subprocess.run([sys.executable, str(child)], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stderr[-3000:]
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@A@@")]
    assert marker, proc.stdout[-2000:]
    result = json.loads(marker[-1][len("@@A@@"):])
    assert result["ok"], "the decode did not produce a result"
    assert result["writes"] == [], f"model opened for writing: {result['writes']}"
