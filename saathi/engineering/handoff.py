"""M20.0 — Durable handoff manager (canonical .saathi-agent-state files)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from saathi.repair.secrets_scan import scan_text, redact

HANDOFF_DIR_NAME = ".saathi-agent-state"
HANDOFF_MD = "HANDOFF.md"
SESSION_JSON = "SESSION_STATE.json"


@dataclass
class HandoffPayload:
    repository: str
    branch: str
    head: str
    remote_state: str
    active_milestone: str
    completed_work: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    tests: str = ""
    failures: list[str] = field(default_factory=list)
    ci_state: str = "unknown"
    blockers: list[str] = field(default_factory=list)
    rollback: str = ""
    disable_controls: dict[str, str] = field(default_factory=dict)
    remaining_risks: list[str] = field(default_factory=list)
    exact_next_action: str = ""
    agent_session_active: bool = False
    user_approval_required: bool = False
    verdict: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def sanitize(self) -> "HandoffPayload":
        """Drop secrets from free-text fields."""
        def clean(s: str) -> str:
            if not s:
                return s
            try:
                return redact(s)
            except Exception:
                return s

        self.tests = clean(self.tests)
        self.exact_next_action = clean(self.exact_next_action)
        self.rollback = clean(self.rollback)
        self.failures = [clean(f) for f in self.failures]
        self.completed_work = [clean(c) for c in self.completed_work]
        # refuse if secrets remain
        blob = json.dumps(self.to_dict(), default=str)
        if not scan_text(blob).clean:
            self.failures.append("handoff_secret_redacted")
            self.tests = "[redacted]"
        return self


class HandoffManager:
    def __init__(self, repository_root: str | Path):
        self.root = Path(repository_root)
        self.dir = self.root / HANDOFF_DIR_NAME
        self.dir.mkdir(parents=True, exist_ok=True)

    def write(self, payload: HandoffPayload) -> dict[str, str]:
        payload = payload.sanitize()
        md_path = self.dir / HANDOFF_MD
        json_path = self.dir / SESSION_JSON

        md = f"""# SaathiOS Agent Handoff — {payload.active_milestone}

- Generated: {time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(payload.timestamp))}
- Branch: `{payload.branch}`
- HEAD: `{payload.head}`
- Remote: {payload.remote_state}
- Repository: {payload.repository}
- Verdict: `{payload.verdict}`

## Completed work

{chr(10).join(f"- {c}" for c in payload.completed_work) or "- (none)"}

## Changed files

{chr(10).join(f"- `{f}`" for f in payload.changed_files[:80]) or "- (none)"}

## Commits

{chr(10).join(f"- {c}" for c in payload.commits) or "- (none)"}

## Tests

{payload.tests or "(not run)"}

## Failures / blockers

{chr(10).join(f"- {b}" for b in (payload.failures + payload.blockers)) or "- none"}

## CI

{payload.ci_state}

## Rollback

```
{payload.rollback or "git revert <sha>"}
```

## Disable controls

{chr(10).join(f"- {k}: `{v}`" for k, v in payload.disable_controls.items()) or "- defaults already disabled"}

## Remaining risks

{chr(10).join(f"- {r}" for r in payload.remaining_risks) or "- none noted"}

## Session

- agent_session_active: {payload.agent_session_active}
- user_approval_required: {payload.user_approval_required}

## Exact next action

{payload.exact_next_action or "(none)"}
"""
        if not scan_text(md).clean:
            md = "# Handoff redacted due to secret scan hits\n"
        md_path.write_text(md, encoding="utf-8")

        session = {
            "schema_version": "1",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(payload.timestamp)),
            "branch": payload.branch,
            "head": payload.head,
            "remote_sync": payload.remote_state,
            "active_objective": payload.active_milestone,
            "completed_steps": payload.completed_work,
            "current_validation_status": payload.tests,
            "blockers": payload.blockers,
            "next_exact_action": payload.exact_next_action,
            "rollback": payload.rollback,
            "verdict": payload.verdict,
            "agent_session_active": payload.agent_session_active,
            "user_approval_required": payload.user_approval_required,
            "merge_deploy": False,
            "failures": payload.failures,
            "ci_state": payload.ci_state,
            "changed_files": payload.changed_files[:80],
            "commits": payload.commits,
        }
        json_path.write_text(json.dumps(session, indent=2, default=str), encoding="utf-8")
        return {"handoff_md": str(md_path), "session_json": str(json_path)}
