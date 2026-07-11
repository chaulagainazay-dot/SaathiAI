"""M15 sync/polling runner — resumable, checkpointed incremental sync.

A sync job pulls pages from a read capability via the ExecutionEngine (so every
fetch is still gateway-governed) and checkpoints its cursor/page_token after
each page. A crashed or paused job resumes from the last checkpoint — never
re-reading from the start, never double-emitting a completed page.
"""
from __future__ import annotations

from typing import Callable, Optional

from saathi.connectors.platform import store as S
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest


class SyncRunner:
    def __init__(self, engine: Optional[ExecutionEngine] = None,
                 store: Optional[S.ConnectorStore] = None):
        self.store = store or S.default_store()
        self.engine = engine or ExecutionEngine(store=self.store)

    def start(self, *, owner: str, connector_id: str, batch_size: int = 100) -> str:
        return self.store.create_sync(owner=owner, connector_id=connector_id,
                                      batch_size=batch_size)

    def run(self, *, sync_id: str, tool_id: str, account_id: str,
            page_extractor: Callable[[dict], tuple[list, Optional[str]]],
            max_pages: int = 100) -> dict:
        """Drive the job to completion (or max_pages), resuming from checkpoint.

        page_extractor(result.data) -> (items, next_page_token). Returns
        summary with total processed and where it stopped."""
        job = self.store.get_sync(sync_id)
        if not job:
            return {"error": "unknown sync job"}
        token = job.get("page_token") or None
        processed = job.get("processed") or 0
        self.store.checkpoint_sync(sync_id, state="running")
        pages = 0
        while pages < max_pages:
            args = {"_fixture": "success"}
            if token:
                args["page_token"] = token
            res = self.engine.execute(ExecRequest(
                owner=job["owner"], tool_id=tool_id, account_id=account_id, args=args))
            if res.status not in ("success", "partial"):
                self.store.checkpoint_sync(sync_id, state="error")
                return {"stopped": "error", "status": res.status,
                        "processed": processed, "pages": pages}
            items, token = page_extractor(res.data or {})
            processed += len(items)
            pages += 1
            # checkpoint AFTER the page is accounted for → resumable
            self.store.checkpoint_sync(sync_id, page_token=token or "",
                                       processed=processed, state="running")
            if not token:
                break
        state = "complete" if not token else "paused"
        self.store.checkpoint_sync(sync_id, state=state)
        return {"stopped": state, "processed": processed, "pages": pages}
