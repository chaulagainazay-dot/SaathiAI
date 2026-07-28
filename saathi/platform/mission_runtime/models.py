"""Fail-closed contracts for the Autonomous Mission Runtime."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
import hashlib
import json


class NodeType(str, Enum):
    GOAL = "GOAL"
    PHASE = "PHASE"
    MILESTONE = "MILESTONE"
    TASK = "TASK"
    SUBTASK = "SUBTASK"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class MissionRuntimeState(str, Enum):
    DRAFT = "DRAFT"
    PLANNED = "PLANNED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    CERTIFIED = "CERTIFIED"


class AgentType(str, Enum):
    PLANNER = "PlannerAgent"
    ARCHITECT = "ArchitectAgent"
    IMPLEMENTER = "ImplementerAgent"
    REVIEWER = "ReviewerAgent"
    TEST = "TestAgent"
    BROWSER = "BrowserAgent"
    DOCUMENTATION = "DocumentationAgent"
    CERTIFICATION = "CertificationAgent"


class EvidenceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    INFO = "INFO"


TASK_TERMINAL = frozenset(
    {
        TaskStatus.FAILED,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.SKIPPED,
    }
)

MISSION_TERMINAL = frozenset(
    {
        MissionRuntimeState.FAILED,
        MissionRuntimeState.COMPLETED,
        MissionRuntimeState.CANCELLED,
        MissionRuntimeState.CERTIFIED,
    }
)

TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED,
        }
    ),
    TaskStatus.READY: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.WAITING,
            TaskStatus.BLOCKED,
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED,
        }
    ),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.COMPLETED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.BLOCKED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED,
        }
    ),
    TaskStatus.BLOCKED: frozenset(
        {
            TaskStatus.READY,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.SKIPPED,
        }
    ),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
    TaskStatus.SKIPPED: frozenset(),
}

MISSION_TRANSITIONS: dict[MissionRuntimeState, frozenset[MissionRuntimeState]] = {
    MissionRuntimeState.DRAFT: frozenset(
        {MissionRuntimeState.PLANNED, MissionRuntimeState.CANCELLED}
    ),
    MissionRuntimeState.PLANNED: frozenset(
        {
            MissionRuntimeState.QUEUED,
            MissionRuntimeState.PAUSED,
            MissionRuntimeState.CANCELLED,
        }
    ),
    MissionRuntimeState.QUEUED: frozenset(
        {
            MissionRuntimeState.RUNNING,
            MissionRuntimeState.PAUSED,
            MissionRuntimeState.BLOCKED,
            MissionRuntimeState.CANCELLED,
        }
    ),
    MissionRuntimeState.RUNNING: frozenset(
        {
            MissionRuntimeState.WAITING,
            MissionRuntimeState.BLOCKED,
            MissionRuntimeState.PAUSED,
            MissionRuntimeState.FAILED,
            MissionRuntimeState.COMPLETED,
            MissionRuntimeState.CANCELLED,
        }
    ),
    MissionRuntimeState.WAITING: frozenset(
        {
            MissionRuntimeState.RUNNING,
            MissionRuntimeState.BLOCKED,
            MissionRuntimeState.PAUSED,
            MissionRuntimeState.FAILED,
            MissionRuntimeState.CANCELLED,
        }
    ),
    MissionRuntimeState.BLOCKED: frozenset(
        {
            MissionRuntimeState.RUNNING,
            MissionRuntimeState.PAUSED,
            MissionRuntimeState.FAILED,
            MissionRuntimeState.CANCELLED,
        }
    ),
    MissionRuntimeState.PAUSED: frozenset(
        {
            MissionRuntimeState.QUEUED,
            MissionRuntimeState.RUNNING,
            MissionRuntimeState.BLOCKED,
            MissionRuntimeState.CANCELLED,
        }
    ),
    MissionRuntimeState.FAILED: frozenset(),
    MissionRuntimeState.COMPLETED: frozenset({MissionRuntimeState.CERTIFIED}),
    MissionRuntimeState.CANCELLED: frozenset(),
    MissionRuntimeState.CERTIFIED: frozenset(),
}


@dataclass(frozen=True)
class ResourceBudget:
    """Bounded mission-wide resource ceilings.

    Zero means "tracked but no caller-specified ceiling" only for effort and
    token estimates. Loop/cycle ceilings are always positive.
    """

    estimated_effort: float = 0.0
    max_elapsed_seconds: float = 3600.0
    max_token_estimate: int = 250_000
    max_commits: int = 20
    max_tests: int = 50
    max_browser_runs: int = 10
    max_cycles: int = 200
    max_no_progress_cycles: int = 3

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "ResourceBudget":
        data = dict(value or {})
        unknown = set(data) - set(cls.__annotations__)
        if unknown:
            raise ValueError(f"unknown resource budget fields: {sorted(unknown)}")
        known = {k: data[k] for k in cls.__annotations__ if k in data}
        try:
            budget = cls(**known)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid resource budget") from exc
        budget.validate()
        return budget

    def validate(self) -> None:
        if not 0 <= float(self.estimated_effort) <= 100_000:
            raise ValueError("estimated_effort must be between 0 and 100000")
        if not 1 <= float(self.max_elapsed_seconds) <= 604_800:
            raise ValueError("max_elapsed_seconds must be between 1 and 604800")
        if not 0 <= int(self.max_token_estimate) <= 10_000_000:
            raise ValueError("max_token_estimate must be between 0 and 10000000")
        if not 0 <= int(self.max_commits) <= 1_000:
            raise ValueError("max_commits must be between 0 and 1000")
        if not 0 <= int(self.max_tests) <= 10_000:
            raise ValueError("max_tests must be between 0 and 10000")
        if not 0 <= int(self.max_browser_runs) <= 1_000:
            raise ValueError("max_browser_runs must be between 0 and 1000")
        if not 1 <= int(self.max_cycles) <= 10_000:
            raise ValueError("max_cycles must be between 1 and 10000")
        if not 1 <= int(self.max_no_progress_cycles) <= 100:
            raise ValueError("max_no_progress_cycles must be between 1 and 100")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_USAGE: dict[str, int | float] = {
    "elapsed_seconds": 0.0,
    "token_estimate": 0,
    "commit_count": 0,
    "test_count": 0,
    "browser_runs": 0,
    "cycles": 0,
    "no_progress_cycles": 0,
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def snapshot_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def loads(raw: str, fallback: Any) -> Any:
    try:
        value = json.loads(raw or "")
    except Exception:
        return fallback
    return value


FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "credential",
        "cookie",
        "authorization",
    }
)


def reject_secret_fields(value: Any, *, path: str = "payload") -> None:
    """Reject secret-shaped keys before persistence.

    Mission tasks carry references and bounded arguments, never credentials.
    """

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in FORBIDDEN_INPUT_KEYS or normalized.endswith("_secret"):
                raise ValueError(f"secret-bearing field rejected at {path}.{key}")
            reject_secret_fields(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            reject_secret_fields(child, path=f"{path}[{index}]")


def validate_task_transition(current: str, target: str) -> None:
    src = TaskStatus(current)
    dst = TaskStatus(target)
    if dst != src and dst not in TASK_TRANSITIONS[src]:
        raise ValueError(f"illegal task transition {src.value}->{dst.value}")


def validate_mission_transition(current: str, target: str) -> None:
    src = MissionRuntimeState(current)
    dst = MissionRuntimeState(target)
    if dst != src and dst not in MISSION_TRANSITIONS[src]:
        raise ValueError(f"illegal mission transition {src.value}->{dst.value}")
