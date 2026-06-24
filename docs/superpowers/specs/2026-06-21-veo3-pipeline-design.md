# Veo 3.1 Pipeline Upgrade — Design Spec
**Date:** 2026-06-21  
**Goal:** 1M views in 1 month across YouTube, TikTok, Instagram, Facebook  
**Channel:** Mr. Yeti (@pieltsapp) — IELTS education, animated Pixar-style character

---

## 1. Cost Analysis & Plan Recommendation

### Real Veo 3.1 Pricing (per second, paid tier)

| Model | 720p | 1080p | Audio included? |
|-------|------|-------|----------------|
| Veo 3.1 Standard | $0.40/sec | $0.40/sec | ✅ Yes |
| Veo 3.1 Fast | $0.10/sec | $0.12/sec | ✅ Yes |
| Veo 3.1 Lite | $0.05/sec | $0.08/sec | ✅ Yes |

### Long Video → Reels Strategy (token/cost savings)

**Key insight:** Generate ONE long video per day → extract 3 reels via ffmpeg (free).

| Approach | Seconds generated | Cost (Lite 720p) | Output |
|----------|-----------------|-----------------|--------|
| Old: 3 separate 24-sec shorts | 72 sec/day | $3.60/day | 3 reels |
| New: 1 long video (64 sec) → extract reels | 64 sec/day | **$3.20/day** | 1 long video + 3 reels + blog |
| **Savings** | **8 sec less** | **$0.40/day = $12/month** | **+1 long video + blog for free** |

### Monthly Budget

| Plan | Cost/month | Quality | Use for |
|------|-----------|---------|---------|
| Veo 3.1 Lite 720p | ~$96/month | Good (Shorts quality) | Daily reels |
| Veo 3.1 Fast 720p | ~$192/month | Better | Hero/viral videos |
| **Hybrid (recommended)** | **~$110/month** | Best value | Lite daily + Fast weekends |

### Which Google Plan to Take

**→ Google AI Studio Paid Tier (pay-as-you-go)**  
- No monthly subscription fee — just add a credit card at aistudio.google.com
- Set a spending alert at **$150/month** in Google Cloud billing
- Use **Veo 3.1 Lite** (`veo-3.1-lite-generate-preview`) for all daily content
- Use **Veo 3.1 Fast** (`veo-3.1-fast-generate-preview`) for weekend "hero" videos only
- **Do NOT use Veo 3.1 Standard** ($0.40/sec) — Lite quality is sufficient for Shorts

**Google One AI Premium ($19.99/month) is NOT needed** — that's for Gemini chat, not Veo API.

---

## 2. Long Video Strategy

### Why Long Video → Reels (not separate short generations)

1. **One generation = multiple assets**: 8 scenes assembled → 64 sec long video
2. **Reels extracted free**: ffmpeg cuts 3 × ~20 sec reels from long video (0 extra cost)
3. **YouTube long-form**: Long video uploaded as regular YouTube video (eligible for mid-roll ads)
4. **Blog from transcript**: faster-whisper transcribes the long video → auto blog post
5. **Character consistency**: Veo generates all 8 scenes in one session = same Mr. Yeti look

### Long Video Structure (64 seconds, 8 scenes × 8 sec)

```
Scene 1: HOOK — "This ONE mistake drops your IELTS score"        [0:00-0:08]
Scene 2: PROBLEM — Show the mistake visually                      [0:08-0:16]
Scene 3: AGITATION — "90% of students do this"                   [0:16-0:24]
Scene 4: TIP #1 — First solution (whiteboard)                    [0:24-0:32]
Scene 5: TIP #2 — Second solution with example                   [0:32-0:40]
Scene 6: RESULT — "With this fix, Band 7 is easy"                [0:40-0:48]
Scene 7: PROOF — Show score improvement visualization             [0:48-0:56]
Scene 8: CTA — "Follow for daily IELTS tips | pielts.web.app"   [0:56-1:04]
```

### Reels extracted (ffmpeg, free):

| Reel | Scenes | Duration | Hook | Platform |
|------|--------|----------|------|----------|
| Reel A (Hook reel) | 1-3 | 24 sec | "This mistake is killing your score" | TikTok, Reels |
| Reel B (Tip reel) | 4-6 | 24 sec | "Fix #1 and #2 for Band 7" | YouTube Shorts |
| Reel C (Full story) | 1-8 trimmed | 58 sec | Full narrative | Facebook |

---

## 3. Veo 3.1 Upgrade

### Model upgrade
- **From:** `veo-3.0-fast-generate-001`  
- **To:** `veo-3.1-lite-generate-preview` (daily) / `veo-3.1-fast-generate-preview` (weekends)

### Character consistency (3 reference images)
Pass 3 Mr. Yeti reference images per generation using `reference_type="asset"`:
1. `yeti_face.jpg` — face closeup (glasses, fur, expression)
2. `yeti_body.jpg` — full body with blazer and tie
3. `yeti_hand.jpg` — hand holding marker/pointing (teaching pose)

All 3 cropped from `client/assets/mr_yeti_reference.jpeg`.

### Native audio (remove separate Charon TTS)
Veo 3.1 generates voice + sound effects + music natively. The script's `speech` field goes directly into the Veo prompt as dialogue. Remove the separate `tts.speak_script()` step from `mr_yeti_pipeline.py`.

Veo prompt format for dialogue:
```
Mr. Yeti looks at camera and says clearly: "[speech text here]"
Sound design: warm classroom ambience, slight reverb.
```

---

## 4. Viral Hook System

10 proven templates rotated automatically (based on IELTS Advantage data: 100K–268K views each):

```python
VIRAL_HOOKS = [
    "This ONE {mistake} is dropping your IELTS {skill} score",
    "Can you tell which {skill} answer is better?",
    "Band {low} vs Band {high}: spot the difference",
    "{X} days to Band {score}. Here's what happened.",
    "Most IELTS students don't know this {topic} secret",
    "Stop saying '{wrong_word}'. Say this instead.",
    "The {method_name} method for IELTS {skill} — try it",
    "IELTS {skill} trap that catches 90% of students",
    "How this student fixed {problem} and got into {university}",
    "{Examiner} secret: what they REALLY look for in {skill}",
]
```

Script generator picks the hook template that fits the day's topic, fills it, returns it as Scene 1 speech.

---

## 5. 3× Daily Posting Schedule

| Time | Content slot | Topic focus | Platform priority |
|------|-------------|-------------|------------------|
| **7:00 AM** | Morning tip | Writing / Grammar | YouTube Shorts (morning commute) |
| **1:00 PM** | Lunch reel | Speaking / Listening | TikTok + Instagram (lunch scroll) |
| **8:00 PM** | Evening story | Exam strategy / Motivation | Facebook + YouTube (wind-down) |

7-day topic rotation:
`Writing → Speaking → Listening → Reading → Vocabulary → Grammar → Exam Strategy`

Long video generated at **7:00 AM** daily. Reels A/B/C extracted and queued for 7am/1pm/8pm auto-post.

---

## 6. Files to Change

| File | Change |
|------|--------|
| `saathi/tools/google_flow.py` | Upgrade model to Veo 3.1 Lite/Fast, add 3 reference images, add long video mode (8 scenes), add reel extraction, add viral hook system |
| `saathi/tools/mr_yeti_pipeline.py` | Remove TTS step (Veo 3.1 has native audio), add long video flow, add reel extraction and separate posting per reel |
| `saathi/scheduler.py` | Change from 1×8pm to 3× daily (7am, 1pm, 8pm), add topic rotation |
| `saathi/tools/thumbnail.py` | Already done — use Mr. Yeti template |
| `client/assets/` | Crop and save 3 reference images from mr_yeti_reference.jpeg |

### New files
| File | Purpose |
|------|---------|
| `saathi/tools/reel_extractor.py` | ffmpeg-based: extract 3 reels from long video at defined timestamps |
| `saathi/data/topic_rotation.json` | Tracks current day's topic + hook template used |

---

## 7. Success Metrics (30-day targets)

| Metric | Target | How |
|--------|--------|-----|
| Videos posted | 90 (3/day) | Automated scheduler |
| YouTube Shorts views | 500K | Viral hooks + Veo 3.1 quality |
| YouTube subscribers | 1,000 | Hit monetization threshold |
| TikTok followers | 10,000 | 3x daily + trending hashtags |
| Instagram followers | 10,000 | Reels + consistent posting |
| Facebook minutes viewed | 600K | Long videos at 8pm slot |
| Cost | <$130/month | Veo 3.1 Lite daily + Fast weekends |
