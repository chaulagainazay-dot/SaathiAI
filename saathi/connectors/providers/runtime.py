"""M32 — Bounded provider execution runtime (governance orchestration).

Drives one provider adapter through a bounded execution loop: mode gating
(DRY_RUN / SIMULATION / SHADOW; CANARY/ACTIVE rejected), request validation,
idempotency reservation, bounded timeout/deadline, deterministic retry, health
tracking, and quarantine. It never grants authority — production authority stays
with policy/approval/ExecutionGateway/rollout/certification/verification.

Retry delay is consumed as virtual time (no real sleeping) so tests are
deterministic and no wall-clock waiting ever exceeds the deadline.
"""
from __future__ import annotations

from typing import Any, Optional

from saathi.connectors.providers.config import ProviderConfig
from saathi.connectors.providers.contract import ProviderAdapter, adapter_satisfies_contract
from saathi.connectors.providers.errors import classify_exception, retry_category_for, safe_error_message
from saathi.connectors.providers.health import ProviderHealthTracker
from saathi.connectors.providers.idempotency import IdempotencyStore, compute_request_fingerprint
from saathi.connectors.providers.models import (
    ExecutionMode,
    M32_PROHIBITED_MODES,
    ProviderAdapterResult,
    ProviderErrorCode,
    ProviderExecutionContext,
    ProviderSideEffectClass,
    ProviderStatus,
    RetryCategory,
)
from saathi.connectors.providers.normalization import NormalizationError
from saathi.connectors.providers.quarantine import ProviderQuarantineStore
from saathi.connectors.providers.retry import RetryGates, decide_retry


class ProviderExecutionRuntime:
    def __init__(
        self,
        *,
        health: Optional[ProviderHealthTracker] = None,
        quarantine: Optional[ProviderQuarantineStore] = None,
        idempotency: Optional[IdempotencyStore] = None,
    ):
        self.health = health or ProviderHealthTracker()
        self.quarantine = quarantine or ProviderQuarantineStore()
        self.idem = idempotency or IdempotencyStore()

    def execute(
        self,
        adapter: ProviderAdapter,
        ctx: ProviderExecutionContext,
        config: ProviderConfig,
        *,
        idempotent: Optional[bool] = None,
        provider_idempotency_support: bool = False,
        credential_eligible: bool = True,
        approval_valid: bool = True,
    ) -> ProviderAdapterResult:
        pid = ctx.provider_id or getattr(getattr(adapter, "identity", None), "provider_id", "")
        deadline = float(config.timeout_policy.total_deadline)
        max_retries = int(config.retry_policy.max_retries)
        max_retry_after = float(config.rate_limit_policy.max_retry_after_seconds)

        # 0. contract sanity — a broken adapter fails closed
        ok, missing = adapter_satisfies_contract(adapter)
        if not ok:
            return self._error(pid, ctx, ProviderErrorCode.INTERNAL_ADAPTER_ERROR,
                               f"contract_incomplete:{','.join(missing)}", RetryCategory.NO_RETRY)

        # 1. mode gating — CANARY/ACTIVE prohibited in M32
        try:
            mode = ExecutionMode(ctx.mode)
        except ValueError:
            return self._error(pid, ctx, ProviderErrorCode.POLICY_BLOCKED, "unknown_mode", RetryCategory.POLICY_BLOCKED)
        if mode in M32_PROHIBITED_MODES:
            r = self._error(pid, ctx, ProviderErrorCode.POLICY_BLOCKED, f"mode_prohibited:{mode.value}", RetryCategory.POLICY_BLOCKED)
            r.status = ProviderStatus.DENIED.value
            return r

        # 2. quarantine block
        if self.quarantine.is_quarantined(pid):
            r = self._error(pid, ctx, ProviderErrorCode.POLICY_BLOCKED, "provider_quarantined", RetryCategory.NO_RETRY)
            r.status = ProviderStatus.DENIED.value
            return r

        # 3. request validation (no provider call yet)
        try:
            adapter.validate_request(ctx)
        except NormalizationError as e:
            return self._error(pid, ctx, e.code, str(e), RetryCategory.NO_RETRY)
        except Exception as e:
            code = classify_exception(e)
            return self._error(pid, ctx, code, safe_error_message(code, str(e)), RetryCategory.NO_RETRY)

        # 4. request fingerprint (for idempotency + retry stability)
        req_fp = compute_request_fingerprint(
            connector_id=ctx.connector_id, provider_id=pid, operation=ctx.operation,
            normalized_payload=ctx.payload, account_link_id=ctx.account_link,
        )

        # 5. DRY_RUN — validate only, no provider execution
        if mode == ExecutionMode.DRY_RUN:
            return ProviderAdapterResult(
                status=ProviderStatus.DRY_RUN.value, provider_id=pid, operation=ctx.operation,
                normalized_data={"validated": True}, side_effect_class=config.side_effect_class,
                mode=mode.value, authoritative=False, request_fingerprint=req_fp,
                retryability=RetryCategory.NO_RETRY.value,
            )

        # 6. idempotency reservation
        idem_state = "none"
        if ctx.idempotency_key:
            state, rec = self.idem.reserve(
                idempotency_key=ctx.idempotency_key, connector_id=ctx.connector_id,
                provider_id=pid, operation=ctx.operation, request_fingerprint=req_fp,
                account_link_id=ctx.account_link,
            )
            idem_state = state
            if state == "conflict":
                r = self._error(pid, ctx, ProviderErrorCode.CONFLICT, "idempotency_conflict", RetryCategory.NO_RETRY)
                r.status = ProviderStatus.DENIED.value
                r.request_fingerprint = req_fp
                return r
            if state == "replay":
                # duplicate request → reuse logical operation; NO new provider call
                return ProviderAdapterResult(
                    status=ProviderStatus.SUCCESS.value, provider_id=pid, operation=ctx.operation,
                    normalized_data={"idempotent_replay": True},
                    provider_request_id_safe=rec.provider_request_id_safe,
                    side_effect_class=config.side_effect_class, mode=mode.value,
                    authoritative=False, request_fingerprint=req_fp,
                    limitations=["idempotent_replay"], retryability=RetryCategory.NO_RETRY.value,
                )

        # 7. idempotency determination
        if idempotent is None:
            is_idem = config.side_effect_class in (
                ProviderSideEffectClass.READ_ONLY.value, ProviderSideEffectClass.NONE.value,
            )
        else:
            is_idem = bool(idempotent)
        effective_idempotent = is_idem or provider_idempotency_support

        # 8. bounded execution loop (virtual-time deadline)
        elapsed = 0.0
        attempts = 0
        result: Optional[ProviderAdapterResult] = None
        while True:
            remaining = deadline - elapsed
            if remaining <= 0:
                result = self._error(pid, ctx, ProviderErrorCode.TIMEOUT, "deadline_exceeded", RetryCategory.NO_RETRY)
                result.status = ProviderStatus.TIMEOUT.value
                break
            attempts += 1
            try:
                result = adapter.execute(ctx)
                if result.ok:
                    self.health.observe_success(pid)
                elif result.error_code:
                    try:
                        self.health.observe_error(pid, ProviderErrorCode(result.error_code))
                    except ValueError:
                        pass
            except Exception as e:  # transport-level (timeout/connection/cancel/shutdown/malformed)
                code = classify_exception(e)
                self.health.observe_error(pid, code)
                result = self._error(pid, ctx, code, safe_error_message(code, type(e).__name__),
                                     retry_category_for(code))
                if code == ProviderErrorCode.TIMEOUT:
                    result.status = ProviderStatus.TIMEOUT.value
                elif code == ProviderErrorCode.CANCELLED:
                    result.status = ProviderStatus.CANCELLED.value
            result.attempts = attempts
            result.request_fingerprint = req_fp
            result.mode = mode.value

            if result.status in (ProviderStatus.SUCCESS.value, ProviderStatus.PARTIAL.value):
                break

            # decide retry
            try:
                cat = RetryCategory(result.retryability)
            except ValueError:
                cat = RetryCategory.NO_RETRY
            retry_after = None
            if result.rate_limit and isinstance(result.rate_limit, dict):
                retry_after = result.rate_limit.get("retry_after")
            gates = RetryGates(
                idempotent=effective_idempotent,
                credential_eligible=credential_eligible,
                approval_valid=approval_valid,
                provider_quarantined=self.quarantine.is_quarantined(pid),
                rollout_permits=True,  # SHADOW/SIMULATION permitted; production rollout is separate
                fingerprint_unchanged=True,
            )
            dec = decide_retry(
                category=cat, attempt=attempts, max_retries=max_retries,
                remaining_deadline=remaining, gates=gates, retry_after=retry_after,
                max_retry_after=max_retry_after,
                backoff_base=config.retry_policy.backoff_base_seconds,
                backoff_factor=config.retry_policy.backoff_factor,
            )
            if not dec.should_retry:
                result.limitations = list(result.limitations) + [f"retry_stop:{dec.reason}"]
                break
            elapsed += dec.delay_seconds  # consume virtual time; never real sleep

        # 9. quarantine on repeated malformed
        if self.health.should_quarantine(pid):
            self.quarantine.quarantine(pid, reason="repeated_malformed_responses")

        # 10. shadow/simulation output is never authoritative
        result.authoritative = False

        # 11. idempotency completion
        if ctx.idempotency_key and idem_state == "new":
            try:
                self.idem.complete(
                    idempotency_key=ctx.idempotency_key, connector_id=ctx.connector_id,
                    provider_id=pid, account_link_id=ctx.account_link,
                    status="completed" if result.ok else "failed",
                    provider_request_id_safe=result.provider_request_id_safe,
                )
            except KeyError:
                pass
        return result

    def _error(
        self, provider_id: str, ctx: ProviderExecutionContext,
        code: ProviderErrorCode, message: str, category: RetryCategory,
    ) -> ProviderAdapterResult:
        return ProviderAdapterResult(
            status=ProviderStatus.ERROR.value,
            provider_id=provider_id,
            operation=ctx.operation,
            normalized_data={},
            error_code=code.value,
            safe_message=safe_error_message(code, message),
            retryability=category.value,
            side_effect_class=getattr(ctx, "side_effect_class", ProviderSideEffectClass.READ_ONLY.value)
            if hasattr(ctx, "side_effect_class") else ProviderSideEffectClass.READ_ONLY.value,
            mode=ctx.mode,
            authoritative=False,
        )
