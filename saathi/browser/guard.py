"""M17.24 — Browser dispatch architectural guardrails.

Enforces a single governed entry boundary for production browser work and
detects residual ungoverned low-level driver access via static repository scan.

Canonical production entry: ``saathi.browser.governed.GovernedBrowser.execute``
→ ExecutionGateway → BrowserAdapter → tier drivers.

Low-level driver modules (Playwright tiers, CDP, human Chrome backend, agent-
browser CLI subprocess) may only be imported/used from an explicit allowlist.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# ── Typed governance errors ──────────────────────────────────────────────────


class BrowserGovernanceError(RuntimeError):
    """Fail-closed browser governance violation (typed for API/tool handlers)."""

    def __init__(self, code: str, message: str, *, details: Optional[dict] = None):
        self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict:
        return {
            "error": "browser_governance",
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


# ── Allowlists (relative paths under repo / package) ─────────────────────────

# Modules allowed to import or invoke low-level browser drivers / subprocess
# browser launches. Everything else in saathi/ is blocked by the static guard.
LOW_LEVEL_DRIVER_ALLOWLIST: frozenset[str] = frozenset({
    # Canonical tier adapters (technical only; callers must be governed)
    "saathi/browser/playwright_tier.py",
    "saathi/browser/http_tier.py",
    "saathi/browser/camofox_tier.py",
    "saathi/browser/service.py",
    "saathi/browser/governed.py",
    "saathi/browser/guard.py",
    "saathi/browser/policy.py",
    "saathi/browser/base.py",
    "saathi/browser/types.py",
    "saathi/browser/session.py",
    "saathi/browser/__init__.py",
    # Live CDP driver — only ComputerAdapter may hold a live session
    "saathi/computer_agent/browser_driver.py",
    "saathi/computer_agent/operations.py",
    "saathi/computer_agent/live_workflow.py",
    "saathi/computer_agent/live_report.py",
    "saathi/computer_agent/permissions.py",
    "saathi/computer_agent/providers.py",
    "saathi/computer_agent/__init__.py",
    "saathi/computer_agent/cli.py",
    # Human browser Mac agent stack (isolated queue; not generic autonomy)
    "saathi/infrastructure/human_browser/chrome_backend.py",
    "saathi/infrastructure/human_browser/driver.py",
    "saathi/infrastructure/human_browser/agent.py",
    "saathi/infrastructure/human_browser/primitives.py",
    "saathi/infrastructure/human_browser/browser_tier.py",
    "saathi/infrastructure/human_browser/proxy.py",
    "saathi/infrastructure/human_browser/queue.py",
    "saathi/infrastructure/human_browser/jobs.py",
    "saathi/infrastructure/human_browser/keyed.py",
    "saathi/infrastructure/human_browser/automation.py",
    "saathi/infrastructure/human_browser/run_store.py",
    "saathi/infrastructure/human_browser/run_agent.py",
    "saathi/infrastructure/human_browser/daily.py",
    "saathi/infrastructure/human_browser/publish.py",
    "saathi/infrastructure/human_browser/teach.py",
    "saathi/infrastructure/human_browser/teach_mode.py",
    "saathi/infrastructure/human_browser/teach_ai.py",
    "saathi/infrastructure/human_browser/profiles.py",
    "saathi/infrastructure/human_browser/selector_registry.py",
    "saathi/infrastructure/human_browser/vision_verifier.py",
    "saathi/infrastructure/human_browser/__init__.py",
    # Fail-closed wrappers (must not call raw drivers in production)
    "saathi/tools/agent_browser.py",
    "saathi/tools/browser.py",
    "saathi/tools/chatgpt_browser.py",
    # Connector technical surface (must route through governance)
    "saathi/infrastructure/connectors/drivers/browser.py",
    "saathi/infrastructure/connectors/drivers/human_publish.py",
    "saathi/infrastructure/browser.py",
    # Read-only diagnostics / status (no dispatch)
    "saathi/infrastructure/diagnostics.py",
    "saathi/infrastructure/connectors/diagnostics.py",
    "saathi/control_center/aggregator.py",
    "saathi/security/redteam/probes.py",
    "saathi/platform_maturity.py",
    "saathi/ceo_os.py",
    "saathi/ceo/service.py",
})

# Import module names / symbols that indicate low-level browser driver access
FORBIDDEN_IMPORT_MODULES: frozenset[str] = frozenset({
    "playwright",
    "playwright.sync_api",
    "playwright.async_api",
    "selenium",
    "selenium.webdriver",
    "puppeteer",
})

FORBIDDEN_FROM_IMPORTS: frozenset[tuple[str, str]] = frozenset({
    ("playwright.sync_api", "sync_playwright"),
    ("playwright.async_api", "async_playwright"),
    ("saathi.computer_agent.browser_driver", "LiveBrowserDriver"),
    ("saathi.browser.playwright_tier", "PlaywrightTier"),
    ("saathi.infrastructure.human_browser.chrome_backend", "ChromeBackend"),
})

# Subprocess / shell browser *launch* patterns (not mere product-name mentions)
SUBPROCESS_BROWSER_LAUNCH_RE = re.compile(
    r"(?i)("
    r"agent-browser"
    r"|playwright\s+install"
    r"|chromium\.launch"
    r"|launch_persistent_context"
    r"|google-chrome"
    r"|chromium-browser"
    r"|open\s+-a\s+[\"']?(Google Chrome|Chromium|Brave Browser|Microsoft Edge)"
    r"|/Applications/Google Chrome\.app"
    r"|/Applications/Chromium\.app"
    r")"
)

# Paths scanned for production violations (relative to repo root)
SCAN_ROOTS: tuple[str, ...] = ("saathi",)
SCAN_SKIP_DIR_NAMES: frozenset[str] = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv",
})

# Env override for local emergency debugging ONLY (never production default)
RAW_BROWSER_ENV = "SAATHI_ALLOW_RAW_BROWSER"


def raw_browser_env_enabled() -> bool:
    return os.environ.get(RAW_BROWSER_ENV, "").strip() in ("1", "true", "TRUE", "yes")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def rel_path(path: Path, root: Path | None = None) -> str:
    root = root or repo_root()
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def is_allowlisted(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel in LOW_LEVEL_DRIVER_ALLOWLIST:
        return True
    # Human browser page/workflow packages (technical only)
    if rel.startswith("saathi/infrastructure/human_browser/pages/"):
        return True
    if rel.startswith("saathi/infrastructure/human_browser/workflows/"):
        return True
    return False


@dataclass
class GuardFinding:
    path: str
    kind: str
    detail: str
    line: int = 0

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "detail": self.detail,
            "line": self.line,
        }


@dataclass
class GuardReport:
    findings: list[GuardFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "finding_count": len(self.findings),
            "findings": [f.as_dict() for f in self.findings],
        }


def _module_name_from_import(node: ast.AST) -> list[tuple[str, int, str]]:
    """Return list of (module_or_symbol, lineno, kind)."""
    out: list[tuple[str, int, str]] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            out.append((alias.name, node.lineno, "import"))
    elif isinstance(node, ast.ImportFrom):
        mod = node.module or ""
        out.append((mod, node.lineno, "import_from"))
        for alias in node.names:
            out.append((f"{mod}.{alias.name}" if mod else alias.name,
                        node.lineno, "import_name"))
    return out


def _string_literals(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, getattr(node, "lineno", 0)


def scan_file(path: Path, *, root: Path | None = None) -> list[GuardFinding]:
    """Scan one Python file for unauthorized low-level browser driver usage."""
    root = root or repo_root()
    rel = rel_path(path, root)
    if is_allowlisted(rel):
        return []
    # scripts/ and tests/ are not production product code
    if rel.startswith("tests/") or rel.startswith("scripts/") or rel.startswith("docs/"):
        return []
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return []
    findings: list[GuardFinding] = []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        findings.append(GuardFinding(rel, "syntax_error", str(e), e.lineno or 0))
        return findings

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name, lineno, kind in _module_name_from_import(node):
                base = name.split(".")[0]
                if base in FORBIDDEN_IMPORT_MODULES or name in FORBIDDEN_IMPORT_MODULES:
                    findings.append(GuardFinding(
                        rel, "forbidden_import",
                        f"{kind} {name}", lineno,
                    ))
                # from X import Y pairs
                if isinstance(node, ast.ImportFrom) and node.module:
                    for alias in node.names:
                        if (node.module, alias.name) in FORBIDDEN_FROM_IMPORTS:
                            findings.append(GuardFinding(
                                rel, "forbidden_from_import",
                                f"from {node.module} import {alias.name}",
                                lineno,
                            ))
        # Dynamic import: __import__("playwright") / importlib.import_module("playwright")
        if isinstance(node, ast.Call):
            func = node.func
            fname = ""
            if isinstance(func, ast.Name):
                fname = func.id
            elif isinstance(func, ast.Attribute):
                fname = func.attr
            if fname in ("__import__", "import_module") and node.args:
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    mod = arg0.value
                    base = mod.split(".")[0]
                    if base in FORBIDDEN_IMPORT_MODULES or mod in FORBIDDEN_IMPORT_MODULES:
                        findings.append(GuardFinding(
                            rel, "dynamic_import",
                            f"{fname}({mod!r})", getattr(node, "lineno", 0),
                        ))

    # Subprocess browser *launch* patterns outside allowlist (product code)
    uses_process = bool(re.search(r"\b(subprocess|Popen|os\.system|osascript)\b", src))
    if uses_process:
        for lit, lineno in _string_literals(tree):
            m = SUBPROCESS_BROWSER_LAUNCH_RE.search(lit)
            if m:
                findings.append(GuardFinding(
                    rel, "subprocess_browser_marker",
                    f"launch pattern {m.group(0)!r}", lineno,
                ))
                break
        # Also scan full source for launch patterns not only in constants
        if not any(f.kind == "subprocess_browser_marker" for f in findings):
            m2 = SUBPROCESS_BROWSER_LAUNCH_RE.search(src)
            if m2 and "agent-browser" in m2.group(0).lower():
                findings.append(GuardFinding(
                    rel, "subprocess_browser_marker",
                    f"launch pattern {m2.group(0)!r}", 0,
                ))

    # Direct re-exports of LiveBrowserDriver from non-allowlisted modules
    if re.search(r"LiveBrowserDriver", src) and "browser_driver" in src:
        if not is_allowlisted(rel):
            findings.append(GuardFinding(
                rel, "live_driver_reference",
                "references LiveBrowserDriver outside allowlist", 0,
            ))

    return findings


def scan_repository(root: Path | None = None) -> GuardReport:
    """Scan production package roots for ungoverned browser driver access."""
    root = root or repo_root()
    report = GuardReport()
    for sub in SCAN_ROOTS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(p in SCAN_SKIP_DIR_NAMES for p in path.parts):
                continue
            report.findings.extend(scan_file(path, root=root))
    return report


def assert_no_ungoverned_driver_imports(root: Path | None = None) -> GuardReport:
    report = scan_repository(root=root)
    if not report.ok:
        summary = "; ".join(
            f"{f.path}:{f.line} {f.kind}" for f in report.findings[:12]
        )
        raise BrowserGovernanceError(
            "UNGOVERNED_DRIVER_IMPORT",
            f"found {len(report.findings)} ungoverned browser driver path(s): {summary}",
            details=report.as_dict(),
        )
    return report


def require_governed_context(
    *,
    actor_id: str = "",
    mission_id: str = "",
    mission_run_id: str = "",
    require_mission: bool = False,
    mission_state: str = "",
    cancelled: bool = False,
    approval_id: str = "",
    approval_valid: bool | None = None,
    approval_expired: bool = False,
    trading_classified: bool = False,
    trading_authorized: bool = False,
    retry_attempt: int = 0,
    retry_authorized: bool = True,
    checkpoint_reference: str = "",
    resume: bool = False,
    schedule_enabled: bool = True,
    trigger_trusted: bool = True,
) -> None:
    """Fail-closed preconditions for a governed browser dispatch.

    Raises BrowserGovernanceError when context is incomplete or invalid.
    """
    if cancelled or (mission_state or "").lower() in ("cancelled", "canceled", "killed"):
        raise BrowserGovernanceError(
            "MISSION_CANCELLED",
            "cancelled or killed mission cannot dispatch browser actions",
        )
    if (mission_state or "").lower() in ("paused", "blocked"):
        raise BrowserGovernanceError(
            "MISSION_BLOCKED",
            f"mission state {mission_state!r} cannot dispatch browser actions",
        )
    actor = (actor_id or "").strip()
    if not actor or actor in ("unknown", "anonymous", "none", "null"):
        raise BrowserGovernanceError(
            "MISSING_ACTOR",
            "browser dispatch requires attributable actor_id",
        )
    if require_mission and not (mission_id or "").strip():
        raise BrowserGovernanceError(
            "MISSING_MISSION",
            "browser dispatch requires mission_id for this request source",
        )
    if require_mission and not (mission_run_id or "").strip():
        raise BrowserGovernanceError(
            "MISSING_RUN",
            "browser dispatch requires mission_run_id / governed run identifier",
        )
    if approval_expired:
        raise BrowserGovernanceError(
            "APPROVAL_EXPIRED",
            "approval reference is expired",
            details={"approval_id": approval_id},
        )
    if approval_valid is False:
        raise BrowserGovernanceError(
            "APPROVAL_INVALID",
            "approval reference is invalid or unbound",
            details={"approval_id": approval_id},
        )
    if trading_classified and not trading_authorized:
        raise BrowserGovernanceError(
            "TRADING_GUARDIAN_REQUIRED",
            "trading-classified browser action requires Trading Guardian authorization; "
            "generic browser approval is insufficient",
        )
    if retry_attempt > 0 and not retry_authorized:
        raise BrowserGovernanceError(
            "RETRY_UNAUTHORIZED",
            "retry attempt lacks retry authorization",
            details={"retry_attempt": retry_attempt},
        )
    if resume and not (checkpoint_reference or "").strip():
        raise BrowserGovernanceError(
            "CHECKPOINT_REQUIRED",
            "resume requires a valid checkpoint_reference",
        )
    if not schedule_enabled:
        raise BrowserGovernanceError(
            "SCHEDULE_DISABLED",
            "disabled schedule cannot dispatch browser actions",
        )
    if not trigger_trusted:
        raise BrowserGovernanceError(
            "TRIGGER_UNTRUSTED",
            "event-trigger dispatch requires a trusted trigger record",
        )


def deny_raw_production_dispatch(*, source: str, action: str = "") -> dict:
    """Standard fail-closed payload for legacy raw browser entry points."""
    return {
        "error": "browser_governance",
        "code": "RAW_BROWSER_DISABLED",
        "message": (
            f"Raw browser path {source!r} is disabled. "
            "Use saathi.browser.governed.GovernedBrowser → ExecutionGateway."
        ),
        "action": action,
        "raw_env_override": RAW_BROWSER_ENV,
    }
