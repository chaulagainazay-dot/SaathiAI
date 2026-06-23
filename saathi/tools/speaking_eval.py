"""
AI Speaking Evaluator — Whisper transcription + Gemini IELTS speaking scorer.
Endpoint: POST /api/v1/evaluate/speaking
Form fields:
  audio: file (optional) — MP3/WAV/WEBM from MediaRecorder
  transcript: str (optional) — if audio unavailable, score from text
  question: str — the question that was asked
  part: int — 1, 2, or 3
Returns: {band_score, criteria, feedback, band8_sample, transcript, source}
"""
import json
import os
import re
import tempfile
from pathlib import Path

from openai import OpenAI

from .. import config


def _transcribe(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    ext_map = {
        "audio/webm": ".webm",
        "audio/wav":  ".wav",
        "audio/mp3":  ".mp3",
        "audio/mpeg": ".mp3",
        "audio/ogg":  ".ogg",
    }
    ext = ext_map.get(mime_type, ".webm")

    try:
        import whisper
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name
        model = whisper.load_model("base")
        result = model.transcribe(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        return result["text"].strip()
    except ImportError:
        pass
    except Exception:
        pass

    api_key = config.GOOGLE_API_KEY
    if not api_key or api_key.startswith("YOUR"):
        return ""
    try:
        import base64
        import httpx
        b64 = base64.b64encode(audio_bytes).decode()
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            json={"contents": [{"parts": [
                {"text": "Transcribe this speech verbatim. Return only the transcript, no commentary."},
                {"inlineData": {"mimeType": mime_type, "data": b64}},
            ]}]},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return ""


_SPEAKING_SCHEMA = """{
  "band_score": 6.5,
  "criteria": {
    "fluency_coherence":  {"band": 6.5, "comment": "I noticed..."},
    "lexical_resource":   {"band": 6.0, "comment": "Your vocabulary..."},
    "grammatical_range":  {"band": 6.5, "comment": "I spotted..."},
    "pronunciation":      {"band": 7.0, "comment": "From what I can see in your transcript..."}
  },
  "feedback": "Overall, I think...",
  "band8_sample": "Here is how a Band 8 student might answer this question: ...",
  "pronunciation_note": "I can estimate pronunciation patterns from your word choices..."
}"""

_SPEAKING_PROMPT = """You are Mr. Yeti — a friendly IELTS speaking coach with 15+ years of experience.
The student answered a Part {part} IELTS speaking question. Evaluate their response using official IELTS speaking band descriptors.

Speak in first person to the student ("I noticed...", "I love how you...", "I think you could...").
Since this is a transcript, evaluate pronunciation based on word choice complexity, sentence rhythm patterns, and typical L1 interference from South/Southeast Asian speakers.

Return ONLY valid JSON — no markdown fences, no extra text:
{schema}

Rules:
- band_score = average of the 4 criteria bands, rounded to nearest 0.5
- band8_sample: write a full Band 8 model answer (80-150 words) for this exact question
- feedback: 2-3 sentences of direct encouragement + what to improve
- pronunciation band: estimate 5.5-7.5 based on vocabulary sophistication (no audio = use 6.0 as neutral)

Question asked: {question}
Student's transcript: {transcript}"""


def _heuristic_speaking(transcript: str, question: str, part: int) -> dict:
    words = transcript.strip().split()
    wc = len(words)
    if wc < 20:   band = 4.5
    elif wc < 50: band = 5.5
    elif wc < 80: band = 6.0
    else:         band = 6.5
    return {
        "band_score": band,
        "source": "heuristic",
        "criteria": {
            "fluency_coherence": {"band": band, "comment": "Heuristic estimate."},
            "lexical_resource":  {"band": band, "comment": "Heuristic estimate."},
            "grammatical_range": {"band": band, "comment": "Heuristic estimate."},
            "pronunciation":     {"band": 6.0, "comment": "Enable AI scoring for pronunciation feedback."},
        },
        "feedback": "Submit your audio to get full AI feedback from Mr. Yeti!",
        "band8_sample": "",
        "pronunciation_note": "",
    }


def evaluate_speaking(transcript: str, question: str, part: int = 1) -> dict:
    if not transcript or len(transcript.strip()) < 10:
        return _heuristic_speaking(transcript or "", question, part)

    api_key = config.GOOGLE_API_KEY
    if not api_key or api_key.startswith("YOUR"):
        return _heuristic_speaking(transcript, question, part)

    model = os.getenv("GEMINI_MODEL", config.GEMINI_MODEL)
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        user_msg = _SPEAKING_PROMPT.format(
            part=part,
            schema=_SPEAKING_SCHEMA,
            question=question,
            transcript=transcript,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_msg}],
            temperature=0.3,
            max_tokens=1500,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result = json.loads(raw)
        result["source"] = "gemini"
        return result
    except Exception as exc:
        fallback = _heuristic_speaking(transcript, question, part)
        fallback["ai_error"] = str(exc)
        return fallback


def transcribe_and_evaluate(
    audio_bytes: bytes,
    mime_type: str,
    question: str,
    part: int = 1,
) -> dict:
    transcript = _transcribe(audio_bytes, mime_type)
    result = evaluate_speaking(transcript or "(inaudible)", question, part)
    result["transcript"] = transcript
    return result
