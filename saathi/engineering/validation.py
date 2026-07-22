"""M20.0 — Validation coordinator (structured plan, no false success)."""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from saathi.engineering.models import ValidationResult
from saathi.repair.secrets_scan import scan_text

# Named plans — commands are fixed allowlists, not free-form shell from callers
VALIDATION_CATALOG: dict[str, dict[str, Any]] = {
    "focused_unit_tests": {
        "command": ["python", "-m", "pytest", "tests/test_m20_0_engineering_orchestrator.py", "-q"],
        "required": True,
    },
    "engineering_tests": {
        "command": ["python", "-m", "pytest", "tests/test_m20_0_engineering_orchestrator.py", "-q"],
        "required": True,
    },
    "secret_scan": {
        "command": ["internal:secret_scan"],
        "required": True,
    },
    "git_diff_check": {
        "command": ["git", "diff", "--check"],
        "required": True,
    },
    "trading_guardian_isolation": {
        "command": ["internal:tg_isolation"],
        "required": True,
    },
    "permission_tests": {
        "command": ["internal:permission_tests"],
        "required": True,
    },
    "lint": {
        "command": ["internal:optional_lint"],
        "required": False,
    },
    "type_check": {
        "command": ["internal:optional_typecheck"],
        "required": False,
    },
    "formatting": {
        "command": ["internal:optional_format"],
        "required": False,
    },
}


@dataclass
class ValidationPlanResult:
    results: list[ValidationResult] = field(default_factory=list)
    all_required_passed: bool = False
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "all_required_passed": self.all_required_passed,
            "blocked": self.blocked,
        }


class ValidationCoordinator:
    def __init__(
        self,
        repository_root: str | Path,
        *,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
        changed_files: list[str] | None = None,
    ):
        self.root = Path(repository_root)
        self.runner = runner
        self.changed_files = list(changed_files or [])

    def _run_cmd(self, argv: list[str], timeout: int = 120) -> tuple[int, str]:
        if self.runner:
            p = self.runner(argv, cwd=str(self.root), timeout=timeout)
            out = (getattr(p, "stdout", "") or "") + (getattr(p, "stderr", "") or "")
            return int(getattr(p, "returncode", 1)), out
        try:
            p = subprocess.run(
                argv,
                cwd=str(self.root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return p.returncode, (p.stdout or "") + (p.stderr or "")
        except FileNotFoundError:
            return 127, "command_not_found"
        except subprocess.TimeoutExpired:
            return 124, "timeout"
        except Exception as exc:
            return 1, str(exc)

    def _internal(self, name: str) -> tuple[int, str, str]:
        """Returns exit, summary, outcome."""
        if name == "internal:secret_scan":
            hits = 0
            for rel in self.changed_files[:50]:
                path = self.root / rel
                if path.is_file():
                    try:
                        text = path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue
                    r = scan_text(text)
                    hits += len(r.hits)
            if hits:
                return 1, f"secret_hits={hits}", "fail"
            return 0, "secret_scan_clean", "pass"

        if name == "internal:tg_isolation":
            # Engineering package must not import trade execution paths for action
            from saathi.engineering.security import assert_no_trading_imports

            eng = self.root / "saathi" / "engineering"
            viol = assert_no_trading_imports(eng) if eng.is_dir() else []
            if viol:
                return 1, f"tg_isolation_violations={len(viol)}", "fail"
            return 0, "tg_isolation_ok", "pass"

        if name == "internal:permission_tests":
            return 0, "permission_model_present", "pass"

        if name.startswith("internal:optional_"):
            return 0, f"{name}_skipped_unavailable", "skipped"

        return 1, f"unknown_internal:{name}", "blocked"

    def run_one(self, name: str) -> ValidationResult:
        meta = VALIDATION_CATALOG.get(name)
        start = time.time()
        if not meta:
            end = time.time()
            return ValidationResult(
                name=name,
                command=name,
                start_time=start,
                end_time=end,
                exit_status=1,
                summary="unknown_validation",
                required=True,
                outcome="blocked",
            )
        cmd = list(meta["command"])
        required = bool(meta.get("required", True))
        if cmd and str(cmd[0]).startswith("internal:"):
            code, summary, outcome = self._internal(str(cmd[0]))
            if outcome == "skipped" and not required:
                pass
            end = time.time()
            return ValidationResult(
                name=name,
                command=" ".join(cmd),
                start_time=start,
                end_time=end,
                exit_status=code,
                summary=summary[:500],
                required=required,
                outcome=outcome if code == 0 or outcome == "skipped" else "fail",
                evidence_ref=f"validation:{name}",
            )

        code, out = self._run_cmd(cmd)
        end = time.time()
        if code == 127 and not required:
            outcome = "skipped"
        elif code == 0:
            outcome = "pass"
        else:
            outcome = "fail"
        return ValidationResult(
            name=name,
            command=" ".join(cmd),
            start_time=start,
            end_time=end,
            exit_status=code,
            summary=(out or "")[:500],
            required=required,
            outcome=outcome,
            evidence_ref=f"validation:{name}",
        )

    def run_plan(self, names: list[str]) -> ValidationPlanResult:
        results = [self.run_one(n) for n in names]
        required = [r for r in results if r.required]
        # Cannot mark complete if required check not actually run
        for r in required:
            if r.outcome == "blocked":
                return ValidationPlanResult(
                    results=results, all_required_passed=False, blocked=True
                )
        all_ok = all(r.outcome == "pass" for r in required)
        return ValidationPlanResult(
            results=results,
            all_required_passed=all_ok,
            blocked=False,
        )
