# v0.4.1 Production Acceptance Test (PAT)

**Definition of done:** *"SaathiAI can autonomously create, publish, learn, and
report from a complete video pipeline using reliable, local-first components."*
Not "N tests pass."

Run the **exact same loop every day for 7 days**. Do not change the pipeline or
the runner during the PAT — the point is to certify the system as it will actually
run. Fix only issues the PAT reveals; add no features.

## Daily run

```bash
# Mac-side; Chrome logged in + CDP on 9222 for the publish step
export CHROME_CDP_URL=http://localhost:9222
export SAATHI_BASE_URL=https://140-245-193-190.nip.io
export SAATHI_TOKEN=<vm token>
.venv/bin/python scripts/pat_run.py "<today's lesson>"     # generates the video on Kokoro
```

Uploads Unlisted, prefixes the title `[PAT]`. Drag test uploads into a dedicated
YouTube **"PAT / test"** playlist so they never clutter real content.

## Expected behavior (NOT failures)

- **Kokoro warm-up:** the first Kokoro generation after a fresh process may take
  **30–60 seconds** while the spaCy model and TTS weights load. `pat_run.py` is a
  fresh process each day, so the daily run includes this warm-up. This is normal —
  a slow first voice stage is **not** a failure.
- **Images are branded scene cards**, not Mr. Yeti art, until Flux is wired (v0.5).
  A card is a passing artifact.
- **No background music** until royalty-free tracks are added to `assets/music/`.
  Rendering without music is expected, not a failure.

## Morning / evening loop

- **Morning:** read the CEO briefing → check `/os` **Today's Factory** card + queue
  → review priorities → record the 4/4 scorecard (Decide · Automate · Learn · Earn).
- **Run:** `pat_run.py` — observe confidence, cost, time, queue movement, approval,
  publish, learning.
- **Evening:** review Episodes generated · Learning recorded · Executive briefing
  updates · queue health · Automation Center · Infrastructure panel. Every issue
  becomes a stabilization item.

## Merge checklist — merge + tag `v0.4.1-infrastructure` only when all are YES

| # | Question | Target |
|---|----------|--------|
| 1 | `AIStudio.run()` completed successfully several days in a row | ✅ |
| 2 | At least one video published end-to-end automatically | ✅ |
| 3 | Learning Runtime received Episodes | ✅ |
| 4 | Executive Intelligence updated from those Episodes | ✅ |
| 5 | CEO dashboard reflected reality | ✅ |
| 6 | Browser automation survived a real run | ✅ |
| 7 | Confidence scores matched judgment | ✅ |
| 8 | Costs recorded correctly | ✅ |
| 9 | Failure recommendations were useful | ✅ |

`pat_run.py` prints evidence for #1, #2, #8, #9 after each run. The rest are the
evening manual verification.

## After the PAT passes

1. Delete the 3 old Unlisted test videos (`-4dCGfbzHcQ`, `kCkc9d2CNHw`, `4OiMszmd0OY`).
2. Merge `milestone/m5.1-infrastructure` → `master`, tag `v0.4.1-infrastructure`.
3. **Freeze new architecture.** Shift to content quality + revenue (v0.5): Creative
   Director 2.0, Character Engine (a consistent Mr. Yeti), Visual Engine (Flux),
   Video Engine (HyperFrames/Runway), multi-platform repurposing, Audience
   Intelligence. Metrics that matter now: videos/week, view duration, followers,
   subscribers, revenue, learners helped.
