"""M257 — Licence policy and governance classification. Fail-closed."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.market_data.errors import LICENCE_FORBIDDEN, LICENCE_GATE_FAILED, LICENCE_UNKNOWN, MarketDataError
from saathi.platform.tg.market_data.models import AUTHORITY_VALUES, LEGAL_REVIEW_REQUIRED, DatasetState, GovernanceClass
from saathi.platform.tg.market_data.storage import MarketDataStore, evidence_hash, _uid

# Known licence → governance mapping (not legal advice)
LICENCE_MAP = {
    "CC0-1.0": {
        "governance": GovernanceClass.OPEN_RESEARCH_USE.value,
        "commercial_use": "permitted",
        "redistribution": "permitted",
        "modification": "permitted",
        "attribution_required": False,
    },
    "CC-BY-4.0": {
        "governance": GovernanceClass.ATTRIBUTION_REQUIRED.value,
        "commercial_use": "permitted",
        "redistribution": "permitted",
        "modification": "permitted",
        "attribution_required": True,
    },
    "CC-BY-NC-4.0": {
        "governance": GovernanceClass.NON_COMMERCIAL_ONLY.value,
        "commercial_use": "forbidden",
        "redistribution": "permitted_non_commercial",
        "modification": "permitted",
        "attribution_required": True,
    },
    "ODC-BY-1.0": {
        "governance": GovernanceClass.ATTRIBUTION_REQUIRED.value,
        "commercial_use": "permitted",
        "redistribution": "permitted",
        "modification": "permitted",
        "attribution_required": True,
    },
    "INTERNAL_ONLY": {
        "governance": GovernanceClass.INTERNAL_RESEARCH_ONLY.value,
        "commercial_use": "internal_only",
        "redistribution": "forbidden",
        "modification": "internal_only",
        "attribution_required": True,
    },
    "PROPRIETARY_NO_REDISTRIBUTION": {
        "governance": GovernanceClass.NO_REDISTRIBUTION.value,
        "commercial_use": "restricted",
        "redistribution": "forbidden",
        "modification": "restricted",
        "attribution_required": True,
    },
    "FORBIDDEN": {
        "governance": GovernanceClass.USE_FORBIDDEN.value,
        "commercial_use": "forbidden",
        "redistribution": "forbidden",
        "modification": "forbidden",
        "attribution_required": True,
    },
    "UNKNOWN": {
        "governance": GovernanceClass.LICENCE_UNCLEAR.value,
        "commercial_use": "unknown",
        "redistribution": "unknown",
        "modification": "unknown",
        "attribution_required": True,
    },
}

USE_CASES = (
    "local_research",
    "internal_product_development",
    "report_generation",
    "chart_generation",
    "derived_feature_storage",
    "redistribution",
    "commercial_use",
    "model_training",
    "user_facing_display",
)


class LicenceEngine:
    def __init__(self, store: MarketDataStore):
        self.store = store

    def record_licence(
        self,
        dataset_id: str,
        dataset_version: str,
        *,
        licence_name: str,
        licence_version: str = "",
        official_source: str = "",
        commercial_use: str | None = None,
        redistribution: str | None = None,
        modification: str | None = None,
        attribution_required: bool | None = None,
        retention_limit: str = "",
        geographic_restriction: str = "",
        usage_restriction: str = "",
        unknown_terms: bool = False,
        legal_review_required: bool | None = None,
    ) -> dict[str, Any]:
        name = (licence_name or "UNKNOWN").strip()
        preset = LICENCE_MAP.get(name) or LICENCE_MAP.get(name.upper()) or LICENCE_MAP["UNKNOWN"]
        if name not in LICENCE_MAP and name.upper() not in LICENCE_MAP and name != "UNKNOWN":
            # Treat unrecognised named licences as needing legal review
            gov = GovernanceClass.LEGAL_REVIEW_REQUIRED.value
            unknown_terms = True
            if legal_review_required is None:
                legal_review_required = True
        else:
            gov = preset["governance"]
            if legal_review_required is None:
                legal_review_required = gov in (
                    GovernanceClass.LICENCE_UNCLEAR.value,
                    GovernanceClass.LEGAL_REVIEW_REQUIRED.value,
                    GovernanceClass.USE_FORBIDDEN.value,
                )

        commercial_use = commercial_use or preset["commercial_use"]
        redistribution = redistribution or preset["redistribution"]
        modification = modification or preset["modification"]
        if attribution_required is None:
            attribution_required = bool(preset["attribution_required"])

        if unknown_terms or name in ("", "UNKNOWN", "unknown"):
            gov = GovernanceClass.LICENCE_UNCLEAR.value
            legal_review_required = True

        if gov == GovernanceClass.USE_FORBIDDEN.value:
            legal_review_required = True

        rec = {
            "id": _uid("lic"),
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "licence_name": name,
            "licence_version": licence_version,
            "official_source": official_source,
            "commercial_use": commercial_use,
            "redistribution": redistribution,
            "modification": modification,
            "attribution_required": 1 if attribution_required else 0,
            "retention_limit": retention_limit,
            "geographic_restriction": geographic_restriction,
            "usage_restriction": usage_restriction,
            "unknown_terms": 1 if unknown_terms else 0,
            "legal_review_required": 1 if legal_review_required else 0,
            "governance_class": gov,
            "detail_json": "{}",
            "evidence_hash": "",
            "created_at": time.time(),
        }
        rec["evidence_hash"] = evidence_hash({k: rec[k] for k in rec if k != "evidence_hash"})
        self.store.execute(
            """INSERT INTO md_licences(
                id, dataset_id, dataset_version, licence_name, licence_version, official_source,
                commercial_use, redistribution, modification, attribution_required, retention_limit,
                geographic_restriction, usage_restriction, unknown_terms, legal_review_required,
                governance_class, detail_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["id"], rec["dataset_id"], rec["dataset_version"], rec["licence_name"],
                rec["licence_version"], rec["official_source"], rec["commercial_use"],
                rec["redistribution"], rec["modification"], rec["attribution_required"],
                rec["retention_limit"], rec["geographic_restriction"], rec["usage_restriction"],
                rec["unknown_terms"], rec["legal_review_required"], rec["governance_class"],
                rec["detail_json"], rec["evidence_hash"], rec["created_at"],
            ),
        )
        # Update dataset licence fields + state
        ds = self.store.get_dataset(dataset_id, dataset_version)
        if ds:
            ds["licence_type"] = name
            ds["redistribution_status"] = redistribution
            ds["commercial_use_status"] = commercial_use
            ds["citation_requirements"] = "attribution_required" if attribution_required else "none"
            if gov in (GovernanceClass.LICENCE_UNCLEAR.value, GovernanceClass.LEGAL_REVIEW_REQUIRED.value):
                ds["state"] = DatasetState.LICENCE_REVIEW_REQUIRED.value
            elif gov == GovernanceClass.USE_FORBIDDEN.value:
                ds["state"] = DatasetState.REVOKED.value
            self.store.upsert_dataset(ds)

        self.store.audit("licence.record", subject=dataset_id, detail={
            "version": dataset_version, "licence": name, "governance": gov,
        })
        out = self._public(rec)
        out["ok"] = True
        out["LEGAL_REVIEW_REQUIRED"] = bool(legal_review_required)
        out["disclaimer"] = "Not legal certification. LEGAL_REVIEW_REQUIRED where rights unclear."
        out.update(AUTHORITY_VALUES)
        return out

    def check_use(self, dataset_id: str, dataset_version: str, use_case: str) -> dict[str, Any]:
        lic = self.latest(dataset_id, dataset_version)
        if not lic:
            return {
                "ok": False,
                "allowed": False,
                "code": LICENCE_UNKNOWN,
                "use_case": use_case,
                "message": "No licence record; fail closed",
                "LEGAL_REVIEW_REQUIRED": True,
                **AUTHORITY_VALUES,
            }
        gov = lic["governance_class"]
        redistribution = lic.get("redistribution_permission") or lic.get("redistribution") or "unknown"
        commercial_use = lic.get("commercial_use_permission") or lic.get("commercial_use") or "unknown"
        if gov == GovernanceClass.USE_FORBIDDEN.value:
            return {
                "ok": False, "allowed": False, "code": LICENCE_FORBIDDEN,
                "use_case": use_case, "governance_class": gov, **AUTHORITY_VALUES,
            }
        if gov in (GovernanceClass.LICENCE_UNCLEAR.value, GovernanceClass.LEGAL_REVIEW_REQUIRED.value):
            return {
                "ok": False, "allowed": False, "code": LICENCE_GATE_FAILED,
                "use_case": use_case, "governance_class": gov,
                "LEGAL_REVIEW_REQUIRED": True,
                "message": "Unknown/unclear licence — research approval blocked",
                **AUTHORITY_VALUES,
            }
        # Policy matrix
        blocked = False
        reason = ""
        if use_case == "redistribution" and redistribution in ("forbidden", "unknown"):
            blocked = True
            reason = "redistribution not permitted"
        if use_case == "commercial_use" and commercial_use in ("forbidden", "unknown"):
            blocked = True
            reason = "commercial use not permitted"
        if use_case == "user_facing_display" and gov == GovernanceClass.INTERNAL_RESEARCH_ONLY.value:
            blocked = True
            reason = "internal research only"
        if use_case == "model_training" and gov == GovernanceClass.NON_COMMERCIAL_ONLY.value:
            # Allowed for research training with limitation flag
            reason = "non_commercial_training_only"
        if blocked:
            return {
                "ok": False, "allowed": False, "code": LICENCE_GATE_FAILED,
                "use_case": use_case, "reason": reason, "governance_class": gov,
                **AUTHORITY_VALUES,
            }
        return {
            "ok": True, "allowed": True, "use_case": use_case,
            "governance_class": gov,
            "attribution_required": bool(
                lic.get("attribution_requirement", lic.get("attribution_required"))
            ),
            "limitations": [reason] if reason else [],
            **AUTHORITY_VALUES,
        }

    def gate_research_approval(self, dataset_id: str, dataset_version: str) -> dict[str, Any]:
        """Fail closed if licence unknown/forbidden/unclear."""
        check = self.check_use(dataset_id, dataset_version, "local_research")
        if not check.get("allowed"):
            raise MarketDataError(
                check.get("code") or LICENCE_GATE_FAILED,
                check.get("message") or "Licence gate failed",
                check,
            )
        return check

    def latest(self, dataset_id: str, dataset_version: str) -> dict[str, Any] | None:
        row = self.store.query_one(
            """SELECT * FROM md_licences WHERE dataset_id=? AND dataset_version=?
               ORDER BY created_at DESC LIMIT 1""",
            (dataset_id, dataset_version),
        )
        return self._public(row) if row else None

    def inventory(self) -> dict[str, Any]:
        rows = self.store.query("SELECT * FROM md_licences ORDER BY created_at DESC")
        items = [self._public(r) for r in rows]
        classes = {}
        for i in items:
            classes[i["governance_class"]] = classes.get(i["governance_class"], 0) + 1
        payload = {
            "schema": "M257_DATASET_GOVERNANCE",
            "count": len(items),
            "licences": items,
            "governance_class_counts": classes,
            "use_cases_checked": list(USE_CASES),
            "legal_disclaimer": "Not legal certification. Fail-closed on unknown terms.",
            **AUTHORITY_VALUES,
        }
        payload["evidence_hash"] = evidence_hash(payload)
        return payload

    @staticmethod
    def _public(rec: dict[str, Any] | None) -> dict[str, Any]:
        if not rec:
            return {}
        return {
            "id": rec.get("id"),
            "dataset_id": rec.get("dataset_id"),
            "dataset_version": rec.get("dataset_version"),
            "licence_name": rec.get("licence_name"),
            "licence_version": rec.get("licence_version") or "",
            "official_licence_source": rec.get("official_source") or "",
            "commercial_use_permission": rec.get("commercial_use"),
            "redistribution_permission": rec.get("redistribution"),
            "modification_permission": rec.get("modification"),
            "attribution_requirement": bool(rec.get("attribution_required")),
            "retention_limit": rec.get("retention_limit") or "",
            "geographic_restriction": rec.get("geographic_restriction") or "",
            "usage_restriction": rec.get("usage_restriction") or "",
            "unknown_terms": bool(rec.get("unknown_terms")),
            "legal_review_requirement": bool(rec.get("legal_review_required")),
            "governance_class": rec.get("governance_class"),
            "evidence_hash": rec.get("evidence_hash") or "",
        }
