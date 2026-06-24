"""
Auto-thumbnail generator for Mr. Yeti YouTube videos.
Uses the Mr. Yeti template image as base and writes the video title on the
left-side flipchart visible in the image.
Output: 1280x720 JPG.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from .. import config
from ._llm_helper import ask_llm, extract_json

OUT_DIR = config.ROOT / "data" / "thumbnails"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Template: Mr. Yeti at flipchart — title goes on the left flipchart board
_TEMPLATE = Path("/Users/macbookpro/Downloads/yeti writing band &.jpeg")

_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
]

def _get_font(size: int):
    for fp in _FONT_PATHS:
        if Path(fp).exists():
            try: return ImageFont.truetype(fp, size)
            except Exception: pass
    return ImageFont.load_default()


def generate(video_path: str, title: str = "", slug: str = "") -> str:
    """
    Load Mr. Yeti template → write video title on left flipchart → save 1280x720 JPG.
    Returns thumbnail path.
    """
    slug = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    out  = OUT_DIR / f"thumb_{slug}.jpg"

    img = Image.open(_TEMPLATE).convert("RGB")
    img = img.resize((1280, 720), Image.LANCZOS)
    W, H = img.size  # 1280x720

    draw = ImageDraw.Draw(img)

    if title:
        short = title.replace("#Shorts", "").replace("#shorts", "").strip()
        if len(short) > 55:
            short = short[:52] + "..."
        short = short.upper()

        # Flipchart bounding box in the template image (at 1280x720):
        # Left flipchart inner text area: x: 18–268, y: 118–548
        board_x1, board_y1 = 18, 118
        board_x2, board_y2 = 310, 548
        board_w = board_x2 - board_x1
        board_h = board_y2 - board_y1
        board_cx = board_x1 + board_w // 2
        board_cy = board_y1 + board_h // 2

        # Paint the flipchart text area white to erase the template's existing text
        draw.rectangle([board_x1, board_y1, board_x2, board_y2], fill=(244, 244, 240))

        # Word wrap to fit flipchart width
        font_size = 44
        while font_size >= 14:
            font = _get_font(font_size)
            words = short.split()
            lines, line = [], []
            for word in words:
                test = " ".join(line + [word])
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] > board_w - 16 and line:
                    lines.append(" ".join(line))
                    line = [word]
                else:
                    line.append(word)
            if line:
                lines.append(" ".join(line))

            line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + 6
            total_h = line_h * len(lines)
            if total_h <= board_h - 60:  # leave room for brand tag
                break
            font_size -= 3

        y = board_cy - total_h // 2

        for line_text in lines:
            bbox = draw.textbbox((0, 0), line_text, font=font)
            text_w = bbox[2] - bbox[0]
            x = board_cx - text_w // 2
            # Dark blue marker ink — matches the reference image style
            draw.text((x, y), line_text, font=font, fill=(15, 25, 90))
            y += line_h

        # pielts.web.app brand tag at bottom of flipchart
        brand_font = _get_font(20)
        brand_text = "pielts.web.app"
        bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
        bx = board_cx - (bbox[2] - bbox[0]) // 2
        draw.text((bx, board_y2 - 38), brand_text, font=brand_font, fill=(108, 99, 241))

    img.save(str(out), "JPEG", quality=95)
    return str(out)


def score_thumbnails(concepts: list) -> list:
    """Score 5 thumbnail concepts on 5 criteria, return ranked list."""
    prompt = f"""You are a YouTube thumbnail expert. Score each of these {len(concepts)} thumbnail concepts for an IELTS education channel.

Concepts:
{json.dumps([{"idx": i, "description": c.get("description", str(c))} for i, c in enumerate(concepts)], ensure_ascii=False)}

Score each concept (0-10) on:
- face_visibility: is a face (Mr. Yeti) clearly visible and expressive?
- text_contrast: is the text readable and high contrast?
- color_pop: does it stand out in a crowded feed?
- emotion: does it convey strong emotion (shock, curiosity, urgency)?
- curiosity_gap: does it make you NEED to click?

Return ONLY valid JSON:
{{"scored": [{{"idx": 0, "face_visibility": 8, "text_contrast": 7, "color_pop": 9, "emotion": 8, "curiosity_gap": 9}}]}}"""
    raw = ask_llm(prompt, system="You are a YouTube CTR optimization expert. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    scored = data.get("scored", [])
    # Merge scores back into concepts
    result = []
    for item in scored:
        idx = item.get("idx", 0)
        total = (item.get("face_visibility", 0) + item.get("text_contrast", 0) +
                 item.get("color_pop", 0) + item.get("emotion", 0) + item.get("curiosity_gap", 0))
        concept = concepts[idx] if idx < len(concepts) else {}
        result.append({**concept, **item, "total": total})
    result.sort(key=lambda x: x["total"], reverse=True)
    for i, r in enumerate(result):
        r["rank"] = i + 1
    return result


def generate_and_score(topic: str, title: str = "") -> dict:
    """Generate 5 thumbnail concepts and score them. Returns top 1 selected."""
    prompt = f"""Generate 5 different thumbnail concepts for a YouTube Short about: "{topic}"
Title: "{title}"
Character: Mr. Yeti — friendly Yeti, white fur, round glasses, teacher suit.
Each concept must describe: facial expression, text overlay (max 5 words), background, color scheme.
Return ONLY valid JSON: {{"concepts": [{{"description": "..."}}]}}"""
    raw = ask_llm(prompt, system="You are a viral YouTube thumbnail designer. Reply ONLY with valid JSON.")
    data = extract_json(raw)
    concepts = data.get("concepts", [])
    scored = score_thumbnails(concepts)
    return {"all": scored, "selected": scored[0] if scored else None}
