"""Voice cloning — F5-TTS on Apple Silicon (MLX).

Clone any voice from a short clean sample (5-10s WAV + its transcript), then
Saathi speaks English replies in that voice. Personal use only (F5-TTS is
CC-BY-NC licensed). Nepali replies still use gTTS — F5 doesn't speak Nepali.

Setup (one time):
  1. Record/obtain a clean 5-10s WAV of the voice (no music, one speaker).
  2. python -m saathi.cloning enroll <sample.wav> "exact words spoken in it"
  3. Set TTS_ENGINE=clone in .env and restart Saathi.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import config

CLONE_DIR = config.ROOT / "data" / "clone"
REF_WAV = CLONE_DIR / "reference.wav"
REF_META = CLONE_DIR / "reference.json"


def enroll(sample_path: str, transcript: str):
    """Store a reference voice. Converts to the 24kHz mono WAV F5 expects."""
    CLONE_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", sample_path, "-ar", "24000", "-ac", "1",
                    str(REF_WAV)], capture_output=True, check=True, timeout=60)
    REF_META.write_text(json.dumps({"transcript": transcript}, ensure_ascii=False))
    print(f"✅ cloned-voice reference saved: {REF_WAV}")


def is_ready() -> bool:
    return REF_WAV.exists() and REF_META.exists()


def synthesize_clone(text: str) -> tuple[bytes, str]:
    """Generate speech in the cloned voice. Returns (wav_bytes, mime)."""
    if not is_ready():
        raise RuntimeError("No cloned voice enrolled — run: "
                           "python -m saathi.cloning enroll <sample.wav> '<transcript>'")
    from f5_tts_mlx.generate import generate
    meta = json.loads(REF_META.read_text())
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    generate(generation_text=text,
             ref_audio_path=str(REF_WAV),
             ref_audio_text=meta["transcript"],
             output_path=out)
    data = Path(out).read_bytes()
    Path(out).unlink(missing_ok=True)
    return data, "audio/wav"


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "enroll":
        enroll(sys.argv[2], " ".join(sys.argv[3:]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "say":
        audio, _ = synthesize_clone(" ".join(sys.argv[2:]))
        p = Path(tempfile.mkstemp(suffix=".wav")[1])
        p.write_bytes(audio)
        subprocess.run(["afplay", str(p)])
        p.unlink()
    else:
        print(__doc__)
