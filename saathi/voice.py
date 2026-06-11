"""Voice pipeline — fully local where possible.

STT : faster-whisper (local, Nepali + English, auto language detection)
TTS : macOS `say` for English (offline) · gTTS for Nepali (online, free)
Speaker verification : resemblyzer embeddings — only Ajay unlocks privileged tools.
"""
import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import config

# ---------- Speech-to-text (faster-whisper, lazy-loaded) ----------

_whisper = None

def _get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        # "small" balances speed/accuracy on CPU; bump to "medium" for better Nepali
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper


# Languages Ajay actually speaks. Anything else detected = Whisper hallucinating
# on noise (it loves inventing Chinese text from silence/background sound).
ALLOWED_LANGS = {"en", "ne", "hi"}


def transcribe_array(wav: np.ndarray, sample_rate: int = 16000) -> dict:
    """Transcribe a float32 mono numpy array. Returns {text, language}."""
    segments, info = _get_whisper().transcribe(wav, beam_size=3, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    lang = info.language or "en"
    if lang not in ALLOWED_LANGS:
        # retry forcing English; if confidence-free garbage persists, discard
        segments, info = _get_whisper().transcribe(wav, beam_size=3, vad_filter=True,
                                                   language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        lang = "en"
        if not any(c.isascii() and c.isalpha() for c in text):
            return {"text": "", "language": lang, "discarded": "noise/unsupported language"}
    return {"text": text, "language": lang}


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> dict:
    """Transcribe an uploaded audio file (any ffmpeg-readable container)."""
    wav, sr = _decode(audio_bytes, filename)
    return transcribe_array(_resample(wav, sr))


# ---------- Text-to-speech ----------

def synthesize(text: str, language: str = "en") -> tuple[bytes, str]:
    """Return (audio_bytes, mime_type) of spoken text — browser-playable."""
    if _has_devanagari(text):
        language = "ne"
    if language.startswith("ne"):
        from gtts import gTTS
        buf = io.BytesIO()
        gTTS(text=text, lang="ne").write_to_fp(buf)
        return buf.getvalue(), "audio/mpeg"
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    subprocess.run(["say", "-v", "Samantha", "-o", path,
                    "--data-format=LEI16@22050", text], check=True, timeout=120)
    data = Path(path).read_bytes()
    Path(path).unlink(missing_ok=True)
    return data, "audio/wav"


def _has_devanagari(text: str) -> bool:
    return any("ऀ" <= c <= "ॿ" for c in text)


def speak(text: str, language: str = "en"):
    """Speak out loud on the Mac (blocking). Voice follows the text's actual
    script — a Nepali reply must use the Nepali voice even if the question was
    in English."""
    if _has_devanagari(text):
        language = "ne"
    if language.startswith("ne"):
        audio, _ = synthesize(text, "ne")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio)
            path = f.name
        subprocess.run(["afplay", path], timeout=300)
        Path(path).unlink(missing_ok=True)
    else:
        subprocess.run(["say", "-v", "Samantha", text], timeout=300)


# ---------- Audio decoding helpers ----------

def _decode(audio_bytes: bytes, filename: str) -> tuple[np.ndarray, int]:
    import soundfile as sf
    try:
        wav, sr = sf.read(io.BytesIO(audio_bytes))
    except Exception:
        # browser sends webm/opus — convert via afconvert-compatible path with ffmpeg
        suffix = "." + (filename.rsplit(".", 1)[-1] if "." in filename else "webm")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            src = f.name
        dst = src + ".wav"
        subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", dst],
                       capture_output=True, check=True, timeout=60)
        wav, sr = sf.read(dst)
        Path(src).unlink(missing_ok=True)
        Path(dst).unlink(missing_ok=True)
    if wav.ndim > 1:
        wav = wav.mean(axis=1)
    return wav.astype(np.float32), sr


def _resample(wav: np.ndarray, sr: int, target: int = 16000) -> np.ndarray:
    if sr == target:
        return wav
    n = int(len(wav) * target / sr)
    return np.interp(np.linspace(0, len(wav), n, endpoint=False),
                     np.arange(len(wav)), wav).astype(np.float32)


# ---------- Speaker verification ----------

_encoder = None

def _get_encoder():
    global _encoder
    if _encoder is None:
        from resemblyzer import VoiceEncoder
        _encoder = VoiceEncoder()
    return _encoder


def _embed_array(wav: np.ndarray, sr: int = 16000) -> np.ndarray:
    from resemblyzer import preprocess_wav
    processed = preprocess_wav(wav, source_sr=sr)
    return _get_encoder().embed_utterance(processed)


def enroll(audio_bytes: bytes):
    wav, sr = _decode(audio_bytes, "enroll.wav")
    emb = _embed_array(wav, sr)
    config.VOICE_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(config.VOICE_PROFILE_PATH, emb)


def verify_array(wav: np.ndarray, sr: int = 16000) -> dict:
    if not config.VOICE_PROFILE_PATH.exists():
        return {"verified": False, "reason": "no_profile_enrolled", "similarity": 0.0}
    profile = np.load(config.VOICE_PROFILE_PATH)
    emb = _embed_array(wav, sr)
    sim = float(np.dot(profile, emb) /
                (np.linalg.norm(profile) * np.linalg.norm(emb)))
    return {"verified": sim >= config.SPEAKER_THRESHOLD, "similarity": round(sim, 3)}


def verify(audio_bytes: bytes) -> dict:
    wav, sr = _decode(audio_bytes, "verify.wav")
    return verify_array(wav, sr)
