"""M15 connector execution engine — substrate under the universal gateway.

M17.22: every connector / CLI / local / MCP action enters the SaathiOS
ExecutionGateway.submit boundary first. The connector layer remains the
substrate that enforces connector-native guarantees:

  * connection lifecycle: only executable states may run
  * risk model: a tool can never downgrade below its capability floor
  * approval binding: an approval is valid only for the EXACT action
        (tool + account + normalized-input hash), unexpired, single-use
  * idempotency: a completed execution with the same key is replayed, not re-run
  * rate limits: per-connector buckets
  * failure classification: uncertain / non-idempotent side effects NEVER auto-retry
  * evidence + provenance recorded for every attempt; secrets never surface

No connector may bypass the gateway path. No agent may bypass connector policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from saathi.connectors.platform import registry as R
from saathi.connectors.platform import store as S
from saathi.connectors.platform.models import (
    ToolResult, ConnState, RiskClass, APPROVAL_THRESHOLD, MANUAL_ONLY,
    is_executable, normalized_input_hash, to_gateway_risk, _now_iso,
)
from saathi.connectors.platform.adapters import FailureClass, is_retryable
from saathi.connectors.platform.credentials import (
    CredentialRef, resolve_secret, has_secret, SecretUnavailable,
)

# Universal ExecutionGateway (M17.22) — optional import guard so the engine
# still runs if the execution package is refactored; connector-native checks
# remain the hard substrate either way.
try:
    from saathi.execution.toolintent import (
        builder, ActorType, RiskLevel, ApprovalLevel, BusinessUnit,
    )
    from saathi.execution.gateway import ExecutionGateway, ExecutionContext
    from saathi.execution.queue.memory import MemoryQueue
    from saathi.execution.record import tool_intent_digest
    _GATEWAY_OK = True
except Exception:  # pragma: no cover
    _GATEWAY_OK = False


_RISK_TO_GATEWAY_LEVEL = {
    RiskClass.LOCAL_READ: "LOW", RiskClass.EXTERNAL_READ: "LOW",
    RiskClass.REVERSIBLE_MUTATION: "MEDIUM",
    RiskClass.EXTERNAL_SIDE_EFFECT: "HIGH", RiskClass.HIGH_IMPACT: "CRITICAL",
}


@dataclass
class ExecRequest:
    owner: str                 # user/org scope
    tool_id: str
    account_id: str = ""       # connector account; "" for local no-auth
    args: dict = None
    approval_id: str = ""      # explicit approval binding, if pre-granted
    idempotency_key: str = ""
    environment: str = "prod"  # prod | staging | test
    target: str = ""           # optional narrowing (e.g. repo, channel)
    actor_type: str = "user"   # user | agent | system

    def __post_init__(self):
        if self.args is None:
            self.args = {}


class ExecutionEngine:
    def __init__(self, store: Optional[S.ConnectorStore] = None):
        self.store = store or S.default_store()
        self._gw = None
        if _GATEWAY_OK:
            try:
                from pathlib import Path
                from saathi.execution.store import ExecutionStore, DEFAULT_DB
                from saathi.execution.universal import UniversalBoundary
                # Keep gateway records co-located with the connector store so
                # tests (temp DBs) stay isolated; production uses default store.
                try:
                    cpath = Path(self.store.db_path)
                    egw_path = cpath.with_name(cpath.stem + ".egw.db")
                except Exception:
                    egw_path = DEFAULT_DB
                boundary = UniversalBoundary(
                    store=ExecutionStore(egw_path),
                    auto_integrations=True,
                )
                self._gw = ExecutionGateway(MemoryQueue(), boundary=boundary)
            except Exception:  # pragma: no cover
                try:
                    self._gw = ExecutionGateway(MemoryQueue())
                except Exception:
                    self._gw = None
        from saathi.connectors.platform.enterprise.resilience import BreakerRegistry
        self._breakers = BreakerRegistry()

    # ── public API ──────────────────────────────────────────────────────────
    def execute(self, req: ExecRequest) -> ToolResult:
        """Execute via universal ExecutionGateway (M17.22) → connector substrate."""
        tool = R.get_tool(req.tool_id)
        if tool is None:
            return self._fail(req, FailureClass.UNSUPPORTED, f"unknown tool {req.tool_id}")
        conn = R.get_connector(tool.connector_id)
        if conn is None:
            return self._fail(req, FailureClass.UNSUPPORTED,
                              f"no connector for {req.tool_id}")

        # Prefer universal gateway path when available
        if self._gw is not None and _GATEWAY_OK:
            try:
                return self._execute_via_gateway(req, tool, conn)
            except Exception as e:
                self.store.event("connector.gateway_submit_error",
                                 {"error": self._redact(str(e)), "tool": req.tool_id})
                # fall through to substrate-only path (still governed checks below)

        return self._execute_substrate(req, tool, conn, gw_ref="gateway-unavailable")

    def _preflight_substrate(self, req: ExecRequest, tool, conn) -> Optional[ToolResult]:
        """Lifecycle / ownership / scope / circuit before approval or adapter.

        Keeps fail-closed ordering: policy denials surface as blocked even when
        the action would also require approval.
        """
        if not conn.local:
            acct = self.store.get_account(req.account_id) if req.account_id else None
            if not acct:
                return self._fail(req, FailureClass.AUTH,
                                  "no connected account for connector")
            if acct.get("owner") != req.owner:
                self.store.event("connector.cross_owner_blocked",
                                 {"account": req.account_id, "caller": req.owner})
                return self._blocked(req, FailureClass.AUTHZ,
                                     "account not owned by caller")
            if acct.get("connector_id") != conn.connector_id:
                return self._blocked(req, FailureClass.AUTHZ,
                                     "account/connector mismatch")
            state = ConnState(acct["state"])
            if not acct.get("enabled", 1):
                return self._blocked(req, FailureClass.POLICY, "account disabled")
            if not is_executable(state):
                return self._fail(req, self._state_failure(state),
                                  f"connection not executable ({state.value})")

        acct_row = None
        if not conn.local:
            acct_row = self.store.get_account(req.account_id) if req.account_id else None
        from saathi.connectors.platform.enterprise import scopes as _scopes
        decision = _scopes.evaluate(tool_id=req.tool_id, account=acct_row,
                                    actor_type=req.actor_type, environment=req.environment)
        if not decision.allowed:
            return self._blocked(req, FailureClass.POLICY,
                                 f"scope/permission denied: {decision.reason_code}")

        breaker = self._breakers.get(connector_id=conn.connector_id,
                                     account_id=req.account_id, operation=req.tool_id)
        if not breaker.allow():
            return self._fail(req, FailureClass.UNAVAILABLE,
                              "circuit open for connector/account/operation",
                              extra={"circuit": "open"})
        return None

    def _execute_via_gateway(self, req: ExecRequest, tool, conn) -> ToolResult:
        """Outer boundary: ToolIntent → ExecutionGateway.submit → substrate handler."""
        risk = tool.risk_class
        input_hash = normalized_input_hash(req.tool_id, req.account_id, req.args)
        needs_appr = int(risk) >= int(APPROVAL_THRESHOLD) or tool.requires_approval
        family = "mcp" if (conn.provider or "").lower() == "mcp" else (
            "cli" if (conn.provider or "").lower() in ("cli", "local-cli") else (
                "local" if conn.local else "connector"))

        # Preflight before approval so scope/ownership denials stay blocked.
        pre = self._preflight_substrate(req, tool, conn)
        if pre is not None:
            return pre

        # Connector-native approval (exact-action binding) — reused, not replaced.
        # Invalid / used / missing approval always short-circuits (single-use).
        connector_appr = None
        if needs_appr:
            connector_appr = self._resolve_approval(
                req, risk, input_hash, int(risk) >= int(MANUAL_ONLY))
            if connector_appr is None:
                # Missing, used, expired, or mismatched approval — single-use
                # and exact-action binding stay connector-native.
                intent = self._build_intent(req, tool, risk, family, require_approval=True)
                rec = self._gw.submit(intent, execute=True)  # stops at approval_required
                return ToolResult(
                    status="approval_required", connector_id=conn.connector_id,
                    tool_id=tool.tool_id, capability_id=tool.capability_id,
                    started_at=_now_iso(), completed_at=_now_iso(),
                    errors=[{"class": FailureClass.APPROVAL,
                             "message": f"risk {int(risk)} action requires bound approval",
                             "input_hash": input_hash,
                             "manual_only": int(risk) >= int(MANUAL_ONLY),
                             "execution_id": rec.execution_id,
                             "digest": rec.tool_intent_digest}],
                    provenance={"risk": int(risk), "input_hash": input_hash,
                                "gateway_ref": rec.execution_id,
                                "gateway_status": rec.status})

        # Auto-approve at gateway when connector approval already resolved (or not needed)
        pre_resolved = bool(connector_appr) or not needs_appr
        intent = self._build_intent(
            req, tool, risk, family,
            require_approval=not pre_resolved,
            approval_pre_resolved=pre_resolved and needs_appr,
        )

        captured: dict = {}

        def _handler(intent_obj, rec):
            # skip preflight (done) + approval (done); still run adapter path
            result = self._execute_substrate(
                req, tool, conn, gw_ref=rec.execution_id,
                skip_idempotency=False, skip_approval=True,
                skip_preflight=True)
            captured["result"] = result
            st = result.status
            if st in ("success", "partial"):
                return {"status": "succeeded",
                        "summary": f"{tool.tool_id}:{st}"}
            if st == "approval_required":
                return {"status": "failed", "summary": "approval_required",
                        "failure_category": "approval", "retryable": False}
            if st == "blocked":
                return {"status": "failed", "summary": (result.errors or [{}])[0].get("message", "blocked"),
                        "failure_category": "permission", "retryable": False}
            err = (result.errors or [{}])[0]
            return {
                "status": "failed",
                "summary": err.get("message", st),
                "failure_category": err.get("class", "execution"),
                "retryable": bool(result.retryable),
            }

        rec = self._gw.submit(
            intent,
            approval_id="",
            handler=_handler,
            execute=True,
        )
        if "result" in captured:
            r = captured["result"]
            r.provenance = {**(r.provenance or {}),
                            "gateway_ref": rec.execution_id,
                            "gateway_status": rec.status,
                            "tool_intent_digest": rec.tool_intent_digest}
            return r
        # Gateway terminal without handler (denied/expired/approval/idempotent replay)
        if rec.status == "approval_required":
            return ToolResult(
                status="approval_required", connector_id=conn.connector_id,
                tool_id=tool.tool_id, capability_id=tool.capability_id,
                started_at=_now_iso(), completed_at=_now_iso(),
                errors=[{"class": FailureClass.APPROVAL,
                         "message": rec.result_summary or "approval required",
                         "input_hash": input_hash}],
                provenance={"gateway_ref": rec.execution_id,
                            "gateway_status": rec.status,
                            "tool_intent_digest": rec.tool_intent_digest})
        if rec.status == "succeeded":
            return ToolResult(
                status="success", connector_id=conn.connector_id,
                tool_id=tool.tool_id, capability_id=tool.capability_id,
                execution_id=rec.execution_id,
                started_at=_now_iso(), completed_at=_now_iso(),
                provenance={"gateway_ref": rec.execution_id,
                            "gateway_status": rec.status,
                            "tool_intent_digest": rec.tool_intent_digest,
                            "replayed": True})
        return ToolResult(
            status="failed" if rec.status != "denied" else "blocked",
            connector_id=conn.connector_id, tool_id=tool.tool_id,
            capability_id=tool.capability_id, execution_id=rec.execution_id,
            started_at=_now_iso(), completed_at=_now_iso(),
            errors=[{"class": rec.failure_category or FailureClass.INTERNAL,
                     "message": rec.result_summary or rec.status}],
            retryable=bool(rec.retryable),
            provenance={"gateway_ref": rec.execution_id,
                        "gateway_status": rec.status,
                        "tool_intent_digest": rec.tool_intent_digest})

    def _build_intent(self, req, tool, risk, family: str, *, require_approval: bool,
                      approval_pre_resolved: bool = False):
        level_name = _RISK_TO_GATEWAY_LEVEL.get(risk, "MEDIUM")
        appr = ApprovalLevel.L4 if require_approval else ApprovalLevel.L1
        b = (builder()
             .actor(req.owner, ActorType.AGENT if req.actor_type == "agent"
                    else ActorType.USER)
             .mission(f"connector:{tool.tool_id}")
             .capability(tool.capability_id or tool.tool_id, tool.connector_id, tool.tool_id)
             .parameters(dict(req.args or {}))
             .reason(f"connector exec {tool.tool_id}")
             .risk(RiskLevel[level_name], appr)
             .metadata({
                 "family": family,
                 "target": req.target or "",
                 "account_id": req.account_id or "",
                 "environment": req.environment,
                 "require_approval": require_approval,
                 "approval_pre_resolved": approval_pre_resolved,
             }))
        import hashlib
        import uuid as _uuid
        if req.idempotency_key:
            # ToolIntent idempotency_key must be 64-char hex; hash arbitrary keys
            key = req.idempotency_key
            if len(key) != 64:
                key = hashlib.sha256(key.encode()).hexdigest()
            b.data["idempotency_key"] = key
        else:
            # No caller key → unique attempt id so terminal success is not
            # auto-replayed (connector single-use approval + re-run semantics).
            # Digest still binds approval for the same action content.
            b.data["idempotency_key"] = hashlib.sha256(
                f"attempt:{_uuid.uuid4().hex}".encode()
            ).hexdigest()
        return b.build()

    def _execute_substrate(self, req: ExecRequest, tool, conn, *, gw_ref: str,
                           skip_idempotency: bool = False,
                           skip_approval: bool = False,
                           skip_preflight: bool = False) -> ToolResult:
        """Connector-native checks + adapter invoke (substrate under the gateway)."""
        risk = tool.risk_class
        input_hash = normalized_input_hash(req.tool_id, req.account_id, req.args)

        # 1) idempotency replay — same key already completed → return stored
        idem = req.idempotency_key
        if idem and not skip_idempotency:
            prior = self.store.execution_by_idempotency(idem)
            if prior:
                self.store.event("connector.idempotent_replay",
                                 {"tool": req.tool_id, "key": idem})
                return self._replay(prior)

        # 2) preflight (lifecycle / scope / circuit) unless already done
        breaker = self._breakers.get(connector_id=conn.connector_id,
                                     account_id=req.account_id, operation=req.tool_id)
        if not skip_preflight:
            pre = self._preflight_substrate(req, tool, conn)
            if pre is not None:
                return pre
        # re-fetch breaker after preflight (same instance)
        breaker = self._breakers.get(connector_id=conn.connector_id,
                                     account_id=req.account_id, operation=req.tool_id)

        # 3) risk / approval binding (skipped when gateway already enforced)
        needs_approval = int(risk) >= int(APPROVAL_THRESHOLD) or tool.requires_approval
        manual_only = int(risk) >= int(MANUAL_ONLY)
        if needs_approval and not skip_approval:
            appr = self._resolve_approval(req, risk, input_hash, manual_only)
            if appr is None:
                return ToolResult(
                    status="approval_required", connector_id=conn.connector_id,
                    tool_id=tool.tool_id, capability_id=tool.capability_id,
                    started_at=_now_iso(), completed_at=_now_iso(),
                    errors=[{"class": FailureClass.APPROVAL,
                             "message": f"risk {int(risk)} action requires bound approval",
                             "input_hash": input_hash, "manual_only": manual_only}],
                    provenance={"risk": int(risk), "input_hash": input_hash,
                                "gateway_ref": gw_ref})

        # 4) legacy governance pass retained for audit when not via submit
        if gw_ref in ("gateway-unavailable", "gateway-error") or not str(gw_ref).startswith("egw"):
            if gw_ref in ("gateway-unavailable",) or not self._gw:
                gw_ref = self._governed(req, tool, risk) or gw_ref

        # 5) rate-limit bucket
        rl = self._rate_check(conn.rate_limit_policy, tool.rate_limit_bucket or conn.connector_id)
        if rl is not None:
            return ToolResult(status="failed", connector_id=conn.connector_id,
                              tool_id=tool.tool_id, capability_id=tool.capability_id,
                              started_at=_now_iso(), completed_at=_now_iso(),
                              errors=[{"class": FailureClass.RATE_LIMIT,
                                       "message": "local rate bucket exhausted"}],
                              retryable=True, rate_limit=rl,
                              provenance={"gateway_ref": gw_ref})

        # 6) execute via adapter
        adapter = R.get_adapter(conn.connector_id)
        if adapter is None or not adapter.available():
            return self._fail(req, FailureClass.UNAVAILABLE,
                              f"adapter for {conn.connector_id} unavailable",
                              extra={"integration_status": conn.integration_status})

        secret_getter = (self._secret_getter(req.account_id, conn.connector_id, req.owner)
                         if not conn.local else None)
        try:
            result = adapter.execute(tool=tool, account_id=req.account_id,
                                     args=req.args, secret_getter=secret_getter)
        except SecretUnavailable as e:
            return self._fail(req, FailureClass.SECRET, str(e))
        except Exception as e:
            return self._fail(req, FailureClass.INTERNAL, self._redact(str(e)))

        # 7) classify + retry policy
        result = self._finalize(req, tool, conn, result, input_hash, gw_ref)
        breaker.record(success=result.status in ("success", "partial"))

        # 8) consume single-use approval + persist execution + evidence
        if needs_approval and req.approval_id and result.status in (
                "success", "partial", "uncertain"):
            self.store.consume_approval(req.approval_id)
        self.store.record_execution(
            owner=req.owner, result=result, risk=int(risk),
            input_hash=input_hash, idempotency_key=idem,
            account_id=req.account_id or "")
        return result

    # ── approval resolution (exact-action binding) ───────────────────────────
    def _resolve_approval(self, req, risk, input_hash, manual_only):
        # explicit approval id → must match this exact action
        if req.approval_id:
            appr = self.store.get_approval(req.approval_id)
            if appr and appr.get("status") == "approved" \
                    and appr.get("used", 0) < appr.get("max_uses", 1) \
                    and appr.get("input_hash") == input_hash \
                    and appr.get("tool_id") == req.tool_id \
                    and appr.get("account_id") == req.account_id \
                    and int(appr.get("risk", -1)) == int(risk) \
                    and not self._expired(appr):
                return appr
            return None
        # otherwise look for an unexpired, unused approval bound to this action
        return self.store.find_valid_approval(
            owner=req.owner, tool_id=req.tool_id, account_id=req.account_id,
            input_hash=input_hash, risk=int(risk),
            environment=req.environment, target=req.target)

    def request_approval(self, req: ExecRequest) -> dict:
        """Create an approval bound to the EXACT action; returns the record."""
        tool = R.get_tool(req.tool_id)
        risk = tool.risk_class if tool else RiskClass.HIGH_IMPACT
        input_hash = normalized_input_hash(req.tool_id, req.account_id, req.args)
        conn_id = tool.connector_id if tool else ""
        cap = tool.capability_id if tool else ""
        aid = self.store.add_approval(
            owner=req.owner, connector_id=conn_id, account_id=req.account_id,
            tool_id=req.tool_id, capability_id=cap, input_hash=input_hash,
            risk=int(risk), environment=req.environment, target=req.target)
        return {"approval_id": aid, "input_hash": input_hash, "risk": int(risk),
                "manual_only": int(risk) >= int(MANUAL_ONLY),
                "binds_to": {"tool": req.tool_id, "account": req.account_id,
                             "environment": req.environment, "target": req.target}}

    # ── governance pass ──────────────────────────────────────────────────────
    def _governed(self, req, tool, risk) -> str:
        if not self._gw:
            return "gateway-unavailable"
        try:
            intent = (builder()
                      .actor(req.owner, ActorType.AGENT if req.actor_type == "agent"
                             else ActorType.USER)
                      .capability(tool.capability_id, tool.connector_id, tool.tool_id)
                      .parameters(dict(req.args))
                      .reason(f"connector exec {tool.tool_id}")
                      .risk(RiskLevel[_RISK_TO_GATEWAY_LEVEL[risk]],
                            ApprovalLevel.L4 if int(risk) >= int(APPROVAL_THRESHOLD)
                            else ApprovalLevel.L1)
                      .build())
            now = datetime.now(timezone.utc)
            ctx = ExecutionContext(actor_id=req.owner, business_unit="connectors",
                                   timestamp=now, current_time=now)
            hist = self._gw.receive_intent(intent)
            hist = self._gw.validate_intent(intent, hist)
            hist = self._gw.check_idempotency(intent, hist)
            hist = self._gw.authorize(intent, ctx, hist)
            hist, lvl = self._gw.classify_risk(intent, ctx, hist)
            self._gw.check_approval(intent, lvl, hist)
            return intent.intent_id
        except Exception as e:  # governance failure is not silent
            self.store.event("connector.gateway_error", {"error": self._redact(str(e))})
            return "gateway-error"

    # ── rate limiting ────────────────────────────────────────────────────────
    def _rate_check(self, policy, bucket) -> Optional[dict]:
        if policy in ("unlimited", "local"):
            return None
        b = self.store.get_bucket(bucket)
        if b and b.get("remaining", 1) <= 0 and b.get("reset_at", 0) > S._now():
            return {"remaining": 0, "reset_at": b["reset_at"]}
        return None

    # ── finalize / classify ──────────────────────────────────────────────────
    def _finalize(self, req, tool, conn, result: ToolResult, input_hash, gw_ref) -> ToolResult:
        result.connector_id = conn.connector_id
        result.tool_id = tool.tool_id
        result.capability_id = tool.capability_id
        result.provenance = {**(result.provenance or {}),
                             "gateway_ref": gw_ref, "input_hash": input_hash,
                             "risk": int(tool.risk_class),
                             "integration_status": conn.integration_status,
                             "idempotent": tool.idempotent}
        if not result.completed_at:
            result.completed_at = _now_iso()
        # retry eligibility — uncertain side effects & non-idempotent never retry
        if result.status in ("failed", "uncertain") and result.errors:
            fclass = result.errors[0].get("class", FailureClass.INTERNAL)
            result.retryable = is_retryable(fclass, idempotent=tool.idempotent)
            if result.status == "uncertain" or not tool.idempotent:
                result.retryable = False
            self.store.record_failure(connector_id=conn.connector_id,
                                      tool_id=tool.tool_id, fingerprint=input_hash,
                                      failure_class=fclass)
        return result

    # ── secret access (in-process only) ──────────────────────────────────────
    def _secret_getter(self, account_id, connector_id, owner):
        store = self.store

        def _get(backend_key_hint: str = "") -> str:
            acct = store.get_account(account_id)
            if not acct or not acct.get("cred_ref_id"):
                raise SecretUnavailable("no credential reference on account")
            row = store.get_cred_ref(acct["cred_ref_id"])
            if not row:
                raise SecretUnavailable("credential reference missing")
            ref = CredentialRef(**{k: row[k] for k in row if k in
                                   CredentialRef.__dataclass_fields__})
            # staging-hardened: validate ownership/scope/connector before lookup
            from saathi.connectors.platform.credentials import resolve_for_account
            return resolve_for_account(account=acct, ref=ref,
                                       expected_connector=connector_id, owner=owner)
        return _get

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _state_failure(state: ConnState) -> str:
        return {ConnState.EXPIRED: FailureClass.AUTH,
                ConnState.UNAUTHORIZED: FailureClass.AUTHZ,
                ConnState.RATE_LIMITED: FailureClass.RATE_LIMIT,
                ConnState.UNAVAILABLE: FailureClass.UNAVAILABLE,
                ConnState.DISABLED: FailureClass.POLICY,
                }.get(state, FailureClass.UNAVAILABLE)

    @staticmethod
    def _expired(appr: dict) -> bool:
        exp = appr.get("expires_at", 0)
        return bool(exp) and exp < S._now()

    @staticmethod
    def _redact(msg: str) -> str:
        # never let a token/cookie surface through an error string
        import re
        return re.sub(r"(?i)(token|secret|key|cookie|bearer)\s*[=:]\s*\S+",
                      r"\1=[redacted]", msg)[:300]

    def _replay(self, prior: dict) -> ToolResult:
        return ToolResult(status=prior.get("status", "success"),
                          connector_id=prior.get("connector_id", ""),
                          tool_id=prior.get("tool_id", ""),
                          execution_id=prior.get("execution_id", ""),
                          started_at=prior.get("started_at", ""),
                          completed_at=prior.get("completed_at", ""),
                          provenance={"replayed": True,
                                      "input_hash": prior.get("input_hash", "")})

    def _fail(self, req, fclass, msg, *, extra=None) -> ToolResult:
        r = ToolResult(status="failed", tool_id=req.tool_id, started_at=_now_iso(),
                       completed_at=_now_iso(),
                       errors=[{"class": fclass, "message": msg}],
                       retryable=fclass in (FailureClass.TIMEOUT, FailureClass.TRANSIENT,
                                            FailureClass.UNAVAILABLE),
                       provenance=extra or {})
        return r

    def _blocked(self, req, fclass, msg) -> ToolResult:
        return ToolResult(status="blocked", tool_id=req.tool_id, started_at=_now_iso(),
                          completed_at=_now_iso(),
                          errors=[{"class": fclass, "message": msg}])


_ENGINE: Optional[ExecutionEngine] = None


def default_engine() -> ExecutionEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ExecutionEngine()
    return _ENGINE
