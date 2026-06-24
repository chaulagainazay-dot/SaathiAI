"""
HyperFrames — HTML-to-MP4 renderer for Baadar.

Uses `npx hyperframes render` (already installed: v0.6.118, Node 26+, FFmpeg).
Takes a project directory with an index.html composition → returns MP4 path.

Usage from other tools:
    from .hyperframes import render_html, render_yeti_short
    path = render_yeti_short(script_dict)   # fast, deterministic Short
    path = render_html(html_str, slug)      # arbitrary HTML → MP4
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .. import config

OUT_DIR = config.ROOT / "videos_output"
OUT_DIR.mkdir(exist_ok=True)

_NODE_BIN  = shutil.which("node") or "node"
_NPX_BIN   = shutil.which("npx")  or "npx"
_YETI_IMG  = config.ROOT / "client" / "assets" / "mr_yeti_reference.jpeg"
_MUSIC     = config.ROOT / "client" / "assets" / "music" / "bg_happy.mp3"


# ── Low-level render ──────────────────────────────────────────────────────────

def render_project(project_dir: str | Path, output_path: str | Path,
                   fps: int = 30, quality: str = "standard") -> dict:
    """
    Run `npx hyperframes render <project_dir> -o <output_path>`.
    Returns {"ok": bool, "path": str, "stderr": str}.
    """
    project_dir = Path(project_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _NPX_BIN, "hyperframes", "render", str(project_dir),
        "-o", str(output_path),
        "--fps", str(fps),
        "--quality", quality,
        "--quiet",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and output_path.exists():
            return {"ok": True, "path": str(output_path), "stderr": r.stderr[-200:]}
        return {"ok": False, "error": f"hyperframes exited {r.returncode}",
                "stderr": r.stderr[-600:], "stdout": r.stdout[-200:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Render timed out (300s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def render_html(html_content: str, slug: str = "",
                fps: int = 30, quality: str = "standard",
                assets: dict[str, bytes] | None = None) -> dict:
    """
    Write html_content to a temp project dir and render to MP4.
    assets: optional extra files {relative_path: bytes} to copy into the project dir.
    Returns {"ok": bool, "path": str, ...}
    """
    slug = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"hf_{slug}.mp4"

    with tempfile.TemporaryDirectory(prefix="hf_") as tmp:
        tmp = Path(tmp)
        (tmp / "index.html").write_text(html_content, encoding="utf-8")
        if assets:
            for rel, data in assets.items():
                dest = tmp / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        return render_project(tmp, out_path, fps=fps, quality=quality)


# ── Mr. Yeti Short template ───────────────────────────────────────────────────

def _yeti_img_b64() -> str:
    """Return Mr. Yeti image as data-URI for embedding in HTML."""
    if _YETI_IMG.exists():
        import base64
        data = base64.b64encode(_YETI_IMG.read_bytes()).decode()
        return f"data:image/jpeg;base64,{data}"
    # Fallback: white circle placeholder
    return ""


def build_yeti_html(script: dict) -> str:
    """
    Build a HyperFrames 9:16 Short composition from a script dict.
    script keys:
      title, hook, scenes (list of {speech, setting, duration}),
      caption_ig, topic
    """
    scenes = script.get("scenes", [])
    if not scenes:
        scenes = [{"speech": script.get("hook", "IELTS tip"), "duration": 5, "setting": "classroom"}]

    total_dur = sum(s.get("duration", 5) for s in scenes)
    yeti_src  = _yeti_img_b64()
    title     = script.get("title", "IELTS Tips | Mr. Yeti").replace('"', "&quot;")
    hook      = script.get("hook", scenes[0].get("speech", ""))

    # Build scene HTML blocks
    scene_blocks = []
    t = 0
    for i, s in enumerate(scenes):
        dur  = s.get("duration", 5)
        text = s.get("speech", "")
        bg_colors = ["#0f172a", "#1e1b4b", "#0c1a2e"]
        bg = bg_colors[i % len(bg_colors)]
        accent = ["#6366f1", "#8b5cf6", "#06b6d4"][i % 3]

        scene_blocks.append(f"""
  <!-- Scene {i+1}: {t}s – {t+dur}s -->
  <div id="scene{i+1}"
       data-scene-id="scene{i+1}"
       data-scene-start="{t}"
       data-scene-duration="{dur}"
       style="position:absolute;inset:0;background:{bg};display:flex;flex-direction:column;
              align-items:center;justify-content:center;padding:60px 40px;gap:32px;opacity:0">
    {"<img id='yeti" + str(i+1) + "' src='" + yeti_src + "' style='width:520px;height:520px;object-fit:cover;border-radius:50%;border:6px solid " + accent + ";box-shadow:0 0 60px " + accent + "88;opacity:0' alt='Mr Yeti'/>" if yeti_src else ""}
    <div id="speech{i+1}"
         style="background:rgba(255,255,255,0.08);border:2px solid {accent};border-radius:20px;
                padding:32px 36px;text-align:center;transform:translateY(40px);opacity:0">
      <p style="font-family:'Helvetica Neue',Arial,sans-serif;font-size:52px;font-weight:800;
                color:#fff;line-height:1.25;letter-spacing:-0.5px">{text}</p>
    </div>
    <div id="brand{i+1}"
         style="position:absolute;bottom:80px;left:0;right:0;text-align:center;opacity:0">
      <p style="font-family:'Helvetica Neue',Arial,sans-serif;font-size:36px;
                font-weight:700;color:{accent};letter-spacing:1px">pielts.web.app</p>
    </div>
  </div>""")
        t += dur

    # GSAP animation blocks
    anim_blocks = []
    t = 0
    for i, s in enumerate(scenes):
        dur = s.get("duration", 5)
        n   = i + 1
        anim_blocks.append(f"""
  // Scene {n} animations
  tl.set('#scene{n}', {{opacity:1}}, {t})
    .from('#scene{n}', {{opacity:0, duration:0.4}}, {t})
    {"+ tl.from('#yeti" + str(n) + "', {scale:0.6, opacity:0, duration:0.6, ease:'back.out(1.7)'}, " + str(t+0.2) + ")" if yeti_src else ""}
    .from('#speech{n}', {{y:40, opacity:0, duration:0.5, ease:'power3.out'}}, {t+0.4})
    .from('#brand{n}', {{opacity:0, duration:0.4}}, {t+0.8})
    .to('#scene{n}', {{opacity:0, duration:0.3}}, {t+dur-0.3});""")
        t += dur

    html = f"""<!DOCTYPE html>
<html
  data-composition-id="mr-yeti-short"
  data-width="1080"
  data-height="1920"
  data-duration="{total_dur}"
  data-fps="30"
>
<head>
  <meta charset="UTF-8">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ width:1080px; height:1920px; overflow:hidden; background:#0f172a; }}
  </style>
</head>
<body>
  <!-- Watermark strip -->
  <div style="position:absolute;top:0;left:0;right:0;height:8px;
              background:linear-gradient(90deg,#6366f1,#8b5cf6,#06b6d4);z-index:999"></div>

  {''.join(scene_blocks)}

  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
  <script>
    const tl = gsap.timeline();
    {''.join(anim_blocks)}
    // Register timeline with HyperFrames so it can scrub the composition
    window.__timelines = window.__timelines || {{}};
    window.__timelines['mr-yeti-short'] = tl;
  </script>
</body>
</html>"""
    return html


def render_yeti_short(script: dict, slug: str = "", quality: str = "standard") -> dict:
    """
    Full pipeline: script dict → HyperFrames HTML → MP4.
    Returns {"ok": bool, "path": str, "method": "hyperframes", ...}
    """
    slug = slug or datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"🎬 HyperFrames: building Mr. Yeti Short composition (slug: {slug})")

    html = build_yeti_html(script)
    result = render_html(html, slug=slug, fps=30, quality=quality)

    if result.get("ok"):
        result["method"]     = "hyperframes"
        result["video_path"] = result.pop("path", "")
        result["title"]      = script.get("title", "IELTS Tips | Mr. Yeti #Shorts")
        result["caption_fb"] = script.get("caption_fb", "")
        result["caption_ig"] = script.get("caption_ig", "")
        print(f"✅ HyperFrames render complete → {result['video_path']}")
    else:
        print(f"❌ HyperFrames render failed: {result.get('error')}")

    return result


# ── High-level: generate script + render ─────────────────────────────────────

def generate_and_render(topic: str = "", long: bool = False) -> dict:
    """
    Full pipeline: LLM script → HyperFrames render → MP4.
    Drop-in alternative to google_flow.generate_full_video().

    long=True: ask the LLM for 8-10 scenes (~3-4 min total) instead of the
               default short format.  Used by run_pipeline() so clips can be
               extracted from the single long video for each posting slot.
    """
    from .google_flow import generate_script   # reuse the script generator
    slug = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"📝 HyperFrames: generating {'LONG-FORM (8-10 scenes)' if long else 'short'} script via LLM…")
    script = generate_script(topic, n_scenes=8 if long else None)

    result = render_yeti_short(script, slug=slug, quality="standard")
    result["slug"] = slug
    result["long"] = long
    return result


# ── Batch rendering ───────────────────────────────────────────────────────────

def batch_render(html_template: str, variables: list[dict],
                 output_dir: str | Path = None) -> list[dict]:
    """
    Render multiple videos from one HTML template with variable substitution.
    Variables are injected as window.__HF_VARS in a <script> tag.
    """
    output_dir = Path(output_dir) if output_dir else OUT_DIR / "batch"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for i, vars_dict in enumerate(variables):
        slug = f"batch_{i:03d}_{datetime.now().strftime('%H%M%S')}"
        # Inject variables
        var_script = f"<script>window.__HF_VARS = {json.dumps(vars_dict)};</script>"
        html = html_template.replace("</head>", f"{var_script}</head>", 1)
        out  = output_dir / f"{slug}.mp4"
        r    = render_html(html, slug=slug)
        r["vars"] = vars_dict
        results.append(r)

    return results
