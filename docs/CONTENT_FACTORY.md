# Autonomous Content Factory — runbook

Turns SaathiAI into a daily producer of Mr. Yeti videos. **The discipline:**

| Layer | Owns | Where |
|-------|------|-------|
| **n8n** | orchestration + scheduling only — no intelligence | `automation/*.json` |
| **SaathiAI** | decisions: rank, score, validate, prompt, gate, learn — **every call records an Episode** | `saathi/content_pipeline.py` + `/api/v1/factory/*` |
| **External services** | generation only: OpenRouter (script), ElevenLabs (voice), Flux (images), Runway (render), YouTube/Meta/TikTok (publish) | called by n8n |

If a workflow contains an `if`/scoring/ranking decision, it's in the wrong place — move it behind a `/factory/*` endpoint. That separation means n8n, AI providers, or infra can be swapped later without touching the core intelligence.

## The pipeline
```
Trend → discover → research → script → assets(prompts) → [n8n: voice/images/render]
      → gate → HUMAN APPROVAL → publish → analytics → learning → better next video
```
Nothing publishes without the **Discovery Gate** passing **and** a human approving (governance). Everything — success or failure — becomes an Episode → Learning Runtime → Knowledge → Executive Intelligence.

## Endpoints (all authed with `x-saathi-token`; n8n is server-side and secret-safe)
| Endpoint | SaathiAI decides | n8n does around it |
|----------|------------------|--------------------|
| `POST /api/v1/factory/discover` | ranks raw trend signals → top 20 (`trend×relevance−saturation`) | fetch Reddit/Trends/YouTube/X, post `{signals:[…]}` |
| `POST /api/v1/factory/research` | confidence for a topic (evidence depth × relevance) | choose top topic |
| `POST /api/v1/factory/script/validate` | structure check (hook/teaching/examples/cta + length) | call OpenRouter for the script, post it |
| `POST /api/v1/factory/scenes` | generates the **Flux image prompts** per beat | call Flux with each prompt |
| `POST /api/v1/factory/gate` | Discovery Gate — blocks incomplete SEO/GEO metadata | build title/desc/tags/thumbnail, post `{metadata}` |
| `POST /api/v1/factory/failure` | records a failure Episode + emits an actionable notification | call after 3 failed retries |

Publish + approval currently run through the existing `PublishingPipeline` / Discovery gate and the CEO approval flow; wire n8n's publish step behind an approval webhook (Telegram) before going live.

## n8n folder structure
```
Automation/
  01 Discovery   02 Research   03 Script   04 Assets   05 Voice   06 Render
  07 Discovery Gate   08 Publish   09 Analytics   10 Learning
  11 Revenue   12 Notifications   13 Executive Reports   14 Error Recovery   15 Maintenance
```
Import the starter: **`automation/daily-mr-yeti.json`** (a thin daily pipeline — schedule → discover → script-validate → gate → publish stub, every decision behind a `/factory/*` call).

## Analytics → Learning (Content Intelligence)
The loop that makes AI Studio *self-improving*. n8n posts raw platform analytics; SaathiAI
normalizes, mines cohort **lift** vs the channel baseline, and promotes findings to **verified
knowledge** once enough videos agree — then into the M2 improvement pipeline. Every ingest is an Episode.

| Endpoint | Does | Access |
|----------|------|--------|
| `POST /api/content/analytics` | normalize (YouTube/Meta/TikTok/…) → store → learn → dream contribution | authed (n8n) |
| `POST /api/content/compare` | why did A beat B? (hook/thumbnail/length/time/cta diffs + metric winners) | authed |
| `GET  /api/content/recommendations` | verified knowledge as actionable recs + a "repeat this format" briefing | public read |
| `GET  /api/content/leaderboard` | best videos by performance (CTR × retention × RPM) | public read |
| `GET  /api/content/experiments` | near-tie cohorts worth an A/B test | public read |

**Content Knowledge Registry** (`content_knowledge` table) is Mr. Yeti's permanent, explainable
memory: dimension (hook / length / thumbnail / publishing / cta) × value × metric lift × sample
count × verified flag. Verified knowledge (≥10 videos, ≥5% lift) becomes a Capability Improvement
proposal on *Autonomous Content Factory* — flowing through your existing M2 promotion → Knowledge
Graph → Executive Intelligence. Example live output:
```
hook: curiosity → +28% ctr (verified, 12 videos)
thumbnail: blue → +28% ctr (verified, 12 videos)
publishing: evening → +22% watch_time (verified, 12 videos)
→ "Repeat this format: curiosity, blue, evening — recommend duplicating."
```

## Error recovery
Each n8n HTTP node: **retry ×3** (n8n's built-in retry), then `POST /api/v1/factory/failure` →
SaathiAI records a failure Episode and returns an actionable notification (Telegram) →
Executive Intelligence sees it. n8n never decides *whether* to alert; it just reports the failure.

## Verified
`tests/test_content_pipeline.py` (9 tests): topic ranking, research confidence + evidence gating,
script validation, scene-prompt generation, the Discovery Gate blocking incomplete metadata,
publish requiring gate + human approval, **every stage recording an Episode**, and failure →
Episode + notification. Full platform suite: 340 passing.

## Phase plan (from the roadmap)
1. **Week 1 — core**: discover → research → script → voice → thumbnail → gate → YouTube ✅ (decision layer built; wire n8n + provider keys)
2. **Week 2 — multi-platform**: FB / IG / TikTok / LinkedIn / Telegram / Reddit
3. **Week 3 — learning loop**: analytics → Audience Intelligence → lessons → Executive Briefing
4. **Week 4 — full autonomy**: daily schedule, retries, revenue tracking, notifications; human approval only at publish
