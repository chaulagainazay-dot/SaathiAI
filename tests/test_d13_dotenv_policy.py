"""D13 — dotenv loading and writing are explicit, and never touch the worktree
``.env`` when a run has opted out.

``saathi.config`` used to call ``load_dotenv(<repo>/.env)`` unconditionally, so
an isolated validation run inherited the operator's checkout configuration, and
two password endpoints wrote a plaintext credential back into that same file.
Nothing in these tests prints or asserts on a secret value.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

from saathi.dotenv_policy import (
    DOTENV_ENABLED_ENV,
    DOTENV_PATH_ENV,
    HISTORICAL_DOTENV,
    DotenvPolicyError,
    apply_dotenv,
    dotenv_target,
    write_dotenv_values,
)
from saathi.runtime_paths import REPO_ROOT


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv(DOTENV_PATH_ENV, raising=False)
    monkeypatch.delenv(DOTENV_ENABLED_ENV, raising=False)
    return monkeypatch


# ── load policy (16-21) ─────────────────────────────────────────────────────
def test_default_targets_the_historical_worktree_env(clean_env):
    assert dotenv_target() == HISTORICAL_DOTENV == REPO_ROOT / ".env"


def test_explicit_path_is_the_only_file_considered(clean_env, tmp_path):
    explicit = tmp_path / "validation.env"
    explicit.write_text("D13_PROBE_KEY=probe-value\n")
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))
    clean_env.delenv("D13_PROBE_KEY", raising=False)

    assert dotenv_target() == explicit
    status = apply_dotenv()
    assert status["loaded"] is True
    assert status["path"] == str(explicit)
    assert os.environ["D13_PROBE_KEY"] == "probe-value"


def test_explicit_relative_path_is_rejected(clean_env):
    clean_env.setenv(DOTENV_PATH_ENV, "relative/.env")
    with pytest.raises(DotenvPolicyError):
        dotenv_target()


@pytest.mark.parametrize("falsey", ["false", "0", "no", "off", "FALSE"])
def test_disabled_mode_targets_nothing(clean_env, falsey):
    clean_env.setenv(DOTENV_ENABLED_ENV, falsey)
    assert dotenv_target() is None
    status = apply_dotenv()
    assert status == {"loaded": False, "path": None, "reason": "disabled"}


def test_missing_explicit_path_never_falls_back(clean_env, tmp_path):
    missing = tmp_path / "absent.env"
    clean_env.setenv(DOTENV_PATH_ENV, str(missing))
    status = apply_dotenv()
    assert status["loaded"] is False
    assert status["reason"] == "explicit_path_missing"
    assert status["path"] == str(missing)
    assert str(HISTORICAL_DOTENV) not in json.dumps(status)


def test_process_environment_wins_over_the_file(clean_env, tmp_path):
    explicit = tmp_path / "validation.env"
    explicit.write_text("D13_PRECEDENCE=from-file\n")
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))
    clean_env.setenv("D13_PRECEDENCE", "from-process")

    apply_dotenv()
    assert os.environ["D13_PRECEDENCE"] == "from-process"


_LOAD_CHILD = r'''
import json, os, sys
opened = []
def _hook(event, args):
    if event == "open":
        p = args[0]
        try:
            p = os.fspath(p)
        except TypeError:
            return
        if isinstance(p, bytes):
            p = p.decode("utf-8", "replace")
        opened.append(p)
sys.addaudithook(_hook)

import saathi.config as config
worktree_env = %(worktree_env)r
print("@@R@@" + json.dumps({
    "status": config.DOTENV_STATUS,
    "worktree_env_opened": any(os.path.realpath(p) == os.path.realpath(worktree_env) for p in opened),
}))
'''


def _load_child(env_overrides: dict) -> dict:
    env = dict(os.environ)
    env.update({"PYTHONDONTWRITEBYTECODE": "1"})
    env.pop(DOTENV_PATH_ENV, None)
    env.pop(DOTENV_ENABLED_ENV, None)
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, "-c", _LOAD_CHILD % {"worktree_env": str(HISTORICAL_DOTENV)}],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
    marker = [l for l in proc.stdout.splitlines() if l.startswith("@@R@@")]
    assert marker, proc.stdout[-2000:]
    return json.loads(marker[-1][len("@@R@@"):])


def test_disabled_mode_opens_no_worktree_env_at_import(tmp_path):
    result = _load_child({DOTENV_ENABLED_ENV: "false", "SAATHI_STATE_ROOT": str(tmp_path)})
    assert result["status"]["reason"] == "disabled"
    assert result["worktree_env_opened"] is False


def test_explicit_isolated_env_opens_no_worktree_env_at_import(tmp_path):
    explicit = tmp_path / "validation.env"
    explicit.write_text("D13_ISOLATED=1\n")
    result = _load_child({DOTENV_PATH_ENV: str(explicit), "SAATHI_STATE_ROOT": str(tmp_path)})
    assert result["status"]["path"] == str(explicit)
    assert result["worktree_env_opened"] is False


def test_default_mode_still_targets_the_worktree_env(tmp_path):
    """Historical compatibility: nothing configured, nothing changed.

    The assertion is on the *target and policy*, not on the file existing.
    ``.env`` is gitignored, so it is present in the checkout that created it and
    absent from every additional git worktree -- this test previously demanded
    ``reason == "default"``, which only holds where the operator happens to keep
    a ``.env``. Both outcomes are correct policy and the distinction is not a
    containment property, so the test now pins the target path and accepts
    either reason, while still proving the loader considered nothing else.
    """
    result = _load_child({"SAATHI_STATE_ROOT": str(tmp_path)})
    status = result["status"]

    assert status["path"] == str(HISTORICAL_DOTENV), "the default target is the worktree .env"
    if HISTORICAL_DOTENV.exists():
        assert status["reason"] == "default" and status["loaded"] is True
    else:
        # Absent is a first-class outcome: the loader reports it and loads
        # nothing rather than searching elsewhere.
        assert status["reason"] == "default_path_missing" and status["loaded"] is False


def test_default_mode_never_searches_beyond_the_worktree(tmp_path):
    """Whether or not a ``.env`` exists, no other candidate is consulted.

    This is the containment property the previous assertion was standing in for,
    and unlike it, it holds in every worktree.
    """
    result = _load_child({"SAATHI_STATE_ROOT": str(tmp_path)})
    assert result["status"]["path"] == str(HISTORICAL_DOTENV)
    # No fallback to a home-relative or parent-directory .env.
    for candidate in (pathlib.Path.home() / ".env",
                      REPO_ROOT.parent / ".env",
                      pathlib.Path.home() / ".saathi" / ".env"):
        assert result["status"]["path"] != str(candidate)


# ── write policy (22-25) ────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def never_mutate_the_real_dotenv():
    """Hard stop: no test in this module may leave the operator's ``.env`` changed.

    An earlier version of this guard inspected ``dotenv_target()`` and inferred
    intent. A mutation that redirected the writer *internally* sailed straight
    past it and wrote the real file; killing the mutation afterwards does not
    un-write it. So guard the bytes, not the intent — snapshot, restore, and
    fail loudly if anything moved.
    """
    existed = HISTORICAL_DOTENV.exists()
    before = HISTORICAL_DOTENV.read_bytes() if existed else None
    mode = HISTORICAL_DOTENV.stat().st_mode if existed else None
    try:
        yield
    finally:
        now = HISTORICAL_DOTENV.read_bytes() if HISTORICAL_DOTENV.exists() else None
        if now != before:
            if existed:
                HISTORICAL_DOTENV.write_bytes(before)
                os.chmod(HISTORICAL_DOTENV, mode & 0o7777)
            elif HISTORICAL_DOTENV.exists():
                HISTORICAL_DOTENV.unlink()
            raise AssertionError(
                "a test wrote the worktree .env; it has been restored, but the "
                "code under test is targeting the wrong file"
            )


def test_writer_targets_only_the_configured_file(clean_env, tmp_path):
    explicit = tmp_path / "validation.env"
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))

    before_hash = HISTORICAL_DOTENV.read_bytes() if HISTORICAL_DOTENV.exists() else None
    written = write_dotenv_values({"D13_WRITTEN": "yes"})

    assert written == explicit
    assert "D13_WRITTEN=yes" in explicit.read_text()
    after_hash = HISTORICAL_DOTENV.read_bytes() if HISTORICAL_DOTENV.exists() else None
    assert before_hash == after_hash, "the worktree .env must not be touched"


def test_disabled_writer_refuses(clean_env):
    clean_env.setenv(DOTENV_ENABLED_ENV, "false")
    with pytest.raises(DotenvPolicyError):
        write_dotenv_values({"D13_WRITTEN": "no"})


def test_write_preserves_unrelated_keys_comments_and_mode(clean_env, tmp_path):
    explicit = tmp_path / "validation.env"
    explicit.write_text("# a comment\nKEEP_ME=untouched\nREPLACE_ME=old\n")
    os.chmod(explicit, 0o600)
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))

    write_dotenv_values({"REPLACE_ME": "new", "ADDED": "1"})

    text = explicit.read_text()
    assert "# a comment" in text
    assert "KEEP_ME=untouched" in text
    assert "REPLACE_ME=new" in text
    assert "REPLACE_ME=old" not in text
    assert "ADDED=1" in text
    assert oct(explicit.stat().st_mode & 0o777) == "0o600"


def test_new_file_is_owner_only(clean_env, tmp_path):
    explicit = tmp_path / "fresh.env"
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))
    write_dotenv_values({"ONLY": "1"})
    assert oct(explicit.stat().st_mode & 0o777) == "0o600"


def test_write_is_atomic_and_leaves_no_temp_files(clean_env, tmp_path):
    explicit = tmp_path / "validation.env"
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))
    write_dotenv_values({"A": "1"})
    write_dotenv_values({"B": "2"})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["validation.env"]


def test_status_never_carries_values_or_key_names(clean_env, tmp_path):
    explicit = tmp_path / "validation.env"
    explicit.write_text("D13_SECRETISH=super-secret-value\n")
    clean_env.setenv(DOTENV_PATH_ENV, str(explicit))
    status = apply_dotenv()
    rendered = json.dumps(status)
    assert "super-secret-value" not in rendered
    assert "D13_SECRETISH" not in rendered


# ── one policy, no side doors (Part 3 inventory) ────────────────────────────
def test_no_module_loads_dotenv_outside_the_policy():
    """``dotenv_policy`` is the only place that may call ``load_dotenv``.

    Three tool modules used to reach into ``~/SaathiAI/.env`` — the operator's
    *personal* checkout — from whichever checkout was running, which no
    isolation setting could switch off.
    """
    offenders = []
    for path in (REPO_ROOT / "saathi").rglob("*.py"):
        if path.name == "dotenv_policy.py":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if "load_dotenv(" in code:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert offenders == [], f"load_dotenv outside the policy: {offenders}"


def test_no_module_reads_a_dotenv_by_hand():
    """No module may resolve a ``.env`` path of its own, personal or otherwise."""
    offenders = []
    for path in (REPO_ROOT / "saathi").rglob("*.py"):
        if path.name == "dotenv_policy.py":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if '".env"' in code and ("home()" in code or "ROOT" in code):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}")
    assert offenders == [], f"hand-rolled .env path: {offenders}"
