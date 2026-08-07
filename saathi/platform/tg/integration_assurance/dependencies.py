"""M235 — Dependency lock inventory and supply-chain inventory."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.models import ALLOWED_PACKAGE_REGISTRIES
from saathi.platform.tg.integration_assurance.store import (
    AssuranceStore,
    _uid,
    evidence_hash,
    file_fingerprint,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


_REQ_LINE = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)\s*([><=!~]=?|==)?\s*([^;#\s]+)?",
)
_PKG_JSON_DEP = re.compile(r'"([^"]+)":\s*"([^"]+)"')


class DependencyInventory:
    def __init__(self, store: AssuranceStore, repo_root: Path | None = None):
        self.store = store
        self.root = Path(repo_root) if repo_root else _repo_root()

    def _parse_requirements(self, path: Path, *, runtime: bool, ecosystem: str = "python") -> list[dict[str, Any]]:
        items = []
        if not path.is_file():
            return items
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            m = _REQ_LINE.match(line)
            if not m:
                continue
            name, op, ver = m.group(1), m.group(2) or "", m.group(3) or ""
            unpinned = op != "==" or not ver or ver in ("*", "latest") or (op and op != "==")
            if not op and not ver:
                unpinned = True
            items.append({
                "package_name": name,
                "version": ver if op == "==" else f"{op}{ver}" if op else ver or "*",
                "source_registry": "pypi.org",
                "direct": True,
                "runtime": runtime,
                "ecosystem": ecosystem,
                "lockfile_present": True,
                "integrity_hash": "",
                "licence": "unknown",
                "purpose": "runtime" if runtime else "development",
                "owning_subsystem": "backend",
                "unpinned": unpinned,
                "deprecated": False,
                "risk_rank": 3 if unpinned else 1,
                "update_policy": "manual-review",
                "security_relevance": "high" if unpinned else "medium",
                "replacement_difficulty": "medium",
            })
        return items

    def _parse_pyproject(self) -> list[dict[str, Any]]:
        path = self.root / "pyproject.toml"
        items = []
        if not path.is_file():
            return items
        text = path.read_text(encoding="utf-8", errors="replace")
        in_deps = False
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("dependencies") and "=" in s and "[" in s:
                in_deps = True
                continue
            if in_deps:
                if s.startswith("]"):
                    in_deps = False
                    continue
                m = re.search(r'"([A-Za-z0-9_.\-]+)([><=!~]=?[^"]*)?"', s)
                if m:
                    name = m.group(1)
                    ver = (m.group(2) or "").lstrip("=<>!~")
                    op_unpinned = "==" not in (m.group(2) or "")
                    items.append({
                        "package_name": name,
                        "version": m.group(2) or "*",
                        "source_registry": "pypi.org",
                        "direct": True,
                        "runtime": True,
                        "ecosystem": "python",
                        "lockfile_present": False,
                        "integrity_hash": "",
                        "licence": "unknown",
                        "purpose": "runtime",
                        "owning_subsystem": "backend",
                        "unpinned": op_unpinned,
                        "deprecated": False,
                        "risk_rank": 3 if op_unpinned else 1,
                        "update_policy": "manual-review",
                        "security_relevance": "high" if op_unpinned else "medium",
                        "replacement_difficulty": "medium",
                    })
        return items

    def _parse_package_json(self) -> list[dict[str, Any]]:
        path = self.root / "saathi-os" / "package.json"
        items = []
        if not path.is_file():
            return items
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return items
        for section, runtime in (("dependencies", True), ("devDependencies", False)):
            deps = data.get(section) or {}
            for name, ver in deps.items():
                ver_s = str(ver)
                unpinned = (
                    ver_s.startswith("^") or ver_s.startswith("~")
                    or ver_s == "latest" or ver_s.startswith("git")
                    or ver_s.startswith("http") or "*" in ver_s
                )
                floating_git = ver_s.startswith("git") or "github:" in ver_s
                items.append({
                    "package_name": name,
                    "version": ver_s,
                    "source_registry": "registry.npmjs.org",
                    "direct": True,
                    "runtime": runtime,
                    "ecosystem": "node",
                    "lockfile_present": (self.root / "saathi-os" / "package-lock.json").is_file(),
                    "integrity_hash": "",
                    "licence": "unknown",
                    "purpose": "runtime" if runtime else "development",
                    "owning_subsystem": "frontend",
                    "unpinned": unpinned,
                    "deprecated": False,
                    "risk_rank": 5 if floating_git else (3 if unpinned else 1),
                    "floating_git": floating_git,
                    "update_policy": "manual-review",
                    "security_relevance": "high" if unpinned else "medium",
                    "replacement_difficulty": "medium",
                })
        return items

    def _scan_install_scripts(self) -> list[dict[str, Any]]:
        findings = []
        # package.json scripts that curl | sh
        for rel in ("saathi-os/package.json", "package.json"):
            p = self.root / rel
            if not p.is_file():
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if "curl" in text and ("| sh" in text or "| bash" in text):
                findings.append({"path": rel, "kind": "curl_to_shell", "risk": "high"})
            if re.search(r'postinstall|preinstall|install\s*":', text):
                findings.append({"path": rel, "kind": "lifecycle_script_present", "risk": "medium"})
        # GH actions floating tags
        gh = self.root / ".github" / "workflows"
        if gh.is_dir():
            for yml in list(gh.glob("*.yml")) + list(gh.glob("*.yaml")):
                text = yml.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r"uses:\s*([^\s@]+)@([^\s]+)", text):
                    action, ref = m.group(1), m.group(2)
                    if ref in ("main", "master", "latest") or (not re.match(r"v?\d+", ref) and len(ref) < 40):
                        if not re.match(r"^[0-9a-f]{40}$", ref):
                            findings.append({
                                "path": str(yml.relative_to(self.root)),
                                "kind": "floating_github_action",
                                "action": action,
                                "ref": ref,
                                "risk": "high",
                            })
        return findings

    def lockfile_checks(self) -> dict[str, Any]:
        results = []
        for rel in (
            "saathi-os/package-lock.json",
            "requirements.txt",
            "pyproject.toml",
        ):
            p = self.root / rel
            present = p.is_file()
            fp = file_fingerprint(p) if present else ""
            floating = []
            if present and rel.endswith("package-lock.json"):
                # package-lock pins versions; treat as consistent if file parses
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                    consistent = True
                except Exception:
                    consistent = False
            else:
                consistent = present
            if present and rel == "requirements.txt":
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip().startswith("#") or not line.strip():
                        continue
                    if "==" not in line and not line.strip().startswith("-"):
                        floating.append(line.strip())
            rec = {
                "path": rel,
                "present": present,
                "fingerprint": fp,
                "consistent": consistent,
                "floating_refs": floating,
            }
            results.append(rec)
            self.store.execute(
                """INSERT INTO ia_lockfile_checks(id, path, present, fingerprint, consistent, floating_refs_json, detail_json, created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    _uid("lf"), rel, 1 if present else 0, fp,
                    1 if consistent else 0, json.dumps(floating), json.dumps(rec), time.time(),
                ),
            )
        all_present = all(r["present"] for r in results)
        return {
            "ok": all_present,
            "checks": results,
            "lock_fingerprint": evidence_hash([r["fingerprint"] for r in results]),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def inventory(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        items.extend(self._parse_requirements(self.root / "requirements.txt", runtime=True))
        items.extend(self._parse_pyproject())
        items.extend(self._parse_package_json())

        # Playwright noted as browser dep
        items.append({
            "package_name": "playwright",
            "version": "devDependency-or-global",
            "source_registry": "registry.npmjs.org",
            "direct": True,
            "runtime": False,
            "ecosystem": "node",
            "lockfile_present": True,
            "integrity_hash": "",
            "licence": "Apache-2.0",
            "purpose": "browser certification",
            "owning_subsystem": "browser-cert",
            "unpinned": False,
            "deprecated": False,
            "risk_rank": 2,
            "update_policy": "manual-review",
            "security_relevance": "high",
            "replacement_difficulty": "high",
        })

        now = time.time()
        for it in items:
            self.store.execute(
                """INSERT INTO ia_dependencies(
                    id, package_name, version, source_registry, direct, runtime, ecosystem,
                    lockfile_present, integrity_hash, licence, purpose, owning_subsystem,
                    unpinned, deprecated, risk_rank, detail_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uid("dep"), it["package_name"], it.get("version", ""),
                    it.get("source_registry", ""), 1 if it.get("direct") else 0,
                    1 if it.get("runtime") else 0, it.get("ecosystem", ""),
                    1 if it.get("lockfile_present") else 0, it.get("integrity_hash", ""),
                    it.get("licence", ""), it.get("purpose", ""),
                    it.get("owning_subsystem", ""), 1 if it.get("unpinned") else 0,
                    1 if it.get("deprecated") else 0, int(it.get("risk_rank", 0)),
                    json.dumps(it), now,
                ),
            )

        unpinned = [i for i in items if i.get("unpinned")]
        floating_git = [i for i in items if i.get("floating_git")]
        install_scripts = self._scan_install_scripts()
        locks = self.lockfile_checks()

        # registry allow-list check
        bad_registry = [
            i for i in items
            if i.get("source_registry") and i["source_registry"] not in ALLOWED_PACKAGE_REGISTRIES
            and i["source_registry"] not in ("local", "")
        ]

        licences = {}
        for i in items:
            licences.setdefault(i.get("licence") or "unknown", []).append(i["package_name"])

        risk_ranked = sorted(items, key=lambda x: -int(x.get("risk_rank", 0)))[:50]
        self.store.audit("dependencies.inventory", detail={"count": len(items), "unpinned": len(unpinned)})

        return {
            "ok": locks["ok"] and not floating_git and not bad_registry,
            "dependencies": items,
            "count": len(items),
            "unpinned": unpinned,
            "unpinned_count": len(unpinned),
            "floating_git": floating_git,
            "install_scripts": install_scripts,
            "lockfiles": locks,
            "bad_registry": bad_registry,
            "licence_inventory": {k: len(v) for k, v in licences.items()},
            "risk_ranked": risk_ranked,
            "allowed_registries": sorted(ALLOWED_PACKAGE_REGISTRIES),
            "integrity_report": {
                "npm_lock_integrity_hashes": "present_in_package-lock when installed",
                "pip_hash_pinning": "not enforced (limitation)",
                "cryptographic_signatures": False,
            },
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
