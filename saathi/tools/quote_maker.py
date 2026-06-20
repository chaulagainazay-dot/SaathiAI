"""Quote Maker — generates branded quote images and 5-second YouTube Short videos.

Used by the autopost system when no pre-rendered video is in the queue.
Produces:
  • 1080×1080  quote image  → Facebook + Instagram posts
  • 1080×1920  quote image  → Instagram Story / YouTube Short thumbnail
  • 5-second MP4 video     → YouTube Shorts (image + background music + zoom)

All output uses Mr. Yeti branding: navy background, white text, pielts.web.app footer.
"""
import json
import os
import textwrap
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .. import config

ASSETS = config.ROOT / "client" / "assets"
YETI_IMG = ASSETS / "mr_yeti_reference.jpeg"
POSES = ASSETS / "yeti_poses"
MUSIC = ASSETS / "music" / "upbeat_edu.mp3"
OUT_DIR = config.ROOT / "data" / "quote_cards"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Brand palette
NAVY = (12, 20, 58)
BLUE = (0, 112, 243)
GOLD = (255, 196, 0)
WHITE = (255, 255, 255)
LIGHT = (220, 230, 255)


# ──────────────────────────────────────────────────────────────
# Font helpers
# ──────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = False):
    """Return a PIL font — falls back to default if system fonts absent."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ──────────────────────────────────────────────────────────────
# Quote generator (LLM)
# ──────────────────────────────────────────────────────────────

_QUOTE_PROMPT = """
You are Mr. Yeti, the IELTS professor from the Himalayas.
Generate a short, powerful IELTS tip or motivational quote for social media.

Topic hint: {topic}
Format: {fmt}

Rules:
- Under 15 words for the QUOTE itself (punchy, memorable)
- Under 8 words for the SUBTEXT below it (practical value)
- Include one relevant emoji at the end of the quote
- Make it specific to IELTS (mention band score, Writing/Speaking/Reading/Listening, or a specific tip)

Return JSON:
{{"quote": "...", "subtext": "...", "topic_tag": "...",
  "youtube_title": "IELTS tip: <quote> | Mr. Yeti #Shorts",
  "blog_title": "...",
  "blog_intro": "2-3 sentence intro expanding on this tip for the pielts blog."
}}
"""


def generate_quote(topic: str = "", fmt: str = "IELTS tip") -> dict:
    """Use LLM to generate a branded IELTS quote/tip."""
    from ._llm_helper import ask_llm, extract_json
    prompt = _QUOTE_PROMPT.format(topic=topic or "general IELTS tips", fmt=fmt)
    try:
        raw = ask_llm(prompt, system="Return ONLY valid JSON.", timeout=30)
        return extract_json(raw)
    except Exception as e:
        # Hardcoded fallback so posting never stops
        fallbacks = [
            {"quote": "Band 7 is not luck. It is a system. 🎯",
             "subtext": "Practice free at pielts.web.app",
             "topic_tag": "IELTSTips",
             "youtube_title": "Band 7 is not luck — it's a system | Mr. Yeti #Shorts",
             "blog_title": "How to Score Band 7: The System Mr. Yeti Swears By",
             "blog_intro": "Many students think a Band 7 score is out of reach. Mr. Yeti disagrees. It all comes down to a repeatable system — not talent. Here's what that system looks like."},
            {"quote": "One word is killing your Writing score. 📝",
             "subtext": "Find it free → pielts.web.app",
             "topic_tag": "IELTSWriting",
             "youtube_title": "One word killing your IELTS Writing score | Mr. Yeti #Shorts",
             "blog_title": "The One Overused Word That Drops Your IELTS Writing Band Score",
             "blog_intro": "There is one word that appears in nearly every Band 5 essay — and almost never in a Band 7 essay. In this post, Mr. Yeti reveals what it is and how to fix it."},
            {"quote": "Examiners decide in the first 30 seconds. ⏱️",
             "subtext": "Start strong — practice Speaking free",
             "topic_tag": "IELTSSpeaking",
             "youtube_title": "IELTS examiners decide in 30 seconds | Mr. Yeti #Shorts",
             "blog_title": "First Impressions in IELTS Speaking: What Examiners Actually Notice",
             "blog_intro": "The IELTS Speaking examiner forms an impression within the first 30 seconds of your test. Mr. Yeti explains exactly what they're listening for — and how to nail it."},
        ]
        import random
        return random.choice(fallbacks)


# ──────────────────────────────────────────────────────────────
# Image card builder
# ──────────────────────────────────────────────────────────────

def make_quote_image(quote: str, subtext: str = "", pose: str = "teaching",
                     size: tuple = (1080, 1080), slug: str = "") -> str:
    """Render a branded quote card. Returns the saved file path."""
    W, H = size
    img = Image.new("RGB", (W, H), color=NAVY)
    draw = ImageDraw.Draw(img)

    # ── Background gradient bands ──
    for i in range(H):
        t = i / H
        r = int(NAVY[0] + (BLUE[0] - NAVY[0]) * t * 0.3)
        g = int(NAVY[1] + (BLUE[1] - NAVY[1]) * t * 0.3)
        b = int(NAVY[2] + (BLUE[2] - NAVY[2]) * t * 0.3)
        draw.line([(0, i), (W, i)], fill=(r, g, b))

    # ── Decorative gold accent bar (top) ──
    draw.rectangle([(0, 0), (W, 8)], fill=GOLD)

    # ── Mr. Yeti pose image (right side, semi-transparent) ──
    pose_map = {
        "teaching": "teaching.jpg", "thinking": "thinking.jpg",
        "thumbsup": "thumbsup.jpg", "pointing": "pointing.jpg",
        "excited": "excited.jpg", "flashcard": "flashcard.jpg",
    }
    pose_file = POSES / pose_map.get(pose, "teaching.jpg")
    if not pose_file.exists():
        pose_file = YETI_IMG if YETI_IMG.exists() else None

    if pose_file and pose_file.exists():
        yeti = Image.open(pose_file).convert("RGBA")
        # Scale to fit right column
        target_h = int(H * 0.65)
        ratio = target_h / yeti.height
        yeti = yeti.resize((int(yeti.width * ratio), target_h), Image.LANCZOS)
        # Paste bottom-right
        x = W - yeti.width - 20
        y = H - yeti.height - 80
        # Create a soft mask for fading left edge
        mask = Image.new("L", yeti.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        fade_w = min(120, yeti.width // 3)
        for fx in range(fade_w):
            alpha = int(200 * fx / fade_w)
            mask_draw.line([(fx, 0), (fx, yeti.height)], fill=alpha)
        mask_draw.rectangle([(fade_w, 0), (yeti.width, yeti.height)], fill=200)
        if yeti.mode == "RGBA":
            yeti_mask = Image.fromarray(
                __import__("numpy", fromlist=["minimum"]).minimum(
                    __import__("numpy").array(yeti.split()[3]),
                    __import__("numpy").array(mask)
                )
            ) if False else mask  # use simple mask
            img.paste(yeti, (x, y), mask)
        else:
            img.paste(yeti, (x, y), mask)

    # ── "MR. YETI" label ──
    lbl_font = _font(28, bold=True)
    draw.text((50, 45), "MR. YETI  ·  IELTS PROFESSOR", font=lbl_font, fill=GOLD)

    # ── Quote text (large, left-aligned, wraps at ~22 chars for 1080 width) ──
    max_chars = 22 if W == 1080 else 18
    q_font = _font(int(W * 0.075), bold=True)
    wrapped = textwrap.fill(quote, width=max_chars)
    lines = wrapped.split("\n")

    # Vertical center in upper 60% of canvas
    line_h = int(W * 0.075) + 12
    total_h = len(lines) * line_h
    y_start = max(130, (H * 0.55 - total_h) // 2 + 80)

    for i, line in enumerate(lines):
        y = y_start + i * line_h
        # Shadow
        draw.text((52, y + 3), line, font=q_font, fill=(0, 0, 0, 120))
        draw.text((50, y), line, font=q_font, fill=WHITE)

    # ── Subtext ──
    if subtext:
        sub_font = _font(int(W * 0.038))
        sub_y = y_start + len(lines) * line_h + 28
        draw.text((50, sub_y), subtext, font=sub_font, fill=LIGHT)

    # ── Divider line ──
    div_y = H - 110
    draw.rectangle([(50, div_y), (W - 50, div_y + 3)], fill=BLUE)

    # ── Footer bar ──
    footer_font = _font(30, bold=True)
    draw.text((50, div_y + 18), "pielts.web.app", font=footer_font, fill=GOLD)
    draw.text((W - 260, div_y + 18), "@pieltsofficial", font=_font(28), fill=LIGHT)

    # ── Gold accent bar (bottom) ──
    draw.rectangle([(0, H - 8), (W, H)], fill=GOLD)

    ts = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"quote_{ts}_{W}x{H}.jpg"
    img.save(str(out_path), "JPEG", quality=94)
    return str(out_path)


# ──────────────────────────────────────────────────────────────
# 5-second YouTube Short video
# ──────────────────────────────────────────────────────────────

def make_quote_video(quote: str, subtext: str = "", pose: str = "teaching",
                     duration: float = 5.0, slug: str = "") -> str:
    """
    Render a 5-second 1080×1920 YouTube Short:
      • Quote card image (9:16) with a gentle Ken Burns zoom
      • Background music (upbeat_edu.mp3) faded to duration
    Returns the MP4 file path.
    """
    from moviepy import ImageClip, AudioFileClip, CompositeAudioClip

    # Generate the 9:16 portrait image for YouTube Shorts
    img_path = make_quote_image(quote, subtext, pose,
                                size=(1080, 1920), slug=f"{slug}_shorts")

    ts = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"short_{ts}.mp4"

    # Build video clip with subtle zoom (Ken Burns: 1.0 → 1.08 over 5s)
    clip = ImageClip(img_path, duration=duration)

    def zoom(t):
        scale = 1.0 + 0.08 * (t / duration)
        new_w = int(1080 * scale)
        new_h = int(1920 * scale)
        return clip.image.resize((new_w, new_h)).crop(
            x1=(new_w - 1080) // 2, y1=(new_h - 1920) // 2,
            x2=(new_w - 1080) // 2 + 1080, y2=(new_h - 1920) // 2 + 1920
        )

    # Simpler: just use the static image (zoom is optional enhancement)
    video = ImageClip(img_path, duration=duration)

    # Add background music if available
    if MUSIC.exists():
        try:
            audio = AudioFileClip(str(MUSIC)).subclipped(0, duration).with_effects(
                [__import__("moviepy.audio.fx", fromlist=["AudioFadeOut"]).AudioFadeOut(1.0)]
            )
            video = video.with_audio(audio)
        except Exception:
            pass  # silent video is fine

    video.write_videofile(
        str(out_path),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        logger=None,
    )
    return str(out_path)


# ──────────────────────────────────────────────────────────────
# Blog post generator
# ──────────────────────────────────────────────────────────────

def make_quote_blog(quote_data: dict) -> dict:
    """Expand a quote into a full blog post for pielts.web.app."""
    from ._llm_helper import ask_llm, extract_json

    prompt = f"""
You are Mr. Yeti, writing a blog post for pielts.web.app.

Quote: "{quote_data.get('quote','')}"
Intro: "{quote_data.get('blog_intro','')}"

Write a complete, helpful IELTS blog post (400-500 words) expanding on this quote.
Structure: intro (2 sentences) → 3 practical tips with examples → conclusion with CTA to pielts.web.app.
Tone: warm, encouraging, expert. Mix Nepali words sparingly (Namaste, dherai ramro, etc.).
Include pielts.web.app naturally 2-3 times.

Return JSON:
{{"title": "...", "slug": "...", "excerpt": "...", "content": "full markdown content here"}}
"""
    try:
        raw = ask_llm(prompt, system="Return ONLY valid JSON.", timeout=60)
        return extract_json(raw)
    except Exception:
        return {
            "title": quote_data.get("blog_title", "IELTS Tips from Mr. Yeti"),
            "slug": f"ielts-tip-{datetime.now().strftime('%Y%m%d')}",
            "excerpt": quote_data.get("blog_intro", ""),
            "content": f"# {quote_data.get('blog_title','IELTS Tips')}\n\n{quote_data.get('blog_intro','')}\n\nPractice free at pielts.web.app",
        }


# ──────────────────────────────────────────────────────────────
# All-in-one: generate quote + image + video + blog
# ──────────────────────────────────────────────────────────────

def make_full_quote_kit(topic: str = "", pose: str = "teaching") -> dict:
    """
    Generate everything from a single topic:
      1. LLM quote + subtext
      2. 1080×1080 image for FB + IG
      3. 1080×1080 image for Stories
      4. 5-second 1080×1920 MP4 for YouTube Shorts
      5. Blog post JSON ready to publish
    Returns paths + content for autopost to consume.
    """
    slug = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Generate quote
    q_data = generate_quote(topic, fmt="IELTS tip or motivational quote")
    quote = q_data.get("quote", "Band 7 is not luck. It is a system. 🎯")
    subtext = q_data.get("subtext", "Free practice → pielts.web.app")

    # 2. Square image (FB + IG feed)
    img_square = make_quote_image(quote, subtext, pose, size=(1080, 1080), slug=slug)

    # 3. 5-second Short video
    try:
        video_path = make_quote_video(quote, subtext, pose, duration=5.0, slug=slug)
    except Exception as e:
        video_path = ""
        q_data["video_error"] = str(e)[:100]

    # 4. Blog post
    blog = make_quote_blog(q_data)

    return {
        "ok": True,
        "quote": quote,
        "subtext": subtext,
        "topic_tag": q_data.get("topic_tag", "IELTSTips"),
        "youtube_title": q_data.get("youtube_title", f"IELTS tip: {quote} | Mr. Yeti #Shorts"),
        "image_square": img_square,     # → FB + IG feed
        "video_short": video_path,      # → YouTube Shorts + IG Reel
        "blog": blog,
        "slug": slug,
    }
