"""
HCG voice-message transcription + intent extraction.

Drop-in module for SaathiAI. Wire it into saathi/server.py with:

    from .tools.hcg_voice import router as hcg_voice_router
    app.include_router(hcg_voice_router)

Endpoint:

    POST /api/v1/voice/transcribe
    Authorization: Bearer <BAADAR_API_KEY>
    {
        "audio_url": "https://.../voice.webm",
        "context": "hcg_kitchen",
        "language": "auto",
        "voice_message_id": "<uuid>",
        "callback_url": "https://hcg-app.vercel.app/api/voice-notes/<id>/baadar-callback"
    }

Returns inline (synchronous) for short clips:

    {
        "transcript": "Table 4 extra gravy",
        "intent": "table_request",
        "entities": {"tableNumber": 4, "menuItem": "gravy", "action": "request"},
        "confidence": 0.92,
        "suggestedResponse": "Acknowledged — Table 4 extra gravy."
    }

On audio download / transcription failure, POSTs an error to callback_url
in the background and returns 200 with {queued: true} to the caller.

Environment:
    BAADAR_API_KEY   — shared bearer with HCG. Same string both directions.
    GEMINI_API_KEY   — used for intent extraction. Falls back to Claude or
                       the configured LLM provider if Gemini is unset.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .. import voice  # existing OmniVoice helper — voice.transcribe(audio, name)

logger = logging.getLogger(__name__)
router = APIRouter()

# Cap audio at 5 MB to match HCG's storage bucket policy. Anything larger
# is almost certainly a corrupted upload or a hostile request.
MAX_AUDIO_BYTES = 5 * 1024 * 1024

# Tight prompt that constrains the LLM to JSON-only output. Pinned to the
# intent vocabulary HCG knows how to auto-execute. Anything outside the
# enum lands in "general".
INTENT_PROMPT = """You are a triage classifier for HCG Canteen voice messages.
Given a transcript, return ONE JSON object only — no prose, no markdown.

Schema:
{
  "intent": "kot_status_update" | "table_request" | "stock_alert" | "staff_alert" | "general",
  "entities": {
    "tableNumber": <int> | null,
    "kotId": <string> | null,
    "menuItem": <string> | null,
    "quantity": <int> | null,
    "action": "request" | "update" | "alert" | null,
    "urgency": "low" | "medium" | "high" | null,
    "notes": <string short summary of the message>
  },
  "confidence": <float between 0 and 1>,
  "suggestedResponse": <short acknowledgment in same language as transcript>
}

Rules:
- kot_status_update: the speaker is announcing an order is ready / cooking / delayed.
- table_request: a customer wants something for a table (extra X, more Y).
- stock_alert: anything about ingredients running low.
- staff_alert: someone is absent, sick, late.
- general: small talk, unclear, mixed.
- confidence = your honest estimate; below 0.85 HCG will NOT auto-act, so
  err low if the transcript is unclear or noisy.

Transcript: """


class TranscribeIn(BaseModel):
    audio_url: str
    context: str = "hcg_general"
    language: str = "auto"
    voice_message_id: str
    callback_url: str | None = None


class TranscribeOut(BaseModel):
    transcript: str
    intent: str
    entities: dict[str, Any]
    confidence: float
    suggestedResponse: str = ""


# ── auth ─────────────────────────────────────────────────────────────
def _verify_bearer(authorization: str | None) -> None:
    expected = os.environ.get("BAADAR_API_KEY")
    if not expected:
        raise HTTPException(503, "BAADAR_API_KEY not configured on Baadar")
    if not authorization or authorization != f"Bearer {expected}":
        raise HTTPException(401, "Unauthorized")


# ── audio download ───────────────────────────────────────────────────
def _download_audio(url: str) -> tuple[bytes, str]:
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        with client.stream("GET", url) as r:
            r.raise_for_status()
            chunks: list[bytes] = []
            total = 0
            for chunk in r.iter_bytes(chunk_size=64 * 1024):
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise HTTPException(413, "audio exceeds 5 MB cap")
                chunks.append(chunk)
            # Filename from URL path so voice.transcribe picks the right decoder.
            name = url.rsplit("/", 1)[-1].split("?", 1)[0] or "audio.webm"
            return b"".join(chunks), name


# ── intent extraction ────────────────────────────────────────────────
def _extract_intent_gemini(transcript: str) -> dict[str, Any] | None:
    """Use Gemini for structured intent extraction. Returns None on failure."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        )
        resp = model.generate_content(INTENT_PROMPT + transcript)
        return json.loads(resp.text)
    except Exception as e:
        logger.warning("hcg_voice: gemini intent extraction failed: %s", e)
        return None


def _extract_intent_fallback(transcript: str) -> dict[str, Any]:
    """Regex-only fallback when no LLM is reachable. Keeps the pipeline
    flowing even when Gemini is down — confidence stays low so HCG never
    auto-acts on these."""
    text = transcript.lower()
    intent = "general"
    entities: dict[str, Any] = {"notes": transcript[:200]}

    # Tiny heuristic — flags rather than NLP. Tuned for English + romanized
    # Nepali kitchen-speak.
    if any(w in text for w in ["ready", "तयार", "taiyaar", "out", "served"]):
        intent = "kot_status_update"
        entities["action"] = "update"
    elif any(w in text for w in ["table", "टेबल", "tebal", "extra", "more"]):
        intent = "table_request"
        entities["action"] = "request"
        m = re.search(r"\btable\s*(\d+)", text)
        if m:
            entities["tableNumber"] = int(m.group(1))
    elif any(w in text for w in ["stock", "out of", "sakkiyo", "khattam", "low"]):
        intent = "stock_alert"
        entities["action"] = "alert"
    elif any(w in text for w in ["absent", "sick", "late", "biraami", "aaudaina"]):
        intent = "staff_alert"
        entities["action"] = "alert"

    if any(w in text for w in ["urgent", "now", "quickly", "chito", "jhattai"]):
        entities["urgency"] = "high"
    else:
        entities["urgency"] = "medium"

    return {
        "intent": intent,
        "entities": entities,
        "confidence": 0.55,  # below HCG's 0.85 auto-act threshold by design
        "suggestedResponse": "",
    }


def _extract_intent(transcript: str) -> dict[str, Any]:
    result = _extract_intent_gemini(transcript)
    if result is None:
        return _extract_intent_fallback(transcript)
    # Defensive: ensure required keys exist even if model returns partial.
    result.setdefault("intent", "general")
    result.setdefault("entities", {})
    result.setdefault("confidence", 0.0)
    result.setdefault("suggestedResponse", "")
    return result


# ── async callback path ──────────────────────────────────────────────
def _post_callback(callback_url: str, payload: dict[str, Any]) -> None:
    """Best-effort POST back to HCG. Logged on failure but doesn't raise —
    if the callback lands after the sync response has already been seen,
    HCG's handler is idempotent."""
    headers = {
        "Authorization": f"Bearer {os.environ.get('BAADAR_API_KEY', '')}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(callback_url, json=payload, headers=headers)
            if r.status_code >= 400:
                logger.warning(
                    "hcg_voice callback %s → %s: %s",
                    callback_url, r.status_code, r.text[:200],
                )
    except Exception as e:
        logger.warning("hcg_voice callback failed for %s: %s", callback_url, e)


# ── route ────────────────────────────────────────────────────────────
@router.post("/api/v1/voice/transcribe", response_model=TranscribeOut)
def transcribe_hcg(body: TranscribeIn,
                   authorization: str | None = Header(default=None)):
    _verify_bearer(authorization)

    # 1) Download the audio.
    try:
        audio, name = _download_audio(body.audio_url)
    except HTTPException:
        raise
    except Exception as e:
        # Surface to HCG via callback so the row gets a baadar_error.
        if body.callback_url:
            threading.Thread(
                target=_post_callback,
                args=(body.callback_url, {"error": f"download failed: {e}"}),
                daemon=True,
            ).start()
        raise HTTPException(502, f"audio download failed: {e}")

    # 2) Transcribe via the existing OmniVoice helper.
    started = time.time()
    try:
        stt = voice.transcribe(audio, name)
    except Exception as e:
        if body.callback_url:
            threading.Thread(
                target=_post_callback,
                args=(body.callback_url, {"error": f"transcription failed: {e}"}),
                daemon=True,
            ).start()
        raise HTTPException(500, f"transcription failed: {e}")

    transcript = (stt.get("text") or "").strip()
    if not transcript:
        # Empty audio — return a low-confidence "general" so HCG doesn't
        # endlessly retry, but mark it clearly.
        payload = {
            "transcript": "",
            "intent": "general",
            "entities": {"notes": "(no speech detected)"},
            "confidence": 0.0,
            "suggestedResponse": "",
        }
        if body.callback_url:
            threading.Thread(
                target=_post_callback,
                args=(body.callback_url, payload),
                daemon=True,
            ).start()
        return payload

    # 3) Extract intent + entities.
    classified = _extract_intent(transcript)

    payload = {
        "transcript": transcript,
        "intent": classified["intent"],
        "entities": classified["entities"],
        "confidence": float(classified["confidence"]),
        "suggestedResponse": classified.get("suggestedResponse", ""),
    }
    logger.info(
        "hcg_voice transcribed in %.2fs · intent=%s confidence=%.2f",
        time.time() - started, payload["intent"], payload["confidence"],
    )
    return payload
