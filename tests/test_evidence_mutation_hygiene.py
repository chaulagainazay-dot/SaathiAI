"""Ordinary operation must not modify committed evidence.

`docs/evidence/**` is the certification record. Several runtime components used
to append their live logs into it, so importing a module or running the test
suite permanently changed checked-in files. A working tree that dirties itself
teaches everyone to ignore `git status` on exactly the paths where a real change
matters most, and it makes "was this evidence produced by a certification run or
by a stray import?" unanswerable.

These tests pin the split enforced by `saathi.runtime_paths`:

  * runtime logs go to the runtime state directory, which is git-ignored;
  * the committed evidence tree is not written to by ordinary operation;
  * historical evidence still exists and is still readable.

The last point matters as much as the first two. The fix is a redirect, not a
deletion.
"""
from __future__ import annotations

import hashlib
import pathlib
import subprocess

import pytest

from saathi import runtime_paths

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMITTED_EVIDENCE = REPO_ROOT / "docs" / "evidence"


def _digest_tree(root: pathlib.Path) -> dict[str, str]:
    """Content digest of every file under `root`, keyed by relative path."""
    if not root.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class TestRuntimeStateLocation:
    def test_default_runtime_dir_is_inside_the_checkout(self, monkeypatch):
        monkeypatch.delenv(runtime_paths.RUNTIME_STATE_ENV, raising=False)
        assert runtime_paths.runtime_state_dir() == REPO_ROOT / ".runtime"

    def test_env_override_relocates_runtime_state(self, monkeypatch, tmp_path):
        monkeypatch.setenv(runtime_paths.RUNTIME_STATE_ENV, str(tmp_path / "state"))
        assert runtime_paths.runtime_state_dir() == tmp_path / "state"

    def test_runtime_evidence_dir_is_never_the_committed_tree(self, monkeypatch):
        monkeypatch.delenv(runtime_paths.RUNTIME_STATE_ENV, raising=False)
        for milestone in ("m25", "m27", "m28"):
            runtime = runtime_paths.runtime_evidence_dir(milestone)
            committed = runtime_paths.committed_evidence_dir(milestone)
            assert runtime != committed
            assert COMMITTED_EVIDENCE not in runtime.parents

    def test_runtime_dir_is_git_ignored(self):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", ".runtime/anything"],
            check=False,
        )
        assert result.returncode == 0, ".runtime/ must be git-ignored"


class TestGovernedRuntimeWritesOutsideCommittedEvidence:
    def test_connector_event_log_is_runtime_state(self):
        from saathi.connectors.gov import runtime as gov_runtime

        assert COMMITTED_EVIDENCE not in gov_runtime.EVIDENCE_DIR.parents
        assert COMMITTED_EVIDENCE not in gov_runtime.M28_EVIDENCE_DIR.parents

    def test_committed_evidence_is_still_reachable_for_reading(self):
        from saathi.connectors.gov import runtime as gov_runtime

        assert gov_runtime.COMMITTED_EVIDENCE_DIR == COMMITTED_EVIDENCE / "m27"
        assert gov_runtime.COMMITTED_M28_EVIDENCE_DIR == COMMITTED_EVIDENCE / "m28"

    def test_deprecation_event_does_not_touch_committed_evidence(self, monkeypatch, tmp_path):
        monkeypatch.setenv(runtime_paths.RUNTIME_STATE_ENV, str(tmp_path / "state"))
        from saathi.connectors.gov import gateway_bridge

        before = _digest_tree(COMMITTED_EVIDENCE / "m28")
        gateway_bridge.emit_deprecation(
            legacy_path="legacy.call",
            canonical_path="canonical.call",
            caller_id="hygiene-test",
            detail="evidence mutation regression guard",
        )
        assert _digest_tree(COMMITTED_EVIDENCE / "m28") == before

        written = tmp_path / "state" / "evidence" / "m28" / "deprecation_events.jsonl"
        assert written.is_file(), "the event must still be recorded, just elsewhere"
        assert "hygiene-test" in written.read_text(encoding="utf-8")


class TestHistoricalEvidenceIsPreserved:
    """The redirect must not have deleted the record it stopped appending to."""

    @pytest.mark.parametrize(
        "relative",
        [
            "m27/connector_events.jsonl",
            "m28/deprecation_events.jsonl",
            "m28/connector_migration_ledger.json",
            "m25/LAST_SUCCESSFUL_LIVE_CERTIFICATION.json",
        ],
    )
    def test_snapshot_still_present(self, relative):
        assert (COMMITTED_EVIDENCE / relative).is_file()


class TestRuntimeDatabaseIsNotVersioned:
    """storage/storage.db is a live SQLite database, recreated on demand."""

    def test_not_tracked_by_git(self):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "ls-files", "--error-unmatch", "storage/storage.db"],
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, (
            "storage/storage.db is tracked again; every run that touches storage "
            "would dirty the working tree"
        )

    def test_is_git_ignored(self):
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", "storage/storage.db"],
            check=False,
        )
        assert result.returncode == 0


class TestSuiteDoesNotDirtyCommittedEvidence:
    """End-to-end: the paths that used to be appended to stay byte-identical
    across a governed-connector exercise."""

    def test_governed_runtime_exercise_leaves_evidence_unchanged(self, monkeypatch, tmp_path):
        monkeypatch.setenv(runtime_paths.RUNTIME_STATE_ENV, str(tmp_path / "state"))
        before = _digest_tree(COMMITTED_EVIDENCE)

        from saathi.connectors.gov import gateway_bridge

        for index in range(5):
            gateway_bridge.emit_deprecation(
                legacy_path=f"legacy.{index}",
                canonical_path=f"canonical.{index}",
                caller_id="hygiene-loop",
                detail="repeated runtime activity",
            )

        assert _digest_tree(COMMITTED_EVIDENCE) == before
