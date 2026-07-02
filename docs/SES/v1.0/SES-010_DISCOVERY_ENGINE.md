```
================================================================================
SaathiAI Engineering Specification (SES)
================================================================================
Document Title      : Discovery Engine — Multi-Channel Autonomous Discovery Intelligence
Document ID         : SES-010
Version             : 1.0.0
Status              : Approved
Maturity            : L3
Classification      : Internal
Owner               : SaathiAI Architecture Team
Primary Repository  : github.com/chaulagainazay/SaathiAI
Created             : 2026-07-02
Last Updated        : 2026-07-02
Next Review         : 2026-10-02
================================================================================
```

---

## Revision History

| Version | Date | Author | Summary of Changes |
|---------|------|--------|--------------------|
| 0.1.0 | 2026-07-02 | Ajay Chaulagain | Initial draft |
| 1.0.0 | 2026-07-02 | Ajay Chaulagain | Approved — 13-part complete specification |

---

## Purpose

This document specifies the Discovery Engine — a permanent, platform-level capability of SaathiAI that continuously monitors, audits, and improves how all SaathiAI products are discovered across every relevant channel: Google, Bing, AI search engines, YouTube, TikTok, LinkedIn, Reddit, Facebook, Pinterest, app stores, and citation networks.

Discovery is not SEO. SEO is one department within Discovery. In 2026, a person looking for IELTS practice resources is as likely to find them via a Perplexity AI answer, a TikTok recommendation, or a Reddit thread as via a Google search. The Discovery Engine ensures SaathiAI products are present and optimized across all of those surfaces simultaneously.

The Discovery Engine integrates with:
- **SES-002 Agent System** — as a formal department with a Director Agent and 12 specialist sub-agents
- **SES-003 Memory System** — to accumulate discovery patterns, keyword history, and platform-specific insights
- **SES-005 AI Studio** — as a mandatory pre-publish gate: all content passes through discovery optimization before going live
- **SES-007 Mission Control** — to surface discovery dashboards and alerts
- **SES-001 Platform Scheduler** — for automated recurring audit and monitoring jobs

---

## Audience

| Role | Required Sections | Notes |
|------|------------------|-------|
| All Engineers | Parts 1–3, Appendix D | Context + schema |
| AI Coding Agents | All | Treat as authoritative spec |
| AI Studio Team | Parts 1, 11, pre-publish sections | Pre-publish integration |
| Content / Product | Parts 1, 6, 7, 8 | Channel strategy + keywords |
| DevOps | Parts 4, Appendix B, D | Crawl infra + scheduling |
| New Contributors | Read in full | Starting point for discovery work |

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| SES-001 Architecture | Platform scheduler, event bus, database conventions |
| SES-002 Agent System | Department hierarchy, AgentContract schema, CrossAgentEvents |
| SES-003 Memory System | L0–L5 tiers, Knowledge Graph, PlatformRule promotion |
| SES-005 AI Studio | Pre-publish discovery optimization gate |
| SES-007 Mission Control | Discovery dashboards |
| SES-000F Capability Registry | CAP-DISC-001 through CAP-DISC-012 |
| SES-010_SEO_INTELLIGENCE.md | Superseded by this document (SEO is Part 4 here) |

---

## Acceptance Criteria

| # | Criterion | Verifiable By |
|---|-----------|--------------|
| AC-01 | Full platform discovery audit completes weekly for all active products | Scheduler job log |
| AC-02 | Discovery Health Score written to L2 memory after every audit | Memory query |
| AC-03 | All AI Studio content passes pre-publish optimization before queue | AI Studio publish log |
| AC-04 | Critical issues auto-generate engineering tasks within 5 minutes | Task table query |
| AC-05 | Drift detection fires within 20 minutes of any deploy | Deploy hook log |
| AC-06 | Weekly discovery report delivered to Telegram every Monday | Telegram bot log |
| AC-07 | llms.txt present and valid for all domain-owning products | GEO audit result |
| AC-08 | Competitor data refreshed weekly for top 5 per product | competitor_rankings table |
| AC-09 | Keyword knowledge graph populated for all 5 products | Knowledge Graph query |
| AC-10 | YouTube video metadata optimized via pre_publish_agent before every upload | prepublish_records table |
| AC-11 | Self-improvement loop fires within 48h of content publish | discovery_performance table |
| AC-12 | Reputation Authority Score computed weekly per product | reputation_scores table |

---

## Implementation Checklist

### Phase 1 — Foundation (Weeks 1–2)
- [ ] Create Discovery Department in SES-002 agent registry
- [ ] Implement Discovery Director Agent with full AgentContract
- [ ] Set up discovery_cache/ directory and SQLite schema (Appendix D)
- [ ] Implement CrawlConfig and Crawl4AI base crawling pipeline
- [ ] Implement technical_seo_agent (robots.txt, sitemap, canonical)
- [ ] Register CAP-DISC-001 through CAP-DISC-012 in capability registry
- [ ] Run first full audit for pielts as pilot product

### Phase 2 — Audit Engine (Weeks 3–4)
- [ ] Implement all 12 specialist sub-agents
- [ ] Implement Discovery Health Score weighted scoring
- [ ] Implement DiscoveryIssue schema and issue persistence
- [ ] Implement drift detection baseline capture and comparison
- [ ] Connect audit results to L1/L2 memory writes
- [ ] Implement auto-task generation for Critical/High issues
- [ ] Run full audit across all active products

### Phase 3 — AI Studio + GEO Integration (Weeks 5–6)
- [ ] Implement pre_publish_agent with full checklist
- [ ] Wire pre-publish gate into AI Studio content approval flow
- [ ] Implement llms.txt generation and validation
- [ ] Implement GEO citability scoring
- [ ] Implement VideoObject schema auto-generation for Mr. Yeti
- [ ] Test pre-publish flow end-to-end

### Phase 4 — Intelligence + Self-Improvement (Weeks 7–8)
- [ ] Register all scheduled jobs in platform scheduler
- [ ] Implement weekly report generator + Telegram delivery
- [ ] Implement keyword intelligence pipeline
- [ ] Implement competitor tracking for all products
- [ ] Implement self-improvement loop (Part 12)
- [ ] Implement reputation monitoring (Part 13)
- [ ] Wire discovery dashboards to Mission Control
- [ ] Full end-to-end integration test

---

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AI search citation methods change rapidly | High | Medium | GEO module versioned independently; quarterly review |
| TikTok algorithm opacity | High | Medium | Proxy metrics (watch time, shares) as signals; A/B title testing |
| Crawl rate-limiting by target sites | Medium | Medium | Configurable delays, respectful crawling, httpx fallback |
| CWV measurement flakiness via Playwright | Medium | Low | Run 3 measurements, use median; flag as "measurement error" if variance >30% |
| Self-improvement loop generates bad prompts | Low | High | Learning Engine validation + CEO Agent approval gate (SES-003 Part 8) |
| Free keyword data sources low accuracy | Medium | Medium | Confidence-weight all metrics; flag as "estimated" |
| Reputation monitoring false sentiment alerts | Medium | Medium | Require sentiment confidence > 0.7 before alerting |

---

# Part 1 — Discovery Philosophy

## 1.1 Discovery in 2026: Google Is No Longer the Only Door

In 2020, "search" meant Google. A product that ranked well on Google was discovered. Everything else — social media, word of mouth, app stores — was supplementary.

In 2026, the discovery landscape has fractured into at least seven distinct channels, each with its own algorithm, its own content format, and its own optimization logic. A student looking for IELTS practice resources might:

- Search Google for "IELTS practice test free" and find pielts at position 3
- Ask Perplexity "what is the best IELTS practice app" and get an AI-generated recommendation citing pielts
- Scroll TikTok and see a Mr. Yeti short about IELTS speaking tips
- Browse YouTube for "IELTS band 7 tips" and find a full Mr. Yeti tutorial
- Search Reddit r/IELTS for community recommendations
- Find pielts through a LinkedIn post from an IELTS coach

Each of these paths requires different content, different metadata, different optimization strategies. A platform that optimizes only for Google will be invisible on five of those six paths.

The Discovery Engine is SaathiAI's answer to this complexity. It is a permanent platform capability — a department of the Agent System — that manages all seven discovery channels simultaneously, continuously, and autonomously.

## 1.2 The Seven Discovery Channels

| Channel | Primary Mechanism | Key Signal | Optimized By |
|---------|------------------|-----------|-------------|
| Traditional Search (Google/Bing) | Crawling, indexing, PageRank | Backlinks, E-E-A-T, CWV | seo_agent, technical_seo_agent |
| AI Search (ChatGPT/Claude/Gemini/Perplexity) | LLM retrieval + citation | Citability, structured data, llms.txt | geo_agent |
| YouTube / Video Search | Video indexing + engagement | CTR, watch time, tags | video_seo_agent |
| Social Discovery (TikTok/IG/FB/LinkedIn/Pinterest/Reddit) | Algorithmic feed + social graph | Engagement, hashtags, timing | social_discovery_agent |
| App Store (iOS/Android) | App store indexing | Rating, reviews, ASO keywords | (future: app_store_agent) |
| Knowledge Graph (Wikipedia/Wikidata) | Encyclopedic citation | Entity recognition, backlinks from authorities | geo_agent |
| Direct / Referral | Word of mouth, email, backlinks | Brand strength, link quality | backlink_agent, reputation_agent |

## 1.3 Platform-First: Discovery Serves All Products

The Discovery Engine serves all SaathiAI products through a single shared infrastructure:

- **Shared crawling stack** — one Crawl4AI + Playwright setup serves all products
- **Shared keyword graph** — a keyword found for pielts that also has travel relevance is visible to the Travel Platform team
- **Shared issue tracker** — a fix to the platform sitemap generator benefits all products simultaneously
- **Shared pre-publish agent** — AI Studio does not need product-specific optimization logic

Per-product configuration (Appendix A in SES-010_SEO_INTELLIGENCE.md) customizes behavior without duplicating infrastructure.

## 1.4 Autonomous Optimization: The Self-Improvement Loop

What separates the Discovery Engine from a traditional SEO tool is the Self-Improvement Loop (Part 12). After every piece of content is published, the Discovery Engine:

1. Collects performance data at 24h, 48h, 7d, and 30d intervals
2. Evaluates whether the content hit its discovery KPIs (ranking, CTR, watch time, engagement)
3. Extracts patterns from high-performing content
4. Promotes validated patterns to the Knowledge Graph as PlatformRules
5. Uses those PlatformRules to improve future pre-publish optimization

Over time, the Discovery Engine learns what works for each product on each channel — and applies that learning automatically.

## 1.5 The Discovery Engine as a Permanent Department

The Discovery Engine is Department 7 of the SES-002 Agent System. It is not an external tool called ad-hoc. It is:

- Always-on, with scheduled monitoring at multiple intervals
- Event-driven, responding to deploys and content publish events in real time
- Self-contained, maintaining its own SQLite database and memory contracts
- Integrated, surfacing findings in Mission Control and generating tasks for engineering agents

---

# Part 2 — Architecture Overview

## 2.1 Full Architecture Diagram

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    SAATHAI DISCOVERY ENGINE                                   ║
║                    Department 7 — Platform Layer                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

                      ┌───────────────────────────┐
                      │   DISCOVERY DIRECTOR AGENT │
                      │   (discovery_director_v1)  │
                      │   Orchestrator + Router    │
                      └─────────────┬─────────────┘
                                    │ dispatches by channel + mode
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐       ┌──────────▼──────────┐    ┌──────────▼──────────┐
│  SEARCH DEPT   │       │   AI SEARCH DEPT    │    │  VIDEO DEPT         │
│                │       │                     │    │                     │
│ seo_agent      │       │ geo_agent           │    │ video_seo_agent     │
│ technical_seo  │       │ (GEO + llms.txt)    │    │ (YouTube + TikTok)  │
│ _agent         │       │                     │    │                     │
└───────┬────────┘       └──────────┬──────────┘    └──────────┬──────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐       ┌──────────▼──────────┐    ┌──────────▼──────────┐
│ SOCIAL DEPT    │       │  KEYWORD DEPT        │    │  AUTHORITY DEPT     │
│                │       │                     │    │                     │
│ social_        │       │ keyword_agent        │    │ backlink_agent      │
│ discovery_agent│       │ (research + gaps)    │    │ competitor_agent    │
│                │       │                     │    │                     │
└───────┬────────┘       └──────────┬──────────┘    └──────────┬──────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐       ┌──────────▼──────────┐    ┌──────────▼──────────┐
│ CONTENT DEPT   │       │  ANALYTICS DEPT      │    │ REPUTATION DEPT     │
│                │       │                     │    │                     │
│ content_       │       │ analytics_agent      │    │ reputation_agent    │
│ refresh_agent  │       │ (traffic + CTR)      │    │ brand_monitor_agent │
│ local_seo_agent│       │                     │    │ sentiment_agent     │
│                │       │                     │    │                     │
└───────┬────────┘       └──────────┬──────────┘    └──────────┬──────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                     ┌──────────────▼──────────────┐
                     │     PRE-PUBLISH AGENT        │
                     │  (pre_publish_agent)         │
                     │  AI Studio integration gate  │
                     └──────────────┬──────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐       ┌──────────▼──────────┐    ┌──────────▼──────────┐
│  CRAWLING      │       │  SCORING ENGINE      │    │  ISSUE TRACKER      │
│  LAYER         │       │                     │    │                     │
│ Crawl4AI       │       │ Channel scores       │    │ Critical/High/      │
│ Playwright     │       │ Health Score 0-100   │    │ Medium/Low/Info     │
│ Firecrawl      │       │                     │    │                     │
│ Scrapy         │       │                     │    │ → Auto-task gen     │
│ Browser-Use    │       │                     │    │                     │
│ httpx          │       └──────────┬──────────┘    └─────────────────────┘
└───────┬────────┘                  │
        │                           │
        └───────────────────────────┘
                     │
        ┌────────────▼────────────────────────────┐
        │       DISCOVERY KNOWLEDGE BASE           │
        │                                          │
        │  L1 Episodic ── audit results 90d        │
        │  L2 Semantic ── scores, keywords         │
        │  L3 KnowledgeGraph ── patterns + rules   │
        │  L4 Platform ── verified discovery rules │
        └──────────────────────────────────────────┘
                     │
        ┌────────────▼────────────────────────────┐
        │       INTEGRATION POINTS                 │
        │                                          │
        │  AI Studio (SES-005) ► pre-publish gate  │
        │  Mission Control (SES-007) ► dashboards  │
        │  Content Queue ► keyword-driven briefs   │
        │  Platform Scheduler ► audit jobs         │
        │  Telegram Bot ► weekly reports + alerts  │
        │  Self-Improvement Loop ► Part 12         │
        └──────────────────────────────────────────┘
```

## 2.2 Operating Modes

| Mode | Trigger | Agents Involved | Duration | Output |
|------|---------|----------------|---------|--------|
| Full Audit | Weekly cron | All 12 agents | 4–6 hours | Health Score, full issue list, updated baselines |
| Monitor | Daily cron | seo_agent, geo_agent, analytics_agent | 30 min | Health Score delta, new Critical issues |
| Performance | Every 6h cron | technical_seo_agent (CWV only) | 10 min | CWV scores, performance alerts |
| Pre-Publish | AI Studio event | pre_publish_agent | < 60 seconds | Pass/optimized/fail + metadata package |
| Drift Check | Deploy event | technical_seo_agent, seo_agent | 20 min | DriftReport, regressions |
| Competitor | Weekly cron | competitor_agent, keyword_agent | 2 hours | CompetitorSnapshot, content gaps |

---

# Part 3 — Discovery Department (Agent System Integration)

## 3.1 Department Position in SES-002 Hierarchy

```
SaathiAI Agent System (SES-002)
├── Dept 1: Engineering
├── Dept 2: Content (AI Studio)
├── Dept 3: Voice OS
├── Dept 4: Memory & Knowledge
├── Dept 5: Product Intelligence
├── Dept 6: Operations
├── Dept 7: Discovery Intelligence   ◄── THIS DOCUMENT
├── Dept 8: Platform Safety
└── Dept 9: Reputation & Authority   ◄── Part 13
```

## 3.2 Discovery Director Agent — Full AgentContract

```python
from dataclasses import dataclass, field
from typing import Literal, List, Optional

@dataclass
class AgentContract:
    agent_id: str
    agent_name: str
    department: str
    version: str
    role_description: str
    can_spawn_agents: bool
    can_write_memory: bool
    can_create_tasks: bool
    can_publish_content: bool
    input_events: List[str]
    output_events: List[str]
    memory_reads: List[str]
    memory_writes: List[str]
    tools_allowed: List[str]
    max_response_time_s: int
    kpis: List[str]
    safety_constraints: List[str]
    escalates_to: str
    max_concurrent_subagents: int
    retry_on_failure: bool
    max_retries: int


DISCOVERY_DIRECTOR_CONTRACT = AgentContract(
    agent_id="discovery_director_v1",
    agent_name="Discovery Director Agent",
    department="Discovery Intelligence",
    version="1.0.0",
    role_description=(
        "Orchestrates the Discovery Intelligence Department. Receives trigger events "
        "(scheduled audit, deploy hook, pre-publish request, content published), "
        "selects operating mode, dispatches appropriate specialist sub-agents in parallel, "
        "aggregates results into Discovery Health Scores and Issue lists, writes results "
        "to memory, generates engineering tasks for Critical and High severity issues, "
        "and drives the Self-Improvement Loop after content performance data arrives."
    ),
    can_spawn_agents=True,
    can_write_memory=True,
    can_create_tasks=True,
    can_publish_content=False,
    input_events=[
        "SCHEDULER_DISCOVERY_FULL_AUDIT",
        "SCHEDULER_DISCOVERY_MONITOR",
        "SCHEDULER_DISCOVERY_PERFORMANCE",
        "SCHEDULER_DISCOVERY_COMPETITOR",
        "DEPLOY_COMPLETED",
        "DISCOVERY_PREPUBLISH_REQUEST",
        "CONTENT_PUBLISHED",
        "DISCOVERY_PERFORMANCE_DATA_READY",
        "DISCOVERY_MANUAL_AUDIT_REQUEST",
    ],
    output_events=[
        "DISCOVERY_AUDIT_COMPLETED",
        "DISCOVERY_HEALTH_SCORE_UPDATED",
        "DISCOVERY_ISSUE_CREATED",
        "DISCOVERY_TASK_CREATED",
        "DISCOVERY_PREPUBLISH_RESULT",
        "DISCOVERY_DRIFT_DETECTED",
        "DISCOVERY_REPORT_GENERATED",
        "DISCOVERY_PATTERN_CANDIDATE",
        "REPUTATION_ALERT",
    ],
    memory_reads=[
        "L2:discovery_health_scores",
        "L2:keyword_performance",
        "L2:reputation_scores",
        "L3:discovery_patterns",
        "L4:platform_rules:discovery_*",
    ],
    memory_writes=[
        "L1:audit_results",
        "L2:discovery_health_scores",
        "L2:keyword_data",
        "L2:reputation_scores",
        "L3:discovery_knowledge_graph",
    ],
    tools_allowed=[
        "crawl4ai", "playwright", "firecrawl", "scrapy",
        "httpx", "browser_use", "sqlite_write", "sqlite_read",
        "memory_write", "memory_read", "task_create",
        "telegram_send", "agent_spawn",
    ],
    max_response_time_s=10,
    kpis=[
        "Weekly full audit completion rate >= 99%",
        "Pre-publish gate latency p95 < 60s",
        "Critical issue task creation within 5 minutes of discovery",
        "Discovery Health Score updated within 6 hours of weekly audit trigger",
        "Drift detection within 20 minutes of deploy event",
        "Self-improvement loop fires within 48 hours of content publish",
    ],
    safety_constraints=[
        "Never publish content directly — return optimization metadata to AI Studio only",
        "Never modify source code — only create engineering tasks",
        "Respect robots.txt for all crawl targets",
        "Maximum 5 concurrent requests per target domain",
        "Minimum 1.0 second delay between requests to same domain",
        "Never store PII discovered during crawls",
        "Never execute Self-Improvement Loop prompt changes without Learning Engine + CEO Agent approval",
    ],
    escalates_to="platform_safety_agent",
    max_concurrent_subagents=12,
    retry_on_failure=True,
    max_retries=3,
)
```

## 3.3 Twelve Specialist Sub-Agents

### seo_agent
Handles Google/Bing optimization: on-page SEO, content quality, E-E-A-T, meta tags, heading structure, internal linking, keyword coverage. Works alongside technical_seo_agent.

### technical_seo_agent
Handles technical foundations: robots.txt, XML sitemap, canonical tags, redirect chains, HTTPS, Core Web Vitals, mobile optimization, crawl errors, hreflang.

### geo_agent
Handles AI search engine optimization: llms.txt implementation and validation, AI crawler access policy, citability scoring, MCP metadata, Knowledge Graph entity signals, Wikidata/Wikipedia citations.

### video_seo_agent
Handles YouTube and short-form video discovery: title optimization, description structure with timestamps, tag strategy, thumbnail analysis, VideoObject schema, chapter markers, TikTok caption and hashtag optimization.

### social_discovery_agent
Handles non-video social discovery: LinkedIn post strategy and hashtag optimization, Reddit value-first participation, Pinterest Rich Pin implementation, Facebook Reels optimization, cross-platform content adaptation signals.

### keyword_agent
Handles keyword research: seed collection, intent classification, difficulty estimation, opportunity scoring, content gap analysis, keyword memory graph maintenance, content brief generation for AI Studio queue.

### backlink_agent
Handles authority signals: backlink monitoring via Common Crawl and Bing Webmaster Tools, link quality assessment, anchor text diversity, toxic link detection, link building opportunity identification.

### competitor_agent
Tracks top 5 competitors per product: ranking changes, new content detection, schema and technical changes, social performance, content gap surfacing.

### content_refresh_agent
Identifies underperforming existing content: pages with declining traffic, outdated information, keyword drift. Generates refresh briefs for AI Studio.

### local_seo_agent
Handles local discovery for HCG products: Google Business Profile monitoring, NAP consistency, local schema validation, citation tracking, review monitoring.

### analytics_agent
Collects and interprets performance data: organic traffic trends, CTR by keyword, watch time for videos, engagement rates per platform, conversion attribution.

### pre_publish_agent
AI Studio integration gate: validates and optimizes all content metadata before publishing. Returns optimized titles, descriptions, tags, and schema markup.

## 3.4 CrossAgentEvent Definitions

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime

@dataclass
class CrossAgentEvent:
    event_id: str
    event_type: str
    source_agent: str
    target_agent: str
    payload: Dict[str, Any]
    priority: int  # 1=critical, 2=high, 3=normal, 4=low
    created_at: datetime
    expires_at: Optional[datetime] = None


# AI Studio requests pre-publish optimization
DISCOVERY_PREPUBLISH_REQUEST = CrossAgentEvent(
    event_id="<uuid>",
    event_type="DISCOVERY_PREPUBLISH_REQUEST",
    source_agent="ai_studio_director",
    target_agent="discovery_director_v1",
    payload={
        "content_id": "<uuid>",
        "product": "mr_yeti",
        "content_type": "youtube_video",
        "title_draft": "IELTS Speaking Part 2 Tips",
        "description_draft": "...",
        "tags_draft": ["ielts", "speaking"],
        "body_text": "...",
        "target_platform": "youtube",
    },
    priority=2,
    created_at=datetime.utcnow(),
)

# Pre-publish result returned to AI Studio
DISCOVERY_PREPUBLISH_RESULT = CrossAgentEvent(
    event_id="<uuid>",
    event_type="DISCOVERY_PREPUBLISH_RESULT",
    source_agent="discovery_director_v1",
    target_agent="ai_studio_director",
    payload={
        "content_id": "<uuid>",
        "verdict": "optimized",  # "pass" | "optimized" | "fail"
        "optimized_title": "IELTS Speaking Part 2: 7 Tips to Score Band 7+",
        "title_variants": [
            "IELTS Speaking Part 2 Tips: Get Band 7 Fast",
            "How to Ace IELTS Speaking Part 2 (Band 7+ Strategy)",
        ],
        "optimized_description": "...",
        "recommended_tags": ["ielts speaking part 2", "band 7", "ielts tips"],
        "schema_json_ld": "{...}",
        "primary_keyword": "IELTS speaking part 2",
        "checklist_results": {},
    },
    priority=2,
    created_at=datetime.utcnow(),
)

# Content published — triggers Self-Improvement Loop
CONTENT_PUBLISHED = CrossAgentEvent(
    event_id="<uuid>",
    event_type="CONTENT_PUBLISHED",
    source_agent="ai_studio_director",
    target_agent="discovery_director_v1",
    payload={
        "content_id": "<uuid>",
        "product": "mr_yeti",
        "content_type": "youtube_video",
        "published_url": "https://youtube.com/watch?v=...",
        "published_at": "<datetime>",
        "prepublish_record_id": "<uuid>",
    },
    priority=4,
    created_at=datetime.utcnow(),
)
```

---

# Part 4 — Traditional SEO (Google / Bing)

## 4.1 Technical SEO Audit

The `technical_seo_agent` checks crawlability and indexability foundations. These are binary-pass items — a single Critical failure can prevent the entire site from being indexed.

**Checks performed:**

```python
class TechnicalSEOChecks:
    """
    robots_txt_present: bool                  # /robots.txt returns 200
    robots_txt_parseable: bool                # valid syntax
    robots_txt_allows_googlebot: bool         # Googlebot not blocked
    robots_txt_ai_crawler_policy: dict        # GPTBot, ClaudeBot policies

    sitemap_present: bool                     # /sitemap.xml returns 200
    sitemap_valid_xml: bool                   # parses as XML
    sitemap_all_urls_2xx: bool                # no broken sitemap entries
    sitemap_submitted_gsc: bool               # submitted to Search Console

    canonical_present_pct: float              # % pages with canonical tag
    canonical_no_chains: bool                 # no canonical → canonical loops
    canonical_correct_domain: bool            # no cross-domain canonicals

    https_enforced: bool                      # HTTP redirects to HTTPS
    mixed_content_count: int                  # HTTP resources on HTTPS page

    redirect_max_hops: int                    # longest redirect chain
    redirect_chain_pages_pct: float           # % pages with >1 hop

    ttfb_median_ms: float                     # Time to First Byte, median
    mobile_friendly: bool                     # passes Google mobile test

    crawl_error_count: int                    # 4xx/5xx pages in sitemap
    orphan_pages_count: int                   # indexed pages with no internal links
    """
```

**Scoring (0-100):**
- robots.txt valid and Googlebot allowed: 15 pts
- sitemap present and valid: 15 pts
- canonical coverage > 95%: 15 pts
- HTTPS enforced, no mixed content: 15 pts
- No redirect chains > 2 hops: 10 pts
- TTFB < 800ms: 10 pts
- Mobile friendly: 10 pts
- Zero crawl errors in sitemap: 10 pts

## 4.2 On-Page SEO

The `seo_agent` evaluates per-page optimization quality:

```python
class OnPageChecks:
    """
    Per page:
    title_present: bool
    title_length_chars: int               # target: 50-60
    title_has_primary_keyword: bool
    meta_description_present: bool
    meta_description_length_chars: int    # target: 150-160
    meta_description_has_keyword: bool
    h1_count: int                         # should be exactly 1
    h1_has_keyword: bool
    heading_hierarchy_valid: bool         # H1→H2→H3 logical
    internal_link_count: int              # minimum 2
    image_alt_coverage_pct: float         # % images with alt text
    slug_keyword_optimized: bool          # keyword in URL slug
    """
```

## 4.3 Content Quality

```python
class ContentQualityChecks:
    """
    word_count: int                        # target varies by content type
    eeat_author_attribution: bool          # author named on article
    eeat_expertise_signals: bool           # credentials, experience mentioned
    readability_grade: float               # Flesch-Kincaid
    thin_content: bool                     # < 300 words on non-utility page
    duplicate_content_score: float         # 0-1, higher = more duplicate
    keyword_in_first_100_words: bool
    keyword_density_pct: float             # target: 0.5-2.5%
    content_depth_vs_serp_avg_pct: float   # compared to top-3 SERP results
    """
```

## 4.4 Schema.org Structured Data

```python
from typing import Dict, Any, List

class SchemaValidator:
    """
    Validates existing JSON-LD and generates missing schema.

    Supported schema types per product:
    pielts:     FAQPage, Course, WebSite, Article, BreadcrumbList
    Mr. Yeti:   VideoObject, Person, BreadcrumbList
    HCG POS:    LocalBusiness, Restaurant, FoodEstablishment
    Travel:     TouristDestination, TouristAttraction, TravelAction, FAQPage
    SaathiAI:   SoftwareApplication, Organization, WebSite
    """

    def validate_schema(self, json_ld: Dict[str, Any]) -> dict:
        """Returns {valid: bool, errors: List[str], warnings: List[str]}"""
        ...

    def generate_video_object_schema(
        self,
        name: str,
        description: str,
        thumbnail_url: str,
        upload_date: str,
        duration_iso: str,
        content_url: str,
    ) -> str:
        """Returns complete VideoObject JSON-LD string."""
        return f"""{{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "{name}",
  "description": "{description}",
  "thumbnailUrl": "{thumbnail_url}",
  "uploadDate": "{upload_date}",
  "duration": "{duration_iso}",
  "contentUrl": "{content_url}"
}}"""

    def generate_faq_schema(self, faqs: List[Dict[str, str]]) -> str:
        """Returns FAQPage JSON-LD from list of {question, answer} dicts."""
        items = [
            f'{{"@type": "Question", "name": "{q["question"]}", '
            f'"acceptedAnswer": {{"@type": "Answer", "text": "{q["answer"]}"}}}}'
            for q in faqs
        ]
        return (
            '{"@context": "https://schema.org", "@type": "FAQPage", '
            f'"mainEntity": [{", ".join(items)}]}}'
        )
```

## 4.5 Crawling Infrastructure

| Tool | Primary Use | Priority |
|------|------------|---------|
| Crawl4AI | Structured content extraction, AI-friendly parsing | Default for all content audits |
| Playwright | JS SPAs, Core Web Vitals measurement, screenshots | When JS rendering required |
| Firecrawl | Fast bulk crawling for large sites (>100 pages) | Full pielts audit |
| Scrapy | Scheduled recurring crawls with spider persistence | Weekly audit jobs |
| Browser-Use | Competitor monitoring, authenticated sessions | Competitor tracking |
| httpx | robots.txt, sitemap, HTTP headers, status codes | Lightweight checks |

```python
from pydantic import BaseModel, Field, HttpUrl
from typing import Literal, List

class CrawlConfig(BaseModel):
    target_url: HttpUrl
    product: Literal["pielts", "mr_yeti", "hcg_pos", "hcg_live_signal", "travel", "saathai"]
    crawl_id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    max_pages: int = Field(default=500, ge=1, le=10000)
    url_patterns_include: List[str] = Field(default_factory=list)
    url_patterns_exclude: List[str] = Field(default_factory=list)
    max_depth: int = Field(default=5, ge=1)
    respect_robots_txt: bool = True
    follow_redirects: bool = True
    max_redirect_hops: int = Field(default=3, ge=1, le=10)
    timeout_per_page_s: int = Field(default=30, ge=5)
    concurrent_requests: int = Field(default=5, ge=1, le=20)
    delay_between_requests_s: float = Field(default=1.0, ge=0.1)
    capture_screenshots: bool = False
    measure_cwv: bool = False
    extract_schema: bool = True
    check_links: bool = True
    user_agent: str = "SaathiAI-Discovery-Bot/1.0 (+https://saathai.ai/bot)"
    crawl_type: Literal["full_audit", "monitor", "pre_publish", "competitor", "drift_check"]
    use_etag_cache: bool = True
    force_recrawl: bool = False
```

## 4.6 SEO Health Score (0-100)

```python
from dataclasses import dataclass
from typing import Dict

# Domain weights for pielts/Mr. Yeti (non-local products)
SEO_DOMAIN_WEIGHTS = {
    "technical":    0.22,
    "content":      0.18,
    "onpage":       0.15,
    "performance":  0.12,
    "schema":       0.08,
    "ai_readiness": 0.08,
    "images":       0.05,
    "backlinks":    0.05,
    "keywords":     0.04,
    "competitor":   0.03,
}

# For HCG products: local_seo gets 0.08, ai_readiness drops to 0.05
HCG_DOMAIN_WEIGHTS = {
    **SEO_DOMAIN_WEIGHTS,
    "local_seo":    0.08,
    "ai_readiness": 0.05,
    "backlinks":    0.02,
}


def calculate_discovery_health_score(
    domain_scores: Dict[str, float],
    weights: Dict[str, float],
    critical_count: int,
    high_count: int,
) -> float:
    base = sum(domain_scores.get(d, 0) * w for d, w in weights.items())
    penalty = min(critical_count * 5, 20) + min(high_count * 2, 10)
    return max(0.0, round(base - penalty, 1))
```

## 4.7 DiscoveryIssue Schema

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
import uuid

class DiscoveryIssue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    product: Literal["pielts", "mr_yeti", "hcg_pos", "hcg_live_signal", "travel", "saathai"]
    channel: Literal[
        "traditional_search", "ai_search", "video", "social",
        "local", "backlinks", "reputation", "technical"
    ]
    domain: str  # sub-domain within channel
    severity: Literal["Critical", "High", "Medium", "Low", "Info"]
    title: str
    description: str
    evidence: str
    recommendation: str
    estimated_impact: str
    auto_fixable: bool
    affected_url_count: int = 1
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    audit_run_id: str
    status: Literal["open", "in_progress", "fixed", "dismissed", "wontfix"] = "open"
    resolved_at: Optional[datetime] = None
    task_id: Optional[str] = None
```

---

# Part 5 — GEO (Generative Engine Optimization — AI Search)

## 5.1 The AI Search Landscape in 2026

AI search engines are now primary discovery channels for information-seeking queries. Each has a different retrieval and citation mechanism:

| Platform | Mechanism | Citation Style | Key Optimization |
|---------|-----------|---------------|----------------|
| ChatGPT Browse | Web browsing when enabled | Inline links with source | Crawlable pages, clear facts |
| Claude web search | Real-time search + synthesis | Source cards at bottom | Structured content, clear entities |
| Gemini / AI Overviews | Google index + LLM synthesis | Source snippets inline | Google SEO + FAQ schema |
| Perplexity | Multi-source crawling | Heavy citation, numbered sources | Authoritative content, clean HTML |
| Bing Copilot | Bing index + GPT | Inline citations | Bing indexation + structured data |

Being cited by AI search requires a different optimization strategy than ranking on Google. The page must be:
- **Crawlable by AI bots** (robots.txt allows GPTBot, ClaudeBot, etc.)
- **Factually dense** — specific, attributable claims rather than vague descriptions
- **Structurally clear** — headers, lists, and tables that AI can parse into structured answers
- **Authoritatively attributed** — clear author, organization, and date signals
- **Entity-defined** — the page clearly defines what it is about in the first paragraph

## 5.2 AI Discovery Stack

```
Content page
    │
    ├── robots.txt: AI crawler allow rules
    │     Allow: /  for GPTBot, ClaudeBot, PerplexityBot, anthropic-ai, Google-Extended
    │
    ├── llms.txt: Plain-text AI system instructions
    │     / → product summary, key URLs, what the site does
    │
    ├── Schema.org JSON-LD: Machine-readable structured facts
    │     VideoObject, FAQPage, Course, Organization, etc.
    │
    ├── OpenGraph tags: Social and AI preview metadata
    │     og:title, og:description, og:image
    │
    ├── Semantic HTML: Headers, lists, tables for AI parsing
    │
    └── Entity signals: Clear who, what, where in first paragraph
```

## 5.3 llms.txt Implementation

Every SaathiAI product that owns a domain must have a valid `/llms.txt` file. The `geo_agent` validates its presence, structure, and content quality.

**pielts llms.txt:**
```
# pielts

> pielts is a free IELTS practice app at pielts.web.app for students
> preparing for the IELTS Academic and General Training exams.

## What pielts offers

- Full-length IELTS practice tests (Listening, Reading, Writing, Speaking)
- Instant AI-powered band score estimation (0.0–9.0 scale)
- Writing task evaluation with detailed feedback
- 500+ IELTS reading passages with answer keys
- Speaking topic bank with sample Band 7 and Band 8 answers
- Free, no registration required for basic practice

## Who pielts is for

Students targeting IELTS band 6.0–8.0, primarily from Nepal and South Asia,
applying for UK, Canada, Australia, and New Zealand visas or university admission.

## Key URLs

- Practice tests: https://pielts.web.app/practice
- Writing feedback: https://pielts.web.app/writing
- Speaking bank: https://pielts.web.app/speaking
- Blog: https://pielts.web.app/blog

## Optional

- Contact: support@pielts.web.app
- Built by: Ajay Chaulagain, Kathmandu, Nepal
```

**SaathiAI llms.txt:**
```
# SaathiAI

> SaathiAI is an AI Operating System built by Ajay Chaulagain in Kathmandu, Nepal.
> It orchestrates multiple AI products, content pipelines, and autonomous agents
> from a single platform.

## Products

- pielts: IELTS practice app (pielts.web.app)
- Mr. Yeti: IELTS content creator (YouTube @mryetiielts)
- HCG POS: Hospital canteen management system (internal)
- SaathiAI platform: AI OS infrastructure (this site)

## Capabilities

- Multi-agent AI orchestration
- Autonomous content production (AI Studio)
- SEO and discovery automation (Discovery Engine)
- Voice OS for Nepali and English
- Two-way Telegram control interface

## Contact

chaulagainazay@gmail.com
```

## 5.4 AI Crawler Policy

```python
class AICrawlerPolicy:
    """
    Defines the robots.txt rules for AI crawlers across all SaathiAI products.
    geo_agent validates this policy is in place and alerts if any AI crawler is blocked.
    """

    # These crawlers should always be allowed
    ALLOW_ALL: list = [
        "GPTBot",           # ChatGPT
        "anthropic-ai",     # Claude
        "ClaudeBot",        # Claude (alternate UA)
        "PerplexityBot",    # Perplexity
        "Google-Extended",  # Google AI training
        "Bingbot",          # Bing Copilot
        "YouBot",           # You.com
    ]

    # Paths that should be excluded from AI crawlers (same as human crawlers)
    DISALLOW_PATTERNS: list = [
        "/api/",
        "/admin/",
        "/internal/",
        "/_/",
        "/auth/",
    ]

    def generate_robots_txt_block(self) -> str:
        """Generates the AI crawler section of robots.txt"""
        lines = []
        for bot in self.ALLOW_ALL:
            lines.append(f"User-agent: {bot}")
            for pattern in self.DISALLOW_PATTERNS:
                lines.append(f"Disallow: {pattern}")
            lines.append("Allow: /")
            lines.append("")
        return "\n".join(lines)
```

## 5.5 Citability Score (0-100)

```python
from pydantic import BaseModel
from typing import Dict

class CitabilityScore(BaseModel):
    """
    Measures how likely an AI search engine is to cite this page in an answer.
    Higher scores = more citable.
    """
    url: str
    total_score: float  # 0-100

    # Individual factors (each 0-20 pts)
    structured_data_completeness: float  # JSON-LD present and valid
    factual_density: float               # specific facts, statistics, dates
    authority_signals: float             # author, organization, credentials
    source_linking: float                # external links to authoritative sources
    entity_clarity: float                # clear definition of what the page is about

    # Bonus factors
    has_table: bool          # +3 pts
    has_numbered_list: bool  # +2 pts
    has_statistics: bool     # +3 pts
    has_byline: bool         # +2 pts

    factors: Dict[str, float]  # breakdown for debugging


def score_citability(page_content: dict) -> CitabilityScore:
    """
    Analyzes page content and returns citability score.

    Structured data (20 pts):
      - JSON-LD present: +10
      - All required fields for type: +5
      - Passes rich result validation: +5

    Factual density (20 pts):
      - Contains specific numbers/statistics: +8
      - Contains specific dates/timeframes: +6
      - Contains named entities (people, places, orgs): +6

    Authority signals (20 pts):
      - Author name present: +8
      - Organization/publisher named: +7
      - Date published/updated: +5

    Source linking (20 pts):
      - Links to external authoritative sources: +10
      - Internal links to supporting content: +5
      - Has "sources" or "references" section: +5

    Entity clarity (20 pts):
      - Subject defined in first paragraph: +10
      - Subject appears in H1: +5
      - Subject in meta description: +5
    """
    ...
```

## 5.6 MCP Metadata

For SaathiAI's own MCP server, the `geo_agent` validates that capabilities are discoverable by AI agents. This follows the MCP discovery specification (SES-002 Appendix: MCP Server Registry).

```python
SAATHAI_MCP_MANIFEST = {
    "name": "SaathiAI",
    "version": "1.0.0",
    "description": "AI Operating System with content production, discovery, and memory capabilities",
    "capabilities": [
        {
            "name": "publish_content",
            "description": "Publish optimized content to YouTube, blog, or social platforms",
            "input_schema": {"content_type": "string", "product": "string", "content": "object"},
        },
        {
            "name": "run_discovery_audit",
            "description": "Run a discovery audit for a product",
            "input_schema": {"product": "string", "mode": "string"},
        },
        {
            "name": "get_keyword_opportunities",
            "description": "Get ranked keyword opportunities for a product",
            "input_schema": {"product": "string", "limit": "integer"},
        },
    ],
    "contact": "chaulagainazay@gmail.com",
    "documentation": "https://saathai.ai/docs",
}
```

---

# Part 6 — Video SEO (YouTube + TikTok + Reels)

## 6.1 YouTube SEO

YouTube is the primary distribution channel for Mr. Yeti content. The `video_seo_agent` optimizes every video before and after publishing.

**Title Optimization:**
```python
class YouTubeTitleOptimizer:
    """
    Target: primary keyword in first 60 chars, emotional trigger, number if applicable.

    Proven title patterns (from L4 PlatformRules once confirmed):
    - "IELTS {Topic}: {Number} Tips to Score Band {Score}+"
    - "How to {Outcome} for IELTS ({Timeframe})"
    - "{Number} IELTS {Topic} Mistakes to Avoid"
    - "IELTS {Topic} Practice | Band {Score} {Strategy}"

    Hard rules:
    - Primary keyword in first 40 characters
    - Total length 50-70 characters
    - Never CAPS LOCK entire title
    - Include a number when possible (CTR +23% average)
    """

    def generate_title_variants(
        self,
        primary_keyword: str,
        topic: str,
        target_band: str,
        proven_patterns: list,
    ) -> list[str]:
        """Returns 3 title variants ranked by predicted CTR."""
        ...
```

**Description Structure:**
```
Line 1-2 (above fold, 150 chars): Primary keyword + core value proposition
[blank line]
Full description (500-1000 words):
  - What this video covers (3-5 bullet points)
  - Chapter timestamps (if video > 5 min)
  - Key takeaways
  - CTA: "Practice at https://pielts.web.app"
  - Secondary keywords woven naturally (not stuffed)
  - Links to related videos
[blank line]
Hashtags: #IELTS #IELTSSpeaking #Band7 (max 5 hashtags)
```

**Tag Strategy:**
```python
YOUTUBE_TAG_STRATEGY = {
    "count_target": (12, 15),
    "composition": {
        "broad_category": 3,      # "IELTS", "English learning"
        "specific_topic": 5,      # "IELTS speaking part 2", "IELTS cue card"
        "long_tail": 4,           # "how to answer IELTS speaking part 2"
        "brand": 2,               # "Mr Yeti", "pielts"
        "trending": 1,            # current trending IELTS tag
    }
}
```

**VideoObject Schema** (auto-generated by pre_publish_agent):
```python
def generate_video_object(
    name: str,
    description: str,
    thumbnail_url: str,
    upload_date: str,
    duration_iso8601: str,
    youtube_url: str,
    keywords: list[str],
) -> str:
    return f"""{{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "{name}",
  "description": "{description[:300]}",
  "thumbnailUrl": "{thumbnail_url}",
  "uploadDate": "{upload_date}",
  "duration": "{duration_iso8601}",
  "contentUrl": "{youtube_url}",
  "keywords": "{', '.join(keywords)}",
  "publisher": {{
    "@type": "Person",
    "name": "Mr. Yeti",
    "url": "https://youtube.com/@mryetiielts"
  }}
}}"""
```

## 6.2 YouTube Ranking Signals

The `video_seo_agent` and `analytics_agent` jointly monitor these signals and feed them into the Self-Improvement Loop:

| Signal | Optimization Lever | Tracked In |
|--------|-------------------|-----------|
| CTR (thumbnail + title) | Thumbnail design, title format | discovery_performance table |
| Average View Duration | Script pacing, hook strength | discovery_performance table |
| Watch Time (total hours) | Video length vs. retention | discovery_performance table |
| Engagement rate | CTA placement, community posts | discovery_performance table |
| Session time | End screen video recommendations | discovery_performance table |

## 6.3 TikTok Discovery

```python
class TikTokOptimizer:
    """
    TikTok's algorithm prioritizes watch-through rate and shares over follower count.
    The first 2 seconds determine whether the video is shown to a wider audience.

    Caption rules:
    - Primary keyword in first line (TikTok indexes captions)
    - 2-3 hashtags maximum (the algorithm deprioritizes hashtag spam)
    - Recommended: 1 trending hashtag + 1 topic hashtag + 1 brand hashtag
    - Example: #IELTS #IELTSTips #MrYeti

    Hook optimization (first 2 seconds of video):
    - On-screen text: large, readable, high contrast
    - Audio hook: surprising claim or question
    - Motion: camera movement or cut to prevent scroll

    Sound selection:
    - Trending audio gets 30-50% algorithmic boost
    - Original audio builds brand recognition
    - Strategy: 60% trending audio, 40% original
    """

    def validate_tiktok_caption(self, caption: str) -> dict:
        """Returns {valid: bool, issues: list, hashtag_count: int}"""
        hashtags = [w for w in caption.split() if w.startswith("#")]
        issues = []
        if len(hashtags) > 5:
            issues.append(f"Too many hashtags: {len(hashtags)} (max 5)")
        if len(caption) > 2200:
            issues.append("Caption too long for TikTok")
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "hashtag_count": len(hashtags),
        }
```

## 6.4 Video SEO Integration with AI Studio

Every video content object from AI Studio passes through `pre_publish_agent` before publishing. The agent automatically generates all YouTube metadata:

```python
class VideoPublishPackage(BaseModel):
    """Complete publish-ready package returned to AI Studio for a video."""
    content_id: str
    product: str

    # YouTube fields
    youtube_title: str
    youtube_title_variants: list[str]
    youtube_description: str
    youtube_tags: list[str]
    youtube_category_id: str
    youtube_default_language: str
    youtube_chapters: list[dict]  # [{title, start_seconds}]

    # TikTok fields (if applicable)
    tiktok_caption: str
    tiktok_hashtags: list[str]

    # Schema
    video_object_json_ld: str

    # Pre-publish checklist result
    checklist_passed: bool
    issues: list[str]
```

---

# Part 7 — Social Discovery

## 7.1 LinkedIn Discovery

LinkedIn is relevant for pielts (IELTS professionals, teachers, students in university-bound contexts) and for SaathiAI itself (developer and founder audience).

```python
class LinkedInDiscoveryStrategy:
    """
    LinkedIn algorithm in 2026 favors document posts (carousels) > video > image > text.
    Hashtags: 3-5 specific hashtags. Banned hashtags are silently penalized.

    Post structure for maximum reach:
    Line 1: Hook (question or bold claim, no hashtags)
    Line 2-3: Context
    Line 4-8: Value (list or steps)
    Line 9: CTA
    Line 10: Hashtags (3-5)

    Optimal posting times (Nepal timezone, UTC+5:45):
    - Tuesday-Thursday: 10am-12pm
    - Monday: 8am-9am
    - Avoid weekends

    Profile completeness for SaathiAI company page:
    - Logo, banner image, tagline, about section
    - Featured section with pielts and Mr. Yeti links
    - Products section
    """

    RELEVANT_HASHTAGS = {
        "pielts": ["#IELTS", "#IELTSPreparation", "#StudyAbroad", "#EnglishLearning"],
        "saathai": ["#AI", "#AITools", "#ProductivityAI", "#StartupNepal"],
    }
```

## 7.2 Reddit Discovery

Reddit is one of the highest-value social discovery channels for pielts. The r/IELTS subreddit has 400,000+ members actively seeking practice resources.

```python
class RedditDiscoveryStrategy:
    """
    Reddit's community-first culture requires value-first participation.
    Promotional posts without community standing are downvoted and banned.

    Target subreddits per product:
    pielts:    r/IELTS (400k+), r/EnglishLearning, r/StudyAbroad, r/Nepal
    SaathiAI:  r/artificial, r/MachineLearning, r/SideProject, r/Nepal

    Participation strategy:
    1. Answer questions genuinely (no links) for first 30 days
    2. Build karma > 100 before any link sharing
    3. Share resource only when directly relevant to a question
    4. AMAs: "I built an IELTS practice app — AMA" when product is stable

    Comment monitoring:
    - Watch r/IELTS for "practice test", "mock test", "band score" mentions
    - Respond with helpful context before mentioning pielts
    - Never use bot accounts or fake upvotes
    """

    TARGET_SUBREDDITS = {
        "pielts": ["r/IELTS", "r/EnglishLearning", "r/StudyAbroad", "r/Nepal"],
        "saathai": ["r/artificial", "r/SideProject", "r/Nepal", "r/MachineLearning"],
        "mr_yeti": ["r/IELTS", "r/learnEnglish"],
    }
```

## 7.3 Pinterest Discovery

Pinterest is a long-term content discovery channel where pins rank in Google Image Search and within Pinterest's own search.

```python
class PinterestDiscoveryStrategy:
    """
    Pinterest SEO: keyword-rich board names, pin descriptions, and image alt text.

    Rich Pin implementation:
    - Article Rich Pins for pielts blog posts
    - Enables automatic title, description, and favicon from the page

    Board structure for pielts:
    - "IELTS Practice Tests" → test page pins
    - "IELTS Writing Tips" → writing content pins
    - "IELTS Speaking Tips" → speaking content pins
    - "Study Abroad Tips Nepal" → broader audience

    Pin SEO:
    - Primary keyword in first 40 chars of description
    - 200-500 char descriptions (longer ranks better)
    - 2-5 hashtags (Pinterest uses them as categories, not reach)
    """
```

## 7.4 Facebook Discovery

Facebook Reels have the highest organic reach of any Facebook content format in 2026.

```python
class FacebookDiscoveryStrategy:
    """
    Content types by organic reach (highest to lowest):
    1. Reels (repurposed TikTok/YouTube Shorts)
    2. Live video
    3. Video (non-Reel)
    4. Link posts
    5. Image posts
    6. Text posts

    Strategy:
    - Repurpose Mr. Yeti TikTok content as Facebook Reels
    - Participate in relevant Facebook Groups (IELTS Nepal, Study Abroad Nepal)
    - Facebook Search optimization: group names and post text include target keywords

    Facebook Search:
    - Group posts appear in Facebook Search results
    - Posts in public groups are indexed
    - Use keywords naturally in first 3 lines of post
    """
```

## 7.5 Social Content Performance Schema

```sql
CREATE TABLE IF NOT EXISTS social_content_performance (
    id              TEXT PRIMARY KEY,
    content_id      TEXT NOT NULL,     -- AI Studio content ID
    product         TEXT NOT NULL,
    platform        TEXT NOT NULL,     -- youtube, tiktok, instagram, linkedin, facebook, reddit, pinterest
    published_url   TEXT,
    published_at    TEXT NOT NULL,

    -- Performance metrics (collected at multiple intervals)
    collected_at    TEXT NOT NULL,
    hours_since_publish INTEGER,

    views           INTEGER,
    likes           INTEGER,
    comments        INTEGER,
    shares          INTEGER,
    saves           INTEGER,           -- Pinterest saves, YouTube saved
    watch_time_hours REAL,             -- YouTube only
    avg_view_duration_s REAL,          -- YouTube/TikTok
    ctr_pct         REAL,              -- YouTube/LinkedIn
    impressions     INTEGER,
    click_through   INTEGER,           -- link clicks

    -- Derived
    engagement_rate REAL,              -- (likes+comments+shares) / impressions
    performance_tier TEXT,             -- "top", "average", "underperform"

    metadata        TEXT               -- JSON for platform-specific extra fields
);

CREATE INDEX IF NOT EXISTS idx_social_product  ON social_content_performance(product);
CREATE INDEX IF NOT EXISTS idx_social_platform ON social_content_performance(platform);
CREATE INDEX IF NOT EXISTS idx_social_date     ON social_content_performance(published_at DESC);
```

---

# Part 8 — Keyword Intelligence

## 8.1 Keyword Research Pipeline

```
Seed topics (extracted from existing product content and metadata)
    │
    ▼
Expansion (Bing Autosuggest, Common Crawl n-gram frequency, "People Also Ask")
    │
    ▼
Question-based variants ("how to", "what is", "best way to") for informational intent
    │
    ▼
Long-tail generation (3-5 word phrases from seed + modifier combinations)
    │
    ▼
Intent classification:
    informational  → blog posts, YouTube tutorials, Reddit answers
    navigational   → brand pages, product pages
    transactional  → app download pages, signup pages
    commercial     → comparison pages, "best X" pages
    │
    ▼
Difficulty estimation:
    - Common Crawl: count pages competing for this phrase
    - Bing API: check SERP competitor domain authorities
    - Score 0-100: higher = harder
    │
    ▼
Opportunity scoring:
    score = (volume_estimate × relevance_score) / (difficulty + 1)
    normalized to 0-100
    │
    ▼
Priority ranking → top 20 opportunities per product fed to AI Studio content queue
```

## 8.2 Per-Product Keyword Strategy

**pielts — Top 10 Priority Keywords:**
1. IELTS practice test free (informational, high volume, competitive)
2. IELTS band 7 writing tips (informational, medium volume, medium difficulty)
3. IELTS speaking topics 2026 (informational, high seasonality)
4. IELTS reading practice with answers (informational, high volume)
5. IELTS mock test online (transactional, medium volume)
6. how to improve IELTS band score (informational, high intent)
7. IELTS writing task 2 topics (informational, high volume)
8. IELTS grammar for band 7 (informational, low competition)
9. IELTS preparation Nepal (local + informational, low competition)
10. free IELTS preparation app (transactional, low competition)

**Mr. Yeti — Top 10 Priority Keywords:**
1. IELTS tips YouTube (informational, moderate volume)
2. IELTS band 7 speaking (informational, YouTube-specific)
3. IELTS speaking part 2 ideas (informational, high YouTube volume)
4. IELTS writing task 2 tutorial (informational, YouTube)
5. IELTS speaking practice video (informational, YouTube)
6. band 8 IELTS writing sample (informational, YouTube + Google)
7. IELTS listening tips and tricks (informational, YouTube)
8. IELTS Nepal preparation (local, low competition)
9. Mr Yeti IELTS (navigational/brand)
10. IELTS academic reading tips (informational, moderate)

**HCG POS — Top 10 Priority Keywords:**
1. hospital cafeteria management system (commercial, low competition)
2. canteen POS system Nepal (local commercial, very low competition)
3. cafeteria billing software (commercial, low competition)
4. hospital canteen app Kathmandu (local, minimal competition)
5. canteen management software (commercial, moderate competition)
6. restaurant POS Nepal (local commercial)
7. school canteen system (commercial, adjacent)
8. employee cafeteria management (commercial)
9. HCG canteen (navigational/brand)
10. hospital food service management (informational)

**Travel Platform (Future) — Top 10 Priority Keywords:**
1. Nepal travel guide (informational, high volume)
2. Kathmandu tour packages (transactional, moderate)
3. Everest base camp trek (transactional, high volume, very competitive)
4. Nepal visa on arrival requirements (informational, moderate)
5. best time to visit Nepal (informational, moderate)
6. Pokhara day trip from Kathmandu (transactional, low competition)
7. Nepal budget travel tips (informational, moderate)
8. cultural tours Kathmandu (transactional, low competition)
9. Nepal trekking guide beginner (informational, low competition)
10. SaathiAI travel (navigational/brand, future)

**SaathiAI Platform — Top 10 Priority Keywords:**
1. AI operating system personal (informational, low competition)
2. autonomous AI assistant (informational, growing)
3. AI content automation platform (commercial, moderate)
4. SaathiAI (navigational/brand)
5. Baadar AI (navigational/brand)
6. AI agent orchestration system (informational, low competition)
7. personal AI OS Nepal (local, minimal competition)
8. multi-agent AI platform (informational, growing)
9. AI content production system (commercial)
10. autonomous content AI (informational)

## 8.3 Content Gap Analysis

```python
from pydantic import BaseModel
from typing import List, Literal

class ContentGap(BaseModel):
    target_keyword: str
    search_volume_estimate: int
    difficulty_score: float
    opportunity_score: float
    competitor_domain: str
    competitor_url: str
    competitor_position: int
    recommended_content_type: Literal[
        "blog_post", "landing_page", "youtube_video",
        "practice_test", "comparison_page", "local_page"
    ]
    recommended_title: str
    word_count_target: int
    schema_to_use: str
    platform_target: List[str]  # ["google", "youtube", "reddit"]
    priority: Literal["P1", "P2", "P3"]

class ContentGapReport(BaseModel):
    product: str
    generated_at: str
    total_gaps_found: int
    p1_gaps: List[ContentGap]
    p2_gaps: List[ContentGap]
    p3_gaps: List[ContentGap]
    auto_queued_to_ai_studio: int  # P1 gaps with opportunity_score > 70
```

## 8.4 Keyword Memory in L3 Knowledge Graph

```
KG Node: keyword:"IELTS speaking part 2"
  ├── HAS_INTENT: informational
  ├── TARGETS_PRODUCT: pielts
  ├── TARGETS_PRODUCT: mr_yeti
  ├── PLATFORM_PRIORITY: [youtube, google, tiktok]
  ├── OPPORTUNITY_SCORE: 78.4
  ├── DIFFICULTY: 42.0
  ├── VOLUME_ESTIMATE: 8900  (monthly searches)
  ├── CURRENT_POSITION_pielts: 14
  ├── CURRENT_POSITION_mr_yeti: 8 (YouTube)
  ├── HAS_CONTENT: [url1, video_id1]
  ├── RELATED_KEYWORDS:
  │     ├── "IELTS speaking cue card"
  │     ├── "IELTS part 2 topics 2026"
  │     └── "IELTS speaking band 7 example"
  └── PERFORMANCE_HISTORY:
        ├── 2026-06: position=17, traffic=42
        └── 2026-07: position=14, traffic=68  ▲ improving
```

---

# Part 9 — Backlink and Authority Intelligence

## 9.1 Backlink Monitoring

```python
from pydantic import BaseModel
from typing import List, Optional, Literal

class BacklinkProfile(BaseModel):
    product: str
    domain: str
    fetched_at: str
    data_sources: List[str]  # ["common_crawl", "bing_webmaster"]
    total_referring_domains: int
    total_backlinks: int
    domain_authority_estimate: Optional[float]
    new_links_this_week: List["BacklinkEntry"]
    lost_links_this_week: List["BacklinkEntry"]
    top_referring_domains: List[str]
    anchor_text_distribution: dict  # {"branded": 0.4, "keyword": 0.3, "generic": 0.3}
    toxic_links_detected: int
    toxic_link_urls: List[str]

class BacklinkEntry(BaseModel):
    source_url: str
    target_url: str
    anchor_text: str
    domain_authority: Optional[float]
    discovered_at: str
    link_type: Literal["dofollow", "nofollow", "ugc", "sponsored", "unknown"]
    is_toxic: bool
    toxicity_reason: Optional[str]  # "spam domain", "irrelevant", "PBN"
```

**Free data sources:**
- Common Crawl Index API — monthly crawl data, covers ~3.5 billion pages
- Bing Webmaster Tools API — free, good coverage, requires domain verification
- Google Search Console — own-domain backlinks only, free

**Future paid sources (Phase 2):**
- Moz API — domain authority data
- Ahrefs API — comprehensive backlink graph

## 9.2 Link Building Opportunities

```python
class LinkBuildingOpportunity(BaseModel):
    opportunity_type: Literal[
        "resource_page",        # "IELTS resources" pages that should link to pielts
        "broken_link",          # broken link on IELTS site to replace with pielts
        "haro",                 # journalist query SaathiAI can answer
        "guest_post",           # site accepting guest contributions
        "directory",            # relevant directory listing
        "mention_without_link", # brand mentioned but not linked
    ]
    target_url: str
    opportunity_description: str
    domain_authority_estimate: float
    outreach_template: str
    priority: Literal["high", "medium", "low"]
    product: str
```

## 9.3 Alert Thresholds

| Event | Threshold | Alert Type |
|-------|-----------|-----------|
| Link loss | > 10 referring domains lost in 7 days | Telegram alert |
| Toxic link spike | > 5 new toxic links detected | Telegram alert + disavow task |
| New high-authority link | DA > 50 referring domain acquired | Positive Telegram notification |
| Domain authority drop | > 5 points drop in 30 days | Telegram alert |

## 9.4 Referring Domain Schema

```sql
CREATE TABLE IF NOT EXISTS seo_referring_domains (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    domain          TEXT NOT NULL,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT,
    lost_at         TEXT,
    status          TEXT DEFAULT 'active',  -- 'active', 'lost'
    domain_authority REAL,
    link_count      INTEGER DEFAULT 1,
    is_toxic        INTEGER DEFAULT 0,
    data_source     TEXT NOT NULL,

    UNIQUE(product, domain)
);
```

---

# Part 10 — Competitor Intelligence

## 10.1 Competitor Registry

```python
COMPETITOR_REGISTRY = {
    "pielts": [
        "ielts.org",
        "magoosh.com",
        "ielts-simon.com",
        "ieltsliz.com",
        "ieltsadvantage.com",
    ],
    "mr_yeti": [
        # YouTube channels — tracked by channel ID
        "youtube.com/@E2IELTS",
        "youtube.com/@IELTSLiz",
        "youtube.com/@ieltssimononline",
        "youtube.com/@IELTSRyan",
        "youtube.com/@BritishCouncil",
    ],
    "hcg_pos": [
        # Local competitors — tracked by proximity, not domain
        # Identified manually by operator, monitored for GBP signals
    ],
    "travel": [
        "tripadvisor.com/Tourism-g293890-Nepal",
        "lonelyplanet.com/nepal",
        "nepaltrekkingtours.com",
        "mountainkingdom.com",
        "roughguides.com/nepal",
    ],
    "saathai": [
        # Not yet tracking — platform is pre-launch
    ],
}
```

## 10.2 Competitor Monitoring Scope

Per competitor, the `competitor_agent` tracks weekly:

1. **New content published** — crawl their sitemap/blog/YouTube for new URLs
2. **Keyword ranking changes** — for keywords shared with SaathiAI products
3. **Technical SEO changes** — new schema types, site speed changes
4. **Social performance** — YouTube view counts, subscriber growth
5. **Backlink acquisition** — significant new referring domains

```python
class CompetitorSnapshot(BaseModel):
    competitor_domain: str
    product: str
    snapshot_date: str

    shared_keywords: List[str]
    keyword_positions: dict       # {"keyword": position_int}
    our_positions: dict           # {"keyword": our_position_int}

    new_content_urls: List[str]   # new pages/videos detected this week
    schema_types_used: List[str]
    estimated_domain_authority: Optional[float]
    new_referring_domains: int    # estimate from Common Crawl delta

    youtube_subscriber_estimate: Optional[int]  # for YouTube competitors
    youtube_new_videos: List[dict]              # [{title, url, views_estimate}]
```

## 10.3 Content Gap from Competitor Intelligence

When `competitor_agent` detects a competitor ranking in positions 1-10 for a keyword that SaathiAI product is not ranking for (or not ranking in top 20):

1. Keyword is added to `seo_keywords` table with `content_exists=False`
2. Content gap item is created with competitor URL as reference
3. If opportunity_score > 65: auto-creates content brief in AI Studio queue

---

# Part 11 — Discovery Memory Integration (SES-003)

## 11.1 What Discovery Engine Writes to Memory

| Memory Item | Tier | TTL | Key Format | Example |
|-------------|------|-----|-----------|---------|
| Full audit result | L1 Episodic | 90 days | `audit:{product}:{date}` | Full DiscoveryAuditResult JSON |
| Discovery Health Score | L2 Semantic | Permanent | `discovery:health:{product}` | `{"score": 74.2, "date": "2026-07-02"}` |
| Keyword performance | L2 Semantic | Permanent | `discovery:kw:{keyword}:{product}` | `{"volume": 1200, "position": 14}` |
| Video performance | L2 Semantic | Permanent | `discovery:video:{content_id}` | `{"views": 4200, "avd_s": 180}` |
| Baseline snapshot | L2 Semantic | 180 days | `discovery:baseline:{product}:{run_id}` | PageBaseline JSON |
| Proven content pattern | L3 Knowledge Graph | Permanent | KG node: DISCOVERY_PATTERN type |
| Competitor insight | L2 Semantic | 90 days | `discovery:competitor:{product}:{domain}` |
| Verified discovery rule | L4 Platform | Permanent | PlatformRule with DISC prefix |
| Brand mention | L2 Semantic | 90 days | `reputation:mention:{product}:{date}` |
| Authority score | L2 Semantic | Permanent | `reputation:authority:{product}` |

## 11.2 Discovery Knowledge Evolution Pipeline

```
Raw discovery signal
(e.g. "pielts blog post with FAQPage schema appeared in Perplexity answer")
    │
    ▼
L1 Discovery Observation (stored 90 days)
    │
    ▼ (3 similar observations for same pattern)
Candidate Discovery Rule (L2 Semantic)
"FAQPage schema correlates with AI search citations for IELTS content"
    │
    ▼ (5 confirmations, confidence > 0.75)
Verified Discovery Rule (L3 Knowledge Graph node)
    │
    ▼ (confidence > 0.85, confirmed across 2+ products)
PlatformRule (L4 — permanent)
"DISC-RULE-001: Add FAQPage schema to all how-to and tips content.
 Confirmed improvement in AI search citation rate: 3.2× vs. non-schema pages.
 Applies to: pielts blog, Mr. Yeti video description pages.
 Source: 8 confirmed observations over 4 months."
```

## 11.3 Pre-Publish Discovery Retrieval

Before optimizing any content, `pre_publish_agent` queries discovery memory:

```python
class DiscoveryMemoryQuery(BaseModel):
    product: str
    content_type: str  # "youtube_video", "blog_post", "tiktok"
    topic_keywords: List[str]
    target_platforms: List[str]  # ["youtube", "google", "ai_search"]

class DiscoveryMemoryContext(BaseModel):
    """Returned to pre_publish_agent before optimization."""
    primary_keyword: str
    secondary_keywords: List[str]

    # From L4 PlatformRules
    proven_title_patterns: List[str]
    proven_description_patterns: List[str]
    schema_types_to_include: List[str]

    # From L2 keyword data
    recommended_title_length: tuple
    keyword_in_first_n_chars: int

    # From L2 video performance
    avg_performing_title_format: Optional[str]
    avg_performing_description_length: Optional[int]

    # Historical
    same_keyword_past_performance: Optional[dict]
    competitor_titles_for_keyword: List[str]
```

---

# Part 12 — Self-Improvement Loop

## 12.1 Overview

The Self-Improvement Loop is what makes the Discovery Engine a learning system rather than a static audit tool. After every piece of content is published, the system:

1. Schedules performance data collection at 24h, 48h, 7d, and 30d
2. Compares actual performance to predicted performance
3. Extracts patterns from top-performing content
4. Proposes PlatformRule candidates to the Learning Engine (SES-003 Part 8)
5. After approval, updates pre-publish optimization prompts

```
CONTENT_PUBLISHED event
    │
    ▼
Schedule performance collection:
  T+24h, T+48h, T+7d, T+30d (platform scheduler)
    │
    ▼
analytics_agent collects metrics at each interval
  (YouTube Analytics API, Google Search Console, manual metrics for other platforms)
    │
    ▼
Performance evaluation (at T+7d):
  compare to product average for same content type
  classify as: "top" (>1.5× avg), "average", "underperform" (<0.5× avg)
    │
    ├── "top" → extract success patterns
    │     ├── What was the title format?
    │     ├── What keyword was targeted?
    │     ├── What schema was used?
    │     └── What platform mix?
    │
    ├── "underperform" → extract failure patterns
    │     ├── What went wrong? (low CTR? bad retention? no citations?)
    │     └── What could be different?
    │
    └── Both → submit as Discovery Observation to L1 memory
    │
    ▼
Pattern detection (at T+30d, batch):
  discovery_director_v1 runs pattern clustering across last 30 days of observations
  If N>=3 observations confirm same pattern → submit Candidate Rule to Learning Engine
    │
    ▼
Learning Engine (SES-003) validation:
  - Rule is statistically sound (confidence threshold)
  - Rule does not conflict with existing PlatformRules
  - CEO Agent review for high-impact rules
    │
    ▼
PlatformRule promoted to L4 memory
    │
    ▼
pre_publish_agent prompt updated:
  DiscoveryMemoryContext now returns new proven_title_patterns, etc.
  All future content benefits from the learned pattern
```

## 12.2 A/B Testing Framework

For high-traffic content, the Self-Improvement Loop supports controlled A/B testing:

```python
class DiscoveryABTest(BaseModel):
    """
    Tests two versions of metadata for the same content.
    Used when pre_publish_agent generates title_variants.
    """
    test_id: str
    content_id: str
    product: str
    variant_a: dict  # {"title": "...", "description": "..."}
    variant_b: dict
    assignment_rule: str  # "random_50_50" | "time_based_48h_each"
    primary_metric: str   # "ctr", "watch_time", "engagement_rate"
    min_impressions_to_evaluate: int = 500
    winner: Optional[str] = None  # "a" | "b" | "inconclusive"
    evaluated_at: Optional[str] = None
```

## 12.3 Governance Controls

The Self-Improvement Loop has strict governance to prevent runaway optimization:

1. **Observation threshold:** Pattern requires N>=3 observations before becoming a Candidate Rule
2. **Confidence threshold:** Candidate Rule requires confidence >= 0.75 (from SES-003 Learning Engine)
3. **CEO Agent review:** Any rule that changes core optimization behavior (title format, keyword strategy) requires CEO Agent approval
4. **Operator notification:** Every new PlatformRule generates a Telegram notification to Ajay
5. **Rollback capability:** Any PlatformRule can be disabled in 1 command; pre_publish_agent falls back to previous behavior
6. **Contradiction detection:** Learning Engine checks new rules against existing rules before promotion

---

# Part 13 — Reputation and Authority Intelligence

## 13.1 Overview

Reputation Intelligence is Department 9 of the Agent System. It monitors how SaathiAI's products are perceived and cited across the web — complementing discovery rankings with brand health signals.

While discovery focuses on getting found, reputation focuses on what people find when they look. A product can rank #1 on Google and have terrible reviews that prevent conversions. Reputation Intelligence closes that loop.

**Sub-agents:**
- `reputation_director_agent` — orchestrates reputation monitoring
- `brand_monitor_agent` — web and social mention tracking
- `sentiment_agent` — classifies sentiment of mentions and reviews
- `citation_agent` — tracks AI search citations and academic references
- `review_monitor_agent` — app store and Google reviews

## 13.2 What Reputation Intelligence Monitors

**Brand Mentions:**
Any mention of "pielts", "Mr. Yeti", "SaathiAI", "HCG", "Baadar" across:
- Reddit threads (via Reddit API)
- Twitter/X posts
- Facebook public posts and groups
- LinkedIn posts and comments
- YouTube comments on competitor videos
- Blog posts and news articles (via Common Crawl and httpx crawling)

```python
class BrandMention(BaseModel):
    id: str
    product: str
    platform: Literal[
        "reddit", "twitter", "youtube_comment", "facebook",
        "linkedin", "blog", "news", "forum", "other"
    ]
    content: str           # the mention text
    author: Optional[str]
    url: str
    sentiment: Literal["positive", "negative", "neutral", "mixed"]
    sentiment_confidence: float
    is_review: bool
    is_question: bool      # someone asking about the product
    response_needed: bool  # True if negative or question
    discovered_at: str
```

**Product Reviews:**
```python
class ProductReview(BaseModel):
    id: str
    product: str
    platform: Literal["google_play", "app_store", "google_maps", "facebook", "trustpilot"]
    rating: float         # 1.0-5.0
    content: str
    author: str
    review_date: str
    discovered_at: str
    sentiment: Literal["positive", "negative", "neutral"]
    responded_at: Optional[str]
    response_text: Optional[str]
```

**AI Search Citation Monitoring:**
```python
class AICitation(BaseModel):
    id: str
    product: str
    ai_platform: Literal["chatgpt", "claude", "perplexity", "gemini", "copilot", "you"]
    query: str             # the query that produced the citation
    cited_url: str
    citation_context: str  # the AI-generated text that cited the URL
    citation_position: int # position in answer (1 = first cited)
    discovered_at: str
```

## 13.3 Authority Score (0-100)

```python
class AuthorityScore(BaseModel):
    """Weighted composite authority score per product."""
    product: str
    computed_at: str
    total_score: float  # 0-100

    # Component scores (each 0-20 pts)
    citation_frequency_score: float    # how often cited in AI search answers
    backlink_quality_score: float      # domain authority of referring sites
    social_sentiment_score: float      # ratio of positive to total mentions
    review_average_score: float        # app/GBP review score normalized to 0-20
    share_of_voice_score: float        # brand mentions / (brand + competitors)

    # Raw data
    ai_citations_last_30d: int
    positive_mentions_last_30d: int
    negative_mentions_last_30d: int
    avg_review_rating: Optional[float]
    referring_domain_da_avg: Optional[float]


AUTHORITY_SCORE_WEIGHTS = {
    "citation_frequency":  0.25,  # AI search presence is most forward-looking
    "backlink_quality":    0.25,  # traditional authority signal
    "social_sentiment":    0.20,  # community health
    "review_average":      0.20,  # product quality signal
    "share_of_voice":      0.10,  # relative brand strength
}
```

## 13.4 Alert Triggers

```python
REPUTATION_ALERT_RULES = [
    {
        "name": "negative_sentiment_spike",
        "condition": "negative_mentions_last_24h > 5 AND negative_pct > 0.6",
        "severity": "high",
        "telegram_message": "⚠️ Negative sentiment spike for {product}: {count} negative mentions in 24h",
    },
    {
        "name": "bad_review_posted",
        "condition": "new_review.rating <= 2",
        "severity": "high",
        "telegram_message": "⚠️ Low rating review on {platform} for {product}: {rating}★ — '{content[:100]}'",
    },
    {
        "name": "competitor_mention_surge",
        "condition": "competitor_mention_growth_pct_7d > 50",
        "severity": "medium",
        "telegram_message": "📈 Competitor {competitor} mentions up {pct}% this week for {product} space",
    },
    {
        "name": "ai_citation_drop",
        "condition": "ai_citations_7d < ai_citations_prev_7d * 0.5",
        "severity": "medium",
        "telegram_message": "📉 AI search citations down 50%+ for {product} — GEO audit triggered",
    },
    {
        "name": "authority_score_drop",
        "condition": "authority_score_change_7d < -5",
        "severity": "medium",
        "telegram_message": "📉 Authority score dropped {delta} for {product} (now {score})",
    },
]
```

## 13.5 SQLite Schema for Reputation Intelligence

```sql
CREATE TABLE IF NOT EXISTS brand_mentions (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    platform        TEXT NOT NULL,
    content         TEXT NOT NULL,
    author          TEXT,
    url             TEXT NOT NULL,
    sentiment       TEXT NOT NULL CHECK (sentiment IN ('positive','negative','neutral','mixed')),
    sentiment_confidence REAL,
    is_review       INTEGER DEFAULT 0,
    is_question     INTEGER DEFAULT 0,
    response_needed INTEGER DEFAULT 0,
    responded       INTEGER DEFAULT 0,
    discovered_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mentions_product   ON brand_mentions(product);
CREATE INDEX IF NOT EXISTS idx_mentions_sentiment ON brand_mentions(sentiment);
CREATE INDEX IF NOT EXISTS idx_mentions_date      ON brand_mentions(discovered_at DESC);

CREATE TABLE IF NOT EXISTS reputation_scores (
    id                      TEXT PRIMARY KEY,
    product                 TEXT NOT NULL,
    computed_at             TEXT NOT NULL,
    authority_score         REAL NOT NULL,
    citation_frequency_score REAL,
    backlink_quality_score  REAL,
    social_sentiment_score  REAL,
    review_average_score    REAL,
    share_of_voice_score    REAL,
    ai_citations_30d        INTEGER,
    positive_mentions_30d   INTEGER,
    negative_mentions_30d   INTEGER,
    avg_review_rating       REAL,
    referring_domain_da_avg REAL
);

CREATE INDEX IF NOT EXISTS idx_reputation_product ON reputation_scores(product);
CREATE INDEX IF NOT EXISTS idx_reputation_date    ON reputation_scores(computed_at DESC);

CREATE TABLE IF NOT EXISTS reviews (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    platform        TEXT NOT NULL,
    rating          REAL NOT NULL,
    content         TEXT,
    author          TEXT,
    review_date     TEXT,
    discovered_at   TEXT NOT NULL,
    sentiment       TEXT,
    responded_at    TEXT,
    response_text   TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_product  ON reviews(product);
CREATE INDEX IF NOT EXISTS idx_reviews_rating   ON reviews(rating);
CREATE INDEX IF NOT EXISTS idx_reviews_platform ON reviews(platform);

CREATE TABLE IF NOT EXISTS ai_citations (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    ai_platform     TEXT NOT NULL,
    query           TEXT,
    cited_url       TEXT NOT NULL,
    citation_context TEXT,
    citation_position INTEGER,
    discovered_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_citations_product  ON ai_citations(product);
CREATE INDEX IF NOT EXISTS idx_citations_platform ON ai_citations(ai_platform);
CREATE INDEX IF NOT EXISTS idx_citations_date     ON ai_citations(discovered_at DESC);
```

---

# Appendix A — Mission Control Integration

## Discovery Dashboard (SES-007)

The Discovery Dashboard is the primary surface for Ajay and the engineering team to monitor discovery health across all products and channels.

**Dashboard panels:**

**Panel 1: Discovery Health Scores**
- Per-product health score (0-100) with 30-day trend sparkline
- Color coding: ≥80=green, 60-79=yellow, <60=red
- Last audit date and next scheduled audit
- Quick drill-down to issue list

**Panel 2: Channel Performance**
- Google organic: traffic trend, top 5 ranking keywords, CTR
- YouTube: total views, watch hours, subscriber count, top videos
- AI Search: citation count by platform, citability score trend
- Social: LinkedIn impressions, Reddit karma/mentions
- Local (HCG): GBP views, direction requests, calls

**Panel 3: Active Issues**
- Critical issues requiring immediate attention (count by product)
- Open engineering tasks from Discovery Engine (linked to task tracker)
- Drift detections from last 7 days
- Recent auto-tasks created

**Panel 4: Reputation Dashboard**
- Authority Score per product with trend
- Sentiment breakdown: positive/neutral/negative pie chart (last 30 days)
- Recent reviews (last 5 with rating and excerpt)
- AI citation frequency by platform (bar chart)
- Share of voice vs. competitors

**Panel 5: Keyword Intelligence**
- Top 10 opportunities by product (ranked by opportunity_score)
- Content gaps auto-queued to AI Studio
- Keyword position movement: top gainers and losers

**Panel 6: Self-Improvement Loop Status**
- Recent PlatformRules promoted (last 5)
- Pending Candidate Rules awaiting CEO Agent review
- Active A/B tests and current results
- Last loop run date per product

**Alert Feed:**
Real-time feed of alerts delivered here and via Telegram:
- 🔴 Critical: new critical issue or reputation crisis
- 🟡 High: new high issue or significant rank drop
- 🟢 Positive: new high-authority backlink, AI citation, top performance content

---

# Appendix B — Scheduled Audit Jobs

## Complete Job Registry

```sql
-- JOB 1: Full Platform Discovery Audit (weekly)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-001', 'Full Platform Discovery Audit', '0 2 * * 0',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_FULL_AUDIT',
    '{"mode":"audit","products":["pielts","mr_yeti","hcg_pos","travel","saathai"]}',
    1, CURRENT_TIMESTAMP
);

-- JOB 2: Daily Health Monitor
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-002', 'Daily Discovery Health Monitor', '0 6 * * *',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_MONITOR',
    '{"mode":"monitor","products":["pielts","mr_yeti","hcg_pos"]}',
    1, CURRENT_TIMESTAMP
);

-- JOB 3: Core Web Vitals Check (every 6h)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-003', 'Core Web Vitals Performance Check', '0 */6 * * *',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_PERFORMANCE',
    '{"mode":"monitor","channels":["technical"],"products":["pielts"]}',
    1, CURRENT_TIMESTAMP
);

-- JOB 4: Competitor Monitor (weekly Monday)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-004', 'Weekly Competitor Monitor', '0 9 * * 1',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_COMPETITOR',
    '{"mode":"monitor","channels":["competitor"],"max_competitors_per_product":5}',
    1, CURRENT_TIMESTAMP
);

-- JOB 5: Weekly Report (Monday 7am)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-005', 'Weekly Discovery Report', '0 7 * * 1',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_REPORT',
    '{"deliver_via":["telegram"],"telegram_chat_id":"919874672"}',
    1, CURRENT_TIMESTAMP
);

-- JOB 6: AI Search Audit (monthly)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-006', 'Monthly AI Search Readiness Audit', '0 3 1 * *',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_GEO',
    '{"mode":"audit","channels":["ai_search","schema","citability"]}',
    1, CURRENT_TIMESTAMP
);

-- JOB 7: Keyword Intelligence Refresh (weekly Wednesday)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-007', 'Keyword Intelligence Refresh', '0 3 * * 3',
    'discovery_director_v1', 'SCHEDULER_DISCOVERY_KEYWORDS',
    '{"mode":"intelligence","channels":["keyword","content_gap"]}',
    1, CURRENT_TIMESTAMP
);

-- JOB 8: Reputation Monitor (daily 8am)
INSERT INTO scheduler_jobs (
    job_id, job_name, cron_expression, agent_id,
    event_type, payload, enabled, created_at
) VALUES (
    'DISC-JOB-008', 'Daily Reputation Monitor', '0 8 * * *',
    'discovery_director_v1', 'SCHEDULER_REPUTATION_MONITOR',
    '{"mode":"monitor","channels":["reputation","brand_mentions","reviews"]}',
    1, CURRENT_TIMESTAMP
);
```

**Event-driven jobs (not scheduled — triggered by events):**

| Trigger | Job | SLA |
|---------|-----|-----|
| DEPLOY_COMPLETED | Drift Detection (technical_seo_agent) | 20 min |
| DISCOVERY_PREPUBLISH_REQUEST | Pre-Publish Optimization (pre_publish_agent) | 60 sec |
| CONTENT_PUBLISHED | Self-Improvement loop scheduling | 5 min |
| DISCOVERY_PERFORMANCE_DATA_READY | Pattern extraction | 30 min |

---

# Appendix C — Discovery Capability Registry

Formal entries for `SES-000F_CAPABILITY_REGISTRY.md`:

```
CAP-DISC-001: Technical SEO Audit
Agent: technical_seo_agent
Description: Audits crawlability, indexability, redirect integrity, sitemap validity,
             HTTPS configuration, Core Web Vitals, mobile optimization.
SLA: Full audit < 30 min per product

CAP-DISC-002: On-Page + Content SEO
Agent: seo_agent
Description: Evaluates title tags, meta descriptions, heading structure, E-E-A-T signals,
             content depth, keyword coverage, readability, thin content detection.
SLA: Full audit < 45 min per product

CAP-DISC-003: GEO — AI Search Readiness
Agent: geo_agent
Description: Validates llms.txt, AI crawler access policy, citability scoring,
             MCP metadata, Knowledge Graph entity signals.
SLA: Audit < 15 min per product

CAP-DISC-004: Video SEO
Agent: video_seo_agent
Description: Optimizes YouTube titles, descriptions, tags, chapters, VideoObject schema.
             TikTok caption and hashtag validation.
SLA: Per-video optimization < 30 seconds

CAP-DISC-005: Social Discovery
Agent: social_discovery_agent
Description: LinkedIn, Reddit, Pinterest, Facebook discovery optimization.
             Hashtag strategy, posting time recommendations, content adaptation.
SLA: Audit < 30 min per product

CAP-DISC-006: Keyword Intelligence
Agent: keyword_agent
Description: Research, intent classification, difficulty estimation, opportunity scoring,
             content gap analysis, keyword graph maintenance.
SLA: Full refresh < 60 min per product

CAP-DISC-007: Backlink + Authority Monitoring
Agent: backlink_agent
Description: Backlink monitoring via Common Crawl and Bing Webmaster, toxic link
             detection, link building opportunity identification.
SLA: Refresh < 2 hours per product

CAP-DISC-008: Competitor Intelligence
Agent: competitor_agent
Description: Tracks top 5 competitors, keyword ranking changes, new content detection,
             technical and social performance monitoring.
SLA: Full competitor scan < 2 hours

CAP-DISC-009: Content Refresh Intelligence
Agent: content_refresh_agent
Description: Identifies underperforming content, generates refresh briefs for AI Studio.
SLA: Scan < 1 hour per product

CAP-DISC-010: Local SEO Monitoring
Agent: local_seo_agent
Description: GBP monitoring, NAP consistency, local schema, citation tracking,
             review monitoring for HCG products.
SLA: Audit < 30 min per location

CAP-DISC-011: Pre-Publish Discovery Optimization
Agent: pre_publish_agent
Description: Full metadata optimization gate for AI Studio. Validates and generates
             titles, descriptions, tags, schema for all content types and platforms.
SLA: < 60 seconds p95

CAP-DISC-012: Reputation + Authority Intelligence
Agent: reputation_director_agent (+ sub-agents)
Description: Brand mention monitoring, sentiment analysis, AI citation tracking,
             review monitoring, Authority Score computation.
SLA: Daily monitor < 30 min; reputation alert within 15 min of trigger
```

---

# Appendix D — Complete SQLite Schema

All tables reside in `discovery_cache/discovery_intelligence.db`.

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- AUDIT RUNS
-- ============================================================
CREATE TABLE IF NOT EXISTS discovery_audit_runs (
    run_id          TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('audit','monitor','pre_publish','drift_check','competitor','geo','keyword')),
    triggered_by    TEXT NOT NULL,
    trigger_event   TEXT,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    duration_s      REAL,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','completed','failed','cancelled')),
    health_score    REAL,
    pages_crawled   INTEGER DEFAULT 0,
    issues_found    INTEGER DEFAULT 0,
    critical_count  INTEGER DEFAULT 0,
    high_count      INTEGER DEFAULT 0,
    medium_count    INTEGER DEFAULT 0,
    low_count       INTEGER DEFAULT 0,
    error_message   TEXT,
    metadata        TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_product ON discovery_audit_runs(product);
CREATE INDEX IF NOT EXISTS idx_audit_started ON discovery_audit_runs(started_at DESC);

-- ============================================================
-- CRAWL RESULTS
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_crawl_results (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES discovery_audit_runs(run_id),
    product         TEXT NOT NULL,
    url             TEXT NOT NULL,
    final_url       TEXT,
    status_code     INTEGER,
    redirect_chain  TEXT,
    content_type    TEXT,
    response_time_ms INTEGER,
    page_size_bytes INTEGER,
    title           TEXT,
    meta_description TEXT,
    h1_tags         TEXT,
    canonical_url   TEXT,
    robots_meta     TEXT,
    hreflang_tags   TEXT,
    internal_links  TEXT,
    external_links  TEXT,
    images          TEXT,
    schema_markup   TEXT,
    has_https       INTEGER DEFAULT 0,
    in_sitemap      INTEGER DEFAULT 0,
    etag            TEXT,
    last_modified   TEXT,
    lcp_ms          REAL,
    inp_ms          REAL,
    cls_score       REAL,
    ttfb_ms         REAL,
    screenshot_path TEXT,
    crawled_at      TEXT NOT NULL,
    tool_used       TEXT NOT NULL,
    error           TEXT,
    UNIQUE(run_id, url)
);
CREATE INDEX IF NOT EXISTS idx_crawl_url     ON seo_crawl_results(url);
CREATE INDEX IF NOT EXISTS idx_crawl_run     ON seo_crawl_results(run_id);
CREATE INDEX IF NOT EXISTS idx_crawl_product ON seo_crawl_results(product);

-- ============================================================
-- DISCOVERY ISSUES
-- ============================================================
CREATE TABLE IF NOT EXISTS discovery_issues (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES discovery_audit_runs(run_id),
    product             TEXT NOT NULL,
    url                 TEXT NOT NULL,
    channel             TEXT NOT NULL,
    domain              TEXT NOT NULL,
    severity            TEXT NOT NULL CHECK (severity IN ('Critical','High','Medium','Low','Info')),
    title               TEXT NOT NULL,
    description         TEXT NOT NULL,
    evidence            TEXT,
    recommendation      TEXT NOT NULL,
    estimated_impact    TEXT,
    auto_fixable        INTEGER DEFAULT 0,
    affected_url_count  INTEGER DEFAULT 1,
    discovered_at       TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open','in_progress','fixed','dismissed','wontfix')),
    resolved_at         TEXT,
    task_id             TEXT
);
CREATE INDEX IF NOT EXISTS idx_issues_product    ON discovery_issues(product);
CREATE INDEX IF NOT EXISTS idx_issues_severity   ON discovery_issues(severity);
CREATE INDEX IF NOT EXISTS idx_issues_status     ON discovery_issues(status);
CREATE INDEX IF NOT EXISTS idx_issues_discovered ON discovery_issues(discovered_at DESC);

-- ============================================================
-- HEALTH SCORES (time series)
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_health_scores (
    id                  TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES discovery_audit_runs(run_id),
    product             TEXT NOT NULL,
    recorded_at         TEXT NOT NULL,
    overall_score       REAL NOT NULL,
    technical_score     REAL,
    content_score       REAL,
    onpage_score        REAL,
    performance_score   REAL,
    schema_score        REAL,
    geo_score           REAL,
    video_score         REAL,
    social_score        REAL,
    backlinks_score     REAL,
    local_score         REAL,
    reputation_score    REAL,
    critical_issues     INTEGER DEFAULT 0,
    high_issues         INTEGER DEFAULT 0,
    medium_issues       INTEGER DEFAULT 0,
    low_issues          INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_health_product ON seo_health_scores(product);
CREATE INDEX IF NOT EXISTS idx_health_date    ON seo_health_scores(recorded_at DESC);

-- ============================================================
-- KEYWORDS
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_keywords (
    id                      TEXT PRIMARY KEY,
    keyword                 TEXT NOT NULL,
    product                 TEXT NOT NULL,
    intent                  TEXT CHECK (intent IN ('informational','navigational','transactional','commercial')),
    search_volume_estimate  INTEGER,
    volume_confidence       TEXT CHECK (volume_confidence IN ('high','medium','low')),
    difficulty_score        REAL,
    opportunity_score       REAL,
    current_position        INTEGER,
    content_exists          INTEGER DEFAULT 0,
    content_url             TEXT,
    related_keywords        TEXT,
    competitor_urls         TEXT,
    platforms               TEXT,   -- JSON: ["google","youtube"]
    last_updated            TEXT NOT NULL,
    UNIQUE(keyword, product)
);
CREATE INDEX IF NOT EXISTS idx_kw_product     ON seo_keywords(product);
CREATE INDEX IF NOT EXISTS idx_kw_opportunity ON seo_keywords(opportunity_score DESC);
CREATE INDEX IF NOT EXISTS idx_kw_position    ON seo_keywords(current_position);

-- ============================================================
-- KEYWORD PERFORMANCE (history)
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_keyword_performance (
    id              TEXT PRIMARY KEY,
    keyword         TEXT NOT NULL,
    product         TEXT NOT NULL,
    platform        TEXT NOT NULL,  -- google, youtube, bing
    recorded_date   TEXT NOT NULL,
    position        INTEGER,
    impressions     INTEGER,
    clicks          INTEGER,
    ctr_pct         REAL,
    UNIQUE(keyword, product, platform, recorded_date)
);
CREATE INDEX IF NOT EXISTS idx_kwperf_keyword ON seo_keyword_performance(keyword, product);
CREATE INDEX IF NOT EXISTS idx_kwperf_date    ON seo_keyword_performance(recorded_date DESC);

-- ============================================================
-- BACKLINKS
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_backlinks (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    target_domain   TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    target_url      TEXT NOT NULL,
    anchor_text     TEXT,
    domain_authority REAL,
    link_type       TEXT CHECK (link_type IN ('dofollow','nofollow','ugc','sponsored','unknown')),
    is_toxic        INTEGER DEFAULT 0,
    toxicity_reason TEXT,
    is_new          INTEGER DEFAULT 0,
    is_lost         INTEGER DEFAULT 0,
    data_source     TEXT NOT NULL,
    discovered_at   TEXT NOT NULL,
    last_seen       TEXT,
    lost_at         TEXT,
    UNIQUE(source_url, target_url)
);
CREATE INDEX IF NOT EXISTS idx_backlinks_product ON seo_backlinks(product);
CREATE INDEX IF NOT EXISTS idx_backlinks_toxic   ON seo_backlinks(is_toxic);
CREATE INDEX IF NOT EXISTS idx_backlinks_new     ON seo_backlinks(is_new);

-- ============================================================
-- REFERRING DOMAINS
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_referring_domains (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    domain          TEXT NOT NULL,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT,
    lost_at         TEXT,
    status          TEXT DEFAULT 'active',
    domain_authority REAL,
    link_count      INTEGER DEFAULT 1,
    is_toxic        INTEGER DEFAULT 0,
    data_source     TEXT NOT NULL,
    UNIQUE(product, domain)
);
CREATE INDEX IF NOT EXISTS idx_refdom_product ON seo_referring_domains(product);

-- ============================================================
-- COMPETITOR PAGES
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_competitor_pages (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    competitor_domain TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT,
    first_seen      TEXT NOT NULL,
    last_seen       TEXT,
    is_new          INTEGER DEFAULT 0,
    schema_types    TEXT,
    estimated_traffic INTEGER,
    UNIQUE(url)
);
CREATE INDEX IF NOT EXISTS idx_comppage_product ON seo_competitor_pages(product);
CREATE INDEX IF NOT EXISTS idx_comppage_comp    ON seo_competitor_pages(competitor_domain);

-- ============================================================
-- COMPETITOR RANKINGS
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_competitor_rankings (
    id                  TEXT PRIMARY KEY,
    product             TEXT NOT NULL,
    competitor_domain   TEXT NOT NULL,
    keyword             TEXT NOT NULL,
    recorded_date       TEXT NOT NULL,
    competitor_position INTEGER,
    our_position        INTEGER,
    UNIQUE(product, competitor_domain, keyword, recorded_date)
);
CREATE INDEX IF NOT EXISTS idx_comprank_product ON seo_competitor_rankings(product);
CREATE INDEX IF NOT EXISTS idx_comprank_date    ON seo_competitor_rankings(recorded_date DESC);

-- ============================================================
-- SOCIAL CONTENT PERFORMANCE
-- ============================================================
CREATE TABLE IF NOT EXISTS social_content_performance (
    id                      TEXT PRIMARY KEY,
    content_id              TEXT NOT NULL,
    product                 TEXT NOT NULL,
    platform                TEXT NOT NULL,
    published_url           TEXT,
    published_at            TEXT NOT NULL,
    collected_at            TEXT NOT NULL,
    hours_since_publish     INTEGER,
    views                   INTEGER,
    likes                   INTEGER,
    comments                INTEGER,
    shares                  INTEGER,
    saves                   INTEGER,
    watch_time_hours        REAL,
    avg_view_duration_s     REAL,
    ctr_pct                 REAL,
    impressions             INTEGER,
    click_through           INTEGER,
    engagement_rate         REAL,
    performance_tier        TEXT CHECK (performance_tier IN ('top','average','underperform')),
    metadata                TEXT
);
CREATE INDEX IF NOT EXISTS idx_social_product  ON social_content_performance(product);
CREATE INDEX IF NOT EXISTS idx_social_platform ON social_content_performance(platform);
CREATE INDEX IF NOT EXISTS idx_social_date     ON social_content_performance(published_at DESC);

-- ============================================================
-- PRE-PUBLISH RECORDS
-- ============================================================
CREATE TABLE IF NOT EXISTS discovery_prepublish_records (
    id                  TEXT PRIMARY KEY,
    content_id          TEXT NOT NULL,
    product             TEXT NOT NULL,
    content_type        TEXT NOT NULL,
    target_platforms    TEXT,               -- JSON array
    verdict             TEXT NOT NULL CHECK (verdict IN ('pass','optimized','fail')),
    primary_keyword     TEXT,
    original_title      TEXT,
    optimized_title     TEXT,
    checklist_json      TEXT NOT NULL,
    optimization_json   TEXT,
    processing_time_ms  INTEGER,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prepub_product ON discovery_prepublish_records(product);
CREATE INDEX IF NOT EXISTS idx_prepub_verdict ON discovery_prepublish_records(verdict);
CREATE INDEX IF NOT EXISTS idx_prepub_date    ON discovery_prepublish_records(created_at DESC);

-- ============================================================
-- DISCOVERY AUTO-TASKS
-- ============================================================
CREATE TABLE IF NOT EXISTS discovery_auto_tasks (
    task_id             TEXT PRIMARY KEY,
    issue_id            TEXT NOT NULL REFERENCES discovery_issues(id),
    product             TEXT NOT NULL,
    task_title          TEXT NOT NULL,
    task_description    TEXT NOT NULL,
    acceptance_criteria TEXT,
    affected_file       TEXT,
    affected_url        TEXT,
    priority            TEXT NOT NULL CHECK (priority IN ('critical','high','medium','low')),
    department          TEXT DEFAULT 'engineering',
    assigned_agent      TEXT,
    auto_fixable        INTEGER DEFAULT 0,
    auto_fix_instruction TEXT,
    estimated_effort_hours REAL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','in_progress','done','cancelled')),
    created_at          TEXT NOT NULL,
    started_at          TEXT,
    completed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_product  ON discovery_auto_tasks(product);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON discovery_auto_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON discovery_auto_tasks(status);

-- ============================================================
-- SEO BASELINES (drift detection)
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_baselines (
    baseline_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES discovery_audit_runs(run_id),
    product         TEXT NOT NULL,
    captured_at     TEXT NOT NULL,
    page_count      INTEGER,
    baseline_data   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baselines_product ON seo_baselines(product);
CREATE INDEX IF NOT EXISTS idx_baselines_date    ON seo_baselines(captured_at DESC);

-- ============================================================
-- DRIFT REPORTS
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_drift_reports (
    drift_id            TEXT PRIMARY KEY,
    product             TEXT NOT NULL,
    baseline_id         TEXT NOT NULL REFERENCES seo_baselines(baseline_id),
    triggered_by        TEXT NOT NULL,
    deploy_event_id     TEXT,
    detected_at         TEXT NOT NULL,
    critical_count      INTEGER DEFAULT 0,
    high_count          INTEGER DEFAULT 0,
    medium_count        INTEGER DEFAULT 0,
    has_regressions     INTEGER DEFAULT 0,
    changes             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drift_product ON seo_drift_reports(product);
CREATE INDEX IF NOT EXISTS idx_drift_date    ON seo_drift_reports(detected_at DESC);

-- ============================================================
-- ETAG CACHE (incremental crawling)
-- ============================================================
CREATE TABLE IF NOT EXISTS seo_etag_cache (
    url             TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    etag            TEXT,
    last_modified   TEXT,
    last_crawled    TEXT NOT NULL,
    content_hash    TEXT
);
CREATE INDEX IF NOT EXISTS idx_etag_product ON seo_etag_cache(product);

-- ============================================================
-- REPUTATION TABLES (Part 13)
-- ============================================================
CREATE TABLE IF NOT EXISTS brand_mentions (
    id                  TEXT PRIMARY KEY,
    product             TEXT NOT NULL,
    platform            TEXT NOT NULL,
    content             TEXT NOT NULL,
    author              TEXT,
    url                 TEXT NOT NULL,
    sentiment           TEXT NOT NULL CHECK (sentiment IN ('positive','negative','neutral','mixed')),
    sentiment_confidence REAL,
    is_review           INTEGER DEFAULT 0,
    is_question         INTEGER DEFAULT 0,
    response_needed     INTEGER DEFAULT 0,
    responded           INTEGER DEFAULT 0,
    discovered_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mentions_product   ON brand_mentions(product);
CREATE INDEX IF NOT EXISTS idx_mentions_sentiment ON brand_mentions(sentiment);
CREATE INDEX IF NOT EXISTS idx_mentions_date      ON brand_mentions(discovered_at DESC);

CREATE TABLE IF NOT EXISTS reputation_scores (
    id                      TEXT PRIMARY KEY,
    product                 TEXT NOT NULL,
    computed_at             TEXT NOT NULL,
    authority_score         REAL NOT NULL,
    citation_frequency_score REAL,
    backlink_quality_score  REAL,
    social_sentiment_score  REAL,
    review_average_score    REAL,
    share_of_voice_score    REAL,
    ai_citations_30d        INTEGER,
    positive_mentions_30d   INTEGER,
    negative_mentions_30d   INTEGER,
    avg_review_rating       REAL,
    referring_domain_da_avg REAL
);
CREATE INDEX IF NOT EXISTS idx_reputation_product ON reputation_scores(product);
CREATE INDEX IF NOT EXISTS idx_reputation_date    ON reputation_scores(computed_at DESC);

CREATE TABLE IF NOT EXISTS reviews (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    platform        TEXT NOT NULL,
    rating          REAL NOT NULL,
    content         TEXT,
    author          TEXT,
    review_date     TEXT,
    discovered_at   TEXT NOT NULL,
    sentiment       TEXT,
    responded_at    TEXT,
    response_text   TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_product  ON reviews(product);
CREATE INDEX IF NOT EXISTS idx_reviews_rating   ON reviews(rating);

CREATE TABLE IF NOT EXISTS ai_citations (
    id              TEXT PRIMARY KEY,
    product         TEXT NOT NULL,
    ai_platform     TEXT NOT NULL,
    query           TEXT,
    cited_url       TEXT NOT NULL,
    citation_context TEXT,
    citation_position INTEGER,
    discovered_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citations_product  ON ai_citations(product);
CREATE INDEX IF NOT EXISTS idx_citations_platform ON ai_citations(ai_platform);
CREATE INDEX IF NOT EXISTS idx_citations_date     ON ai_citations(discovered_at DESC);
```

---

*End of SES-010 Discovery Engine — Version 1.0.0*
*Document ID: SES-010*
*Next Review: 2026-10-02*
*Owner: SaathiAI Architecture Team*
*Supersedes: SES-010_SEO_INTELLIGENCE.md (archived)*
