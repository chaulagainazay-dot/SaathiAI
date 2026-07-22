"""In-memory queue for ExecutionGateway (testing only; non-durable)."""

from typing import Optional, Dict
from collections import deque
import logging

from saathi.execution.toolintent import ToolIntent
from saathi.execution.queue.base import ExecutionQueue, QueuedItem

logger = logging.getLogger(__name__)


class MemoryQueue(ExecutionQueue):
    """Non-durable in-memory queue (testing only)."""

    def __init__(self):
        self.queue = deque()
        self.seen_ids = set()
        self.running = {}

    async def enqueue(self, intent: ToolIntent, priority: int = 0) -> QueuedItem:
        if await self.is_duplicate(intent.intent_id):
            raise ValueError(f"Duplicate intent: {intent.intent_id}")

        item = QueuedItem(
            intent_id=intent.intent_id,
            position=len(self.queue),
            eta=None,  # TODO: Calculate ETA
            retry_count=0,
            attempt_number=1,
            priority=priority,
        )
        self.queue.append((intent, item))
        self.seen_ids.add(intent.intent_id)
        logger.info(f"Enqueued: {intent.intent_id} (pos {item.position})")
        return item

    async def dequeue(self) -> Optional[ToolIntent]:
        if not self.queue:
            return None
        intent, item = self.queue.popleft()
        self.running[intent.intent_id] = item
        logger.info(f"Dequeued: {intent.intent_id}")
        return intent

    async def peek(self) -> Optional[ToolIntent]:
        if not self.queue:
            return None
        intent, _ = self.queue[0]
        return intent

    async def get_status(self, intent_id: str) -> Optional[QueuedItem]:
        for intent, item in self.queue:
            if intent.intent_id == intent_id:
                return item
        return self.running.get(intent_id)

    async def depth(self) -> int:
        return len(self.queue)

    async def is_duplicate(self, intent_id: str) -> bool:
        return intent_id in self.seen_ids

    async def mark_started(self, intent_id: str) -> None:
        logger.info(f"Execution started: {intent_id}")

    async def mark_completed(self, intent_id: str) -> None:
        if intent_id in self.running:
            del self.running[intent_id]
        logger.info(f"Execution completed: {intent_id}")

    async def mark_failed(self, intent_id: str, retriable: bool) -> None:
        if retriable:
            # Re-enqueue for retry
            logger.info(f"Retriable failure, re-queuing: {intent_id}")
        else:
            # Mark failed, remove from running
            if intent_id in self.running:
                del self.running[intent_id]
            logger.info(f"Final failure: {intent_id}")

    async def clear(self) -> None:
        self.queue.clear()
        self.seen_ids.clear()
        self.running.clear()
        logger.warning("Queue cleared")
