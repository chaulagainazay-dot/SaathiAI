"""M232 — Clean-clone dependency / required-source audit."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.models import REQUIRED_SOURCE_TREES
from saathi.platform.tg.integration_assurance.store import AssuranceStore, _uid


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _git(*args: str, cwd: Path | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd or _repo_root()),
            capture_output=True,
            text=True,
            timeout=60,
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


class SourceAuditor:
    """Forensic audit of committed vs required source for M216–M239."""

    def __init__(self, store: AssuranceStore, repo_root: Path | None = None):
        self.store = store
        self.root = Path(repo_root) if repo_root else _repo_root()

    def _is_tracked(self, rel: str) -> bool:
        code, out = _git("ls-files", "--error-unmatch", rel, cwd=self.root)
        return code == 0 and bool(out.strip())

    def _list_tracked(self, prefix: str) -> list[str]:
        code, out = _git("ls-files", prefix, cwd=self.root)
        if code != 0:
            return []
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    def _list_untracked(self, prefix: str) -> list[str]:
        code, out = _git("status", "--short", "--", prefix, cwd=self.root)
        if code != 0:
            return []
        results = []
        for ln in out.splitlines():
            ln = ln.rstrip()
            if not ln:
                continue
            status = ln[:2]
            path = ln[3:].strip()
            if status.strip() == "??" or status.startswith("?"):
                results.append(path)
        return results

    def classify_path(self, rel: str, *, required: bool) -> dict[str, Any]:
        full = self.root / rel
        exists = full.exists()
        tracked = self._is_tracked(rel) if exists or True else False
        # For directories, check if any tracked children exist
        if full.is_dir() or rel.endswith("/"):
            tracked_children = self._list_tracked(rel.rstrip("/"))
            untracked = self._list_untracked(rel.rstrip("/"))
            has_tracked = len(tracked_children) > 0
            has_untracked_src = any(
                u.endswith(".py") or u.endswith(".js") or u.endswith(".jsx")
                for u in untracked
            )
            # Directory exists with .py children but git has not tracked them yet
            has_local_src = exists and any(full.rglob("*.py"))
            if required and has_tracked and not has_untracked_src:
                classification = "COMMITTED_AND_REQUIRED"
            elif required and not has_tracked and (has_untracked_src or has_local_src):
                classification = "UNCOMMITTED_AND_REQUIRED"
            elif required and not has_tracked and not exists:
                classification = "UNRESOLVED_DEPENDENCY"
            elif not required and has_tracked:
                classification = "COMMITTED_NOT_REQUIRED"
            elif (has_untracked_src or has_local_src) and not required:
                classification = "UNCOMMITTED_NOT_REQUIRED"
            else:
                classification = "COMMITTED_AND_REQUIRED" if has_tracked else "UNRESOLVED_DEPENDENCY"
            return {
                "path": rel,
                "classification": classification,
                "committed": has_tracked,
                "required": required,
                "tracked_count": len(tracked_children),
                "untracked_source_count": sum(1 for u in untracked if u.endswith((".py", ".js", ".jsx"))),
                "untracked": untracked[:50],
            }

        # file
        if not exists and required:
            return {
                "path": rel, "classification": "UNRESOLVED_DEPENDENCY",
                "committed": False, "required": required,
            }
        if tracked and required:
            classification = "COMMITTED_AND_REQUIRED"
        elif tracked and not required:
            classification = "COMMITTED_NOT_REQUIRED"
        elif not tracked and required and exists:
            classification = "UNCOMMITTED_AND_REQUIRED"
        elif not tracked and not required and exists:
            classification = "UNCOMMITTED_NOT_REQUIRED"
        else:
            classification = "UNRESOLVED_DEPENDENCY"
        return {
            "path": rel,
            "classification": classification,
            "committed": tracked,
            "required": required,
        }

    def audit_m216_baseline(self) -> dict[str, Any]:
        """Specifically resolve the reported uncommitted broker_sandbox baseline question."""
        sandbox = self.classify_path("saathi/platform/tg/broker_sandbox", required=True)
        readiness = self.classify_path("saathi/platform/tg/broker_readiness", required=True)
        # Import dependency check: readiness imports sandbox?
        readiness_imports_sandbox = False
        sandbox_dir = self.root / "saathi/platform/tg/broker_sandbox"
        readiness_dir = self.root / "saathi/platform/tg/broker_readiness"
        if readiness_dir.is_dir():
            for py in readiness_dir.glob("*.py"):
                try:
                    text = py.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if "broker_sandbox" in text:
                    readiness_imports_sandbox = True
                    break
        uncommitted_required = [
            x for x in (sandbox, readiness)
            if x["classification"] == "UNCOMMITTED_AND_REQUIRED"
        ]
        finding = {
            "question": "Does M224–M231 depend on uncommitted M216 broker_sandbox files?",
            "broker_sandbox": sandbox,
            "broker_readiness": readiness,
            "readiness_imports_sandbox": readiness_imports_sandbox,
            "uncommitted_required_files": uncommitted_required,
            "resolution": (
                "ALL_REQUIRED_SOURCE_COMMITTED"
                if not uncommitted_required and sandbox["committed"] and readiness["committed"]
                else "REQUIRED_SOURCE_UNCOMMITTED"
            ),
            "m216_uncommitted_dependency": bool(uncommitted_required),
        }
        return finding

    def run(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for tree in REQUIRED_SOURCE_TREES:
            items.append(self.classify_path(tree, required=True))

        # also classify common non-required local artifacts
        for artifact, required in (
            ("data/platform/broker_readiness.db", False),
            ("data/platform/broker_sandbox.db", False),
            ("saathi-os/node_modules", False),
            (".venv", False),
            (".env", False),
        ):
            p = self.root / artifact
            if p.exists() or artifact.endswith(".db"):
                if p.is_dir() and artifact in ("saathi-os/node_modules", ".venv"):
                    items.append({
                        "path": artifact,
                        "classification": "STALE_LOCAL_ARTIFACT" if p.exists() else "COMMITTED_NOT_REQUIRED",
                        "committed": False,
                        "required": False,
                        "note": "Must not be required for clean clone; install from lockfiles",
                    })
                elif artifact == ".env":
                    items.append({
                        "path": artifact,
                        "classification": "STALE_LOCAL_ARTIFACT" if p.exists() else "COMMITTED_NOT_REQUIRED",
                        "committed": False,
                        "required": False,
                        "note": "Forbidden secret source; must not be required",
                    })
                else:
                    items.append({
                        "path": artifact,
                        "classification": "GENERATED_REPRODUCIBLY" if "data/platform" in artifact else "STALE_LOCAL_ARTIFACT",
                        "committed": False,
                        "required": False,
                    })

        m216 = self.audit_m216_baseline()
        now = time.time()
        for it in items:
            self.store.execute(
                """INSERT INTO ia_source_audit(id, path, classification, committed, required, detail_json, created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    _uid("src"), it["path"], it["classification"],
                    1 if it.get("committed") else 0,
                    1 if it.get("required") else 0,
                    json.dumps(it), now,
                ),
            )
        self.store.audit("source_audit.complete", detail={"count": len(items), "m216": m216["resolution"]})

        # Baseline M216–M231 trees must never be uncommitted for certification.
        baseline_prefixes = (
            "saathi/platform/tg/broker_sandbox",
            "saathi/platform/tg/broker_readiness",
            "tests/test_m224_m231_broker_readiness.py",
            "tests/test_m216_m223_broker_sandbox.py",
        )
        uncommitted_required = [
            i for i in items if i["classification"] == "UNCOMMITTED_AND_REQUIRED"
        ]
        unresolved = [i for i in items if i["classification"] == "UNRESOLVED_DEPENDENCY" and i.get("required")]
        baseline_uncommitted = [
            i for i in uncommitted_required
            if any(i["path"].startswith(p) or i["path"] == p for p in baseline_prefixes)
        ]
        baseline_unresolved = [
            i for i in unresolved
            if any(i["path"].startswith(p) or i["path"] == p for p in baseline_prefixes)
        ]
        # New milestone package must be present (committed or local source); full ok after commit.
        ia_items = [i for i in items if i["path"].startswith("saathi/platform/tg/integration_assurance")]
        ia_dir_exists = (self.root / "saathi/platform/tg/integration_assurance").is_dir()
        ia_ok = bool(ia_items) and ia_dir_exists and all(
            i["classification"] in (
                "COMMITTED_AND_REQUIRED",
                "UNCOMMITTED_AND_REQUIRED",  # allowed only pre-commit of this milestone
            )
            for i in ia_items
        )
        ia_committed = all(bool(i.get("committed")) for i in ia_items) if ia_items else False

        baseline_ok = (
            not baseline_uncommitted
            and not baseline_unresolved
            and not m216["m216_uncommitted_dependency"]
            and m216["resolution"] == "ALL_REQUIRED_SOURCE_COMMITTED"
        )
        # Certification-grade ok requires everything committed including IA package.
        ok = baseline_ok and ia_committed and not unresolved
        verdict = (
            "ALL_REQUIRED_SOURCE_COMMITTED" if ok
            else ("BASELINE_COMMITTED_MILESTONE_PACKAGE_PENDING" if baseline_ok and ia_ok and not ia_committed
                  else "REQUIRED_SOURCE_UNCOMMITTED")
        )
        return {
            "ok": ok,
            "baseline_ok": baseline_ok,
            "milestone_package_committed": ia_committed,
            "items": items,
            "m216_baseline": m216,
            "uncommitted_required_count": len(uncommitted_required),
            "unresolved_required_count": len(unresolved),
            "verdict": verdict,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
