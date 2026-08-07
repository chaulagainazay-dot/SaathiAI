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
            "app_id": "saathi.ielts_alert",
            "production_authorized": False,
            "live_gemini": False,
            "live_firebase": False,
            "official_ielts_scoring": False,
            "local_only": True,
        }

    # ── M139+ productization: diagnostic, plan, mock, readiness, coaching ──

    def content_catalog(self, ctx, *, exam_type: str = "academic") -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        from saathi.platform.ielts import content as c

        et = exam_type if exam_type in ("academic", "general_training") else "academic"
        return {
            "speaking": c.speaking_prompts(),
            "writing": c.writing_prompts(exam_type=et),
            "reading": c.reading_fixture(exam_type=et),
            "listening": c.listening_fixture(),
            "label": c.CONTENT_LABEL,
            "rubric_version": c.RUBRIC_VERSION,
            "scoring_version": c.SCORING_VERSION,
            "official_content": False,
        }

    def run_diagnostic(self, ctx, *, exam_type: str = "academic",
                       idempotency_key: str = "") -> dict:
        """Bounded four-skill diagnostic using synthetic fixtures."""
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_PRACTICE_CREATE)
        from saathi.platform.ielts import content as c

        et = exam_type if exam_type in ("academic", "general_training") else "academic"
        if idempotency_key:
            existing = self.repo.find_idempotent(
                org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=ctx.user_id,
                record_type="diagnostic", idempotency_key=idempotency_key,
            )
            if existing:
                return existing.to_public()

        attempts = []
        # Speaking (text-only)
        sp = c.speaking_prompts()[0]
        sp_fb = self.scorer.score_speaking(
            prompt=sp["prompt"],
            transcript="My hometown is quiet and friendly. I enjoy the parks and local markets.",
            part=sp["part"], has_audio=False,
        )
        attempts.append({"skill": "speaking", "feedback": sp_fb, "prompt_id": sp["prompt_id"]})
        # Writing
        wr = c.writing_prompts(exam_type=et)[0]
        sample = (
            "The information shows growth over time. Overall, access increased in all regions. "
            "The largest change appeared after 2015. In conclusion, connectivity expanded."
        )
        wr_fb = self.scorer.score_writing(prompt=wr["prompt"], response=sample, task_type=wr["task"])
        attempts.append({"skill": "writing", "feedback": wr_fb, "prompt_id": wr["prompt_id"]})
        # Reading
        rd = c.reading_fixture(exam_type=et)
        answers = [q["answer"] for q in rd["questions"]]
        # intentionally leave last unanswered to exercise incompleteness
        rd_answers = answers[:-1] + [""]
        rd_fb = self.scorer.score_objective(
            skill="reading", exam_type=et, answers=rd_answers, key=rd["questions"],
        )
        attempts.append({"skill": "reading", "feedback": rd_fb, "passage_id": rd["passage_id"]})
        # Listening
        ls = c.listening_fixture()
        ls_answers = [q["answer"] for q in ls["questions"]]
        ls_fb = self.scorer.score_objective(
            skill="listening", exam_type=et, answers=ls_answers, key=ls["questions"],
        )
        attempts.append({"skill": "listening", "feedback": ls_fb, "section_id": ls["section_id"]})

        skill_bands = {}
        for a in attempts:
            fb = a["feedback"]
            skill_bands[a["skill"]] = fb.get("estimated_overall_band")
        present = [v for v in skill_bands.values() if isinstance(v, (int, float))]
        overall = round(sum(present) / len(present) * 2) / 2 if present else None
        weak = min(
            ((k, v) for k, v in skill_bands.items() if isinstance(v, (int, float))),
            key=lambda x: x[1],
            default=("reading", None),
        )[0]
        body = {
            "exam_type": et,
            "attempts": attempts,
            "skill_estimates": skill_bands,
            "overall_estimate": overall,
            "strongest_skill": max(
                ((k, v) for k, v in skill_bands.items() if isinstance(v, (int, float))),
                key=lambda x: x[1],
                default=("listening", None),
            )[0],
            "weakest_skill": weak,
            "priorities": [weak, "writing" if weak != "writing" else "speaking"],
            "recommended_daily_minutes": 45,
            "confidence": 0.4,
            "confidence_label": "low–moderate; short diagnostic with fixtures",
            "missing_data_warnings": ["Diagnostic uses short synthetic tasks only."],
            "official": False,
            "label": "demo/certification diagnostic",
            "rubric_version": c.RUBRIC_VERSION,
            "scoring_version": c.SCORING_VERSION,
        }
        rec = self._create(
            ctx, record_type="diagnostic", status="completed", body=body,
            permission=PlatformPermission.IELTS_PRACTICE_CREATE,
            idempotency_key=idempotency_key,
        )
        return rec.to_public()

    def generate_study_plan(self, ctx, *, weeks: int = 4, idempotency_key: str = "") -> dict:
        """Deterministic personalized plan from goal + latest diagnostic."""
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_GOAL_MANAGE)
        goals = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            record_type="goal", owner_id=ctx.user_id, limit=5,
        )
        diags = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            record_type="diagnostic", owner_id=ctx.user_id, limit=5,
        )
        goal = goals[0] if goals else None
        diag = diags[0] if diags else None
        daily = int((goal.body if goal else {}).get("daily_minutes") or 30)
        weak = (diag.body if diag else {}).get("weakest_skill") or "writing"
        exam_type = (goal.body if goal else {}).get("exam_type") or "academic"
        target = (goal.body if goal else {}).get("target_band") or 6.5
        weeks = max(1, min(int(weeks), 12))
        tasks = []
        skills_cycle = [weak, "reading", "listening", "writing", "speaking"]
        # ensure all four skills appear
        for w in range(1, weeks + 1):
            for day in range(1, 6):  # weekdays
                skill = skills_cycle[(w + day) % len(skills_cycle)]
                minutes = min(daily, 60 if skill == weak else max(15, daily // 2))
                tasks.append({
                    "week": w,
                    "day": day,
                    "skill": skill,
                    "minutes": minutes,
                    "task": f"Practice {skill} — focus {weak if skill == weak else 'balanced review'}",
                    "priority": skill == weak,
                })
            tasks.append({
                "week": w, "day": 6, "skill": "review", "minutes": 20,
                "task": "Review feedback and vocabulary notes", "priority": False,
            })
            tasks.append({
                "week": w, "day": 7, "skill": "rest", "minutes": 0,
                "task": "Rest / light reading", "priority": False,
            })
        total_minutes = sum(t["minutes"] for t in tasks)
        weekly_cap = daily * 7 * weeks
        valid = total_minutes <= weekly_cap + 60  # small slack
        body = {
            "exam_type": exam_type,
            "target_band": target,
            "weeks": weeks,
            "daily_minutes": daily,
            "weakest_skill": weak,
            "tasks": tasks,
            "total_minutes": total_minutes,
            "validation": {
                "within_time_budget": valid,
                "covers_four_skills": True,
                "includes_rest": True,
                "prioritizes_weak_areas": True,
                "deterministic": True,
            },
            "reasoning": f"Prioritize {weak}; target band {target}; {daily} min/day budget.",
            "plan_validator": "local_deterministic_v1",
            "orchestration_subject_to_plan_validator": True,
            "official": False,
            "label": "demo/certification study plan",
            "status_note": "pause/resume/replan supported by creating a new plan record",
        }
        if not valid:
            raise PlatformContextError("PLAN_INVALID", "study plan exceeds available time")
        rec = self._create(
            ctx, record_type="study_plan", status="active", body=body,
            permission=PlatformPermission.IELTS_GOAL_MANAGE,
            idempotency_key=idempotency_key,
        )
        return rec.to_public()

    def submit_objective_practice(
        self, ctx, *, skill: str, exam_type: str, answers: list,
        idempotency_key: str = "",
    ) -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_PRACTICE_CREATE)
        from saathi.platform.ielts import content as c

        skill = skill if skill in ("reading", "listening") else "reading"
        et = exam_type if exam_type in ("academic", "general_training") else "academic"
        fixture = c.listening_fixture() if skill == "listening" else c.reading_fixture(exam_type=et)
        key = fixture["questions"]
        feedback = self.scorer.score_objective(
            skill=skill, exam_type=et, answers=list(answers or []), key=key,
        )
        body = {
            "skill": skill,
            "task_type": "objective_fixture",
            "exam_type": et,
            "prompt": fixture.get("title") or fixture.get("passage_id") or fixture.get("section_id"),
            "response": ",".join(str(a) for a in (answers or [])),
            "answers": list(answers or [])[:20],
            "feedback": feedback,
            "fixture_id": fixture.get("passage_id") or fixture.get("section_id"),
            "modality": fixture.get("modality", "text"),
            "audio_available": fixture.get("audio_available", False),
            "scoring_state": "completed_local",
            "label": c.CONTENT_LABEL,
        }
        rec = self._create(
            ctx, record_type="practice", status="feedback_ready", body=body,
            permission=PlatformPermission.IELTS_PRACTICE_CREATE,
            idempotency_key=idempotency_key,
        )
        return rec.to_public()

    def submit_writing_revision(
        self, ctx, *, parent_submission_id: str, response: str,
        idempotency_key: str = "",
    ) -> dict:
        """Create a linked revision attempt; never overwrite the original."""
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_SUBMISSION_CREATE)
        parent = self.repo.get(
            parent_submission_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id,
        )
        if not parent or parent.record_type != "submission":
            raise PlatformContextError("NOT_FOUND", "parent submission not found")
        if parent.owner_id != ctx.user_id and ctx.role not in ("owner", "admin"):
            raise PlatformContextError("NOT_FOUND", "parent submission not found")
        # immutability: original body unchanged
        practice = {
            "skill": "writing",
            "task_type": (parent.body or {}).get("task_type") or "task_2",
            "prompt": (parent.body or {}).get("prompt") or "",
            "response": str(response or "")[:12000],
            "duration_seconds": 0,
            "artifact_ref": "",
            "transcript_ref": "",
            "parent_submission_id": parent.record_id,
            "is_revision": True,
        }
        feedback = self.scorer.score_writing(
            prompt=practice["prompt"], response=practice["response"],
            task_type=practice["task_type"],
        )
        rec = self._create(
            ctx, record_type="submission", status="feedback_ready",
            body={**practice, "feedback": feedback, "scoring_state": "completed_local"},
            permission=PlatformPermission.IELTS_SUBMISSION_CREATE,
            idempotency_key=idempotency_key,
        )
        # parent remains unchanged
        return {"revision": rec.to_public(), "parent_id": parent.record_id, "parent_immutable": True}

    def create_mock_test(self, ctx, *, exam_type: str = "academic",
                         idempotency_key: str = "") -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_PRACTICE_CREATE)
        et = exam_type if exam_type in ("academic", "general_training") else "academic"
        body = {
            "exam_type": et,
            "sections": [
                {"skill": "listening", "status": "pending"},
                {"skill": "reading", "status": "pending"},
                {"skill": "writing", "status": "pending"},
                {"skill": "speaking", "status": "pending"},
            ],
            "status": "in_progress",
            "official": False,
            "label": "demo/certification mock test",
        }
        rec = self._create(
            ctx, record_type="mock_test", status="in_progress", body=body,
            permission=PlatformPermission.IELTS_PRACTICE_CREATE,
            idempotency_key=idempotency_key,
        )
        return rec.to_public()

    def complete_mock_section(
        self, ctx, mock_id: str, *, skill: str, answers: list | None = None,
        response: str = "",
    ) -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_PRACTICE_CREATE)
        rec = self.repo.get(mock_id, org_id=ctx.org_id, workspace_id=ctx.workspace_id)
        if not rec or rec.record_type != "mock_test" or rec.owner_id != ctx.user_id:
            raise PlatformContextError("NOT_FOUND", "mock test not found")
        skill = skill if skill in ("reading", "listening", "writing", "speaking") else "reading"
        et = (rec.body or {}).get("exam_type") or "academic"
        section_result: dict
        if skill in ("reading", "listening"):
            section_result = self.submit_objective_practice(
                ctx, skill=skill, exam_type=et, answers=answers or [],
                idempotency_key=f"mock:{mock_id}:{skill}",
            )
        else:
            section_result = self.create_practice(
                ctx,
                {
                    "skill": skill,
                    "task_type": "task_2" if skill == "writing" else "part_1",
                    "prompt": f"Mock {skill} prompt",
                    "response": response or "Mock practice response with enough words to score. " * 8,
                    "duration_seconds": 60,
                },
                idempotency_key=f"mock:{mock_id}:{skill}",
            )
        sections = list((rec.body or {}).get("sections") or [])
        for s in sections:
            if s.get("skill") == skill:
                s["status"] = "completed"
                s["result_id"] = section_result.get("record_id")
        all_done = all(s.get("status") == "completed" for s in sections)
        updated = self.repo.transition(
            rec,
            status="completed" if all_done else "in_progress",
            body_updates={"sections": sections},
        )
        return {"mock_test": updated.to_public(), "section": section_result}

    def readiness_snapshot(self, ctx) -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        records = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=ctx.user_id, limit=500,
        )
        practices = [x for x in records if x.record_type in ("practice", "submission", "diagnostic")]
        goals = [x for x in records if x.record_type == "goal"]
        diags = [x for x in records if x.record_type == "diagnostic"]
        by_skill = {"reading": [], "listening": [], "writing": [], "speaking": []}
        for p in practices:
            skill = (p.body or {}).get("skill")
            band = ((p.body or {}).get("feedback") or {}).get("estimated_overall_band")
            if skill in by_skill and isinstance(band, (int, float)):
                by_skill[skill].append(float(band))
        skill_means = {
            k: (round(sum(v) / len(v) * 2) / 2 if v else None) for k, v in by_skill.items()
        }
        present = [v for v in skill_means.values() if v is not None]
        overall = round(sum(present) / len(present) * 2) / 2 if present else None
        target = (goals[0].body if goals else {}).get("target_band")
        gap = (float(target) - overall) if (target is not None and overall is not None) else None
        insufficient = len(present) < 2
        confidence = 0.25 if insufficient else min(0.75, 0.35 + 0.05 * len(practices))
        weak = None
        if present:
            weak = min(
                ((k, v) for k, v in skill_means.items() if v is not None),
                key=lambda x: x[1],
            )[0]
        snap = {
            "skill_estimates": skill_means,
            "overall_estimate": overall,
            "target_band": target,
            "gap_to_target": gap,
            "weakest_skill": weak,
            "practice_count": len(practices),
            "has_diagnostic": bool(diags),
            "insufficient_data": insufficient,
            "confidence": confidence,
            "confidence_label": "low" if insufficient else "moderate",
            "official": False,
            "readiness_label": (
                "insufficient_data" if insufficient
                else ("approaching_target" if gap is not None and gap <= 0.5 else "needs_work")
            ),
            "recommendations": [
                f"Focus practice on {weak}" if weak else "Complete a diagnostic assessment",
                "Review writing revisions weekly",
                "Schedule one timed mock test",
            ],
            "label": "indicative readiness — not official IELTS",
        }
        # persist snapshot
        rec = self.repo.create(
            record_type="readiness_snapshot", org_id=ctx.org_id, workspace_id=ctx.workspace_id,
            owner_id=ctx.user_id, status="ready", body=snap,
            idempotency_key=f"ready:{ctx.user_id}:{int(self.store._now()) // 3600}",
        )
        return {"snapshot": rec.to_public(), "data": snap}

    def grounded_answer(self, ctx, question: str) -> dict:
        """Yeti/Conversation read-only coaching answers — never mutates assessments."""
        ctx.require_permission(PlatformPermission.IELTS_READ)
        q = (question or "").lower()
        dash = self.dashboard(ctx)
        ready = self.readiness_snapshot(ctx)["data"]
        facts = []
        if "readiness" in q or "ready" in q:
            answer = (
                f"Indicative readiness: {ready.get('readiness_label')}. "
                f"Overall estimate {ready.get('overall_estimate')} vs target {ready.get('target_band')}. "
                "This is not an official IELTS result."
            )
            facts.append(ready)
        elif "weak" in q:
            answer = f"Weakest skill estimate: {ready.get('weakest_skill')}. Focus practice there first."
            facts.append({"weakest_skill": ready.get("weakest_skill")})
        elif "plan" in q or "study" in q:
            plans = [r for r in self.list(ctx, record_type="study_plan") if r]
            answer = (
                f"You have {len(plans)} study plan record(s). "
                "Plans are deterministic and validated against your daily minutes budget."
            )
            facts.append({"plan_count": len(plans)})
        elif "score" in q or "band" in q:
            answer = (
                f"Practice progress: {dash['progress']['practice_count']} attempts. "
                "All bands are estimates with rubric/scoring versions — never official."
            )
            facts.append(dash["progress"])
        else:
            answer = (
                "I can help with readiness, weak skills, study plans, and practice feedback. "
                "I cannot change assessment records or claim official IELTS scores."
            )
        return {
            "answer": answer,
            "facts": facts,
            "can_mutate": False,
            "mutable": False,
            "official": False,
            "source": "IELTSService.grounded_answer",
            "knowledge_posture": "scoped_local_curriculum_label",
        }

    def propose_action(self, ctx, *, action: str, payload: dict | None = None) -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        return {
            "proposal": {
                "action": action,
                "payload": payload or {},
                "requires_confirmation": True,
                "executed": False,
            },
            "note": "Conversation/Yeti cannot directly mutate assessment records.",
        }

    def export_backup_payload(self, ctx) -> dict:
        ctx.require_permission(PlatformPermission.IELTS_READ)
        records = self.repo.list(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=ctx.user_id, limit=500,
        )
        evidence = self.repo.timeline(
            org_id=ctx.org_id, workspace_id=ctx.workspace_id, owner_id=ctx.user_id, limit=500,
        )
        import hashlib, json
        data = {
            "records": [r.to_public() for r in records],
            "evidence": evidence,
            "record_count": len(records),
            "evidence_count": len(evidence),
        }
        blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(blob).hexdigest()
        self._audit(ctx, "ielts.backup.exported", detail={"hash": digest, "records": len(records)})
        return {
            "schema_version": "ielts.backup.v1",
            "app_id": "saathi.ielts_alert",
            "org_id": ctx.org_id,
            "workspace_id": ctx.workspace_id,
            "owner_id": ctx.user_id,
            "content_hash": digest,
            "data": data,
            "created_at": self.store._now(),
            "production": False,
        }

    def restore_payload(self, ctx, payload: dict, *, approval_reference: str = "") -> dict:
        """Restore learner records requires approval when overwriting."""
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_ADMIN)
        if not approval_reference:
            raise PlatformContextError("APPROVAL_REQUIRED", "IELTS restore requires approval")
        if payload.get("org_id") and payload["org_id"] != ctx.org_id:
            raise PlatformContextError("RESTORE_SCOPE", "org mismatch")
        if payload.get("workspace_id") and payload["workspace_id"] != ctx.workspace_id:
            raise PlatformContextError("RESTORE_SCOPE", "workspace mismatch")
        import hashlib, json
        data = payload.get("data") or {}
        blob = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(blob).hexdigest()
        if payload.get("content_hash") and payload["content_hash"] != digest:
            raise PlatformContextError("INTEGRITY_MISMATCH", "content hash mismatch")
        # Soft restore: re-create missing records by idempotency where possible
        restored = 0
        for raw in data.get("records") or []:
            try:
                self.repo.create(
                    record_type=raw["record_type"],
                    org_id=ctx.org_id,
                    workspace_id=ctx.workspace_id,
                    owner_id=ctx.user_id,
                    status=raw.get("status") or "active",
                    body=raw.get("body") or {},
                    idempotency_key=raw.get("idempotency_key") or f"restore:{raw.get('record_id')}",
                )
                restored += 1
            except Exception:
                continue
        self._audit(ctx, "ielts.restore.applied", detail={"restored": restored, "hash": digest})
        return {"restored": restored, "content_hash": digest, "evidence_preserved": True}

    def create_reminder(self, ctx, *, title: str, due_date: str = "",
                        kind: str = "study", idempotency_key: str = "") -> dict:
        self._human(ctx)
        ctx.require_permission(PlatformPermission.IELTS_ALERT_MANAGE)
        from saathi.platform.ielts.models import bounded
        body = {
            "title": bounded(title, "title", maximum=200, required=True),
            "due_date": bounded(due_date or date.today().isoformat(), "due_date", maximum=10),
            "kind": bounded(kind, "kind", maximum=40),
            "label": "demo/certification reminder",
        }
        rec = self._create(
            ctx, record_type="reminder", status="active", body=body,
            permission=PlatformPermission.IELTS_ALERT_MANAGE,
            idempotency_key=idempotency_key,
        )
        self._notify(
            ctx, title=body["title"], summary=f"Reminder scheduled for {body['due_date']}",
            record=rec, event_type="ielts.reminder",
        )
        return rec.to_public()

    def product_dashboard(self, ctx) -> dict:
        """Extended readiness-oriented dashboard for native app surface."""
        base = self.dashboard(ctx)
        ready = self.readiness_snapshot(ctx)["data"]
        plans = self.list(ctx, record_type="study_plan")
        mocks = self.list(ctx, record_type="mock_test")
        diags = self.list(ctx, record_type="diagnostic")
        return {
            **base,
            "readiness": ready,
            "study_plan_count": len(plans),
            "mock_test_count": len(mocks),
            "diagnostic_count": len(diags),
            "label": "demo/certification data — not official IELTS",
            "official_scoring": False,
            "fabricated": False,
            "app_id": "saathi.ielts_alert",
        }
