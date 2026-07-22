"""ExecutionGateway queue interface (abstract)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from saathi.execution.toolintent import ToolIntent


@dataclass
class QueuedItem:
    """Item in execution queue."""
    intent_id: str
    position: int
    eta: datetime
    retry_count: int
    attempt_number: int
    priority: int = 0
    enqueued_at: datetime = None

    def __post_init__(self):
        if self.enqueued_at is None:
            self.enqueued_at = datetime.utcnow()


class ExecutionQueue(ABC):
    """Abstract queue interface."""

    @abstractmethod
    def enqueue(self, intent: ToolIntent, priority: int = 0) -> QueuedItem:
        """Add intent to queue. Returns QueuedItem with position."""
        pass

    @abstractmethod
    def dequeue(self) -> Optional[ToolIntent]:
        """Remove and return next intent (FIFO). Returns None if empty."""
        pass

    @abstractmethod
    def peek(self) -> Optional[ToolIntent]:
        """View next intent without removing."""
        pass

    @abstractmethod
    def get_status(self, intent_id: str) -> Optional[QueuedItem]:
        """Get queue status for specific intent."""
        pass

    @abstractmethod
    def depth(self) -> int:
        """Return current queue depth."""
        pass

    @abstractmethod
    def is_duplicate(self, intent_id: str) -> bool:
        """Check if intent already in queue (by ID)."""
        pass

    @abstractmethod
    def mark_started(self, intent_id: str) -> None:
        """Mark intent as execution started."""
        pass

    @abstractmethod
    def mark_completed(self, intent_id: str) -> None:
        """Mark intent as execution completed (remove from queue)."""
        pass

    @abstractmethod
    def mark_failed(self, intent_id: str, retriable: bool) -> None:
        """Mark intent as failed (re-queue if retriable)."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear entire queue (dangerous operation)."""
        pass
