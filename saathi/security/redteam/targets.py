"""M15.2 in-process red-team targets — isolated SaathiOS test harness.

Each target wraps the REAL SaathiOS boundary (ExecutionEngine, connector
registry, credential resolver, integration funnel, MCP wrapper, webhook,
store) but with an isolated test user / project / namespace / temp database.
No production data, no live credentials, deterministic adapters. Attacks probe
these targets and we assert on the genuine observable outcome.
"""
from __future__ import annotations

import tempfile

from saathi.connectors.platform import store as S
from saathi.connectors.platform import registry as R
from saathi.connectors.platform.execution import ExecutionEngine, ExecRequest
from saathi.connectors.platform import integration as I
from saathi.security.redteam.config import RedTeamConfig, assert_target_authorized


class SaathiTarget:
    """Isolated, authorized, in-process target bound to a temp connectors.db."""

    def __init__(self, config: RedTeamConfig | None = None):
        self.config = config or RedTeamConfig()
        self.config.validate()
        assert_target_authorized(self.config.target)
        self.store = S.ConnectorStore(tempfile.mktemp(suffix=".db"))
        self.engine = ExecutionEngine(store=self.store)
        self.user = self.config.isolated_user
        self.attacker = "redteam-attacker"   # a DIFFERENT isolated identity

    # ── helpers to set up isolated accounts ─────────────────────────────────
    def add_account(self, connector_id="github", owner=None, state="healthy"):
        return self.store.add_account(owner=owner or self.user,
                                      connector_id=connector_id, label="rt",
                                      state=state)

    def execute(self, *, owner, tool_id, account_id="", args=None, approval_id="",
                idempotency_key="", environment="staging", actor_type="user"):
        return self.engine.execute(ExecRequest(
            owner=owner, tool_id=tool_id, account_id=account_id, args=args or {},
            approval_id=approval_id, idempotency_key=idempotency_key,
            environment=environment, actor_type=actor_type))

    def request_and_grant_approval(self, *, owner, tool_id, account_id, args):
        appr = self.engine.request_approval(ExecRequest(
            owner=owner, tool_id=tool_id, account_id=account_id, args=args,
            environment="staging"))
        self.store.resolve_approval(appr["approval_id"], approved=True, actor=owner)
        return appr["approval_id"]

    def describe(self, *, tool_id, account_id="", args=None):
        return I.describe_action(tool_id=tool_id, account_id=account_id,
                                 args=args or {}, owner=self.user)

    def ceo_tier(self, result: dict) -> str:
        return I.ceo_evidence_tier(result)
