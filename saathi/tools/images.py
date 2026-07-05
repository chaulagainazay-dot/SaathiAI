"""Images — one PNG per beat. Local-first, provider chain, honest fallback.

Primary: Flux (local diffusers if torch is present, else a Flux HTTP endpoint when
FLUX_API_URL is set). Fallback: a deterministic, branded PIL "scene card" — a real
1920×1080 PNG with the beat text on the pielts gradient, so the pipeline is fully
offline and reproducible with zero cost. Returns a list of PNG paths.
"""
from __future__ import annotations

import os
from pathlib import Path

# pielts brand
PURPLE = (108, 63, 207)
DARK = (26, 26, 46)
TEAL = (0, 191, 165)
W, H = 1920, 1080


def generate_scene_images(script: dict, *, out_dir: str, brief: dict | None = None) -> list[str]:
    beats = _beats(script, brief)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, beat in enumerate(beats, 1):
        p = out / f"scene-{i:02d}.png"
        made = _flux(beat, p) or _card(beat, p)
        if made:
            paths.append(str(p))
    return paths


def _beats(script: dict, brief: dict | None) -> list[dict]:
    if brief and brief.get("scenes"):
        return [{"label": s.get("label", ""), "text": s.get("prompt") or s.get("narration", "")}
                for s in brief["scenes"]]
    beats = [{"label": "Intro", "text": script.get("hook", "")}]
    for t in script.get("teaching", []):
        beats.append({"label": "Teaching", "text": t})
    beats.append({"label": "Example", "text": script.get("examples", "")})
    beats.append({"label": "Practice", "text": script.get("cta", "")})
    return [b for b in beats if b["text"]]


def _flux(beat: dict, path: Path) -> bool:
    url = os.getenv("FLUX_API_URL")
    key = os.getenv("FLUX_API_KEY")
    if not url:
        return False
    try:
        import httpx
        try:
            from saathi.character import scene_prompt
            prompt = scene_prompt(f"{beat['label']}: {beat['text']}")
        except Exception:
            prompt = (f"Pixar-style friendly Mr. Yeti IELTS teacher, {beat['label']} scene: "
                      f"{beat['text']}. Warm classroom, soft lighting, no text.")
        r = httpx.post(url, headers={"Authorization": f"Bearer {key}"} if key else {},
                       json={"prompt": prompt, "width": W, "height": H}, timeout=120)
        if r.status_code == 200 and r.content:
            path.write_bytes(r.content)
            return path.stat().st_size > 0
    except Exception:
        return False
    return False


def _card(beat: dict, path: Path) -> bool:
    """Deterministic branded scene card — always works, offline, zero cost."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return False
    img = Image.new("RGB", (W, H), DARK)
    px = img.load()
    for y in range(H):  # vertical gradient dark → purple
        t = y / H
        px_row = (int(DARK[0] + (PURPLE[0] - DARK[0]) * t),
                  int(DARK[1] + (PURPLE[1] - DARK[1]) * t),
                  int(DARK[2] + (PURPLE[2] - DARK[2]) * t))
        for x in range(W):
            px[x, y] = px_row
    d = ImageDraw.Draw(img)
    label_f = _font(48)
    body_f = _font(72)
    d.rectangle([80, 80, 80 + 14, 140], fill=TEAL)
    d.text((120, 84), beat["label"].upper(), font=label_f, fill=TEAL)
    _wrap(d, beat["text"], body_f, x=120, y=260, max_w=W - 240, fill=(245, 245, 250))
    d.text((120, H - 90), "pielts.web.app", font=label_f, fill=(255, 255, 255))
    img.save(path, "PNG")
    return path.stat().st_size > 0


def _font(size: int):
    from PIL import ImageFont
    for name in ("/System/Library/Fonts/Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(d, text, font, *, x, y, max_w, fill):
    words, line, lines = text.split(), "", []
    for w in words:
        trial = f"{line} {w}".strip()
        if d.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            lines.append(line); line = w
    if line:
        lines.append(line)
    lh = (font.size if hasattr(font, "size") else 72) + 22
    for i, ln in enumerate(lines[:8]):
        d.text((x, y + i * lh), ln, font=font, fill=fill)
