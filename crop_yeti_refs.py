"""
Run once to crop 3 Mr. Yeti reference images from mr_yeti_reference.jpeg.
Usage: cd ~/SaathiAI && .venv/bin/python crop_yeti_refs.py
"""
from pathlib import Path
from PIL import Image

src = Path("client/assets/mr_yeti_reference.jpeg")
out = Path("client/assets")
img = Image.open(src)
w, h = img.size
print(f"Source: {w}×{h}px")

# ── Face crop: top-center (glasses, expression, fur texture) ────────────────
# Yeti face occupies roughly top 40% of the image, horizontally centered
face = img.crop((
    int(w * 0.15),   # left  — cut off left edge
    int(h * 0.00),   # top   — from very top
    int(w * 0.85),   # right — cut off right edge
    int(h * 0.48),   # bottom — just below chin
))
face.save(out / "yeti_face.jpg", quality=95)
print(f"✅ yeti_face.jpg  {face.size}")

# ── Body crop: full torso (blazer, tie, mug hand, character silhouette) ──────
body = img.crop((
    int(w * 0.00),   # full width
    int(h * 0.20),   # from neck down
    int(w * 1.00),
    int(h * 0.90),   # above the desk nameplate
))
body.save(out / "yeti_body.jpg", quality=95)
print(f"✅ yeti_body.jpg  {body.size}")

# ── Hand crop: right hand holding pointer stick (teaching pose) ───────────
# Pointer hand is in the right half, middle-to-upper area
hand = img.crop((
    int(w * 0.52),   # right half
    int(h * 0.28),   # mid height
    int(w * 0.98),   # near right edge
    int(h * 0.65),   # above desk
))
hand.save(out / "yeti_hand.jpg", quality=95)
print(f"✅ yeti_hand.jpg  {hand.size}")

print("\nAll 3 reference images saved to client/assets/")
print("Veo will use these for character consistency across all 8 scenes.")
