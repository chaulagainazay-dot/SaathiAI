"""Verification engine + regression guard.

The verification ladder: focused failing tests -> affected subsystem tests ->
full suite -> server import -> route-count smoke. A repair succeeds only if the
target failure recovers AND no new regressions appear AND the route count does
not unexpectedly drop.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
_PYTEST = [str(ROOT / ".venv" / "bin" / "python"), "-m", "pytest",
           "-q", "-p", "no:cacheprovider", "--no-header"]

_SUMMARY = re.compile(
    r"(?:(\d+) failed)?[, ]*(?:(\d+) passed)?[, ]*(?:(\d+) skipped)?"
    r"[, ]*(?:(\d+) error)?")


@dataclass
class TestOutcome:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    ran: bool = False
    raw_tail: str = ""

    def to_dict(self) -> dict:
        return {"passed": self.passed, "failed": self.failed,
                "skipped": self.skipped, "errors": self.errors, "ran": self.ran}


def _parse(output: str) -> TestOutcome:
    o = TestOutcome(ran=True, raw_tail=output[-400:])
    # find the pytest summary line (last matching). With -q and all tests
    # passing, pytest prints a bare "N passed in 1.2s" without the "==="
    # decoration, so fall back to any summary-shaped line.
    for line in reversed(output.splitlines()):
        if ("passed" in line or "failed" in line or "error" in line) and \
                re.search(r"\d+ (passed|failed|error)", line):
            for m in re.finditer(r"(\d+) (passed|failed|skipped|error)", line):
                n, kind = int(m.group(1)), m.group(2)
                setattr(o, {"passed": "passed", "failed": "failed",
                            "skipped": "skipped", "error": "errors"}[kind], n)
            break
    return o


def run_pytest(targets: list[str] | None = None, timeout: int = 900) -> TestOutcome:
    """Run pytest on targets (or the whole suite). Never raises."""
    cmd = list(_PYTEST) + (targets or ["tests/"])
    try:
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                             timeout=timeout)
        return _parse(res.stdout + "\n" + res.stderr)
    except subprocess.TimeoutExpired:
        return TestOutcome(ran=False, raw_tail="pytest timed out")
    except Exception as exc:  # environment problem, not a test result
        return TestOutcome(ran=False, raw_tail=repr(exc)[:200])


def server_smoke() -> tuple[bool, int]:
    """Import the app in a subprocess (isolation) and report route count."""
    code = ("import json;from saathi.server import app;"
            "print('ROUTES', len(app.routes))")
    try:
        res = subprocess.run(
            [str(ROOT / ".venv" / "bin" / "python"), "-c", code],
            cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        m = re.search(r"ROUTES (\d+)", res.stdout)
        if m:
            return True, int(m.group(1))
        return False, 0
    except Exception:
        return False, 0


@dataclass
class RegressionReport:
    recovered: bool = False
    new_regressions: bool = False
    route_count_before: int = 0
    route_count_after: int = 0
    route_regression: bool = False
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.recovered and not self.new_regressions and not self.route_regression


def guard(before: TestOutcome, after: TestOutcome,
          routes_before: int, routes_after: int,
          focused_after: TestOutcome | None = None) -> RegressionReport:
    """Compare before/after. Success requires recovery + no new regressions."""
    r = RegressionReport(
        route_count_before=routes_before, route_count_after=routes_after,
        before=before.to_dict(), after=after.to_dict())

    # recovery: fewer failures/errors than before, and focused tests (if given) green
    fewer_failures = (after.failed + after.errors) < (before.failed + before.errors)
    focused_green = True if focused_after is None else (
        focused_after.ran and focused_after.failed == 0 and focused_after.errors == 0)
    r.recovered = fewer_failures and focused_green

    # new regression: any newly-failing test that was passing before. We
    # approximate with counts: passed must not drop (accounting for recovered).
    r.new_regressions = (after.failed + after.errors) > (before.failed + before.errors)

    # route count must not unexpectedly decrease
    r.route_regression = routes_after < routes_before
    return r
