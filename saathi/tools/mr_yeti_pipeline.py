"""
Mr. Yeti Video Pipeline — daily end-to-end automation.

Flow (runs at 8am via scheduler):
  1. Google Flow / Veo → generate 9:16 Short MP4  (≤60s)
  2. Upload to YouTube as a Short (via n8n webhook)
  3. Upload to TikTok via Content Posting API
  4. Send Telegram with results + video preview

Also exposes `run_pipeline()` so Baadar chat can trigger on demand.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from .. import config

OUT_DIR = config.ROOT / "videos_output"
OUT_DIR.mkdir(exist_ok=True)

QUEUE_FILE = config.ROOT / "data" / "mr_yeti_queue.json"


# ── Ensure Short is truly ≤60 s ──────────────────────────────────────────────

def _trim_to_60s(video_path: str) -> str:
    """If the video is longer than 60 s, hard-trim it. Returns (possibly new) path."""
    p = Path(video_path)
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(p)],
            capture_output=True, text=True, timeout=30,
        )
        dur = float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        dur = 0

    if dur <= 60 or dur == 0:
        return video_path

    out = p.parent / f"{p.stem}_60s.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(p), "-t", "59",
        "-c:v", "copy", "-c:a", "copy", str(out),
    ], capture_output=True, timeout=120)
    return str(out) if out.exists() else video_path


# ── YouTube upload helper ─────────────────────────────────────────────────────

def _upload_youtube(video_path: str, title: str, description: str, tags: str) -> dict:
    try:
        from . import content_studio
        from .. import connections
        cfg = connections.get_all().get("youtube", {})
        if not cfg.get("connected"):
            return {"status": "skipped", "reason": "YouTube not connected"}
        return content_studio.publish_to_youtube(video_path, title, description, tags)
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ── TikTok upload helper ──────────────────────────────────────────────────────

def _upload_tiktok(video_path: str, title: str, description: str) -> dict:
    try:
        from .tiktok_post import token_ok, token_expired, post_and_mark
        if token_expired():
            return {"status": "skipped", "reason": "TikTok token expired — go to Baadar Settings → TikTok → Re-authenticate"}
        if not token_ok():
            return {"status": "skipped", "reason": "TikTok not connected — visit Settings → TikTok"}
        today = datetime.now().strftime("%Y-%m-%d")
        result = post_and_mark(today, video_path, title, description)
        return result
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ── Instagram Reels upload ────────────────────────────────────────────────────

def _pad_video_to_min_duration(video_path: str, min_secs: int = 15) -> str:
    """Loop-extend video to at least min_secs using ffmpeg (no re-encode of video stream)."""
    p = Path(video_path)
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(p)],
            capture_output=True, text=True, timeout=15,
        )
        dur = float(r.stdout.strip() or 0)
    except Exception:
        dur = 0
    if dur >= min_secs or dur == 0:
        return video_path
    out = p.parent / f"{p.stem}_padded.mp4"
    loops = int(min_secs / dur) + 1
    subprocess.run([
        "ffmpeg", "-y", "-stream_loop", str(loops), "-i", str(p),
        "-t", str(min_secs), "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p", str(out),
    ], capture_output=True, timeout=120)
    return str(out) if out.exists() else video_path


def _upload_instagram_reel(video_path: str, caption: str) -> dict:
    """Upload video as Instagram Reel via Meta Resumable Upload API (no public URL needed)."""
    try:
        from . import meta_post
        from .. import connections

        cfg = connections.get_all().get("instagram", {})
        if not cfg.get("connected"):
            return {"status": "skipped", "reason": "Instagram not connected"}

        # Instagram requires minimum ~15s for Reels; pad short HyperFrames videos
        video_path = _pad_video_to_min_duration(video_path, min_secs=15)

        ig_caption = (
            f"{caption}\n\n"
            f"🎓 Free IELTS practice → pielts.web.app\n"
            f"#IELTS #IELTSTips #MrYeti #pielts #StudyAbroad #IELTSCoach #Reels"
        )
        # Pass local file path — meta_post.post_instagram_reel detects it
        # and uses the resumable direct upload (no tunnel, no hosting needed)
        return meta_post.post_instagram_reel(video_path, ig_caption)
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}



# ── Facebook video post helper ───────────────────────────────────────────────

def _upload_facebook_video(video_path: str, caption: str) -> dict:
    """Post video to Facebook page via Graph API."""
    try:
        from .. import connections
        cfg = connections.get_all().get("facebook", {})
        token   = cfg.get("page_access_token", "")
        page_id = cfg.get("page_id", "")
        if not token or not page_id:
            return {"status": "skipped", "reason": "Facebook not connected"}

        vp = Path(video_path)
        if not vp.exists():
            return {"status": "error", "error": f"Video file not found: {video_path}"}
        if vp.stat().st_size < 10 * 1024:
            return {"status": "error", "error": f"Video file too small ({vp.stat().st_size} bytes): {video_path}"}

        import httpx

        # Retry loop — transient network errors are common on large uploads
        last_err = ""
        for attempt in range(3):
            try:
                with open(video_path, "rb") as f:
                    r = httpx.post(
                        f"https://graph.facebook.com/v19.0/{page_id}/videos",
                        data={"description": caption, "access_token": token},
                        files={"source": ("video.mp4", f, "video/mp4")},
                        timeout=300,
                    )
                d = r.json()
                if d.get("id"):
                    return {"status": "published", "video_id": d["id"]}
                last_err = str(d)[:200]
                print(f"  ⚠️  Facebook upload attempt {attempt+1} returned no id: {last_err}")
                if attempt < 2:
                    import time; time.sleep(5)
            except Exception as req_err:
                last_err = str(req_err)[:200]
                print(f"  ⚠️  Facebook upload attempt {attempt+1} error: {last_err}")
                if attempt < 2:
                    import time; time.sleep(5)
        return {"status": "error", "error": last_err}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


# ── Slot-based posting (called by scheduler at 1pm and 8pm) ──────────────────

def post_slot(slot: str) -> dict:
    """
    Post clips for a specific daily time slot (Stage 1 Growth Strategy).

    Schedule:
      "7am"  → 2 Shorts → YouTube Shorts + TikTok
      "12pm" → 2 Shorts → YouTube Shorts + Instagram
      "5pm"  → 2 Shorts → TikTok + Instagram
      "8pm"  → Long video → YouTube (full) + Reel → Facebook

    All reels extracted from today's master video by run_pipeline() at 8am.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    q = _load_queue()
    entry = next((e for e in reversed(q) if e.get("date") == today), None)
    if not entry:
        return {"ok": False, "error": "No video generated today yet — run pipeline first"}

    reels        = entry.get("reels", {})
    clips_by_slot = entry.get("clips_by_slot", {})
    flow         = entry

    def _best_video(*keys: str, slot: str = "") -> str:
        # For HyperFrames long videos, prefer the slot-matched extracted clip first
        if slot and clips_by_slot.get(slot):
            candidate = clips_by_slot[slot]
            if Path(candidate).exists() and Path(candidate).stat().st_size > 10 * 1024:
                return candidate
        for k in keys:
            candidate = reels.get(k) or entry.get(k, "")
            if candidate and Path(candidate).exists() and Path(candidate).stat().st_size > 10 * 1024:
                return candidate
        return entry.get("short_path") or entry.get("video_path", "")

    caption_ig = flow.get("caption_ig", "")
    caption_tt = flow.get("caption_tiktok", caption_ig)
    title_tt   = flow.get("shorts_title", flow.get("title", "IELTS Tips")).replace("#Shorts","").strip()
    yt_short_title = flow.get("shorts_title", flow.get("title", "IELTS Tips #Shorts"))
    if "#Shorts" not in yt_short_title:
        yt_short_title = yt_short_title.rstrip(".") + " #Shorts"
    tags = "IELTS,IELTSTips,MrYeti,pielts,StudyAbroad,IELTSPrep,Band7,Shorts"

    def _telegram(msg: str):
        try:
            from .n8n_tools import send_telegram
            send_telegram(msg)
        except Exception:
            pass

    if slot == "7am":
        # Hook clip → YouTube Shorts + TikTok
        video = _best_video("reel_a", "short_path", slot="7am")
        yt = _upload_youtube(video, yt_short_title, caption_ig, tags)
        tt = _upload_tiktok(video, title_tt, caption_tt)
        _telegram(
            f"🌅 7am slot posted!\n"
            f"▶️ YouTube Shorts: {yt.get('status','?')}\n"
            f"🎵 TikTok: {'✅' if tt.get('ok') else tt.get('reason','?')}"
        )
        return {"ok": True, "slot": "7am", "youtube_short": yt, "tiktok": tt}

    elif slot == "12pm":
        # Tip clip → YouTube Shorts + Instagram
        video = _best_video("reel_b", "short_path", slot="12pm")
        yt = _upload_youtube(video, yt_short_title, caption_ig, tags)
        ig = _upload_instagram_reel(video, caption_ig)
        _telegram(
            f"☀️ 12pm slot posted!\n"
            f"▶️ YouTube Shorts: {yt.get('status','?')}\n"
            f"📸 Instagram: {ig.get('status','?')}"
        )
        return {"ok": True, "slot": "12pm", "youtube_short": yt, "instagram": ig}

    elif slot == "5pm":
        # Quiz/funny clip → TikTok + Instagram
        video = _best_video("reel_c", "reel_a", "short_path", slot="5pm")
        tt = _upload_tiktok(video, title_tt, caption_tt)
        ig = _upload_instagram_reel(video, caption_ig)
        _telegram(
            f"🌆 5pm slot posted!\n"
            f"🎵 TikTok: {'✅' if tt.get('ok') else tt.get('reason','?')}\n"
            f"📸 Instagram: {ig.get('status','?')}"
        )
        return {"ok": True, "slot": "5pm", "tiktok": tt, "instagram": ig}

    elif slot == "8pm":
        # Long video → YouTube (full) + Facebook reel
        video_fb  = _best_video("reel_c", "video_path", "short_path", slot="8pm")
        video_yt  = entry.get("video_path") or video_fb
        caption_fb = flow.get("caption_fb", caption_ig)
        title_long = flow.get("title", "IELTS Tips | Mr. Yeti")
        description = (
            f"{caption_fb}\n\n"
            f"📄 FREE Band 7 Cheatsheet → https://pielts.web.app\n"
            f"🎓 Free IELTS practice tests → https://pielts.web.app\n"
            f"📱 Follow @pieltsapp for daily tips\n\n"
            f"#IELTS #IELTSTips #MrYeti #pielts #Band7 #StudyAbroad #IELTSPrep"
        )
        fb = _upload_facebook_video(video_fb, caption_fb + "\n\n📄 FREE Band 7 Cheatsheet → pielts.web.app")
        yt = _upload_youtube(video_yt, title_long, description,
                             "IELTS,IELTSTips,MrYeti,pielts,Band7,StudyAbroad,IELTSPrep")
        _telegram(
            f"🌙 8pm slot posted!\n"
            f"▶️ YouTube (long): {yt.get('status','?')}\n"
            f"📘 Facebook: {fb.get('status','?')}"
        )
        return {"ok": True, "slot": "8pm", "youtube_long": yt, "facebook": fb}

    # Legacy aliases
    elif slot == "1pm":
        return post_slot("12pm")

    return {"ok": False, "error": f"Unknown slot: {slot}. Use: 7am, 12pm, 5pm, 8pm"}


# ── Analytics feedback loop ───────────────────────────────────────────────────

_ANALYTICS_LOG = config.ROOT / "data" / "yeti_analytics.json"

def _log_analytics_entry(date: str, results: dict):
    """Log each video's metadata for weekly analytics feedback."""
    import json as _json
    entries = []
    if _ANALYTICS_LOG.exists():
        try: entries = _json.loads(_ANALYTICS_LOG.read_text())
        except Exception: entries = []

    entries.append({
        "date": date,
        "title": results.get("title", ""),
        "method": results.get("method", ""),
        "youtube": results.get("youtube", {}).get("status", "?"),
        "tiktok": results.get("tiktok", {}).get("status", "?"),
        "instagram": results.get("instagram_reel", {}).get("status", "?"),
        "thumbnail": bool(results.get("thumbnail")),
    })
    _ANALYTICS_LOG.write_text(_json.dumps(entries[-90:], indent=2))  # keep 90 days


# ── Chalkboard captions (embedded-captions skill, chalkboard identity) ───────

SKILL_SCRIPTS = Path.home() / ".claude" / "skills" / "embedded-captions" / "scripts"
HF_DEPS = Path("/tmp/caption_deps")   # puppeteer+sharp installed here once


def _auto_hero_word(words: list[dict]) -> str:
    """Pick the best hero word from transcript — prefer IELTS-related terms."""
    PRIORITY = ["IELTS", "Band", "Writing", "Speaking", "Reading", "Listening",
                "Score", "Task", "Essay", "Grammar", "Vocabulary", "Coach",
                "Goals", "Together", "Practice", "Strategy"]
    word_texts = [w.get("text", "").strip(".,!?") for w in words]
    for p in PRIORITY:
        for wt in word_texts:
            if wt.lower() == p.lower():
                return wt
    # fall back to last content word
    return word_texts[-1] if word_texts else "IELTS"


def _apply_chalkboard_captions(video_path: str, date_slug: str) -> str:
    """
    Run embedded-captions `chalkboard` identity on a video.
    Returns path to final_fx.mp4, or raises on failure.
    """
    import tempfile, shutil

    if not SKILL_SCRIPTS.exists():
        raise FileNotFoundError(f"embedded-captions skill not found at {SKILL_SCRIPTS}")

    # Set up hyperframes CLI symlink once
    hf_cli_link = Path.home() / "Downloads/hyperframes/packages/cli/dist/cli.js"
    if not hf_cli_link.exists():
        npx_cli = Path.home() / ".npm/_npx/702923228c2ce1e6/node_modules/hyperframes/dist/cli.js"
        if npx_cli.exists():
            hf_cli_link.parent.mkdir(parents=True, exist_ok=True)
            hf_cli_link.symlink_to(npx_cli)

    proj = Path(tempfile.mkdtemp(prefix=f"yeti_caps_{date_slug}_"))
    try:
        shutil.copy2(video_path, proj / "source.mp4")

        env = os.environ.copy()
        env["HYPERFRAMES_ROOT"] = str(HF_DEPS if HF_DEPS.exists() else Path.home() / "Downloads/hyperframes")

        # Step 1: matte + transcribe in parallel
        mp = subprocess.Popen(["node", str(SKILL_SCRIPTS / "matte.cjs"), str(proj)], env=env)
        tp = subprocess.Popen(["node", str(SKILL_SCRIPTS / "transcribe.cjs"), str(proj)], env=env)
        mp.wait(timeout=600)
        tp.wait(timeout=300)

        # Step 2: build theme.json from transcript
        transcript_path = proj / "transcript.json"
        if not transcript_path.exists():
            raise RuntimeError("transcribe.cjs produced no transcript.json")
        with open(transcript_path) as f:
            tx = json.load(f)
        words = tx.get("words", [])
        hero = _auto_hero_word(words)

        # Build lines (1-4 words each at clause boundaries)
        lines, chunk = [], []
        for w in words:
            if w.get("text", "").strip(".,!?").lower() == hero.lower():
                if chunk:
                    lines.append(chunk)
                    chunk = []
                continue   # hero word goes in hero.match, not lines
            chunk.append(w["text"])
            if len(chunk) >= 4 or w["text"].endswith((".", "!", "?")):
                lines.append(chunk)
                chunk = []
        if chunk:
            lines.append(chunk)

        # Emphasis words: IELTS-adjacent nouns that aren't the hero
        MINORS = {"Band", "Writing", "Speaking", "Reading", "Listening",
                  "Score", "Yeti", "Goals", "Together", "Practice"}
        minors = [w["text"] for w in words
                  if w["text"].strip(".,!?") in MINORS
                  and w["text"].strip(".,!?").lower() != hero.lower()]

        theme_data = {
            "dna": "chalkboard",
            "width": 1080,
            "height": 1920,
            "lines": lines,
            "hero": {"match": hero},
        }
        if minors:
            theme_data["minors"] = list(dict.fromkeys(minors))  # dedupe, preserve order

        with open(proj / "theme.json", "w") as f:
            json.dump(theme_data, f, indent=2)

        # Step 3: compile
        r = subprocess.run(
            ["node", str(SKILL_SCRIPTS / "make-theme.cjs"), str(proj)],
            env=env, capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            raise RuntimeError(f"make-theme.cjs failed: {r.stderr[:300]}")

        # Step 4: render
        r = subprocess.run(
            ["bash", str(SKILL_SCRIPTS / "render-theme.sh"), str(proj)],
            env=env, capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise RuntimeError(f"render-theme.sh failed: {r.stderr[:300]}")

        final = proj / "final_fx.mp4"
        if not final.exists():
            final = proj / "final.mp4"
        if not final.exists():
            raise RuntimeError("render produced no final mp4")

        # Copy to output dir
        out_name = Path(video_path).stem + "_chalk.mp4"
        out_path = OUT_DIR / out_name
        shutil.copy2(final, out_path)

        # Upload to R2 and clean up local copy
        from .r2_storage import upload_file as _r2_upload, is_configured as _r2_ok
        if _r2_ok():
            r2_url = _r2_upload(out_path, f"mr_yeti/{out_name}", "video/mp4")
            try:
                out_path.unlink()
            except Exception:
                pass
            return r2_url

        return str(out_path)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


# ── Queue helpers ─────────────────────────────────────────────────────────────

def _load_queue() -> list:
    try: return json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
    except Exception: return []

def _save_queue(q: list):
    """Write queue atomically (temp file + rename) to prevent corruption on crash."""
    import tempfile
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_FILE.parent / f".mr_yeti_queue_tmp_{os.getpid()}.json"
    try:
        tmp.write_text(json.dumps(q, indent=2, ensure_ascii=False))
        tmp.replace(QUEUE_FILE)  # atomic on POSIX filesystems
    except Exception as e:
        print(f"⚠️  Queue save failed: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(topic: str = "", force: bool = False,
                 renderer: str = "auto") -> dict:
    """
    Full Mr. Yeti pipeline: generate → YouTube Shorts → TikTok → Telegram.
    renderer: "auto" | "veo" | "hyperframes"
      auto = try Veo first; fall back to HyperFrames if no GOOGLE_API_KEY or Veo fails
    """
    """
    Full Mr. Yeti pipeline: generate → YouTube Shorts → TikTok → Telegram.
    Safe to call multiple times (idempotent unless force=True).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    q = _load_queue()

    # idempotency check
    if not force and any(e["date"] == today and e.get("done") for e in q):
        return {"ok": True, "skipped": True, "reason": "Already ran today"}

    # Use top-performing topics from analytics feedback if no topic specified
    if not topic:
        try:
            import json as _j
            fb = config.ROOT / "data" / "content_feedback.json"
            if fb.exists():
                data = _j.loads(fb.read_text())
                top = data.get("top_topics_last_week", [])
                if top:
                    import random
                    topic = f"Similar to: {random.choice(top)}"
                    print(f"📊 Using analytics feedback topic: {topic}")
        except Exception:
            pass

    results: dict = {"date": today, "done": False}

    # ── Step 1: Generate video ────────────────────────────────────────────────
    use_veo = renderer in ("veo", "auto")
    use_hf  = renderer == "hyperframes"
    flow    = None

    if not use_hf and use_veo:
        print("🎬 Mr. Yeti Pipeline — Step 1: Generate video via Google Flow / Veo")
        try:
            from .google_flow import generate_full_video
            flow = generate_full_video(topic=topic, use_veo=True)
        except Exception as e:
            print(f"⚠️  Google Flow failed ({e}) — falling back to HyperFrames")
            flow = None

    if not flow or not flow.get("ok") or not flow.get("video_path"):
        print("🎞️  Mr. Yeti Pipeline — Using HyperFrames renderer (long-form, 8 scenes ≈ 3-4 min)")
        try:
            from .hyperframes import generate_and_render
            flow = generate_and_render(topic=topic, long=True)
            # normalise key name
            if flow.get("ok") and "path" in flow and "video_path" not in flow:
                flow["video_path"] = flow.pop("path")
        except Exception as e:
            print(f"⚠️  HyperFrames failed ({e}) — trying backup_video static fallback")
            flow = None

    if not flow or not flow.get("ok") or not flow.get("video_path"):
        print("🛟  Mr. Yeti Pipeline — Backup video generator (static FFmpeg fallback)")
        try:
            from .backup_video import generate_with_fallback
            scene = {"topic": topic or "IELTS Band 7 tips", "speech": "Master IELTS with Mr. Yeti!"}
            slug = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = generate_with_fallback(scene, slug, preferred="static")
            if backup_path and Path(backup_path).exists():
                flow = {
                    "ok": True,
                    "video_path": backup_path,
                    "title": f"IELTS Tips | Mr. Yeti | {datetime.now().strftime('%b %d')}",
                    "shorts_title": f"IELTS Tips | Mr. Yeti #Shorts",
                    "method": "static",
                    "caption_fb": "Today's IELTS tip from Mr. Yeti! 🎓 Free practice → pielts.web.app",
                    "caption_ig": "Today's IELTS tip! 🎓 pielts.web.app",
                }
            else:
                return {"ok": False, "error": "All renderers failed including static fallback"}
        except Exception as e:
            return {"ok": False, "error": f"All renderers failed. Backup: {e}"}

    if not flow or not flow.get("ok") or not flow.get("video_path"):
        return {"ok": False, "error": "All renderers failed", "raw": flow}

    raw_path = flow["video_path"]
    results["video_path"]   = raw_path
    results["title"]        = flow.get("title", "IELTS Tips | Mr. Yeti")
    results["shorts_title"] = flow.get("shorts_title", flow.get("title", "IELTS Tips #Shorts"))
    results["method"]       = flow.get("method", "static")

    # ── Step 1a: Extract clips / reels from long video ───────────────────────
    reels = {}
    if flow.get("method") == "veo":
        print("✂️  Step 1a: Extracting reels from long Veo video via ffmpeg…")
        try:
            from .reel_extractor import extract_reels
            slug_today = today.replace("-", "")
            reels = extract_reels(raw_path, slug_today, out_dir=OUT_DIR)
            results["reels"] = reels
            if reels.get("ok"):
                print(f"  ✅ 3 reels extracted")
        except Exception as e:
            print(f"⚠️  Reel extraction failed ({e}) — using full video for all platforms")

    elif flow.get("method") == "hyperframes":
        print("✂️  Step 1a: Extracting 4 slot clips from long HyperFrames video…")
        try:
            from .clip_extractor import extract_clips
            clips_list = extract_clips(raw_path, out_dir=OUT_DIR, n_clips=4)
            # Store as both a list and a slot-keyed dict for easy lookup
            clips_by_slot = {c["slot"]: c["path"] for c in clips_list if c.get("ok")}
            results["clips"] = clips_list
            results["clips_by_slot"] = clips_by_slot
            # Also populate reels keys so the existing _valid_video() logic works:
            #   reel_a → 7am clip (hook) → TikTok + Instagram
            #   reel_b → 12pm clip (tip)  → YouTube Shorts
            #   reel_c → 5pm/8pm clip     → Facebook / extra slot
            if clips_by_slot.get("7am"):
                reels["reel_a"] = clips_by_slot["7am"]
            if clips_by_slot.get("12pm"):
                reels["reel_b"] = clips_by_slot["12pm"]
            if clips_by_slot.get("5pm"):
                reels["reel_c"] = clips_by_slot["5pm"]
            results["reels"] = reels
            print(f"  ✅ {len(clips_by_slot)} clips extracted for slots: {list(clips_by_slot.keys())}")
        except Exception as e:
            print(f"⚠️  Clip extraction failed ({e}) — using full video for all platforms")

    # Long video title (no #Shorts) for YouTube full video
    yt_long_title = results["title"]
    # Shorts title for YouTube Shorts reel
    yt_title = results["shorts_title"]
    if "#Shorts" not in yt_title and "#shorts" not in yt_title:
        yt_title = yt_title.rstrip(".") + " #Shorts"

    description = (
        f"{flow.get('caption_fb', '')}\n\n"
        f"📄 FREE Band 7 Cheatsheet → https://pielts.web.app\n"
        f"🎓 Free IELTS practice tests → https://pielts.web.app\n"
        f"📱 Follow @pieltsapp on TikTok, Instagram, YouTube for daily tips\n\n"
        f"#IELTS #IELTSTips #MrYeti #pielts #StudyAbroad #IELTSPrep #Band7 #IELTSBand7"
    ).strip()

    tags = "IELTS,IELTSTips,MrYeti,pielts,StudyAbroad,IELTSPrep,Band7,IELTSBand7,Shorts,YouTubeShorts"

    # ── Step 1b: Voiceover (only for static/HyperFrames — Veo 3.1 has native voice) ──
    if flow.get("method") != "veo":
        print("🎙️  Step 1b: Generating voiceover (en-GB-RyanNeural) for static renderer")
        try:
            from .tts import speak_script, add_voiceover
            script_dict = flow.get("script") or {
                "hook": flow.get("title", ""),
                "scenes": [{"speech": flow.get("caption_ig", flow.get("caption_fb", ""))}]
            }
            audio_path = speak_script(script_dict, slug=f"yeti_{today.replace('-','')}")
            if audio_path and Path(audio_path).exists():
                voiced_path = add_voiceover(raw_path, audio_path)
                raw_path = voiced_path
                print(f"✅ Voiceover added → {voiced_path}")
        except Exception as e:
            print(f"⚠️  Voiceover failed ({e}) — continuing without audio")
    else:
        print("🔇 Step 1b: Skipping TTS — Veo 3.1 native audio preserved (no double voice)")

    # Trim to 60s for Shorts / TikTok compliance
    short_path = _trim_to_60s(raw_path)
    results["short_path"] = short_path

    # ── Step 1c: Embedded chalkboard captions (Mr. Yeti brand identity) ─────────
    print("🖊️  Step 1c: Applying chalkboard captions")
    try:
        captioned = _apply_chalkboard_captions(short_path, today)
        if captioned and Path(captioned).exists():
            short_path = captioned
            results["short_path"] = short_path
            print(f"✅ Chalkboard captions → {short_path}")
        else:
            raise RuntimeError("captioned path empty")
    except Exception as e:
        print(f"⚠️  Chalkboard captions failed ({e}) — falling back to plain subtitles")
        try:
            from .subtitles import burn_subtitles
            subbed_path = burn_subtitles(short_path)
            short_path = subbed_path
            results["short_path"] = short_path
        except Exception as e2:
            print(f"⚠️  Plain subtitles also failed ({e2}) — continuing without captions")

    # ── Step 1d: Generate thumbnail ───────────────────────────────────────────
    print("🖼️  Step 1d: Generating thumbnail")
    thumb_path = ""
    try:
        from .thumbnail import generate as gen_thumb
        thumb_path = gen_thumb(short_path, title=results["title"],
                               slug=today.replace("-", ""))
        # Upload thumbnail to R2
        from .r2_storage import upload_file as _r2_upload, is_configured as _r2_ok
        if _r2_ok() and thumb_path and Path(thumb_path).exists():
            try:
                r2_thumb = _r2_upload(thumb_path, f"thumbnails/{Path(thumb_path).name}", "image/jpeg")
                try:
                    Path(thumb_path).unlink()
                except Exception:
                    pass
                thumb_path = r2_thumb
            except Exception as r2e:
                print(f"⚠️  R2 thumbnail upload failed ({r2e}) — keeping local")
        results["thumbnail"] = thumb_path
        print(f"✅ Thumbnail → {thumb_path}")
    except Exception as e:
        print(f"⚠️  Thumbnail failed ({e})")

    # Per-platform video selection:
    #   Reel B (tip, 24s) → YouTube Shorts
    #   Reel A (hook, 24s) → TikTok + Instagram
    #   Full short_path → Facebook (longest engagement)
    # Only use a reel if the file actually exists and is >10KB; fall back to short_path.
    def _valid_video(path: "str | None") -> str:
        if path and Path(path).exists() and Path(path).stat().st_size > 10 * 1024:
            return path
        return short_path

    yt_video  = _valid_video(reels.get("reel_b"))
    tt_video  = _valid_video(reels.get("reel_a"))
    ig_video  = _valid_video(reels.get("reel_a"))
    fb_video  = _valid_video(reels.get("reel_c"))

    # Guard: short_path itself must exist before we try to upload anything
    if not Path(short_path).exists():
        err = f"Primary video file missing before upload: {short_path}"
        print(f"❌ {err}")
        results["done"] = False
        return {"ok": False, "error": err}

    # ── Step 2: YouTube Shorts ────────────────────────────────────────────────
    print("▶️  Step 2: Upload to YouTube Shorts")
    yt_result = _upload_youtube(yt_video, yt_title, description, tags)
    results["youtube"] = yt_result
    yt_ok = yt_result.get("status") in ("published", "triggered")

    # ── Step 3: TikTok ────────────────────────────────────────────────────────
    print("🎵 Step 3: Upload to TikTok")
    tiktok_title = results["shorts_title"].replace("#Shorts", "").replace("#shorts", "").strip()
    tiktok_desc  = flow.get("caption_tiktok") or (
        f"{flow.get('caption_ig', description)}\n\n"
        f"Free practice → pielts.web.app\n"
        f"#IELTS #IELTSTips #MrYeti #pielts #StudyAbroad"
    )
    tt_result = _upload_tiktok(tt_video, tiktok_title, tiktok_desc)
    results["tiktok"] = tt_result
    tt_ok = tt_result.get("ok") or tt_result.get("status") == "skipped"

    # ── Step 4: Instagram Reels ───────────────────────────────────────────────
    print("📸 Step 4: Upload to Instagram Reels")
    ig_result = _upload_instagram_reel(ig_video, flow.get("caption_ig", description))
    results["instagram_reel"] = ig_result

    # ── Step 5: Analytics feedback loop ──────────────────────────────────────
    print("📊 Step 5: Logging for analytics feedback loop")
    try:
        _log_analytics_entry(today, results)
    except Exception as e:
        print(f"⚠️  Analytics log failed ({e})")

    # ── Step 5b: Save to content library DB ──────────────────────────────────
    print("🗄️  Step 5b: Saving to content library")
    try:
        from .content_library import save_video
        yt_url = results.get("youtube", {}).get("url", "") if isinstance(results.get("youtube"), dict) else ""
        tt_url = results.get("tiktok", {}).get("share_url", "") if isinstance(results.get("tiktok"), dict) else ""
        script = flow.get("script", {})
        save_video(
            slug=today.replace("-", ""),
            date=today,
            title=results.get("title", ""),
            topic=flow.get("topic", flow.get("title", "")),
            pillar=flow.get("pillar", "ielts_tips"),
            hook=flow.get("hook", flow.get("shorts_title", "")),
            script_json=json.dumps(script) if isinstance(script, dict) else str(script),
            method=results.get("method", "static"),
            video_path=results.get("short_path", results.get("video_path", "")),
            duration_sec=0.0,
        )
        print("  ✅ Saved to content library")
    except Exception as e:
        print(f"⚠️  Content library save failed ({e})")

    # ── Step 5c: Record character appearances ─────────────────────────────────
    try:
        from .character_memory import record_episode_characters
        script = flow.get("script", {})
        characters_in_episode = []
        if isinstance(script, dict):
            # Pull character names mentioned in script scenes
            import re
            full_text = " ".join(
                str(s.get("speech", "")) + " " + str(s.get("visual", ""))
                for s in script.get("scenes", [])
            )
            for name in ["Rahul", "Sarah", "Diego", "Fatima"]:
                if name.lower() in full_text.lower():
                    characters_in_episode.append(name)
        if characters_in_episode:
            record_episode_characters(today.replace("-", ""), characters_in_episode)
            print(f"  ✅ Characters recorded: {characters_in_episode}")
    except Exception as e:
        print(f"⚠️  Character memory record failed ({e})")

    results["done"] = True

    # persist to queue
    q = [e for e in q if e.get("date") != today]
    q.append(results)
    _save_queue(q[-60:])

    # ── Step 4: Telegram notification ─────────────────────────────────────────
    _send_telegram_report(results, yt_title, yt_result, tt_result, flow)

    return {"ok": True, **results}


def _send_telegram_report(results, title, yt, tt, flow):
    try:
        from .n8n_tools import send_telegram, send_video
        method_icon = "🎬 Veo 3D" if results.get("method") == "veo" else "🖼️ Static"

        yt_status = yt.get("status", "?")
        tt_status  = "✅ posted" if tt.get("ok") else tt.get("reason") or tt.get("error") or "?"

        # Parse YouTube video ID if available
        yt_link = ""
        try:
            vid_id = json.loads(yt.get("response", "{}")).get("uploadId", "") or \
                     json.loads(yt.get("response", "{}")).get("videoId", "")
            if vid_id:
                yt_link = f"\n▶️ https://youtu.be/{vid_id}"
        except Exception:
            pass

        tt_link = tt.get("share_url", "")

        msg = (
            f"🎥 Mr. Yeti video posted! ({method_icon})\n\n"
            f"📌 {title}\n\n"
            f"📺 YouTube Shorts: {yt_status}{yt_link}\n"
            f"🎵 TikTok: {tt_status}"
            + (f"\n🔗 {tt_link}" if tt_link else "") +
            f"\n\n💡 Topic: {flow.get('topic', '')}"
        )
        send_telegram(msg)

        # Also send the video file so Ajay can view it on mobile
        vp = results.get("short_path") or results.get("video_path", "")
        if vp and Path(vp).exists():
            try:
                send_video(vp, f"Mr. Yeti | {title}")
            except Exception:
                pass
    except Exception as e:
        print(f"⚠️  Telegram notification failed: {e}")


# ── Queue today's video for manual review before posting ─────────────────────

def queue_for_review(topic: str = "") -> dict:
    """Generate video and queue it, but don't post yet. For manual approval flow."""
    try:
        from .google_flow import generate_full_video
        flow = generate_full_video(topic=topic, use_veo=True)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    if not flow.get("ok"):
        return flow

    short_path = _trim_to_60s(flow["video_path"])
    today = datetime.now().strftime("%Y-%m-%d")
    entry = {
        "date": today,
        "video_path": flow["video_path"],
        "short_path": short_path,
        "title": flow.get("title", ""),
        "method": flow.get("method", "static"),
        "caption_ig": flow.get("caption_ig", ""),
        "caption_fb": flow.get("caption_fb", ""),
        "done": False,
        "created_at": datetime.now().isoformat(),
    }
    q = _load_queue()
    q = [e for e in q if e.get("date") != today]
    q.append(entry)
    _save_queue(q[-60:])

    try:
        from .n8n_tools import send_video, send_telegram
        send_telegram(
            f"🎬 Mr. Yeti video ready for review!\n"
            f"📌 {entry['title']}\n"
            f"Method: {entry['method']}\n\n"
            f"Open Baadar → Video tab to approve & post."
        )
        if Path(short_path).exists():
            send_video(short_path, f"Review: {entry['title']}")
    except Exception:
        pass

    return {"ok": True, "queued": entry}


def get_today_queue() -> "dict | None":
    today = datetime.now().strftime("%Y-%m-%d")
    for e in reversed(_load_queue()):
        if e.get("date") == today:
            return e
    return None


def post_queued_today() -> dict:
    """Post whatever is queued for today (called from UI 'Post Now' button)."""
    entry = get_today_queue()
    if not entry:
        return {"ok": False, "error": "No video queued for today — generate one first"}
    if entry.get("done"):
        return {"ok": False, "error": "Already posted today"}

    title = entry.get("title", "IELTS Tips | Mr. Yeti #Shorts")
    yt_title = title if "#Shorts" in title else title.rstrip(".") + " #Shorts"
    description = (
        f"{entry.get('caption_fb', '')}\n\n"
        "🎓 Free IELTS practice → https://pielts.web.app\n"
        "#IELTS #IELTSTips #MrYeti #pielts #StudyAbroad"
    )
    short_path = entry.get("short_path") or entry.get("video_path", "")

    yt = _upload_youtube(short_path, yt_title, description,
                         "IELTS,IELTSTips,MrYeti,pielts,Shorts")
    tt = _upload_tiktok(short_path, title.replace("#Shorts", "").strip(),
                        entry.get("caption_ig", description))

    entry["done"]    = True
    entry["youtube"] = yt
    entry["tiktok"]  = tt

    q = _load_queue()
    for i, e in enumerate(q):
        if e.get("date") == entry["date"]:
            q[i] = entry
            break
    _save_queue(q)

    _send_telegram_report(entry, yt_title, yt, tt, entry)
    return {"ok": True, "youtube": yt, "tiktok": tt}
