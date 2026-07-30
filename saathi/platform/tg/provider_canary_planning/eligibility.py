"""M242 — Eligibility, terms and data-governance review (planning only).

Not legal advice. Not legal certification. Owner eligibility is not claimed.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    PREFERRED_PROVIDER,
    RETRIEVAL_DATE,
    EligibilityItemClass,
    EligibilityResult,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

ELIGIBILITY_ITEMS: list[dict[str, Any]] = [
    {
        "item": "geographic_eligibility",
        "classification": EligibilityItemClass.OWNER_CONFIRMATION_REQUIRED.value,
        "finding": "Alpaca product availability is jurisdiction-specific. Owner country not verified in this package.",
        "source": "https://docs.alpaca.markets/docs/getting-started",
    },
    {
        "item": "residency_requirements",
        "classification": EligibilityItemClass.OWNER_CONFIRMATION_REQUIRED.value,
        "finding": "Residency and tax residency may affect account eligibility; owner must confirm.",
        "source": "owner confirmation required",
    },
    {
        "item": "account_eligibility",
        "classification": EligibilityItemClass.OWNER_CONFIRMATION_REQUIRED.value,
        "finding": "Individual vs business account type and KYC status unknown for this owner.",
        "source": "owner confirmation required",
    },
    {
        "item": "api_eligibility",
        "classification": EligibilityItemClass.SUPPORTED_BY_OFFICIAL_SOURCE.value,
        "finding": "Official Trading API documentation exists for account-authenticated API access.",
        "source": "https://docs.alpaca.markets/docs/getting-started-with-trading-api",
    },
    {
        "item": "api_terms_of_use",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "API and brokerage terms must be reviewed by owner/legal before connectivity.",
        "source": "provider legal pages (owner must open current version)",
    },
    {
        "item": "automated_access_restrictions",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "Automated access must comply with rate limits and API terms; bot use restrictions need review.",
        "source": "API terms (current version at canary time)",
    },
    {
        "item": "data_retention_restrictions",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "Account and market data retention/redistribution may be restricted by licence.",
        "source": "terms + market data licence",
    },
    {
        "item": "redistribution_restrictions",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "Snapshots stored in SaathiOS must not be redistributed without licence clearance.",
        "source": "market data and API terms",
    },
    {
        "item": "privacy_requirements",
        "classification": EligibilityItemClass.OWNER_CONFIRMATION_REQUIRED.value,
        "finding": "Account PII handling must match owner privacy obligations and provider privacy policy.",
        "source": "provider privacy policy + owner policy",
    },
    {
        "item": "audit_requirements",
        "classification": EligibilityItemClass.SUPPORTED_BY_OFFICIAL_SOURCE.value,
        "finding": "Canary design requires full local audit of calls; provider may retain own logs.",
        "source": "planning design M243",
    },
    {
        "item": "account_data_storage_restrictions",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "Storing balances/positions locally must comply with provider and privacy rules.",
        "source": "terms + privacy",
    },
    {
        "item": "third_party_software_restrictions",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "Using SaathiOS as third-party software against provider API needs terms clearance.",
        "source": "API terms",
    },
    {
        "item": "credential_sharing_restrictions",
        "classification": EligibilityItemClass.SECURITY_REVIEW_REQUIRED.value,
        "finding": "Credentials must never be shared with LLMs or multi-tenant untrusted actors.",
        "source": "planning invariant + security model",
    },
    {
        "item": "rate_limit_obligations",
        "classification": EligibilityItemClass.SUPPORTED_BY_OFFICIAL_SOURCE.value,
        "finding": "Canary must respect provider rate limits; budget enforced in design.",
        "source": "provider rate-limit behaviour",
    },
    {
        "item": "provider_branding_requirements",
        "classification": EligibilityItemClass.UNRESOLVED.value,
        "finding": "Branding/attribution requirements not fully inventoried.",
        "source": "pending legal review",
    },
    {
        "item": "prohibited_activities",
        "classification": EligibilityItemClass.LEGAL_REVIEW_REQUIRED.value,
        "finding": "Order submission, wash trading, market manipulation remain prohibited; canary is read-only by design.",
        "source": "terms + planning invariant",
    },
    {
        "item": "termination_and_suspension_risks",
        "classification": EligibilityItemClass.OWNER_CONFIRMATION_REQUIRED.value,
        "finding": "Provider may suspend API access; canary must abort cleanly on suspension signals.",
        "source": "terms + canary abort design",
    },
]

LEGAL_REVIEW_ITEMS = [
    "api_terms_of_use current version acknowledgement",
    "automated-access and bot restrictions",
    "data retention and redistribution licences",
    "third-party software authorization",
    "privacy/PII handling for account snapshots",
    "jurisdiction-specific brokerage regulations for owner",
    "branding and attribution obligations",
]


class EligibilityReview:
    def __init__(self, store: PlanningStore):
        self.store = store

    def ensure_seeded(self, provider: str = PREFERRED_PROVIDER) -> None:
        row = self.store.fetchone(
            "SELECT COUNT(*) AS c FROM pcp_eligibility WHERE provider=?",
            (provider,),
        )
        if row and int(row["c"]) > 0:
            return
        result = EligibilityResult.ELIGIBILITY_UNCONFIRMED.value
        unresolved = [
            i["item"] for i in ELIGIBILITY_ITEMS
            if i["classification"] in (
                EligibilityItemClass.OWNER_CONFIRMATION_REQUIRED.value,
                EligibilityItemClass.UNRESOLVED.value,
            )
        ]
        legal = list(LEGAL_REVIEW_ITEMS)
        payload = {
            "items": ELIGIBILITY_ITEMS,
            "legal_review_items": legal,
            "unresolved": unresolved,
            "result": result,
            "retrieval_date": RETRIEVAL_DATE,
            "disclaimer": (
                "This is not legal advice or legal certification. "
                "Owner eligibility is not claimed without explicit verified evidence."
            ),
        }
        self.store.execute(
            """INSERT INTO pcp_eligibility(
                id, provider, result, items_json, legal_review_items_json,
                unresolved_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                _uid("elig"), provider, result,
                json.dumps(ELIGIBILITY_ITEMS),
                json.dumps(legal),
                json.dumps(unresolved),
                evidence_hash(payload),
                time.time(),
            ),
        )
        self.store.audit("eligibility.seeded", subject=provider, detail={"result": result})

    def review(self, provider: str = PREFERRED_PROVIDER) -> dict[str, Any]:
        self.ensure_seeded(provider)
        row = self.store.fetchone(
            "SELECT * FROM pcp_eligibility WHERE provider=? ORDER BY created_at DESC LIMIT 1",
            (provider,),
        )
        assert row is not None
        return {
            "provider": provider,
            "result": row["result"],
            "items": json.loads(row["items_json"] or "[]"),
            "legal_review_items": json.loads(row["legal_review_items_json"] or "[]"),
            "unresolved": json.loads(row["unresolved_json"] or "[]"),
            "owner_eligibility_claimed": False,
            "legal_approval_generated_by_automation": False,
            "disclaimer": (
                "This is not legal advice or legal certification. "
                "Owner eligibility is not claimed without explicit verified evidence."
            ),
            "retrieval_date": RETRIEVAL_DATE,
            "evidence_hash": row["evidence_hash"],
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def terms(self, provider: str = PREFERRED_PROVIDER) -> dict[str, Any]:
        r = self.review(provider)
        terms_items = [
            i for i in r["items"]
            if i["item"] in (
                "api_terms_of_use",
                "automated_access_restrictions",
                "data_retention_restrictions",
                "redistribution_restrictions",
                "third_party_software_restrictions",
                "prohibited_activities",
                "termination_and_suspension_risks",
            )
        ]
        return {
            "provider": provider,
            "terms_review_status": "TERMS_REVIEW_INCOMPLETE",
            "items": terms_items,
            "legal_review_items": r["legal_review_items"],
            "legal_approval_generated_by_automation": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
