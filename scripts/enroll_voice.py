"""Record ~30s of Ajay's voice from the Mac mic and enroll it as the owner profile.
Usage: python scripts/enroll_voice.py [seconds]
"""
import sys
import io

import sounddevice as sd
import soundfile as sf

sys.path.insert(0, ".")
from saathi import voice  # noqa: E402

seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 30
SR = 16000

print(f"Recording {seconds}s — speak naturally in Nepali AND English…")
audio = sd.rec(int(seconds * SR), samplerate=SR, channels=1)
sd.wait()
print("Done recording. Enrolling…")

buf = io.BytesIO()
sf.write(buf, audio, SR, format="WAV")
voice.enroll(buf.getvalue())
print("✅ Voice profile saved. Only this voice can run privileged actions.")
