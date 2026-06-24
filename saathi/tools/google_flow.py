from __future__ import annotations
"""
Google Flow / Veo 2 — 3D video generation for Baadar social media.

Pipeline:
  1. Groq LLM → IELTS video script + scene prompts
  2. Veo 2 (google-genai) → 3D video clips per scene (5-8s each)
  3. moviepy → concat clips + music + Mr. Yeti text overlay
  4. Returns final MP4 path + YouTube/FB/IG metadata

Model: veo-2.0-generate-001 (AI Studio free tier)
       veo-3.0-generate-preview (if Vertex AI / waitlisted)
"""

import json
import os
import time
import base64
import tempfile
from datetime import datetime
from pathlib import Path

from .. import config

ROOT     = config.ROOT
ASSETS   = ROOT / "client" / "assets"
YETI_IMG       = ASSETS / "mr_yeti_reference.jpeg"
YETI_FACE      = ASSETS / "yeti_face.jpg"
YETI_BODY      = ASSETS / "yeti_body.jpg"
YETI_HAND      = ASSETS / "yeti_hand.jpg"
MUSIC    = ASSETS / "music" / "bg_happy.mp3"
OUT_DIR  = ROOT / "videos_output"
OUT_DIR.mkdir(exist_ok=True)

# Veo 3.1 Lite — native audio (voice + sfx + music), no separate TTS needed
# Cost: $0.05/sec at 720p — ~$3.20/day for a 64-sec long video
VEO_MODEL   = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")
GOOGLE_KEY  = config.GOOGLE_API_KEY


# ── Scene prompt builder ──────────────────────────────────────────────────────

# 7-day topic rotation (index 0=Mon … 6=Sun)
TOPIC_ROTATION = [
    "IELTS Writing",      # Monday
    "IELTS Speaking",     # Tuesday
    "IELTS Listening",    # Wednesday
    "IELTS Reading",      # Thursday
    "Vocabulary",         # Friday
    "Grammar",            # Saturday
    "Exam Strategy",      # Sunday
]

# 10 viral hook templates (rotated by week number)
VIRAL_HOOKS = [
    "This ONE mistake is dropping your IELTS {skill} score",
    "Can you spot which {skill} answer is better?",
    "Band 5 vs Band 7: spot the difference in {skill}",
    "90% of IELTS students don't know this {skill} secret",
    "Stop saying this in IELTS {skill} — say THIS instead",
    "The {skill} trick examiners don't want you to know",
    "IELTS {skill} trap that catches most students",
    "Do this for 5 days and your {skill} band will jump",
    "Why your {skill} is Band 5 even when you study hard",
    "How to get Band 7 in IELTS {skill} — step by step",
]


def _todays_topic() -> str:
    """Return today's topic from the 7-day rotation."""
    from datetime import date
    return TOPIC_ROTATION[date.today().weekday()]


def _todays_hook(skill: str) -> str:
    """Pick hook template by week number, fill in skill."""
    from datetime import date
    week = date.today().isocalendar()[1]
    template = VIRAL_HOOKS[week % len(VIRAL_HOOKS)]
    return template.format(skill=skill)


_SCENE_SYSTEM = """
You are a video director for the pielts IELTS YouTube channel featuring Mr. Yeti —
a photorealistic 3D Pixar-style white fluffy yeti in a brown tweed blazer and
round glasses who teaches IELTS.

Generate a LONG-FORM educational video script with EXACTLY 8 scenes (8 seconds each = 64 seconds total).
This single video will be used as:
  - Full 64-sec video on YouTube
  - Reel A (scenes 1-3, hook reel) on TikTok + Instagram
  - Reel B (scenes 4-6, tip reel) on YouTube Shorts
  - Reel C (scenes 7-8 + scenes 1-3 trimmed) on Facebook

Scene structure (follow exactly):
  Scene 1: HOOK    — shocking stat or question, Mr. Yeti reacts dramatically
  Scene 2: PROBLEM — show the mistake visually on whiteboard/chalkboard
  Scene 3: AGITATE — "90% of students do this" — deepen the pain
  Scene 4: TIP 1   — first solution with example on board
  Scene 5: TIP 2   — second solution with real IELTS example
  Scene 6: RESULT  — "With this fix, Band 7 is easy"
  Scene 7: PROOF   — visualise score improvement (chart or example answer)
  Scene 8: CTA     — "Follow for daily IELTS tips | pielts.web.app"

Return JSON ONLY (no markdown, no code fences):
{
  "title": "YouTube title (max 60 chars, no #Shorts — this is a long video)",
  "shorts_title": "YouTube Shorts title (max 60 chars, include #Shorts)",
  "hook": "First 5 words of Scene 1 speech",
  "topic": "one IELTS skill covered",
  "scenes": [
    {
      "id": 1,
      "duration": 8,
      "action": "what Mr. Yeti does (vivid motion description)",
      "speech": "what he says (max 20 words — will be spoken by Veo native audio)",
      "veo_prompt": "Cinematic 3D Pixar-style animated scene. Mr. Yeti IELTS teacher — large white fluffy yeti, round black glasses, brown tweed blazer, navy polka-dot tie. [DESCRIBE SPECIFIC ACTION AND SETTING IN RICH DETAIL]. Mr. Yeti says clearly: \\"[speech text here]\\". Vertical 9:16 composition. Warm studio lighting. High quality render. 8 seconds duration.",
      "setting": "classroom / exam hall / studio"
    }
  ],
  "caption_fb": "Facebook post caption (150-200 words, enthusiastic, hashtags at end)",
  "caption_ig": "Instagram caption (80-100 words, 10 hashtags)",
  "caption_tiktok": "TikTok caption (50-70 words, 5 trending hashtags)",
  "blog_title": "SEO blog post title (include IELTS + skill keyword)",
  "blog_intro": "3-sentence blog intro"
}
"""


def generate_script(topic: str = "", n_scenes: int | None = None) -> dict:
    """
    Generate a Mr. Yeti IELTS video script with viral hook via LLM.

    n_scenes: number of scenes to request.
      None / 8  → standard long-form 8-scene script (64 s Veo, or ~4 min HyperFrames)
      10        → extended long-form (10 scenes × 25-30 s ≈ 4-5 min HyperFrames)
    Injects: analytics weights, trending topics, character memory,
             winning hook patterns, and duplicate-topic check.
    """
    from ._llm_helper import ask_llm, extract_json

    # ── Duplicate check ───────────────────────────────────────────────────
    if not topic:
        topic = _todays_topic()
    try:
        from .content_library import is_duplicate_topic, get_topics_used
        if topic and is_duplicate_topic(topic):
            used = get_topics_used(days_back=60)
            from .trend_hunter import get_trending_topics
            fresh = get_trending_topics(n=5)
            for t in fresh:
                candidate = t.get("video_title", "")
                if candidate and not is_duplicate_topic(candidate):
                    topic = candidate
                    break
    except Exception:
        pass

    # ── Analytics intelligence injection ─────────────────────────────────
    analytics_context = ""
    try:
        from .analytics_loop import get_weights
        w = get_weights()
        ct = w.get("clip_type_scores", {})
        pt = w.get("pillar_scores", {})
        if ct and any(v != 1.0 for v in ct.values()):
            best_clip  = max(ct, key=lambda k: ct[k])
            best_pillar = max(pt, key=lambda k: pt[k]) if pt else ""
            hook_kws   = ", ".join(w.get("hook_patterns", [])[:5])
            opt_dur    = w.get("optimal_duration", 45)
            analytics_context = (
                f"\n\nANALYTICS INSIGHTS (from real viewer data — follow these):\n"
                f"- Best performing clip type: {best_clip} (make Scene 1 a {best_clip})\n"
                f"- Best content pillar: {best_pillar}\n"
                f"- Winning hook keywords: {hook_kws or 'mistake, secret, never, stop'}\n"
                f"- Optimal short clip duration: {opt_dur}s\n"
                f"- Top performing titles recently: "
                + ", ".join(f'"{t}"' for t in w.get("top_video_titles", [])[:3])
            )
    except Exception:
        pass

    # ── Trending topics injection ─────────────────────────────────────────
    trend_context = ""
    try:
        from .trend_hunter import get_trending_topics
        trends = get_trending_topics(n=3)
        if trends:
            trend_context = (
                "\n\nTRENDING NOW (incorporate if relevant):\n"
                + "\n".join(f"- {t.get('video_title','')}" for t in trends)
            )
    except Exception:
        pass

    # ── Comment-driven ideas injection ────────────────────────────────────
    comment_context = ""
    try:
        from .comment_miner import get_top_ideas
        ideas = get_top_ideas(n=2)
        if ideas:
            comment_context = (
                "\n\nWHAT VIEWERS ARE ASKING FOR (from real comments):\n"
                + "\n".join(f"- {i.get('comment_theme','')}: {i.get('hook_line','')}"
                            for i in ideas)
            )
    except Exception:
        pass

    # ── Character memory injection ────────────────────────────────────────
    character_context = ""
    try:
        from .character_memory import get_character_context_for_script
        character_context = "\n\n" + get_character_context_for_script()
    except Exception:
        pass

    # ── A/B hook generation ───────────────────────────────────────────────
    try:
        from .ab_tester import generate_hooks
        hooks_data = generate_hooks(topic, "hook", n=5)
        rec = hooks_data.get("recommended_a", {})
        hook_template = rec.get("title", "") or _todays_hook(topic.replace("IELTS ", "").strip())
        hook_opening  = rec.get("opening", "")
    except Exception:
        hook_template = _todays_hook(topic.replace("IELTS ", "").strip())
        hook_opening  = ""

    # Determine target scene count and per-scene duration
    _n = n_scenes if n_scenes and n_scenes > 0 else 8
    # For HyperFrames long-form, each scene is 25-30 s so the total ≈ 3-4 min.
    # For the default 8-scene Veo script each scene stays at 8 s (64 s total).
    _scene_dur = 28 if _n >= 9 else 8
    _total_s   = _n * _scene_dur

    prompt = (
        f"Create a {_n}-scene Mr. Yeti IELTS {'LONG-FORM' if _n >= 9 else 'long'} video script "
        f"({_total_s} seconds total, {_scene_dur}s per scene).\n"
        f"Topic: {topic}\n"
        f"Use this viral hook for Scene 1 title: '{hook_template}'\n"
        f"Scene 1 opening line: '{hook_opening}'\n"
        f"Make it highly educational, entertaining, and shareable. "
        f"Mr. Yeti must feel alive — use expressive actions and clear speech per scene."
        f"{analytics_context}"
        f"{trend_context}"
        f"{comment_context}"
        f"{character_context}"
    )

    raw = ask_llm(prompt, system=_SCENE_SYSTEM, timeout=90, max_tokens=4000)
    data = extract_json(raw)
    if not data or "scenes" not in data or len(data["scenes"]) < 6:
        return _fallback_script(topic)

    for i, sc in enumerate(data["scenes"]):
        sc["id"] = i + 1
        sc["duration"] = _scene_dur

    # Store the topic so we don't repeat it
    try:
        from .content_library import save_topic_used
        pillar = data.get("pillar", "horror_story")
        save_topic_used(topic, pillar)
    except Exception:
        pass

    return data


def _fallback_script(topic: str = "") -> dict:
    skill = (topic or "Writing").replace("IELTS ", "").strip()
    return {
        "title": f"IELTS {skill}: Band 7 Secret Revealed | Mr. Yeti",
        "shorts_title": f"IELTS {skill} Mistake #Shorts | Mr. Yeti",
        "hook": "Stop making this ONE mistake",
        "topic": topic or "IELTS Writing",
        "scenes": [
            {
                "id": 1, "duration": 8,
                "action": "Mr. Yeti bursts through classroom door looking shocked",
                "speech": f"Stop! This ONE {skill} mistake is costing you a whole band!",
                "veo_prompt": (
                    f"Cinematic 3D Pixar-style animated scene. Mr. Yeti IELTS teacher — "
                    f"large white fluffy yeti, round black glasses, brown tweed blazer, navy polka-dot tie. "
                    f"Bursting dramatically through a classroom door with wide shocked eyes, pointing at camera. "
                    f"Mr. Yeti says clearly: \"Stop! This ONE {skill} mistake is costing you a whole band!\" "
                    f"Vertical 9:16. Warm classroom lighting. 8 seconds."
                ),
                "setting": "classroom",
            },
            {
                "id": 2, "duration": 8,
                "action": "Mr. Yeti writes common mistake on chalkboard and underlines it",
                "speech": f"Most students use the wrong structure in IELTS {skill}.",
                "veo_prompt": (
                    f"Cinematic 3D Pixar-style. Mr. Yeti at chalkboard writing 'WRONG STRUCTURE' in large letters "
                    f"and underlining it twice with red chalk, shaking head. "
                    f"Mr. Yeti says: \"Most students use the wrong structure in IELTS {skill}.\" "
                    f"Vertical 9:16. 8 seconds."
                ),
                "setting": "classroom",
            },
            {
                "id": 3, "duration": 8,
                "action": "Mr. Yeti holds up statistic card showing 90%",
                "speech": "Ninety percent of IELTS students make this exact error every exam.",
                "veo_prompt": (
                    "Cinematic 3D Pixar-style. Mr. Yeti holding a large card that reads '90%' with a shocked expression. "
                    "Behind him, a crowd of cartoon students all making the same mistake. "
                    "Mr. Yeti says: \"Ninety percent of IELTS students make this exact error every exam.\" "
                    "Vertical 9:16. 8 seconds."
                ),
                "setting": "studio",
            },
            {
                "id": 4, "duration": 8,
                "action": "Mr. Yeti draws Tip 1 diagram on whiteboard with marker",
                "speech": f"Fix number one: always start your {skill} response with the main idea.",
                "veo_prompt": (
                    f"Cinematic 3D Pixar-style. Mr. Yeti at whiteboard drawing 'TIP 1 → MAIN IDEA FIRST' with "
                    f"arrows and stars, looking excited and teaching confidently. "
                    f"Mr. Yeti says: \"Fix number one: always start your {skill} response with the main idea.\" "
                    f"Vertical 9:16. 8 seconds."
                ),
                "setting": "classroom",
            },
            {
                "id": 5, "duration": 8,
                "action": "Mr. Yeti shows before/after example on tablet",
                "speech": "Compare these two answers — the Band 7 version is always specific!",
                "veo_prompt": (
                    "Cinematic 3D Pixar-style. Mr. Yeti holding a glowing tablet showing 'Band 5 ❌' and 'Band 7 ✅' "
                    "side by side, tapping Band 7 with enthusiasm. "
                    "Mr. Yeti says: \"Compare these two answers — the Band 7 version is always specific!\" "
                    "Vertical 9:16. 8 seconds."
                ),
                "setting": "studio",
            },
            {
                "id": 6, "duration": 8,
                "action": "Mr. Yeti gestures to rising score graphic floating in air",
                "speech": "Apply both fixes and your band score will jump — guaranteed!",
                "veo_prompt": (
                    "Cinematic 3D Pixar-style. Mr. Yeti standing next to a large floating bar chart showing "
                    "score rising from 5.5 to 7.0, pointing at it with a big smile. "
                    "Mr. Yeti says: \"Apply both fixes and your band score will jump — guaranteed!\" "
                    "Vertical 9:16. Bright motivating lighting. 8 seconds."
                ),
                "setting": "studio",
            },
            {
                "id": 7, "duration": 8,
                "action": "Mr. Yeti shows real student example with Band 7 stamp",
                "speech": "This student used the same method and scored Band 7 in one month.",
                "veo_prompt": (
                    "Cinematic 3D Pixar-style. Mr. Yeti holding a large glowing certificate stamped 'BAND 7' "
                    "with a proud expression, confetti falling around him. "
                    "Mr. Yeti says: \"This student used the same method and scored Band 7 in one month.\" "
                    "Vertical 9:16. Celebration lighting. 8 seconds."
                ),
                "setting": "studio",
            },
            {
                "id": 8, "duration": 8,
                "action": "Mr. Yeti waves at camera and points to phone",
                "speech": "Follow for daily IELTS tips and practice free at pielts.web.app!",
                "veo_prompt": (
                    "Cinematic 3D Pixar-style. Mr. Yeti waving cheerfully at camera, "
                    "a glowing phone appearing with 'pielts.web.app' and a follow button. "
                    "Mr. Yeti says: \"Follow for daily IELTS tips and practice free at pielts.web.app!\" "
                    "Vertical 9:16. Warm friendly lighting. 8 seconds."
                ),
                "setting": "studio",
            },
        ],
        "caption_fb": (
            f"🎓 IELTS {skill} mistake that's costing you a full band — watch Mr. Yeti explain the fix in 60 seconds!\n\n"
            f"✅ Tip 1: Start with your main idea\n"
            f"✅ Tip 2: Be specific, not vague\n\n"
            f"Free IELTS practice at pielts.web.app 🌐\n\n"
            f"#IELTS #IELTS{skill.replace(' ','')} #IELTSTips #pielts #MrYeti #StudyAbroad #Band7"
        ),
        "caption_ig": (
            f"This {skill} mistake is killing your IELTS score 😱\n\n"
            f"Mr. Yeti shows you the exact fix → Free practice at pielts.web.app\n\n"
            f"#IELTS #IELTS{skill.replace(' ','')} #IELTSTips #pielts #Band7 #MrYeti "
            f"#IELTSPrep #StudyAbroad #EnglishLearning #Nepal"
        ),
        "caption_tiktok": (
            f"IELTS {skill} secret 🎯 Mr. Yeti drops the fix in 60 sec!\n"
            f"Free practice → pielts.web.app\n"
            f"#IELTS #IELTSTips #MrYeti #StudyAbroad #pielts"
        ),
        "blog_title": f"The {skill} Mistake That Drops Your IELTS Score — And How to Fix It",
        "blog_intro": (
            f"Thousands of IELTS candidates lose a full band in {skill} due to one structural mistake. "
            f"Mr. Yeti breaks down the exact error and the two-step fix that takes less than a week to master. "
            f"Practice it free today at pielts.web.app."
        ),
    }


# ── Veo 2 video generation ────────────────────────────────────────────────────

def generate_scene_video(scene: dict, slug: str, reference_image_path: str = None) -> "str | None":
    """
    Call Veo 2 to generate one scene clip.
    Returns local MP4 path or None on failure.
    """
    if not GOOGLE_KEY:
        print("⚠️  No GOOGLE_API_KEY — using static image fallback for scene")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_KEY)

        # Build the generation config
        cfg = types.GenerateVideosConfig(
            aspect_ratio="9:16",           # vertical Short
            number_of_videos=1,
            enhance_prompt=True,
        )

        # Pass 3 reference images for strong Mr. Yeti character consistency.
        # Face = expressions/glasses, Body = blazer/tie silhouette, Hand = teaching pose.
        source = None
        ref_files = [YETI_FACE, YETI_BODY, YETI_HAND]
        # Fallback to single reference if crops don't exist yet
        if not all(p.exists() for p in ref_files):
            ref_files = [Path(reference_image_path or str(YETI_IMG))]

        ref_images = []
        for rp in ref_files:
            if rp.exists():
                img_b64 = base64.b64encode(rp.read_bytes()).decode()
                ref_images.append(
                    types.VideoGenerationReferenceImage(
                        reference_image=types.Image(
                            image_bytes=img_b64,
                            mime_type="image/jpeg",
                        ),
                        reference_type="ASSET",
                    )
                )

        if ref_images:
            source = types.GenerateVideosSource(reference_images=ref_images)

        print(f"  🎬 Generating scene {scene['id']}: {scene['action'][:60]}…")
        op = client.models.generate_videos(
            model=VEO_MODEL,
            prompt=scene["veo_prompt"],
            config=cfg,
            source=source,
        )

        # Poll until done (Veo is async — 8-scene video needs up to 300s)
        # Each scene is polled independently; 8 scenes × ~30-60s each in parallel on Veo's
        # servers, but we still allow generous per-scene headroom.
        max_wait = 300
        waited   = 0
        while not op.done and waited < max_wait:
            time.sleep(10)
            waited += 10
            try:
                op = client.operations.get(op)
            except Exception as poll_err:
                print(f"    ⚠️  Veo poll error ({poll_err}) — retrying in 10s")
            print(f"    ⏳ Waiting for Veo… {waited}s / {max_wait}s")

        if not op.done:
            print(f"  ⚠️  Veo timeout ({max_wait}s) for scene {scene['id']} — using static fallback")
            return None

        videos = op.response.generated_videos
        if not videos:
            print(f"  ⚠️  No video returned for scene {scene['id']}")
            return None

        # Save video bytes to disk
        out_path = OUT_DIR / f"flow_scene_{slug}_{scene['id']}.mp4"
        video_bytes = videos[0].video.video_bytes
        out_path.write_bytes(video_bytes)
        print(f"  ✅ Scene {scene['id']} saved → {out_path.name} ({len(video_bytes)//1024}KB)")
        return str(out_path)

    except Exception as e:
        print(f"  ❌ Veo error for scene {scene['id']}: {e}")
        return None


# ── Fallback: static image → video via moviepy ───────────────────────────────

def _scene_to_static_video(scene: dict, slug: str) -> str:
    """
    Fallback when Veo unavailable: render a branded quote-card as a video clip.
    Uses PIL for image, moviepy for clip.
    """
    from .quote_maker import make_quote_image
    img_path = make_quote_image(
        quote=scene.get("speech", "IELTS tip"),
        subtext="Free practice → pielts.web.app",
        pose="teaching",
        size=(1080, 1920),
        slug=f"{slug}_s{scene['id']}",
    )
    try:
        from moviepy import ImageClip
        clip = ImageClip(img_path, duration=scene.get("duration", 5))
        out = OUT_DIR / f"flow_scene_{slug}_{scene['id']}_static.mp4"
        clip.write_videofile(str(out), fps=24, codec="libx264",
                             audio_codec="aac", preset="ultrafast", logger=None)
        # Add Mr. Yeti voice to static scenes
        try:
            from .mr_yeti_voice import generate_voice
            from .video_editor import add_background_music
            speech = scene.get("speech", "")
            if speech:
                voice_path = str(OUT_DIR / f"voice_{slug}_s{scene['id']}.mp3")
                generate_voice(speech, voice_path)
                from pathlib import Path as _P
                if _P(voice_path).exists():
                    voiced = add_background_music(str(out), voice_path, music_vol=0.0, voice_vol=1.0)
                    if voiced:
                        out = _P(voiced)
        except Exception as ve:
            print(f"  ⚠️  Voice overlay failed ({ve}) — continuing without voice")
        return str(out)
    except Exception as e:
        print(f"  ⚠️  Static fallback failed: {e}")
        return img_path   # return image path as last resort


def _scene_with_fallback(scene: dict, slug: str) -> str:
    """Try backup_video chain (Runway→Kling→MiniMax→Pika→static), then _scene_to_static_video."""
    try:
        from .backup_video import generate_with_fallback
        path = generate_with_fallback(scene, f"{slug}_s{scene.get('id','x')}", preferred="runway")
        if path:
            return path
    except Exception as e:
        print(f"  ⚠️  backup_video chain failed ({e})")
    return _scene_to_static_video(scene, slug)


# ── Assemble clips → final Short ─────────────────────────────────────────────

def assemble_video(clip_paths: list[str], script: dict, slug: str,
                   has_native_audio: bool = False) -> str:
    """
    Concatenate scene clips, optionally add music, return final MP4.

    has_native_audio=True  → Veo clips already have voice + music embedded.
                             DO NOT add bg_happy.mp3 (would cause double audio).
    has_native_audio=False → Static/HyperFrames clips are silent; add music.
    """
    try:
        from moviepy import (
            VideoFileClip, AudioFileClip,
            concatenate_videoclips,
        )

        clips = []
        for p in clip_paths:
            if p and Path(p).exists() and p.endswith(".mp4"):
                try:
                    clips.append(VideoFileClip(p).resized((1080, 1920)))
                except Exception:
                    pass

        if not clips:
            print("⚠️  No valid clips — using static fallback video")
            from .quote_maker import make_quote_video
            return make_quote_video(
                script.get("hook", "IELTS tip"),
                "Free practice → pielts.web.app",
                slug=slug,
            )

        final = concatenate_videoclips(clips, method="compose")

        # Only add background music for silent (non-Veo) clips.
        # Veo 3.1 already embeds voice + music natively — adding more = double audio.
        if not has_native_audio and MUSIC.exists() and final.duration > 0:
            try:
                audio = AudioFileClip(str(MUSIC)).subclipped(0, final.duration)
                audio = audio.with_volume_scaled(0.25)   # 25% — background only
                final = final.with_audio(audio)
                print("🎵 Background music added (static mode)")
            except Exception as e:
                print(f"⚠️  Music add failed: {e}")
        elif has_native_audio:
            print("🔇 Skipping music — Veo native audio preserved")

        out_path = OUT_DIR / f"google_flow_{slug}.mp4"
        final.write_videofile(
            str(out_path),
            fps=30,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            logger=None,
        )
        if not out_path.exists() or out_path.stat().st_size < 1024:
            raise RuntimeError(f"moviepy wrote no output to {out_path}")
        print(f"✅ Final video → {out_path.name} ({out_path.stat().st_size//1024}KB)")
        return str(out_path)

    except Exception as e:
        print(f"❌ Assembly error: {e}")
        from .quote_maker import make_quote_video
        return make_quote_video(
            script.get("hook", "IELTS tip"),
            "pielts.web.app",
            slug=slug,
        )


# ── Full pipeline ─────────────────────────────────────────────────────────────

def generate_full_video(topic: str = "", use_veo: bool = True) -> dict:
    """
    End-to-end: script → Veo 3D clips → assemble → return metadata.

    Returns:
      {
        ok: bool,
        video_path: str,       # final MP4
        title: str,            # YouTube title
        caption_fb: str,
        caption_ig: str,
        blog_title: str,
        blog_intro: str,
        scenes_generated: int,
        method: "veo" | "static",
        slug: str,
      }
    """
    slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n🎬 Google Flow pipeline — slug: {slug}")

    # Step 1: Generate script
    print("📝 Step 1: Generating script via Groq LLM…")
    script = generate_script(topic)
    scenes = script.get("scenes", [])
    print(f"   → {len(scenes)} scenes: {script.get('title','')}")

    # Step 2: Generate video clips
    clip_paths = []
    method = "static"

    if use_veo and GOOGLE_KEY:
        print(f"🎬 Step 2: Generating {len(scenes)} Veo 2 clips…")
        for scene in scenes:
            path = generate_scene_video(scene, slug)
            if path:
                clip_paths.append(path)
                method = "veo"
            else:
                # Veo failed → backup_video chain (Runway→Kling→static)
                fallback = _scene_with_fallback(scene, slug)
                clip_paths.append(fallback)
    else:
        print("🖼️  Step 2: Static fallback (no GOOGLE_API_KEY or Veo disabled)…")
        for scene in scenes:
            fallback = _scene_with_fallback(scene, slug)
            clip_paths.append(fallback)

    # Step 3: Run full editing pipeline (stitch → captions → music → shorts)
    print("🎞️  Step 3: Full editing pipeline (stitch → Whisper → captions → music → Shorts)…")
    try:
        from .video_editor import run_full_edit_pipeline
        edit_result = run_full_edit_pipeline(
            scene_clips=[p for p in clip_paths if p],
            slug=slug,
        )
        final_path = edit_result.get("ready_to_publish") or edit_result.get("master", "")
        shorts     = edit_result.get("shorts", [])
        thumbnail  = edit_result.get("thumbnail", "")
    except Exception as e:
        print(f"  ⚠ Editing pipeline error: {e} — falling back to simple assembly")
        final_path = assemble_video(clip_paths, script, slug,
                                    has_native_audio=(method == "veo"))
        shorts, thumbnail = [], ""

    return {
        "ok":                True,
        "video_path":        final_path,
        "shorts":            shorts,
        "thumbnail":         thumbnail,
        "title":             script.get("title", "IELTS Tips | Mr. Yeti"),
        "shorts_title":      script.get("shorts_title", script.get("title", "IELTS Tips #Shorts")),
        "hook":              script.get("hook", ""),
        "topic":             script.get("topic", ""),
        "caption_fb":        script.get("caption_fb", ""),
        "caption_ig":        script.get("caption_ig", ""),
        "caption_tiktok":    script.get("caption_tiktok", script.get("caption_ig", "")),
        "blog_title":        script.get("blog_title", ""),
        "blog_intro":        script.get("blog_intro", ""),
        "scenes_generated":  len(clip_paths),
        "method":            method,
        "slug":              slug,
        "veo_model":         VEO_MODEL if method == "veo" else "static",
    }


# ── Post-process: strip Google Flow audio → replace with good music ───────────

def replace_audio(video_path: str, output_path: str = None) -> str:
    """
    Strip Google Flow's AI audio from a video and replace with bg_happy.mp3.
    Returns the output MP4 path.
    """
    import subprocess
    vp = Path(video_path)
    out = Path(output_path) if output_path else vp.parent / f"{vp.stem}_clean.mp4"
    music = ASSETS / "music" / "bg_happy.mp3"

    try:
        if not music.exists():
            # fallback — just strip audio, no music
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", str(vp), "-an", "-c:v", "copy", str(out)],
                capture_output=True, timeout=180,
            )
        else:
            # Strip original audio, add bg music at low volume, loop music to fit video
            r = subprocess.run([
                "ffmpeg", "-y",
                "-i", str(vp),
                "-stream_loop", "-1", "-i", str(music),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-af", "volume=0.20",        # 20% volume — background only
                "-shortest",
                str(out)
            ], capture_output=True, timeout=180)
        if r.returncode != 0:
            print(f"⚠️  replace_audio ffmpeg error: {r.stderr.decode()[:200]}")
            return video_path  # return original on failure
    except subprocess.TimeoutExpired:
        print("⚠️  replace_audio timed out — returning original")
        return video_path

    if not out.exists() or out.stat().st_size < 1024:
        print(f"⚠️  replace_audio output missing/empty — returning original")
        return video_path

    print(f"✅ Audio replaced → {out.name} ({out.stat().st_size//1024}KB)")
    return str(out)
