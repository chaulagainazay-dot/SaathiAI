"""Resolving real authority inputs for one execution intent.

Kept apart from `saathi.execution.authorization`, which stays pure. Everything
that touches a store, a registry or the clock lives here, so the composer can be
tested exhaustively without any of them and so no gate can be "satisfied" by a
resolver quietly returning a default.

Every resolver has the same contract: return the truth, or return None. None
means *could not establish*, and the composer turns that into a non-positive
finding. No resolver may return a permissive value on failure -- an `except`
branch here that returned `False` for "kill switch not blocked" would reopen
exactly the unconditional-allow hole this milestone closed.
"""
from __future__ import annotations

import contextlib
import contextvars

from saathi.agent_runtime.contracts import AuthorityClass
from saathi.agent_runtime.models import RiskClass
from saathi.execution.authorization import AuthorizationInputs, ResolvedAction
from saathi.execution.record import tool_intent_digest

#: The server-trusted actor for the current call, set only by an authenticated
#: boundary. Unset means no human session reached the gateway -- which is a fact
#: about this call, not a licence: see `SYSTEM_ACTOR_MAX_AUTHORITY`.
_ACTOR: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "saathi_execution_actor", default=None)


@contextlib.contextmanager
def actor_context(user_id: str | None):
    """Bind a server-resolved user id for the duration of a gateway call.

    Authenticated route handlers wrap gateway work in this. The value must come
    from session resolution -- never from a request body, header or intent field,
    which is the difference between identity and a claim about identity.
    """
    token = _ACTOR.set(user_id or None)
    try:
        yield
    finally:
        _ACTOR.reset(token)


def current_actor() -> str | None:
    return _ACTOR.get()


def current_actor_id() -> str:
    """The bound session as `user:<id>`, or the named system actor.

    The one place this translation happens, so the gateway, the chat engine and
    anything added later cannot drift into different spellings of "nobody" --
    and so no caller has to decide for itself what to do when identity is
    absent. It never invents a user.
    """
    from saathi.execution.authorization import SYSTEM_ACTOR

    actor = _ACTOR.get()
    return f"user:{actor}" if actor else SYSTEM_ACTOR


def _kill_switch_blocked() -> bool | None:
    """Global stop state, or None when it cannot be read.

    Only the GLOBAL and TRADING_GUARDIAN scopes are meaningful for a gateway
    intent; the narrower scopes key on strategy/instrument/portfolio, which a
    generic intent does not carry.
    """
    try:
        from saathi.platform.tg.kill_switch import KillSwitchStore

        return bool(KillSwitchStore().is_blocked().get("blocked"))
    except Exception:
        return None


def _has_permission(user_id: str) -> bool | None:
    try:
        from saathi.security.store import get_store

        return bool(get_store().has_permission(user_id, "write"))
    except Exception:
        return None


#: Connector-platform RiskClass → gateway authority class, by *meaning* rather
#: than by ordinal. The two enums are both 0-4 but they do not line up: the
#: connector platform's 1 is EXTERNAL_READ (search email, list events), which is
#: a read, whereas the agent runtime's 1 is LOCAL_REVERSIBLE, which is a write.
#: Mapping by ordinal would classify every external read as a mutation, so each
#: level is stated explicitly and this table is the only place the translation
#: happens.
_CONNECTOR_RISK_TO_AUTHORITY = {
    0: (AuthorityClass.READ_ONLY, RiskClass.READ_ONLY),               # LOCAL_READ
    1: (AuthorityClass.READ_ONLY, RiskClass.READ_ONLY),               # EXTERNAL_READ
    2: (AuthorityClass.LOCAL_MUTATION, RiskClass.LOCAL_MUTATION),     # REVERSIBLE_MUTATION
    3: (AuthorityClass.EXTERNAL_MUTATION, RiskClass.EXTERNAL_SIDE_EFFECT),
    4: (AuthorityClass.ADMINISTRATIVE, RiskClass.HIGH_IMPACT),        # HIGH_IMPACT
}


def _connector_action(intent) -> ResolvedAction | None:
    """The registered class of the connector tool this intent names.

    Authoritative when it resolves. When the intent names a connector but the
    tool is unregistered, or names a tool belonging to a different connector,
    this returns None -- the action then stays unclassified and the action gate
    refuses it. An unregistered connector tool is not a low-risk one.
    """
    operation = str(getattr(intent, "operation", "") or "")
    connector_id = str(getattr(intent, "connector_id", "") or "")
    if not connector_id:
        return None
    try:
        from saathi.connectors.platform import registry as R

        tool = R.get_tool(operation)
        if tool is None or tool.connector_id != connector_id:
            return None
        entry = _CONNECTOR_RISK_TO_AUTHORITY.get(int(tool.risk_class))
        if entry is None:
            return None
        authority, risk = entry
        return ResolvedAction(
            authority_class=authority,
            risk=risk,
            source="connector_registry",
            requires_connector=True,
        )
    except Exception:
        return None


def _connector_state(intent) -> str | None:
    """Canonical connector lifecycle state for the account this intent targets.

    Presence is not permission: this returns the state verbatim and the gate
    decides. An account that cannot be read returns None, which denies.
    """
    meta = getattr(intent, "metadata", None) or {}
    account_id = str(meta.get("account_id") or "")
    if not account_id:
        return None
    try:
        from saathi.connectors.platform import store as S

        account = S.default_store().get_account(account_id)
        if not account:
            return None
        if not account.get("enabled", 1):
            return "disabled"
        return str(account.get("state") or "") or None
    except Exception:
        return None


def _run(intent) -> tuple[bool, dict | None]:
    """(declared, run) for the run this intent executes within.

    `declared` separates "this action is not run-scoped" from "a run was named
    and could not be read"; the second must not be silently treated as the first.
    """
    meta = getattr(intent, "metadata", None) or {}
    run_id = str(meta.get("run_id") or "")
    if not run_id:
        return False, None
    try:
        from saathi.agent_runtime.orchestrator import default_orchestrator

        return True, default_orchestrator().store.get_run(run_id)
    except Exception:
        return True, None


def _approvals(intent) -> list[dict] | None:
    """Approvals bound to this exact action, by canonical digest.

    Looked up *by digest* rather than by run or actor, so an approval granted for
    a different action is never in the returned set to begin with.
    """
    try:
        from saathi.execution.universal import default_boundary

        store = default_boundary().store
        rows = store.approvals_for_digest(tool_intent_digest(intent))
        return [dict(r) for r in rows]
    except Exception:
        return None


def resolve_inputs(intent, context=None) -> AuthorizationInputs:
    """Gather every authority input for one intent from its real source.

    The actor comes from `actor_context`, never from `context.actor_id`: the
    ExecutionContext is caller-supplied and would let a caller name whoever they
    liked. When no session was bound, the caller is the backend process itself
    and is marked as such, which caps it at `SYSTEM_ACTOR_MAX_AUTHORITY`.
    """
    actor = current_actor()
    run_declared, run = _run(intent)
    return AuthorizationInputs(
        actor_user_id=actor,
        has_permission=_has_permission(actor) if actor else None,
        actor_is_system=actor is None,
        kill_switch_blocked=_kill_switch_blocked(),
        connector_action=_connector_action(intent),
        connector_state=_connector_state(intent),
        run_declared=run_declared,
        run=run,
        approvals=_approvals(intent),
        guardian_verdict=None,  # no generic per-intent Guardian verdict exists
    )
