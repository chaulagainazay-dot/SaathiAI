"""Structured objective intake with ambiguity detection."""
from __future__ import annotations

from typing import Any

from .models import (
    MAX_OBJECTIVE_CHARS,
    ObjectiveIntake,
    RiskLevel,
    reject_secrets,
)
from .templates import infer_template


def _clip(value: Any, maximum: int) -> str:
    return str(value or "").strip()[:maximum]


class ObjectiveIntakeService:
    def parse(self, payload: dict[str, Any], *, ctx=None) -> ObjectiveIntake:
        if not isinstance(payload, dict):
            raise ValueError("intake payload must be an object")
        objective = reject_secrets(
            _clip(payload.get("objective") or payload.get("goal"), MAX_OBJECTIVE_CHARS),
            field="objective",
        )
        if not objective:
            raise ValueError("objective is required")

        risk = str(payload.get("risk_level") or RiskLevel.MEDIUM.value).lower()
        if risk not in {r.value for r in RiskLevel}:
            risk = RiskLevel.MEDIUM.value

        domain = _clip(payload.get("domain") or "engineering", 40).lower()
        template_id = _clip(payload.get("template_id"), 80)
        if not template_id:
            template_id = infer_template(objective, domain)

        intake = ObjectiveIntake(
            objective=objective,
            expected_outcome=_clip(payload.get("expected_outcome"), 2000),
            scope=_clip(payload.get("scope"), 2000),
            exclusions=_clip(payload.get("exclusions"), 2000),
            project_id=_clip(
                payload.get("project_id") or getattr(ctx, "project_id", ""), 160
            ),
            mission_id=_clip(payload.get("mission_id"), 160),
            workspace_id=_clip(
                payload.get("workspace_id") or getattr(ctx, "workspace_id", ""), 160
            ),
            tenant_id=_clip(
                payload.get("tenant_id") or getattr(ctx, "org_id", ""), 160
            ),
            risk_level=risk,
            budget_constraints=_clip(payload.get("budget_constraints"), 500),
            time_constraints=_clip(payload.get("time_constraints"), 500),
            production_impact=bool(payload.get("production_impact", False)),
            credential_requirements=bool(payload.get("credential_requirements", False)),
            external_dependencies=_clip(payload.get("external_dependencies"), 1000),
            success_criteria=_clip(payload.get("success_criteria"), 2000),
            stop_conditions=_clip(payload.get("stop_conditions"), 1000),
            domain=domain,
            template_id=template_id,
        )
        intake.ambiguities = self._detect_ambiguities(intake)
        intake.missing_required = self._missing_required(intake)
        # High-impact constraints must not be invented
        if intake.production_impact and not intake.success_criteria:
            intake.ambiguities.append(
                "production_impact set without explicit success criteria"
            )
        if intake.credential_requirements:
            intake.missing_required.append(
                "credential_requirements cannot be satisfied in this local-only runtime"
            )
        return intake

    def _detect_ambiguities(self, intake: ObjectiveIntake) -> list[str]:
        amb: list[str] = []
        o = intake.objective.lower()
        vague = ("make it better", "fix everything", "do whatever", "somehow", "maybe")
        if any(v in o for v in vague):
            amb.append("objective is vague; prefer concrete outcome language")
        if len(intake.objective) < 12:
            amb.append("objective is very short; may need more detail")
        if "production" in o and not intake.production_impact:
            amb.append("mentions production but production_impact flag is false")
        if not intake.scope and ("all" in o or "entire" in o):
            amb.append("broad scope language without explicit scope field")
        return amb[:10]

    def _missing_required(self, intake: ObjectiveIntake) -> list[str]:
        missing: list[str] = []
        # Project is preferred but can be created later; not hard-required for draft
        if intake.risk_level == RiskLevel.CRITICAL.value and not intake.success_criteria:
            missing.append("success_criteria required for critical risk")
        return missing
