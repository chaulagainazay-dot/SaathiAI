"""Governed IELTSAlert application service.

All public methods require a validated platform context. The service delegates
identity, tenancy, RBAC, notifications, evidence references and audit to existing
platform authorities; it is not a parallel platform.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from saathi.platform.context import PlatformContextError
from saathi.platform.models import PlatformPermission
from saathi.platform.safety.models import is_agent_actor

from .models import (
    ALERT_TRANSITIONS,
    PAYMENT_TRANSITIONS,
    AlertStatus,
    IELTSRecord,
    PaymentStatus,
    validate_alert,
    validate_goal,
    validate_payment,
    validate_practice,
    validate_profile,
)
from .repository import IELTSRepository
from .scoring import SafeFallbackScorer, UnavailableScoringProvider


LOCAL_CENTERS = (
    {"center_id": "fixture_ktm_01", "name": "Kathmandu Practice Fixture", "location": "Kathmandu",
     "formats": ["computer"], "dates": ["2030-01-12", "2030-02-09"]},
    {"center_id": "fixture_pkr_01", "name": "Pokhara Practice Fixture", "location": "Pokhara",
     "formats": ["computer", "paper"], "dates": ["2030-01-20"]},
)


class IELTSService:
    def __init__(self, platform_store, *, scorer=None):
        self.store = platform_store
        self.repo = IELTSRepository(platform_store)
        self.scorer = scorer or SafeFallbackScorer(UnavailableScoringProvider())

    @staticmethod
    def _human(ctx) -> None:
        if is_agent_actor(ctx):
            raise PlatformContextError("PERMISSION_DENIED", "IELTS human workflow is unavailable to agent actors")

    def _audit(self, ctx, event: str, *, record: IELTSRecord | None = None,
               outcome: str = "success", detail: dict | None = None, evidence: str = "") -> None:
        safe = {"record_id": record.record_id, "record_type": record.record_type} if record else {}
        safe.update(detail or {})
        self.store.append_audit(
            event, user_id=ctx.user_id, role=ctx.role, org_id=ctx.org_id,
            workspace_id=ctx.workspace_id, project_id=getattr(ctx, "project_id", ""),
            mission_id=getattr(ctx, "mission_id", ""), outcome=outcome,
            evidence=evidence[:500], detail=safe,
        )

    def _notify(self, ctx, *, title: str, summary: str, record: IELTSRecord,
                event_type: str, evidence: str = "") -> None:
        self.store.create_notification(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, user_id=record.owner_id,
            type=event_type, title=title[:200], summary=summary[:500], severity="info",
            actor=f"user:{ctx.user_id}", related_object=record.record_id,
            related_type=record.record_type, evidence=evidence[:500],
            dedupe_key=f"{event_type}:{record.record_id}:{record.version}",
        )

    def _create(self, ctx, *, record_type: str, status: str, body: dict,
                permission: PlatformPermission, idempotency_key: str = "",
                owner_id: str = "") -> IELTSRecord:
        self._human(ctx)
        ctx.require_permission(permission)
        rec = self.repo.create(
            record_type=record_type, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            owner_id=owner_id or ctx.user_id, project_id=getattr(ctx, "project_id", ""),
            mission_id=getattr(ctx, "mission_id", ""), status=status, body=body,
            idempotency_key=idempotency_key,
        )
        self.repo.evidence(record=rec, event_type=f"{record_type}.created",
                           summary=f"{record_type} created")
        self._audit(ctx, f"ielts.{record_type}.created", record=rec)
        return rec

    def get(self, ctx, record_id: str) -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        rec = self.repo.get(record_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not rec:
            raise PlatformContextError("NOT_FOUND", "IELTS record not found")
        if rec.owner_id != ctx.user_id and ctx.role not in ("owner", "admin"):
            raise PlatformContextError("NOT_FOUND", "IELTS record not found")
        return rec.to_public()

    def list(self, ctx, *, record_type: str = "", all_owners: bool = False, limit: int = 200) -> list[dict]:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        owner = "" if (all_owners and ctx.role in ("owner", "admin")) else ctx.user_id
        return [x.to_public() for x in self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, record_type=record_type,
            owner_id=owner, limit=limit,
        )]

    def upsert_profile(self, ctx, body: dict, *, idempotency_key: str = "") -> dict:
        profiles = self.repo.list(org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                  record_type="profile", owner_id=ctx.user_id, limit=1)
        validated = validate_profile(body)
        if profiles:
            self._human(ctx)
            ctx.require_permission(PlatformPermission.IELTS_PROFILE_MANAGE)
            rec = self.repo.transition(profiles[0], status="active", body_updates=validated)
            self.repo.evidence(record=rec, event_type="profile.updated", summary="Learner profile updated")
            self._audit(ctx, "ielts.profile.updated", record=rec)
            return rec.to_public()
        return self._create(
            ctx, record_type="profile", status="active", body=validated,
            permission=PlatformPermission.IELTS_PROFILE_MANAGE,
            idempotency_key=idempotency_key,
        ).to_public()

    def create_goal(self, ctx, body: dict, *, idempotency_key: str = "") -> dict:
        rec = self._create(
            ctx, record_type="goal", status="active", body=validate_goal(body),
            permission=PlatformPermission.IELTS_GOAL_MANAGE, idempotency_key=idempotency_key,
        )
        return rec.to_public()

    def create_practice(self, ctx, body: dict, *, idempotency_key: str = "") -> dict:
        practice = validate_practice(body)
        skill = practice["skill"]
        rec_type = "submission" if skill in ("writing", "speaking") else "practice"
        permission = (PlatformPermission.IELTS_SUBMISSION_CREATE
                      if rec_type == "submission" else PlatformPermission.IELTS_PRACTICE_CREATE)
        feedback: dict[str, Any]
        if skill == "writing":
            feedback = self.scorer.score_writing(
                prompt=practice["prompt"], response=practice["response"],
                task_type=practice["task_type"],
            )
        elif skill == "speaking":
            feedback = self.scorer.score_speaking(
                prompt=practice["prompt"], transcript=practice["response"],
                part=practice["task_type"], has_audio=bool(practice["artifact_ref"]),
            )
        else:
            answers = [x.strip() for x in practice["response"].split(",") if x.strip()]
            feedback = {
                "label": "deterministic practice result", "official": False,
                "source": "local_answer_record_v1", "answers_recorded": len(answers),
                "limitations": ["No copyrighted answer key or official IELTS score is used."],
            }
        rec = self._create(
            ctx, record_type=rec_type, status="feedback_ready",
            body={**practice, "feedback": feedback, "scoring_state": "completed_local"},
            permission=permission, idempotency_key=idempotency_key,
        )
        ev = self.repo.evidence(
            record=rec, event_type="feedback.ready",
            summary=f"{skill.title()} practice feedback ready",
            evidence_ref=practice.get("artifact_ref", ""),
        )
        self._notify(ctx, title="IELTS practice feedback ready",
                     summary=f"{skill.title()} practice has local indicative feedback.",
                     record=rec, event_type="ielts.feedback_ready", evidence=ev["event_id"])
        return rec.to_public()

    def create_alert(self, ctx, body: dict, *, idempotency_key: str = "") -> dict:
        rec = self._create(
            ctx, record_type="availability_alert", status=AlertStatus.ACTIVE.value,
            body=validate_alert(body), permission=PlatformPermission.IELTS_ALERT_MANAGE,
            idempotency_key=idempotency_key,
        )
        return rec.to_public()

    def transition_alert(self, ctx, alert_id: str, status: str) -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_ALERT_MANAGE)
        rec = self.repo.get(alert_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not rec or rec.record_type != "availability_alert" or rec.owner_id != ctx.user_id:
            raise PlatformContextError("NOT_FOUND", "availability alert not found")
        source, target = AlertStatus(rec.status), AlertStatus(status)
        if target not in ALERT_TRANSITIONS[source]:
            raise PlatformContextError("VALIDATION_FAILED", f"illegal alert transition {source.value}->{target.value}")
        updated = self.repo.transition(rec, status=target.value)
        self.repo.evidence(record=updated, event_type="alert.transition",
                           summary=f"Alert {source.value} to {target.value}")
        self._audit(ctx, "ielts.alert.transition", record=updated,
                    detail={"from": source.value, "to": target.value})
        return updated.to_public()

    def evaluate_alerts(self, ctx) -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_ALERT_MANAGE)
        alerts = self.repo.list(org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                record_type="availability_alert", owner_id=ctx.user_id)
        matches = []
        for alert in alerts:
            if alert.status != AlertStatus.ACTIVE.value:
                continue
            preferred = {x.lower() for x in alert.body["preferred_locations"]}
            for center in LOCAL_CENTERS:
                if center["location"].lower() not in preferred:
                    continue
                dates = [d for d in center["dates"] if alert.body["date_from"] <= d <= alert.body["date_to"]]
                if not dates:
                    continue
                match = self.repo.create(
                    record_type="alert_match", org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                    owner_id=ctx.user_id, status="fixture_match",
                    body={"alert_id": alert.record_id, "center": center, "matching_dates": dates,
                          "source": "local_fixture", "live_availability": False,
                          "notice": "Fixture data only; verify with an official test provider."},
                    idempotency_key=f"{alert.record_id}:{center['center_id']}:{','.join(dates)}",
                )
                matches.append(match.to_public())
                updated = self.repo.transition(alert, status=AlertStatus.MATCHED.value)
                ev = self.repo.evidence(record=updated, event_type="alert.fixture_match",
                                        summary="Fixture availability match recorded")
                self._notify(ctx, title="IELTS fixture availability match",
                             summary="A local fixture matched your alert; this is not live availability.",
                             record=updated, event_type="ielts.alert_match", evidence=ev["event_id"])
                break
        self._audit(ctx, "ielts.alerts.evaluated", detail={"matches": len(matches), "source": "local_fixture"})
        return {"matches": matches, "source": "local_fixture", "live_availability": False}

    def submit_payment(self, ctx, body: dict, *, idempotency_key: str = "") -> dict:
        rec = self._create(
            ctx, record_type="payment", status=PaymentStatus.SUBMITTED.value,
            body=validate_payment(body), permission=PlatformPermission.IELTS_PAYMENT_SUBMIT,
            idempotency_key=idempotency_key,
        )
        ev = self.repo.evidence(record=rec, event_type="payment.submitted",
                                summary="Manual payment evidence submitted",
                                evidence_ref=rec.body["evidence_ref"])
        self._notify(ctx, title="Manual payment submitted",
                     summary="Your evidence is awaiting authorized human review.", record=rec,
                     event_type="ielts.payment_submitted", evidence=ev["event_id"])
        return rec.to_public()

    def review_payment(self, ctx, payment_id: str, *, approve: bool, reason: str) -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_PAYMENT_REVIEW)
        reason = str(reason or "").strip()
        if not reason or len(reason) > 1000:
            raise PlatformContextError("VALIDATION_FAILED", "bounded review reason is required")
        rec = self.repo.get(payment_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not rec or rec.record_type != "payment":
            raise PlatformContextError("NOT_FOUND", "payment submission not found")
        if rec.owner_id == ctx.user_id:
            raise PlatformContextError("PERMISSION_DENIED", "self-approval is prohibited")
        if rec.status == PaymentStatus.SUBMITTED.value:
            rec = self.repo.transition(rec, status=PaymentStatus.UNDER_REVIEW.value,
                                       body_updates={"reviewer_id": ctx.user_id})
        target = PaymentStatus.APPROVED if approve else PaymentStatus.REJECTED
        source = PaymentStatus(rec.status)
        if target not in PAYMENT_TRANSITIONS[source]:
            if source == target:
                return rec.to_public()
            raise PlatformContextError("VALIDATION_FAILED", f"illegal payment transition {source.value}->{target.value}")
        updated = self.repo.transition(
            rec, status=target.value,
            body_updates={"reviewer_id": ctx.user_id, "review_reason": reason,
                          "settlement_performed": False},
        )
        ev = self.repo.evidence(record=updated, event_type=f"payment.{target.value}",
                                summary=f"Manual payment {target.value}")
        self._notify(ctx, title=f"Manual payment {target.value}",
                     summary="An authorized human completed manual verification; no settlement was performed.",
                     record=updated, event_type=f"ielts.payment_{target.value}", evidence=ev["event_id"])
        self._audit(ctx, "ielts.payment.reviewed", record=updated,
                    detail={"decision": target.value, "self_review": False})
        return updated.to_public()

    def evidence_timeline(self, ctx, *, all_owners: bool = False) -> list[dict]:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        owner = "" if (all_owners and ctx.role in ("owner", "admin")) else ctx.user_id
        return self.repo.timeline(org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=owner)

    def dashboard(self, ctx) -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        records = self.repo.list(org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                 owner_id=ctx.user_id, limit=500)
        latest_goal = next((x for x in records if x.record_type == "goal"), None)
        practices = [x for x in records if x.record_type in ("practice", "submission")]
        alerts = [x for x in records if x.record_type == "availability_alert"
                  and x.status in ("active", "matched", "notified")]
        payments = [x for x in records if x.record_type == "payment"
                    and x.status in ("submitted", "under_review")]
        by_skill = {skill: sum(x.body.get("skill") == skill for x in practices)
                    for skill in ("reading", "listening", "writing", "speaking")}
        return {
            "goal": latest_goal.to_public() if latest_goal else None,
            "next_practice": min(by_skill, key=by_skill.get) if practices else "reading",
            "progress": {"practice_count": len(practices), "by_skill": by_skill},
            "active_alerts": len(alerts), "pending_payments": len(payments),
            "scoring": {"default": "local_heuristic_v1", "provider_assisted": False,
                        "official_scoring": False, "health": self.scorer.health()},
            "availability": {"source": "local_fixture", "live": False},
            "manual_payment_only": True,
            "generated_on": date.today().isoformat(),
        }

    def search(self, ctx, query: str, *, limit: int = 50) -> list[dict]:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        needle = str(query or "").strip().lower()[:100]
        if not needle:
            return []
        records = self.repo.list(org_id=ctx.org_id, workspace_id=ctx.workspace_id,
                                 owner_id=ctx.user_id, limit=500)
        found = []
        for rec in records:
            haystack = f"{rec.record_type} {rec.status} {rec.body}".lower()
            if needle in haystack:
                found.append({"record_id": rec.record_id, "record_type": rec.record_type,
                              "status": rec.status, "updated_at": rec.updated_at})
            if len(found) >= max(1, min(limit, 100)):
                break
        return found

    def health(self, ctx) -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        return {
            "status": "healthy", "persistence": "single_host_sqlite",
            "scoring": self.scorer.health(), "provider_assisted_scoring": False,
            "availability_provider": "local_fixture", "external_notifications": False,
            "payment_mode": "manual_verification",
        }
