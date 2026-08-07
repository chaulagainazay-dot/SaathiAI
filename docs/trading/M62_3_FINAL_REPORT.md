# M62.3 — Final Report: Evidence-Backed Agentic Research Pipeline

1. **Verdict:** `M62_3_COMPLETE_WITH_LIMITATIONS` — research substrate is
   technically ready and certified via backend tests; the operator browser
   workspace + production browser certification are deferred (bounded limitation).
2. **Starting branch/SHA:** `milestone/m61-backend-workflow-persistence` @ `ef58ac3`.
3. **Ending branch/SHA:** same branch @ (this commit).
4. **Commits:** one.
5. **Reuse audit:** M62.1 `trading_models` + M62.2 `market_data` reused read-only.
6. **Legacy disposition:** M5 `research.py` (confidence framework) + `investment.py`
   = LEGACY_ISOLATED (kept, not wired — avoids a second platform research
   architecture). `tools/research.py`/`web_research.py` = OUT_OF_SCOPE (may network).
7. **New modules:** `saathi/platform/research/{__init__,models,analysis,store,service,
   fixtures}.py`; research endpoints in `platform/api.py`; 6 permissions in `models.py`.
8. **Canonical models:** ResearchProject/Plan, ResearchSource, Claim, Citation,
   Contradiction, Thesis (+ Assumption/Catalyst/Risk/Scenario embedded in thesis body).
9. **Fact classes:** FACT/CALCULATION/ASSUMPTION/INFERENCE/OPINION/FORECAST — mandatory.
10. **Source types:** LOCAL_DOCUMENT, PLATFORM_MARKET_DATA, STRUCTURED_DATASET,
    OPERATOR_NOTE, APPROVED_WEB_SOURCE_REFERENCE, API_RESULT, RESEARCH_OUTPUT.
11. **Trust model:** PRIMARY_AUTHORITY … REJECTED; trust never auto-determines truth.
12. **Source-quality states:** VALID/STALE/INCOMPLETE/MISSING_DATE/DUPLICATE/
    SUPERSEDED/CONFLICT_OF_INTEREST/PROMPT_INJECTION_SUSPECTED/MALFORMED/REJECTED.
13. **Provenance:** identity, hash (sha256), timestamps (published/retrieved/effective),
    trust, quality, injection state, tenant, parent project; content vs interpretation
    separated; locator is a reference, never a fetch proxy.
14. **Prompt-injection defense:** untrusted source text; BLOCKED patterns (execute
    trade/approve/reveal-secret/…) → not extracted, audited-rejected, block auto-publish.
15. **Claim extraction:** deterministic rule-based (line format + fact-class + topic +
    numeric); model-assisted extraction is an optional future adapter (uncertified).
16. **Citation verification:** machine-checkable (source exists + hash match + locator
    resolves + same tenant); fabricated locators fail.
17. **Contradiction handling:** first-class; 7 types; both claims preserved; critical
    same-date numeric conflicts block publication.
18-19. **Thesis lifecycle + versioning:** versioned; published immutable; corrections =
    new version; parent chain + rationale retained.
20. **Confidence model:** component-based, documented weights, breakdown preserved.
21. **Independent challenge:** ContrarianReviewer scans for unresolved contradictions,
    uncited facts, unsupported certainty, single-source risk, stale evidence, missing
    downside; critical findings force REVISION_REQUIRED and block publication.
22. **Market-data integration:** read-only reuse of M62.2 (no duplicate model; invalid
    market data cannot become a verified fact).
23. **Persistence:** SQLite, tenant-scoped, versioned, published-immutable; restart-safe.
24. **API:** projects CRUD + plan + sources + validate + claims/extract +
    citations/verify + contradictions/search + synthesize + challenge + revise +
    publish + thesis(+versions). Authenticated, tenant-scoped, audited, bounded, 409/400.
25. **Permission matrix:** viewer=read; operator=create/edit/challenge; owner+=review/
    publish. No self-publish by agents.
26. **Audit:** project/plan/source(add+reject)/claims/citations/contradictions/
    synthesize/challenge/revise/publish — actor+tenant+project+correlation.
27. **Fixtures/hashes:** 8 deterministic hashed sets (`m62_3_evidence/fixture_manifest.json`).
28-31. **Tests:** 14 M62.3 (unit/persistence/integration/RBAC/adversarial/HTTP) pass;
    48 regression (M62.2+M62.1+M61+M50) pass.
32-34. **Frontend / browser certification:** DEFERRED — backend substrate is the M62.3
    core; a read-only Glass Frame research workspace + fresh-browser certification are a
    recommended immediate follow-up (limitation, not a safety gap).
35. **Regression:** all green; `git diff --check` clean.
36. **Safety scan:** no order/broker/execution/network/subprocess/secret in `research/`;
    no runtime/gateway/execution import; no trading endpoint.
37. **Known limitations:** deterministic local fixtures only; model-assisted extraction
    uncertified; single-host SQLite; browser workspace + cert deferred; manual human
    publication approval (by design).
38. **Working tree:** clean except preserved `docs/design-spec/`.
39. **Push/merge/deploy:** none.
40. **Recommended M62.4:** strategy versioning + deterministic backtesting (no look-
    ahead/leakage; transaction costs; out-of-sample; broken-strategy detection) consuming
    M62.2 replay + M62.3 theses read-only.

PlatformAgentRuntime remains the canonical agent runtime.
ExecutionGateway remains the sole authority for registered tool execution.
Trading Guardian remains an independent fail-closed veto layer.
Research agents may collect, analyze, challenge, and publish evidence-backed research
only through server-authorized workflows.
Research agents have no trading, approval, broker, portfolio-mutation, or
capital-allocation authority.
M62.3 research readiness does not prove strategy validity or profitability.
No backtesting, paper trading, live trading, leverage, margin, short-selling,
derivatives, production deployment, or autonomous capital use is authorized.
Services remain localhost-only.
No push, merge, deployment, or external rollout authority is granted.
