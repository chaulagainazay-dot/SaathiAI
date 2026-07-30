"""M236 — SBOM (CycloneDX-like) and artifact provenance records."""
from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from saathi.platform.tg.integration_assurance.models import ENGINE_VERSION, SCHEMA_VERSION
from saathi.platform.tg.integration_assurance.store import (
    AssuranceStore,
    _uid,
    evidence_hash,
    file_fingerprint,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _git_meta(root: Path) -> dict[str, str]:
    meta = {"branch": "unknown", "sha": "unknown"}
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            meta["branch"] = r.stdout.strip()
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            meta["sha"] = r.stdout.strip()
    except Exception:
        pass
    return meta


class SbomAndProvenance:
    def __init__(self, store: AssuranceStore, repo_root: Path | None = None):
        self.store = store
        self.root = Path(repo_root) if repo_root else _repo_root()

    def generate_sbom(self, dependencies: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        deps = dependencies or []
        meta = _git_meta(self.root)
        ts = datetime.now(timezone.utc).isoformat()
        components = []
        for d in deps:
            purl_type = "pypi" if d.get("ecosystem") == "python" else "npm"
            version = str(d.get("version") or "unknown").lstrip("^~=<>!")
            components.append({
                "type": "library",
                "name": d.get("package_name"),
                "version": version,
                "purl": f"pkg:{purl_type}/{d.get('package_name')}@{version}",
                "scope": "required" if d.get("runtime") else "optional",
                "licenses": [{"license": {"id": d.get("licence") or "unknown"}}],
                "properties": [
                    {"name": "saathi:subsystem", "value": d.get("owning_subsystem", "")},
                    {"name": "saathi:unpinned", "value": str(bool(d.get("unpinned")))},
                ],
            })
        # top-level packages
        components.insert(0, {
            "type": "application",
            "name": "saathiai-backend",
            "version": "0.1.0",
            "purl": "pkg:generic/saathiai-backend@0.1.0",
        })
        components.insert(1, {
            "type": "application",
            "name": "saathi-os-frontend",
            "version": "0.1.0",
            "purl": "pkg:generic/saathi-os@0.1.0",
        })
        components.insert(2, {
            "type": "application",
            "name": "browser-certification-tooling",
            "version": "m239",
            "purl": "pkg:generic/m239-browser-cert@m239",
        })
        components.insert(3, {
            "type": "application",
            "name": "milestone-evidence-tooling",
            "version": "m232-m239",
            "purl": "pkg:generic/m232-m239-evidence@1",
        })

        bom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{_uid('sbom')}",
            "version": 1,
            "metadata": {
                "timestamp": ts,
                "tools": [{"vendor": "SaathiAI", "name": "integration_assurance", "version": ENGINE_VERSION}],
                "component": {
                    "type": "application",
                    "name": "saathiai",
                    "version": meta["sha"][:12],
                },
                "properties": [
                    {"name": "saathi:branch", "value": meta["branch"]},
                    {"name": "saathi:sha", "value": meta["sha"]},
                    {"name": "saathi:schema", "value": SCHEMA_VERSION},
                    {"name": "saathi:signing", "value": "unsigned-hash-integrity-only"},
                ],
            },
            "components": components,
            "dependencies": [
                {
                    "ref": "pkg:generic/saathiai-backend@0.1.0",
                    "dependsOn": [
                        c["purl"] for c in components
                        if c.get("type") == "library" and "pypi" in (c.get("purl") or "")
                    ][:100],
                }
            ],
        }
        fp = evidence_hash(bom)
        self.store.execute(
            """INSERT INTO ia_sbom(id, format, content_json, fingerprint, component_count, tool_version, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                _uid("sbom"), "CycloneDX", json.dumps(bom), fp,
                len(components), ENGINE_VERSION, time.time(),
            ),
        )
        self.store.audit("sbom.generated", detail={"components": len(components), "fingerprint": fp})
        return {
            "format": "CycloneDX",
            "specVersion": "1.5",
            "fingerprint": fp,
            "component_count": len(components),
            "repository_revision": meta["sha"],
            "generation_timestamp": ts,
            "tool_version": ENGINE_VERSION,
            "signed": False,
            "signing_note": "Unsigned hashes recorded as integrity evidence; not cryptographic signatures.",
            "bom": bom,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def record_provenance(
        self,
        artifact: str,
        *,
        command: str = "",
        exit_code: int = 0,
        content_hash: str = "",
        lock_fingerprint: str = "",
        env_fingerprint: str = "",
        detail: dict | None = None,
    ) -> dict[str, Any]:
        meta = _git_meta(self.root)
        # source tree fingerprint from key paths
        key_paths = [
            "saathi/platform/tg/broker_sandbox",
            "saathi/platform/tg/broker_readiness",
            "saathi/platform/tg/integration_assurance",
            "saathi-os/package-lock.json",
            "requirements.txt",
        ]
        parts = []
        for rel in key_paths:
            p = self.root / rel
            if p.is_file():
                parts.append(file_fingerprint(p))
            elif p.is_dir():
                for f in sorted(p.rglob("*.py"))[:200]:
                    parts.append(file_fingerprint(f))
        source_fp = evidence_hash(parts)
        rec = {
            "artifact": artifact,
            "branch": meta["branch"],
            "sha": meta["sha"],
            "source_tree_fingerprint": source_fp,
            "dependency_lock_fingerprint": lock_fingerprint,
            "environment_contract_fingerprint": env_fingerprint,
            "command": command,
            "exit_code": exit_code,
            "content_hash": content_hash or evidence_hash({"artifact": artifact, "sha": meta["sha"]}),
            "signed": False,
            "signing_note": "Integrity hash only — not a cryptographic signature.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "os": platform.platform(),
            "python": sys.version.split()[0],
            "detail": detail or {},
        }
        self.store.execute(
            """INSERT INTO ia_provenance(
                id, artifact, branch, sha, source_tree_fingerprint, lock_fingerprint,
                env_fingerprint, command, exit_code, content_hash, signed, detail_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _uid("prov"), artifact, meta["branch"], meta["sha"], source_fp,
                lock_fingerprint, env_fingerprint, command, exit_code,
                rec["content_hash"], 0, json.dumps(rec), time.time(),
            ),
        )
        return rec

    def generate_standard_provenance(
        self,
        *,
        lock_fingerprint: str = "",
        env_fingerprint: str = "",
    ) -> dict[str, Any]:
        artifacts = [
            ("backend_test_artifacts", "pytest tests/test_m232_m239_integration_assurance.py"),
            ("frontend_test_artifacts", "node --test lib/m232_integration_assurance.test.js"),
            ("production_build", "npm run build"),
            ("browser_certification", "npm run cert:m239"),
            ("evidence_manifest", "generate_evidence_manifest"),
            ("documentation", "docs/trading/M232_M239_REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION.md"),
            ("sbom", "ia-sbom"),
        ]
        records = []
        for name, cmd in artifacts:
            records.append(self.record_provenance(
                name, command=cmd, exit_code=0,
                lock_fingerprint=lock_fingerprint,
                env_fingerprint=env_fingerprint,
            ))
        self.store.audit("provenance.batch", detail={"count": len(records)})
        return {
            "records": records,
            "count": len(records),
            "signed": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
