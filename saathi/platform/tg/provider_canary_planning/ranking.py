"""M240 — Provider selection framework and transparent ranking.

Recommendations only. Does not claim owner eligibility or authorize connectivity.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    FALLBACK_PROVIDER,
    PREFERRED_PROVIDER,
    RETRIEVAL_DATE,
    CandidateClass,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

# Transparent score records: score 0-5 with evidence/confidence/uncertainty.
# Missing evidence is never hidden behind a bare number.


def _crit(score: int | None, evidence: str, confidence: str, uncertainty: str,
          disqualifying: str = "", unresolved: str = "") -> dict[str, Any]:
    return {
        "score": score,  # None means insufficient evidence
        "evidence": evidence,
        "confidence": confidence,
        "uncertainty": uncertainty,
        "disqualifying_issue": disqualifying or None,
        "unresolved_question": unresolved or None,
    }


CANDIDATE_SPECS: list[dict[str, Any]] = [
    {
        "provider": "alpaca",
        "display_name": "Alpaca",
        "classification": CandidateClass.OWNER_ELIGIBILITY_UNCONFIRMED.value,
        "preferred": True,
        "fallback": False,
        "scores": {
            "eligibility": _crit(
                3,
                "Official docs describe individual/business trading accounts and paper environment; "
                "availability is jurisdiction-specific.",
                "medium",
                "Owner country/residency and product eligibility not verified for this installation.",
                unresolved="Confirm owner residency and Alpaca account eligibility before any future canary.",
            ),
            "security": _crit(
                4,
                "API key model with paper/live separation; IP restrictions commonly supported; "
                "OAuth Connect exists but is forbidden for this canary path.",
                "medium",
                "Exact console paths for key expiry and IP allow-list need owner verification.",
            ),
            "api_quality": _crit(
                5,
                "Official Trading API + Market Data docs; account, positions, orders, portfolio history endpoints documented.",
                "high",
                "Schema drift possible; pin docs version at canary time.",
            ),
            "operational_suitability": _crit(
                5,
                "Dedicated paper-api environment supports deterministic testing without live capital.",
                "high",
                "Paper vs live host isolation must be enforced by network allow-list.",
            ),
            "commercial_product_fit": _crit(
                5,
                "US equities + crypto APIs align with SaathiOS paper-to-read-only roadmap.",
                "high",
                "Market-data redistribution limits require legal review before any redistribution.",
            ),
        },
        "disqualifying_issues": [],
        "unresolved_questions": [
            "Is the owner eligible to open/use Alpaca in their jurisdiction?",
            "Will paper keys remain strictly isolated from live keys?",
            "What market-data terms apply to stored snapshots?",
        ],
        "rationale": (
            "Strongest first-canary candidate: clear paper environment, strong account/position/history "
            "coverage, equities+crypto fit, and documented API quality. Owner eligibility remains UNCONFIRMED."
        ),
    },
    {
        "provider": "kraken",
        "display_name": "Kraken",
        "classification": CandidateClass.CONDITIONALLY_ELIGIBLE.value,
        "preferred": False,
        "fallback": True,
        "scores": {
            "eligibility": _crit(
                3,
                "Kraken offers accounts and API keys broadly; country restrictions exist and are owner-specific.",
                "medium",
                "Owner residency and product access unconfirmed.",
                unresolved="Confirm Kraken account eligibility and entity for owner country.",
            ),
            "security": _crit(
                5,
                "Official permission matrix separates Query Funds / Query Orders from Create & Modify Orders / Withdraw Funds; "
                "GetApiKeyInfo enables permission introspection.",
                "high",
                "Key expiry and IP allow-list options need owner console confirmation.",
            ),
            "api_quality": _crit(
                4,
                "Mature REST private endpoints for balances, orders, trades, ledgers with documented permissions.",
                "high",
                "Nonce/signature model is operationally heavier than simple key headers.",
            ),
            "operational_suitability": _crit(
                3,
                "No full equities paper broker equivalent; crypto-focused; good status/docs.",
                "medium",
                "Limited equity coverage vs SaathiOS multi-asset roadmap.",
            ),
            "commercial_product_fit": _crit(
                3,
                "Strong crypto coverage; weaker multi-asset equities fit for SaathiOS primary paper path.",
                "medium",
                "Asset universe and fee structures need product review.",
            ),
        },
        "disqualifying_issues": [],
        "unresolved_questions": [
            "Does owner already have or can open a Kraken account legally?",
            "Is crypto-only canary acceptable as fallback for roadmap?",
        ],
        "rationale": (
            "Best fallback: excellent granular query-only permissions and key introspection. "
            "Crypto-centric product fit is secondary to Alpaca for multi-asset paper path."
        ),
    },
    {
        "provider": "coinbase",
        "display_name": "Coinbase (Advanced Trade / CDP)",
        "classification": CandidateClass.CONDITIONALLY_ELIGIBLE.value,
        "preferred": False,
        "fallback": False,
        "scores": {
            "eligibility": _crit(
                3,
                "Coinbase products vary by region; Advanced Trade CDP keys documented.",
                "medium",
                "Owner jurisdiction eligibility unconfirmed.",
            ),
            "security": _crit(
                4,
                "can_view / can_trade / can_transfer separation; IP whitelist encouraged; keys may not expire by default.",
                "medium",
                "Non-expiring keys are a residual security concern requiring forced rotation policy.",
            ),
            "api_quality": _crit(
                4,
                "Advanced Trade REST with portfolio/account endpoints and key permission introspection.",
                "high",
                "CDP JWT auth complexity and portfolio UUID binding.",
            ),
            "operational_suitability": _crit(
                3,
                "No equity paper broker equivalent; crypto focused.",
                "medium",
                "OAuth paths exist and must remain disabled.",
            ),
            "commercial_product_fit": _crit(
                3,
                "Crypto coverage good; equities fit limited for primary roadmap.",
                "medium",
                "Brand/terms constraints on third-party software need legal review.",
            ),
        },
        "disqualifying_issues": [],
        "unresolved_questions": [
            "Can keys be forced to expire or only rotated manually?",
            "Owner entity eligibility for Advanced Trade?",
        ],
        "rationale": "Viable crypto alternative with clear view/trade/transfer flags; not preferred due to non-expiring keys residual risk and weaker equities fit.",
    },
    {
        "provider": "binance",
        "display_name": "Binance",
        "classification": CandidateClass.LEGAL_REVIEW_REQUIRED.value,
        "preferred": False,
        "fallback": False,
        "scores": {
            "eligibility": _crit(
                2,
                "Binance entities and products are highly jurisdiction-sensitive; many regions restricted.",
                "low",
                "Owner country may be unsupported; entity selection unresolved.",
                unresolved="Which Binance legal entity (if any) serves the owner?",
            ),
            "security": _crit(
                4,
                "API key restrictions support disabling withdrawals and trading for read-oriented use; IP bind recommended.",
                "medium",
                "Regional product differences (global vs US etc.).",
            ),
            "api_quality": _crit(
                4,
                "Extensive REST/WS docs for account, balances, trades.",
                "medium",
                "Version fragmentation and product matrix complexity.",
            ),
            "operational_suitability": _crit(
                2,
                "High complexity; geographic/entity risk elevates ops burden for first canary.",
                "medium",
                "Testnet availability and parity with production vary by product.",
            ),
            "commercial_product_fit": _crit(
                3,
                "Strong crypto coverage; equities not primary.",
                "medium",
                "Terms and redistribution need legal review.",
            ),
        },
        "disqualifying_issues": [],
        "unresolved_questions": [
            "Is the owner in a supported Binance jurisdiction?",
            "Which official entity API applies?",
        ],
        "rationale": "Capable API but eligibility/legal entity risk too high for preferred first canary.",
    },
    {
        "provider": "interactive_brokers",
        "display_name": "Interactive Brokers",
        "classification": CandidateClass.NOT_RECOMMENDED.value,
        "preferred": False,
        "fallback": False,
        "scores": {
            "eligibility": _crit(
                3,
                "IBKR serves many countries with multi-asset accounts; account type complexity high.",
                "medium",
                "Owner account type and API access entitlements unconfirmed.",
            ),
            "security": _crit(
                3,
                "Client Portal session/OAuth-oriented models; less simple static read-only API key model than peers.",
                "medium",
                "Session-based auth increases operational and security surface for a bounded canary.",
            ),
            "api_quality": _crit(
                3,
                "CPAPI and TWS/Gateway documented; powerful but complex.",
                "medium",
                "Gateway process dependency elevates maintenance burden.",
            ),
            "operational_suitability": _crit(
                1,
                "Requires gateway/session lifecycle; poor fit for first isolated canary.",
                "high",
                "Excessive implementation complexity for M240–M247 planning scope.",
                disqualifying="Session/gateway model unsuitable as first read-only canary target.",
            ),
            "commercial_product_fit": _crit(
                4,
                "Excellent multi-asset coverage long-term.",
                "high",
                "Complexity outweighs fit for first canary.",
            ),
        },
        "disqualifying_issues": [
            "Session/gateway authentication model is unsuitable for the first bounded canary.",
        ],
        "unresolved_questions": [
            "Could a future milestone design a gateway-isolated canary?",
        ],
        "rationale": "Excellent multi-asset product but operational model is too complex for first canary.",
    },
    {
        "provider": "zerodha",
        "display_name": "Zerodha (Kite Connect)",
        "classification": CandidateClass.OWNER_ELIGIBILITY_UNCONFIRMED.value,
        "preferred": False,
        "fallback": False,
        "scores": {
            "eligibility": _crit(
                1,
                "Kite Connect is primarily for Indian market participants; residency restrictions likely apply.",
                "medium",
                "Owner India residency/account eligibility unconfirmed — likely blocking for non-IN owners.",
                unresolved="Is the owner an eligible Indian resident Zerodha client?",
            ),
            "security": _crit(
                3,
                "Login token model; API key + access token; daily login flows typical.",
                "medium",
                "Token lifecycle differs from long-lived read-only keys.",
            ),
            "api_quality": _crit(
                4,
                "Kite Connect v3 docs cover holdings, positions, orders, margins.",
                "high",
                "Daily re-auth patterns complicate long-lived canary windows.",
            ),
            "operational_suitability": _crit(
                2,
                "India-market focus; login ceremony complicates automated bounded canary.",
                "medium",
                "Product geography may not match owner.",
            ),
            "commercial_product_fit": _crit(
                2,
                "Indian equities; limited global multi-asset fit for SaathiOS primary path.",
                "medium",
                "Roadmap fit depends on owner market.",
            ),
        },
        "disqualifying_issues": [],
        "unresolved_questions": [
            "Owner residency and Zerodha account status?",
        ],
        "rationale": "Strong India-market API; owner eligibility highly uncertain; not preferred for first global canary.",
    },
    {
        "provider": "bybit",
        "display_name": "Bybit",
        "classification": CandidateClass.LEGAL_REVIEW_REQUIRED.value,
        "preferred": False,
        "fallback": False,
        "scores": {
            "eligibility": _crit(
                2,
                "Bybit availability is region-dependent; restrictions apply in multiple jurisdictions.",
                "low",
                "Owner eligibility unconfirmed.",
            ),
            "security": _crit(
                3,
                "API key permissions exist for read vs trade; withdrawal controls expected but console-verified.",
                "medium",
                "IP/expiry options need verification.",
            ),
            "api_quality": _crit(
                4,
                "V5 REST docs for account, positions, order history.",
                "medium",
                "Derivatives-centric semantics.",
            ),
            "operational_suitability": _crit(
                2,
                "Derivatives focus and regional complexity elevate risk for first canary.",
                "medium",
                "Testnet parity verification needed.",
            ),
            "commercial_product_fit": _crit(
                2,
                "Crypto derivatives-heavy; weaker fit to paper equities path.",
                "medium",
                "Roadmap misalignment for first canary.",
            ),
        },
        "disqualifying_issues": [],
        "unresolved_questions": [
            "Is Bybit available and lawful for the owner?",
        ],
        "rationale": "API capable but legal/regional risk and derivatives focus make it non-preferred.",
    },
]


def _numeric_total(scores: dict[str, Any]) -> float:
    vals = []
    for dim, c in scores.items():
        s = c.get("score")
        if s is None:
            continue
        vals.append(float(s))
    return sum(vals) / len(vals) if vals else 0.0


class ProviderRanking:
    def __init__(self, store: PlanningStore):
        self.store = store

    def ensure_seeded(self) -> None:
        row = self.store.fetchone("SELECT COUNT(*) AS c FROM pcp_candidates")
        if row and int(row["c"]) > 0:
            return
        now = time.time()
        for spec in CANDIDATE_SPECS:
            self.store.execute(
                """INSERT INTO pcp_candidates(
                    id, provider, display_name, classification, preferred, fallback,
                    scores_json, disqualifying_issues_json, unresolved_questions_json,
                    rationale, evidence_json, created_at, updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    _uid("cand"),
                    spec["provider"],
                    spec["display_name"],
                    spec["classification"],
                    1 if spec["preferred"] else 0,
                    1 if spec["fallback"] else 0,
                    json.dumps(spec["scores"]),
                    json.dumps(spec["disqualifying_issues"]),
                    json.dumps(spec["unresolved_questions"]),
                    spec["rationale"],
                    json.dumps({"retrieval_date": RETRIEVAL_DATE}),
                    now, now,
                ),
            )
        ranking = self._build_ranking_payload()
        self.store.execute(
            """INSERT INTO pcp_rankings(id, preferred_provider, fallback_provider, ranking_json, matrix_json, evidence_hash, created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (
                _uid("rank"),
                PREFERRED_PROVIDER,
                FALLBACK_PROVIDER,
                json.dumps(ranking["ranking"]),
                json.dumps(ranking["matrix"]),
                ranking["evidence_hash"],
                now,
            ),
        )
        self.store.audit("ranking.seeded", detail={
            "preferred": PREFERRED_PROVIDER,
            "fallback": FALLBACK_PROVIDER,
        })

    def _build_ranking_payload(self) -> dict[str, Any]:
        rows = self.store.fetchall("SELECT * FROM pcp_candidates")
        items = []
        matrix = {}
        for r in rows:
            scores = json.loads(r["scores_json"] or "{}")
            item = {
                "provider": r["provider"],
                "display_name": r["display_name"],
                "classification": r["classification"],
                "preferred": bool(r["preferred"]),
                "fallback": bool(r["fallback"]),
                "average_score": round(_numeric_total(scores), 3),
                "scores": scores,
                "disqualifying_issues": json.loads(r["disqualifying_issues_json"] or "[]"),
                "unresolved_questions": json.loads(r["unresolved_questions_json"] or "[]"),
                "rationale": r["rationale"],
            }
            items.append(item)
            matrix[r["provider"]] = scores
        items.sort(key=lambda x: (-x["average_score"], x["provider"]))
        for i, it in enumerate(items, 1):
            it["rank"] = i
        return {
            "preferred_provider": PREFERRED_PROVIDER,
            "fallback_provider": FALLBACK_PROVIDER,
            "preferred_is_recommendation_only": True,
            "owner_eligibility_claimed": False,
            "ranking": items,
            "matrix": matrix,
            "retrieval_date": RETRIEVAL_DATE,
            "evidence_hash": evidence_hash(items),
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "note": "Preferred provider selection is a recommendation only.",
        }

    def ranking(self) -> dict[str, Any]:
        self.ensure_seeded()
        return self._build_ranking_payload()

    def candidates(self) -> dict[str, Any]:
        self.ensure_seeded()
        r = self.ranking()
        return {
            "candidates": r["ranking"],
            "count": len(r["ranking"]),
            "preferred_provider": r["preferred_provider"],
            "fallback_provider": r["fallback_provider"],
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def preferred(self) -> dict[str, Any]:
        self.ensure_seeded()
        r = self.ranking()
        pref = next(x for x in r["ranking"] if x["provider"] == PREFERRED_PROVIDER)
        return {
            "preferred_provider": PREFERRED_PROVIDER,
            "recommendation_only": True,
            "owner_eligibility_claimed": False,
            "detail": pref,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def fallback(self) -> dict[str, Any]:
        self.ensure_seeded()
        r = self.ranking()
        fb = next(x for x in r["ranking"] if x["provider"] == FALLBACK_PROVIDER)
        return {
            "fallback_provider": FALLBACK_PROVIDER,
            "recommendation_only": True,
            "detail": fb,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
