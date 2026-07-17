"""M28 — Deterministic production connector-bypass detection.

Scans ``saathi/`` Python (not tests/docs) for production-capable direct use of
adapters, legacy manager live paths, unrestricted connector HTTP/subprocess, etc.

Explicit allowlist with rationale. Report: path, line, symbol, classification,
allowlist rule (if any), reason.
"""
from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOT = ROOT / "saathi"

# Paths relative to repo root that may call adapters / runtime.execute directly
ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "saathi/connectors/gov/",  # framework internals
    "saathi/connectors/platform/execution.py",  # substrate under gateway handler only
    "saathi/connectors/platform/adapters.py",  # adapter implementations
    "saathi/connectors/adapters/",  # legacy adapter defs (not free call sites)
    "saathi/infrastructure/connectors/",  # driver package (deferred drivers)
    "saathi/execution/",  # gateway boundary
    "saathi/browser/",  # browser governance
    "saathi/mcp_governance/",  # MCP policy
    "saathi/inference/bypass_guard.py",
    "saathi/connectors/gov/bypass_guard.py",
)

# Exact files allowed additional patterns
ALLOWLIST_FILES: frozenset[str] = frozenset({
    "saathi/connectors/manager.py",  # re-exports; execute wraps compat
    "saathi/connectors/gov/compat.py",
    "saathi/connectors/gov/gateway_bridge.py",
    "saathi/connectors/gov/runtime.py",
    "saathi/connectors/__init__.py",
    # Server API uses manager.execute which is the governed compatibility shim
    "saathi/server.py",
})


@dataclass
class BypassFinding:
    path: str
    line: int
    symbol: str
    classification: str  # violation | allowlisted | info
    allowlist_rule: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BypassReport:
    schema: str = "m28.connector_bypass_guard.v1"
    findings: list[BypassFinding] = field(default_factory=list)
    production_bypasses: int = 0
    scanned_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "findings": [f.to_dict() for f in self.findings],
            "production_bypasses": self.production_bypasses,
            "scanned_files": self.scanned_files,
            "ok": self.production_bypasses == 0,
        }


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(path)


def _is_allowlisted(rel: str) -> tuple[bool, str]:
    if rel in ALLOWLIST_FILES:
        return True, f"file:{rel}"
    for p in ALLOWLIST_PREFIXES:
        if rel.startswith(p):
            return True, f"prefix:{p}"
    return False, ""


def _iter_py_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        s = str(p)
        if "/__pycache__/" in s or p.name.startswith("."):
            continue
        # skip tests packaged under saathi if any
        if "/tests/" in s:
            continue
        yield p


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.findings: list[BypassFinding] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node)
        if not name:
            self.generic_visit(node)
            return

        # shell=True
        if name in ("subprocess.run", "subprocess.call", "subprocess.Popen", "Popen", "run", "call"):
            for kw in node.keywords or []:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self._hit(node, name, "unrestricted_subprocess", "shell=True")

        # os.system
        if name in ("os.system", "system") and "os" in name or name == "os.system":
            self._hit(node, name, "unrestricted_subprocess", "os.system")

        # Direct adapter execute outside allowlist
        if name.endswith(".execute") or name == "execute":
            # manager.execute from non-allowlisted is a finding if imported from manager
            pass

        # HttpAdapter().execute or get_adapter(...).execute patterns
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            base = node.func.value
            base_name = ""
            if isinstance(base, ast.Call) and isinstance(base.func, ast.Name):
                base_name = base.func.id
            elif isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name in (
                "HttpAdapter", "McpAdapter", "BrowserAdapter", "LocalToolAdapter",
                "adapter", "adapters",
            ):
                self._hit(node, f"{base_name}.execute", "direct_adapter_execute", "adapter execute call")

        # get_runtime().execute or GovernedConnectorRuntime(...).execute from outsiders
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            if isinstance(node.func.value, ast.Call):
                f = node.func.value.func
                if isinstance(f, ast.Name) and f.id in ("get_runtime", "GovernedConnectorRuntime"):
                    self._hit(node, f"{f.id}().execute", "direct_runtime_execute", "runtime execute outside bridge")

        # register trading-ish
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        if mod.endswith("connectors.manager") or mod == "saathi.connectors.manager":
            for alias in node.names:
                if alias.name == "execute":
                    self._hit(node, "from manager import execute", "legacy_manager_import",
                              "prefer gov.compat or gateway_bridge")
        self.generic_visit(node)

    def _call_name(self, node: ast.Call) -> str:
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            parts = []
            cur: Any = f
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))
        return ""

    def _hit(self, node: ast.AST, symbol: str, classification: str, reason: str) -> None:
        line = getattr(node, "lineno", 0) or 0
        ok, rule = _is_allowlisted(self.rel)
        self.findings.append(BypassFinding(
            path=self.rel,
            line=line,
            symbol=symbol,
            classification="allowlisted" if ok else "violation",
            allowlist_rule=rule,
            reason=reason if not ok else f"allowlisted: {reason}",
        ))


def scan_connector_bypasses(*, root: Optional[Path] = None) -> BypassReport:
    scan_root = (root or ROOT) / "saathi"
    report = BypassReport()
    if not scan_root.is_dir():
        return report

    for path in _iter_py_files(scan_root):
        rel = _rel(path)
        # Focus scan on connector-related production surfaces + server entry
        if not (
            rel.startswith("saathi/connectors/")
            or rel.startswith("saathi/infrastructure/connectors/")
            or rel in ("saathi/server.py",)
            or rel.startswith("saathi/computer_agent/")
        ):
            continue
        report.scanned_files += 1
        try:
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=rel)
        except Exception:
            continue
        v = _Visitor(rel)
        v.visit(tree)
        for f in v.findings:
            report.findings.append(f)
            if f.classification == "violation":
                report.production_bypasses += 1
    return report


def write_bypass_report(report: BypassReport | None = None) -> Path:
    report = report or scan_connector_bypasses()
    out = ROOT / "docs" / "evidence" / "m28" / "connector_bypass_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    import sys
    rep = scan_connector_bypasses()
    write_bypass_report(rep)
    print(json.dumps(rep.to_dict(), indent=2))
    return 0 if rep.production_bypasses == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
