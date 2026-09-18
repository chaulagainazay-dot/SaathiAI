"""SaathiOS AI Company — declarative organization charter.

Adding an office or specialist is a data change here; nothing in the API or the
Company View needs to change. ``load_charter()`` validates the whole structure
(unique ids, membership, bindings, authority) and fails loudly on violations.

Bindings reference REAL runtime identities that already exist:
  * agent_runtime → ``saathi.agent_runtime.registry`` ids
    (planner, researcher, architect, builder, reviewer, writer, ceo)
  * mission_agent → ``saathi.platform.mission_runtime.models.AgentType`` values
  * organization  → served by organization missions (deterministic steps)
  * logical       → declared only; shown IDLE (or UNAVAILABLE when ``requires``
                    cannot be satisfied). Never shown as working.

The M10 ``executor`` agent is intentionally NOT bound to any organization role:
execution belongs to the deterministic authority chain, not to the company.
"""
from __future__ import annotations

from functools import lru_cache

from saathi.organization.models import (
    ActivityKind as K,
    AgentRole,
    AuthorityLevel as A,
    AuthoritySystem,
    Department,
    Floor,
    Office,
    RuntimeBinding,
)

OWNER = {
    "owner_id": "owner",
    "name": "Ajay",
    "title": "Owner & Founder",
    "initials": "AJ",
    "authority": "Ultimate human authority — approvals, priorities, capital",
    "in_agent_hierarchy": False,
}

DEPARTMENTS = (
    Department("executive", "Executive", "exec.saathi"),
    Department("investment", "Investment", "inv.fund_manager"),
    Department("research", "Research", "research.head"),
    Department("engineering", "Engineering", "eng.cto"),
    Department("business", "Business & Operations", "biz.coo"),
    Department("personal", "Personal Office", "personal.ea"),
)

# Top of the building first.
FLOORS = (
    Floor("f7", 7, "Executive", "Decide & Direct", "executive"),
    Floor("f6", 6, "Investment · Desks", "Grow Wealth", "investment"),
    Floor("f5", 5, "Investment · Portfolio & Risk", "Protect Capital", "investment"),
    Floor("f4", 4, "Research", "Find the Truth", "research"),
    Floor("f3", 3, "Engineering", "Build the Future", "engineering"),
    Floor("f2", 2, "Business & Operations", "Run & Grow", "business"),
    Floor("f1", 1, "Personal Office", "For a Better You", "personal"),
)

OFFICES = (
    # F7 executive
    Office("board", "Board & Governance", "executive", "f7",
           "Independent governance, compliance and audit of the company", "gov.strategy", "amber", "scale"),
    Office("ceo", "CEO Office", "executive", "f7",
           "Saathi orchestrates the organization on the owner's behalf", "exec.saathi", "cyan", "spark"),
    Office("owner", "Owner Office", "executive", "f7",
           "Ajay — ultimate human authority", "", "blue", "user"),
    # F6 investment desks
    Office("cio", "CIO / Fund Manager", "investment", "f6",
           "Portfolio-level reasoning and capital allocation proposals", "inv.fund_manager", "green", "target"),
    Office("crypto", "Crypto Desk", "investment", "f6",
           "Crypto market analysis and strategy mandates (analysis only)", "crypto.lead", "orange", "coin"),
    Office("nepse", "NEPSE Desk", "investment", "f6",
           "NEPSE market analysis via governed research (analysis only)", "nepse.lead", "green", "trend"),
    # F5 portfolio & risk
    Office("portfolio", "Portfolio Management", "investment", "f5",
           "Consumes deterministic portfolio engines; proposes allocation", "pm.manager", "teal", "pie"),
    Office("risk", "Risk Management", "investment", "f5",
           "Risk analysis; deterministic engines remain authoritative", "risk.chief", "teal", "shield"),
    Office("committee", "Investment Committee", "investment", "f5",
           "Adversarial review and decision synthesis (proposals only)", "ic.chair", "violet", "scale"),
    # F4 research
    Office("research_hq", "Head of Research", "research", "f4",
           "Research planning, standards and knowledge curation", "research.head", "blue", "search"),
    Office("web_news", "Web & News", "research", "f4",
           "Governed web research and news intelligence", "research.web", "violet", "globe"),
    Office("doc_data", "Document & Data", "research", "f4",
           "Documents, datasets and source verification", "research.document", "blue", "doc"),
    Office("macro", "Macro & Economic", "research", "f4",
           "Macro, economic and policy monitoring", "research.macro", "cyan", "bars"),
    Office("intel", "Competitive Intel", "research", "f4",
           "Competitor and trend intelligence", "research.competitive", "pink", "eye"),
    # F3 engineering
    Office("cto", "CTO Office", "engineering", "f3",
           "Architecture and technical planning", "eng.cto", "teal", "cpu"),
    Office("dev", "Development", "engineering", "f3",
           "Code, review and tests via the governed agent runtime", "eng.coding", "blue", "code"),
    Office("infra", "Infra & DevOps", "engineering", "f3",
           "Deployment readiness and monitoring (no deploy authority)", "eng.devops", "cyan", "server"),
    Office("aiops", "AI & Model Ops", "engineering", "f3",
           "Model routing, prompts and evaluation", "eng.model_manager", "violet", "spark"),
    Office("security", "Security", "engineering", "f3",
           "Security review, vulnerabilities and access audits", "eng.security", "green", "lock"),
    # F2 business
    Office("coo", "COO Office", "business", "f2",
           "Operations, workflows and scheduling", "biz.coo", "teal", "briefcase"),
    Office("finance", "Finance", "business", "f2",
           "Business finance, budgets and forecasts (no fund movement)", "biz.cfo", "green", "dollar"),
    Office("business", "Business", "business", "f2",
           "Product, growth, sales and support", "biz.product", "blue", "trend"),
    # F1 personal
    Office("assistant", "Executive Assistant", "personal", "f1",
           "Owner assistance across email, calendar and travel", "personal.ea", "teal", "calendar"),
    Office("knowledge", "Knowledge & Life", "personal", "f1",
           "Documents, notes, learning and life planning", "personal.document", "violet", "book"),
)

AUTHORITY_CHAIN = (
    AuthoritySystem("portfolio_construction", "Portfolio Construction", 1,
                    "PortfolioConstructionEngine — deterministic target/proposal construction"),
    AuthoritySystem("portfolio_risk", "Portfolio Risk", 2,
                    "PortfolioRiskEngine — enforceable limits; BLOCK / DATA_INSUFFICIENT deny"),
    AuthoritySystem("trading_guardian", "Trading Guardian", 3,
                    "Order veto: circuit breaker, paper-only, concentration, exposure"),
    AuthoritySystem("approval", "Owner Approval", 4,
                    "Platform approvals — only OWNER decides; never self-granted"),
    AuthoritySystem("execution_gateway", "Execution Gateway", 5,
                    "Registered paper tools only; FINANCIAL_EXECUTION tools prohibited"),
)
# The reasoning half of the chain (all LLM-free today or proposal-only).
REASONING_CHAIN = ("specialists", "desk_synthesis", "fund_manager",
                   "investment_committee", "decision_synthesis")

_AR = lambda ref: RuntimeBinding("agent_runtime", ref)   # noqa: E731
_MA = lambda ref: RuntimeBinding("mission_agent", ref)   # noqa: E731
_ORG = RuntimeBinding("organization")
_LOG = RuntimeBinding("logical")


def _r(role_id, name, office, title, mandate, activity, authority, *,
       binding=_LOG, financial=False, lead=False, requires=(), can=(),
       tier="specialist", evidence=(), tools=(), escalates="", output="structured_result"):
    return AgentRole(
        role_id=role_id, name=name, office_id=office, title=title, mandate=mandate,
        activity=activity, authority=authority, binding=binding, financial=financial,
        lead=lead, requires=tuple(requires), can=tuple(can), tier=tier,
        evidence_requirements=tuple(evidence), tools=tuple(tools),
        escalates_to=escalates, output_schema=output,
    )


_FIN_EVIDENCE = ("market_data_ref", "data_freshness", "source_provenance")

ROLES = (
    # ── F7 Executive ─────────────────────────────────────────────────────────
    _r("exec.saathi", "Saathi", "ceo", "AI CEO",
       "Understand owner goals, decompose them, delegate to departments, surface "
       "disagreement, escalate decisions and report back.",
       K.ORCHESTRATE, A.ORCHESTRATE, binding=_AR("ceo"), lead=True,
       can=("Create and delegate organization missions", "Request research and reviews",
            "Summarize company activity for the owner", "Escalate decisions to the owner"),
       evidence=("mission_record", "delegation_trace"), output="mission_report"),
    _r("gov.strategy", "Strategy Agent", "board", "Strategy",
       "Assess strategic fit of company priorities and major proposals.",
       K.ANALYSIS, A.ADVISE, lead=True, can=("Review priorities", "Advise the owner")),
    _r("gov.risk_governance", "Risk Governance Agent", "board", "Risk Gov.",
       "Review that risk processes were followed; cannot change limits.",
       K.REVIEW, A.CHALLENGE, financial=True, can=("Challenge risk process gaps",)),
    _r("gov.compliance", "Compliance Agent", "board", "Compliance",
       "Check proposals against policy and paper-only constraints.",
       K.REVIEW, A.CHALLENGE, binding=_ORG, can=("Verify paper-only posture", "Flag policy conflicts")),
    _r("gov.audit", "Evidence & Audit Agent", "board", "Audit",
       "Verify that outputs are backed by recorded evidence.",
       K.REVIEW, A.CHALLENGE, binding=_MA("CertificationAgent"),
       can=("Verify evidence links", "Refuse unevidenced claims")),
    _r("gov.ethics", "Ethics & Policy Agent", "board", "Ethics",
       "Review proposals for ethical and policy concerns.",
       K.REVIEW, A.ADVISE),

    # ── F6 Investment: CIO ───────────────────────────────────────────────────
    _r("inv.fund_manager", "Fund Manager", "cio", "Fund Manager",
       "Portfolio-level reasoning: allocation, cash, exposure, diversification, "
       "correlation, concentration, rebalance and hedge PROPOSALS across Crypto and NEPSE.",
       K.ANALYSIS, A.PROPOSE, binding=_ORG, financial=True, lead=True,
       can=("Synthesize desk analyses", "Propose allocation / rebalance / hedge",
            "Request risk review"), evidence=_FIN_EVIDENCE + ("risk_engine_snapshot",),
       escalates="ic.chair", output="portfolio_proposal"),

    # ── Crypto desk ──────────────────────────────────────────────────────────
    _r("crypto.lead", "Crypto Desk Lead", "crypto", "Desk Lead",
       "Coordinate crypto specialists and synthesize the desk view.",
       K.ANALYSIS, A.PROPOSE, binding=_ORG, financial=True, lead=True,
       escalates="inv.fund_manager", evidence=_FIN_EVIDENCE, output="desk_synthesis"),
    _r("crypto.research", "Crypto Market Research", "crypto", "Research",
       "Market structure and asset research.", K.RESEARCH, A.ADVISE, financial=True, evidence=_FIN_EVIDENCE),
    _r("crypto.technical", "Crypto Technical Analyst", "crypto", "Technical",
       "Price-action and indicator analysis from recorded bars.", K.ANALYSIS, A.ADVISE,
       binding=_ORG, financial=True, evidence=_FIN_EVIDENCE),
    _r("crypto.token", "Crypto Token Analyst", "crypto", "Token Fund.",
       "Token fundamentals and tokenomics.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("crypto.onchain", "Crypto On-chain Analyst", "crypto", "On-chain",
       "On-chain flows and holder behaviour.", K.ANALYSIS, A.ADVISE, financial=True,
       requires=("provider:onchain",)),
    _r("crypto.sentiment", "Crypto Sentiment Analyst", "crypto", "Sentiment",
       "Social and news sentiment.", K.ANALYSIS, A.ADVISE, financial=True,
       requires=("provider:social_sentiment",)),
    _r("crypto.news", "Crypto News Analyst", "crypto", "News",
       "Crypto news monitoring.", K.RESEARCH, A.ADVISE, financial=True),
    _r("crypto.quant", "Crypto Quant Analyst", "crypto", "Quant",
       "Quantitative signals and backtests (research only).", K.ANALYSIS, A.ADVISE, financial=True),
    _r("crypto.regime", "Crypto Market-Regime Analyst", "crypto", "Regime",
       "Classify market regime.", K.ANALYSIS, A.ADVISE, financial=True),
    *[
        _r(f"crypto.{k}", f"Crypto {label} Analyst", "crypto", label,
           f"{label} strategy mandate — analysis only, no execution.",
           K.ANALYSIS, A.ADVISE, financial=True, tier="mandate")
        for k, label in (("intraday", "Intraday"), ("short_term", "Short-Term"),
                         ("swing", "Swing"), ("position", "Position"),
                         ("long_term", "Long-Term"), ("hedge", "Hedge"))
    ],

    # ── NEPSE desk ───────────────────────────────────────────────────────────
    _r("nepse.lead", "NEPSE Desk Lead", "nepse", "Desk Lead",
       "Coordinate NEPSE specialists and synthesize the desk view.",
       K.ANALYSIS, A.PROPOSE, binding=_ORG, financial=True, lead=True,
       escalates="inv.fund_manager", evidence=_FIN_EVIDENCE, output="desk_synthesis"),
    _r("nepse.company", "NEPSE Company Research", "nepse", "Company",
       "Company research through governed browser research evidence.",
       K.RESEARCH, A.ADVISE, binding=_ORG, financial=True,
       evidence=("governed_research_evidence",)),
    _r("nepse.technical", "NEPSE Technical Analyst", "nepse", "Technical",
       "Price/volume analysis from the market-data store.", K.ANALYSIS, A.ADVISE,
       binding=_ORG, financial=True, requires=("engine:nepse_market_data",), evidence=_FIN_EVIDENCE),
    _r("nepse.fundamental", "NEPSE Fundamental Analyst", "nepse", "Fundamental",
       "Financial statements and valuation.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("nepse.sector", "NEPSE Sector Analyst", "nepse", "Sector",
       "Sector rotation and breadth.", K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True),
    _r("nepse.news", "NEPSE News Agent", "nepse", "News",
       "NEPSE news monitoring.", K.RESEARCH, A.ADVISE, financial=True),
    _r("nepse.disclosure", "NEPSE Disclosure Agent", "nepse", "Disclosure",
       "Corporate disclosures and filings.", K.RESEARCH, A.ADVISE, financial=True),
    _r("nepse.macro", "NEPSE Macro Analyst", "nepse", "Macro",
       "Nepal macro drivers of the market.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("nepse.regime", "NEPSE Market-Regime Analyst", "nepse", "Regime",
       "Classify NEPSE market regime.", K.ANALYSIS, A.ADVISE, financial=True),
    *[
        _r(f"nepse.{k}", f"NEPSE {label} Analyst", "nepse", label,
           f"{label} strategy mandate — analysis only, no execution.",
           K.ANALYSIS, A.ADVISE, financial=True, tier="mandate",
           binding=_ORG if k == "swing" else _LOG)
        for k, label in (("short_term", "Short-Term"), ("swing", "Swing"),
                         ("position", "Position"), ("long_term", "Long-Term"))
    ],

    # ── F5 Portfolio management ──────────────────────────────────────────────
    _r("pm.manager", "Portfolio Manager", "portfolio", "Manager",
       "Read portfolio state from deterministic engines and frame proposals.",
       K.ANALYSIS, A.PROPOSE, binding=_ORG, financial=True, lead=True,
       evidence=("paper_ledger_snapshot",), escalates="inv.fund_manager"),
    _r("pm.allocation", "Asset Allocation Analyst", "portfolio", "Allocation",
       "Allocation analysis (consumes engine output).", K.ANALYSIS, A.ADVISE, financial=True),
    _r("pm.position", "Position Analyst", "portfolio", "Positions",
       "Position-level review from the paper ledger.", K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True),
    _r("pm.exposure", "Exposure Analyst", "portfolio", "Exposure",
       "Gross/net exposure from engine calculations.", K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True),
    _r("pm.correlation", "Correlation Analyst", "portfolio", "Correlation",
       "Correlation analysis (requires return series).", K.ANALYSIS, A.ADVISE, financial=True),
    _r("pm.performance", "Performance Analyst", "portfolio", "Performance",
       "Performance attribution.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("pm.rebalancing", "Rebalancing Analyst", "portfolio", "Rebalance",
       "Rebalance proposals for deterministic construction.", K.ANALYSIS, A.PROPOSE, financial=True),
    _r("pm.hedging", "Hedging Analyst", "portfolio", "Hedging",
       "Hedge proposals (analysis only).", K.ANALYSIS, A.PROPOSE, financial=True),

    # ── Risk management ──────────────────────────────────────────────────────
    _r("risk.chief", "Chief Risk Agent", "risk", "Chief Risk",
       "Synthesize risk analyses. Deterministic risk engines remain authoritative.",
       K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True, lead=True,
       evidence=("risk_engine_snapshot", "guardian_posture")),
    _r("risk.market", "Market Risk Analyst", "risk", "Market",
       "Market risk analysis.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("risk.portfolio", "Portfolio Risk Analyst", "risk", "Portfolio",
       "Reads PortfolioRiskEngine limit status.", K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True),
    _r("risk.liquidity", "Liquidity Risk Analyst", "risk", "Liquidity",
       "Liquidity risk analysis.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("risk.concentration", "Concentration Risk Analyst", "risk", "Concentr.",
       "Concentration risk from positions.", K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True),
    _r("risk.drawdown", "Drawdown Analyst", "risk", "Drawdown",
       "Drawdown analysis (requires NAV history).", K.ANALYSIS, A.ADVISE, financial=True),
    _r("risk.scenario", "Scenario Analyst", "risk", "Scenario",
       "Scenario analysis.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("risk.stress", "Stress-Test Analyst", "risk", "Stress",
       "Stress tests using deterministic engines.", K.ANALYSIS, A.ADVISE, binding=_ORG, financial=True),
    _r("risk.challenger", "Risk Challenger", "risk", "Challenger",
       "Adversarially challenge optimistic assumptions.", K.CHALLENGE, A.CHALLENGE,
       binding=_ORG, financial=True),

    # ── Investment committee ─────────────────────────────────────────────────
    _r("ic.chair", "Decision Synthesizer", "committee", "Chair",
       "Chair the committee and synthesize a PROPOSAL (supporting/opposing evidence, "
       "agreement, disagreement, uncertainty, confidence, missing information). "
       "Never a decision maker; output stays a proposal until deterministic authority permits.",
       K.ANALYSIS, A.PROPOSE, binding=_ORG, financial=True, lead=True,
       evidence=("member_opinions", "risk_engine_snapshot"), output="decision_proposal"),
    _r("ic.bull", "Bull Analyst", "committee", "Bull",
       "Argue the strongest evidence-backed case for.", K.CHALLENGE, A.CHALLENGE, binding=_ORG, financial=True),
    _r("ic.bear", "Bear Analyst", "committee", "Bear",
       "Argue the strongest evidence-backed case against.", K.CHALLENGE, A.CHALLENGE, binding=_ORG, financial=True),
    _r("ic.skeptic", "Skeptic", "committee", "Skeptic",
       "Devil's advocate: attack assumptions and missing data.", K.CHALLENGE, A.CHALLENGE,
       binding=_ORG, financial=True),
    _r("ic.risk_rep", "Risk Representative", "committee", "Risk Rep",
       "Represent the risk office in committee.", K.REVIEW, A.CHALLENGE, financial=True),
    _r("ic.desk_rep", "Desk Representative", "committee", "Desk Rep",
       "Represent the trading desks in committee.", K.REVIEW, A.ADVISE, financial=True),

    # ── F4 Research ──────────────────────────────────────────────────────────
    _r("research.head", "Head of Research", "research_hq", "Head",
       "Plan research, enforce evidence standards.", K.REVIEW, A.ADVISE, binding=_ORG, lead=True),
    _r("research.librarian", "Research Librarian", "research_hq", "Librarian",
       "Curate and index research evidence.", K.RESEARCH, A.OBSERVE, binding=_ORG),
    _r("research.web", "Web Research Agent", "web_news", "Web",
       "Governed web research (GovernedBrowser via ExecutionGateway).",
       K.RESEARCH, A.OBSERVE, binding=_AR("researcher"), lead=True,
       evidence=("source_refs", "freshness")),
    _r("research.deep", "Deep Research Agent", "web_news", "Deep",
       "Multi-source deep research.", K.RESEARCH, A.ADVISE, binding=_MA("ResearcherAgent")),
    _r("research.news", "News Intelligence Agent", "web_news", "News",
       "News intelligence.", K.RESEARCH, A.OBSERVE),
    _r("research.fact_checker", "Fact Checker", "web_news", "Fact Check",
       "Verify claims against sources.", K.REVIEW, A.CHALLENGE),
    _r("research.document", "Document Analyst", "doc_data", "Documents",
       "Document analysis.", K.ANALYSIS, A.ADVISE, lead=True),
    _r("research.data", "Data Analyst", "doc_data", "Data",
       "Dataset analysis.", K.ANALYSIS, A.ADVISE),
    _r("research.source_verifier", "Source Verification Agent", "doc_data", "Sources",
       "Freshness and source reconciliation.", K.REVIEW, A.CHALLENGE, binding=_ORG),
    _r("research.macro", "Macro Research Agent", "macro", "Macro",
       "Macro research.", K.RESEARCH, A.ADVISE, lead=True),
    _r("research.economic", "Economic Analyst", "macro", "Economic",
       "Economic analysis.", K.ANALYSIS, A.ADVISE),
    _r("research.policy", "Policy Monitor", "macro", "Policy",
       "Monitor policy changes.", K.RESEARCH, A.OBSERVE),
    _r("research.competitive", "Competitive Intelligence Agent", "intel", "Competitors",
       "Competitor watch.", K.RESEARCH, A.ADVISE, lead=True),
    _r("research.trend", "Trend Analyst", "intel", "Trends",
       "Trend analysis.", K.ANALYSIS, A.ADVISE),

    # ── F3 Engineering ───────────────────────────────────────────────────────
    _r("eng.cto", "CTO Agent", "cto", "CTO",
       "Technical direction; no deploy/credential authority.", K.REVIEW, A.ADVISE, lead=True),
    _r("eng.architect", "Software Architect", "cto", "Architect",
       "Design systems and interfaces.", K.ANALYSIS, A.ADVISE, binding=_AR("architect")),
    _r("eng.planning", "Technical Planning Agent", "cto", "Planning",
       "Decompose work into bounded plans.", K.ANALYSIS, A.ADVISE, binding=_AR("planner")),
    _r("eng.coding", "Coding Agent", "dev", "Coding",
       "Implement approved changes in allowed files (reversible, behind approval).",
       K.WORK, A.LOCAL_CHANGE, binding=_AR("builder"), lead=True,
       can=("Edit allowed files after approval", "Write and run tests"),
       tools=("file.read", "file.write", "test.run")),
    _r("eng.code_review", "Code Review Agent", "dev", "Review",
       "Independent review of plans and code.", K.REVIEW, A.CHALLENGE, binding=_AR("reviewer")),
    _r("eng.test", "Test Engineer", "dev", "Tests",
       "Deterministic verification via registered tools.", K.WORK, A.ADVISE, binding=_MA("TestAgent")),
    _r("eng.debugging", "Debugging Agent", "dev", "Debug",
       "Root-cause analysis.", K.ANALYSIS, A.ADVISE),
    _r("eng.devops", "DevOps Agent", "infra", "DevOps",
       "Build/runtime readiness (no deploy authority).", K.WORK, A.ADVISE, lead=True),
    _r("eng.deployment", "Deployment Agent", "infra", "Deploy",
       "Release readiness checks (no deploy authority).", K.REVIEW, A.ADVISE),
    _r("eng.monitoring", "Monitoring Agent", "infra", "Monitoring",
       "Observe system health signals.", K.RESEARCH, A.OBSERVE, binding=_ORG),
    _r("eng.model_manager", "Model Manager", "aiops", "Models",
       "Model routing and availability.", K.ANALYSIS, A.ADVISE, lead=True),
    _r("eng.prompt", "Prompt Engineer", "aiops", "Prompts",
       "Prompt design and versioning.", K.WORK, A.ADVISE),
    _r("eng.model_eval", "Model Evaluation Agent", "aiops", "Evaluation",
       "Model/provider evaluation.", K.REVIEW, A.ADVISE),
    _r("eng.security", "Security Engineer", "security", "Security",
       "Security, isolation and policy review.", K.REVIEW, A.CHALLENGE,
       binding=_MA("SecurityAgent"), lead=True),
    _r("eng.vulnerability", "Vulnerability Analyst", "security", "Vulns",
       "Dependency and vulnerability analysis.", K.ANALYSIS, A.ADVISE),
    _r("eng.access_audit", "Access-Control Auditor", "security", "Access",
       "Audit RBAC and access boundaries.", K.REVIEW, A.CHALLENGE),

    # ── F2 Business & operations ─────────────────────────────────────────────
    _r("biz.coo", "COO Agent", "coo", "COO",
       "Operational coordination.", K.ANALYSIS, A.ADVISE, lead=True),
    _r("biz.operations", "Operations Agent", "coo", "Operations",
       "Operate mission controls under human authority.", K.WORK, A.ADVISE, binding=_MA("OperatorAgent")),
    _r("biz.workflow", "Workflow Agent", "coo", "Workflow",
       "Workflow design.", K.WORK, A.ADVISE),
    _r("biz.scheduling", "Scheduling Agent", "coo", "Scheduling",
       "Scheduling (requires calendar).", K.WORK, A.ADVISE, requires=("connector:gcal",)),
    _r("biz.cfo", "CFO Agent", "finance", "CFO",
       "Business finance oversight; cannot move funds.", K.ANALYSIS, A.ADVISE, financial=True, lead=True),
    _r("biz.accounting", "Accounting Agent", "finance", "Accounting",
       "Bookkeeping analysis.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("biz.budget", "Budget Agent", "finance", "Budget",
       "Budget analysis.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("biz.forecasting", "Forecasting Agent", "finance", "Forecast",
       "Financial forecasting.", K.ANALYSIS, A.ADVISE, financial=True),
    _r("biz.product", "Product Manager", "business", "Product",
       "Product planning and priorities.", K.ANALYSIS, A.ADVISE, lead=True),
    _r("biz.growth", "Growth Agent", "business", "Growth",
       "Growth analysis.", K.ANALYSIS, A.ADVISE),
    _r("biz.sales", "Sales Agent", "business", "Sales",
       "Sales analysis (no outbound messaging).", K.ANALYSIS, A.ADVISE),
    _r("biz.support", "Customer Support Agent", "business", "Support",
       "Support triage (no outbound messaging).", K.WORK, A.ADVISE),

    # ── F1 Personal office ───────────────────────────────────────────────────
    _r("personal.ea", "Executive Assistant", "assistant", "Assistant",
       "Coordinate owner assistance.", K.WORK, A.ADVISE, lead=True),
    _r("personal.email", "Email Agent", "assistant", "Email",
       "Email triage (never sends without approval).", K.WORK, A.ADVISE,
       requires=("connector:gmail",)),
    _r("personal.calendar", "Calendar Agent", "assistant", "Calendar",
       "Calendar management.", K.WORK, A.ADVISE, requires=("connector:gcal",)),
    _r("personal.travel", "Travel Agent", "assistant", "Travel",
       "Travel planning (no purchases).", K.RESEARCH, A.ADVISE, requires=("provider:travel",)),
    _r("personal.reminder", "Reminder Agent", "assistant", "Reminders",
       "Reminders and follow-ups.", K.WORK, A.OBSERVE),
    _r("personal.document", "Document Agent", "knowledge", "Documents",
       "Docs, reports and specs.", K.WORK, A.ADVISE, binding=_AR("writer"), lead=True),
    _r("personal.notes", "Note Agent", "knowledge", "Notes",
       "Note taking and summaries.", K.WORK, A.OBSERVE),
    _r("personal.learning", "Learning Agent", "knowledge", "Learning",
       "Learning plans and practice.", K.WORK, A.ADVISE),
    _r("personal.life_planning", "Life Planning Agent", "knowledge", "Life Plan",
       "Personal planning.", K.ANALYSIS, A.ADVISE),
)

# Runtime identity → default organization role, for runs NOT started by an
# organization mission (they carry no explicit role attribution).
AGENT_RUNTIME_ROLE = {
    "ceo": "exec.saathi", "planner": "eng.planning", "researcher": "research.web",
    "architect": "eng.architect", "builder": "eng.coding", "reviewer": "eng.code_review",
    "writer": "personal.document",
    # "executor" deliberately unmapped — execution is not a company role.
}
MISSION_AGENT_ROLE = {
    "PlannerAgent": "eng.planning", "ArchitectAgent": "eng.architect",
    "ResearcherAgent": "research.deep", "ImplementerAgent": "eng.coding",
    "ReviewerAgent": "eng.code_review", "TestAgent": "eng.test",
    "BrowserAgent": "research.web", "SecurityAgent": "eng.security",
    "DocumentationAgent": "personal.document", "CertificationAgent": "gov.audit",
    "OperatorAgent": "biz.operations", "DomainSpecialistAgent": "research.deep",
}


class CharterError(ValueError):
    pass


class Charter:
    def __init__(self, departments, floors, offices, roles, chain):
        self.departments = {d.department_id: d for d in departments}
        self.floors = {f.floor_id: f for f in floors}
        self.offices = {o.office_id: o for o in offices}
        self.roles = {r.role_id: r for r in roles}
        self.chain = tuple(sorted(chain, key=lambda s: s.order))
        self.owner = dict(OWNER)
        self.floor_order = [f.floor_id for f in floors]
        self.office_order = [o.office_id for o in offices]
        self.role_order = [r.role_id for r in roles]

    def members(self, office_id: str) -> list[AgentRole]:
        return [self.roles[r] for r in self.role_order if self.roles[r].office_id == office_id]

    def offices_on(self, floor_id: str) -> list[Office]:
        return [self.offices[o] for o in self.office_order if self.offices[o].floor_id == floor_id]


def validate(departments, floors, offices, roles, chain) -> list[str]:
    errs: list[str] = []
    from saathi.organization.models import FORBIDDEN_CAPABILITIES

    def dupes(ids, what):
        seen = set()
        for i in ids:
            if i in seen:
                errs.append(f"duplicate {what} id {i!r}")
            seen.add(i)

    dupes([d.department_id for d in departments], "department")
    dupes([f.floor_id for f in floors], "floor")
    dupes([o.office_id for o in offices], "office")
    dupes([r.role_id for r in roles], "role")
    dupes([f.number for f in floors], "floor number")
    dept_ids = {d.department_id for d in departments}
    floor_ids = {f.floor_id for f in floors}
    office_ids = {o.office_id for o in offices}
    role_ids = {r.role_id for r in roles}
    for f in floors:
        if f.department_id not in dept_ids:
            errs.append(f"floor {f.floor_id} → unknown department {f.department_id}")
    for o in offices:
        if o.department_id not in dept_ids:
            errs.append(f"office {o.office_id} → unknown department {o.department_id}")
        if o.floor_id not in floor_ids:
            errs.append(f"office {o.office_id} → unknown floor {o.floor_id}")
        if o.lead_role_id and o.lead_role_id not in role_ids:
            errs.append(f"office {o.office_id} lead {o.lead_role_id} is not a role")
    for d in departments:
        if d.head_role_id and d.head_role_id not in role_ids:
            errs.append(f"department {d.department_id} head {d.head_role_id} is not a role")
    from saathi.agent_runtime import registry as ar
    from saathi.platform.mission_runtime.models import AgentType
    mission_types = {a.value for a in AgentType}
    for r in roles:
        if r.office_id not in office_ids:
            errs.append(f"role {r.role_id} → unknown office {r.office_id}")
        if r.escalates_to and r.escalates_to not in role_ids:
            errs.append(f"role {r.role_id} escalates to unknown {r.escalates_to}")
        bad = FORBIDDEN_CAPABILITIES.intersection(r.capabilities)
        if bad:
            errs.append(f"role {r.role_id} declares forbidden capabilities {sorted(bad)}")
        if r.execution_authority != "NONE":
            errs.append(f"role {r.role_id} has execution authority")
        if r.tier not in ("specialist", "mandate"):
            errs.append(f"role {r.role_id} has unknown tier {r.tier}")
        b = r.binding
        if b.kind == "agent_runtime":
            if ar.get(b.ref) is None:
                errs.append(f"role {r.role_id} binds unknown agent_runtime id {b.ref}")
            elif b.ref == "executor":
                errs.append(f"role {r.role_id} may not bind the executor agent")
        elif b.kind == "mission_agent":
            if b.ref not in mission_types:
                errs.append(f"role {r.role_id} binds unknown mission agent {b.ref}")
        elif b.kind not in ("organization", "logical"):
            errs.append(f"role {r.role_id} has unknown binding kind {b.kind}")
    for rid in list(AGENT_RUNTIME_ROLE.values()) + list(MISSION_AGENT_ROLE.values()):
        if rid not in role_ids:
            errs.append(f"runtime mapping targets unknown role {rid}")
    if "executor" in AGENT_RUNTIME_ROLE:
        errs.append("executor must not map to an organization role")
    orders = [s.order for s in chain]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        errs.append("authority chain order must be unique and ascending")
    return errs


@lru_cache(maxsize=1)
def load_charter() -> Charter:
    errs = validate(DEPARTMENTS, FLOORS, OFFICES, ROLES, AUTHORITY_CHAIN)
    if errs:
        raise CharterError("; ".join(errs))
    return Charter(DEPARTMENTS, FLOORS, OFFICES, ROLES, AUTHORITY_CHAIN)
