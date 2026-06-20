"""Thumbnail Generator — Stage 7.
Generates YouTube thumbnails: Yeti pose + bold text overlay.
Uses cached Yeti poses for consistency.
"""
import urllib.parse
import time
from pathlib import Path

import httpx

_THUMBS_DIR = Path.home() / "SaathiAI" / "thumbnails"
_THUMBS_DIR.mkdir(parents=True, exist_ok=True)

_YETI_BASE = (
    "Mr. Yeti IELTS teacher — large broad-shouldered yeti, fluffy white fur, "
    "round black-rimmed glasses, brown tweed blazer, light-blue shirt, navy tie. "
    "Pixar 3D cinematic render. Warm studio lighting. "
)


def generate_thumbnail(title: str, thumbnail_text: str, style: str = "shocked") -> dict:
    """Generate a YouTube thumbnail (1280x720) with Yeti + bold text."""
    from PIL import Image, ImageDraw, ImageFont

    # Fixed seeds per style for consistency
    style_seeds = {
        "shocked":  22222,
        "pointing": 33333,
        "teaching": 11111,
        "thumbsup": 66666,
    }
    seed = style_seeds.get(style, 22222)

    style_prompts = {
        "shocked":  _YETI_BASE + "Wide-eyed shocked expression, mouth open, hands on cheeks. YouTube thumbnail style. Bright orange/yellow background.",
        "pointing": _YETI_BASE + "Pointing at text on the right side of image. Confident expression. Dark navy background with glow effects.",
        "teaching": _YETI_BASE + "Standing at chalkboard, pointing with marker. Warm classroom. Educational feel.",
        "thumbsup": _YETI_BASE + "Huge thumbs up, big smile, looking at camera. Green success background.",
    }

    prompt = style_prompts.get(style, style_prompts["shocked"])
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=1280&height=720&model=flux&nologo=true&seed={seed}"
    )

    # Check cache
    cache_key = f"thumb_{style}_{seed}.jpg"
    yeti_cache = Path.home() / "SaathiAI" / "client" / "assets" / "yeti_poses" / cache_key
    if not yeti_cache.exists() or yeti_cache.stat().st_size < 10_000:
        for attempt in range(3):
            try:
                r = httpx.get(url, timeout=90, follow_redirects=True)
                r.raise_for_status()
                yeti_cache.write_bytes(r.content)
                break
            except Exception:
                if attempt == 2:
                    return {"ok": False, "error": "Image generation failed"}
                time.sleep(5)

    # Add text overlay with Pillow
    img = Image.open(yeti_cache).convert("RGB")
    img = img.resize((1280, 720), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    lines = [l.strip() for l in thumbnail_text.upper().split("\n") if l.strip()][:2]
    y_positions = [80, 220]
    font_sizes = [110, 85]

    for i, line in enumerate(lines[:2]):
        fs = font_sizes[i]
        y = y_positions[i]
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", fs)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = max(20, (640 - tw) // 2)  # left-center (Yeti on right)
        # Shadow
        draw.text((x+4, y+4), line, font=font, fill=(0, 0, 0))
        # Yellow text
        draw.text((x, y), line, font=font, fill=(255, 220, 0))

    # Watermark
    try:
        wf = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    except Exception:
        wf = ImageFont.load_default()
    draw.text((20, 685), "pielts.web.app", font=wf, fill=(255, 255, 255, 180))

    ts = int(time.time())
    out_path = _THUMBS_DIR / f"thumb_{ts}.jpg"
    img.save(str(out_path), "JPEG", quality=95)

    return {
        "ok": True,
        "thumbnail_path": str(out_path),
        "title": title,
        "thumbnail_text": thumbnail_text,
    }
