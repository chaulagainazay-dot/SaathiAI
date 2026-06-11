"""SaathiAI FastAPI server — voice + text + files, serving the Siri-style web app."""
import base64
import time

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, voice
from .agent import SaathiAgent

app = FastAPI(title="SaathiAI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# Simple access key for remote/tunnel use. Local requests (the Mac itself)
# are always allowed; remote requests must send X-Saathi-Token.
import os as _os
ACCESS_TOKEN = _os.getenv("SAATHI_TOKEN", "")


@app.middleware("http")
async def _auth(request, call_next):
    from fastapi.responses import JSONResponse
    if (ACCESS_TOKEN and request.url.path.startswith("/api/")
            and request.client.host not in ("127.0.0.1", "::1")
            and request.headers.get("x-saathi-token") != ACCESS_TOKEN):
        return JSONResponse({"error": "missing or wrong access token"}, status_code=401)
    return await call_next(request)

agent = SaathiAgent()

FILES_DIR = config.ROOT / "data" / "files"
FILES_DIR.mkdir(parents=True, exist_ok=True)

# follow-up window: after a reply, commands don't need the wake word
_last_reply_at = 0.0
FOLLOWUP_WINDOW = 15.0


class ChatIn(BaseModel):
    text: str
    session_id: str = "default"
    speaker_verified: bool = False


def _safe_respond(text: str, session_id: str, speaker_verified: bool) -> str:
    try:
        return agent.respond(text, session_id, speaker_verified=speaker_verified)
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower():
            return ("Maaf garnus Ajay — my free brain quota is finished for today "
                    "and the local brain isn't running. Open the Ollama app on the "
                    "Mac, or try again after midnight (Pacific time).")
        return f"Sorry, something broke on my side: {type(e).__name__}. Try again?"


@app.post("/api/v1/agent/chat")
def chat(body: ChatIn):
    reply = _safe_respond(body.text, body.session_id, body.speaker_verified)
    return {"reply": reply}


@app.post("/api/v1/voice/command")
async def voice_command(file: UploadFile = File(...),
                        session_id: str = Form("default"),
                        speak_reply: bool = Form(True),
                        require_wake: bool = Form(False)):
    """Full voice turn: audio → verify speaker → transcribe → (wake check) → agent → TTS."""
    global _last_reply_at
    audio = await file.read()

    stt = voice.transcribe(audio, file.filename or "audio.wav")
    text = stt["text"].strip()
    if not text:
        return {"ignored": "no_speech"}

    if require_wake:
        from .listener import strip_wake_word
        stripped = strip_wake_word(text)
        in_conversation = (time.time() - _last_reply_at) < FOLLOWUP_WINDOW
        if stripped is not None:
            text = stripped or "hello"
        elif in_conversation:
            pass  # follow-up, use full text
        else:
            return {"ignored": "no_wake_word", "transcript": stt["text"]}

    try:
        ver = voice.verify(audio)
    except Exception as e:
        ver = {"verified": False, "reason": f"verify_error: {e}", "similarity": 0.0}

    reply = _safe_respond(text, session_id, ver.get("verified", False))
    _last_reply_at = time.time()

    out = {"transcript": text, "language": stt["language"],
           "verification": ver, "reply": reply}
    if speak_reply:
        try:
            audio_out, mime = voice.synthesize(reply, stt["language"])
            out["reply_audio_b64"] = base64.b64encode(audio_out).decode()
            out["reply_audio_mime"] = mime
        except Exception as e:
            out["tts_error"] = str(e)
    return out


@app.post("/api/v1/voice/enroll")
async def enroll_voice(file: UploadFile = File(...)):
    voice.enroll(await file.read())
    return {"status": "enrolled"}


@app.post("/api/v1/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """Drag-and-drop target: store the file where Saathi's file tools can read it."""
    name = (file.filename or "unnamed").replace("/", "_")
    dest = FILES_DIR / name
    dest.write_bytes(await file.read())
    return {"stored": name, "size": dest.stat().st_size,
            "note": "Saathi can now read this file — just ask about it."}


@app.get("/api/v1/health")
def health():
    return {"ok": True, "provider": config.LLM_PROVIDER}


app.mount("/", StaticFiles(directory=str(config.ROOT / "client"), html=True),
          name="client")


@app.on_event("startup")
def _start_self_improvement():
    """Run a self-improvement cycle once a day in the background."""
    import threading

    def loop():
        import time
        while True:
            time.sleep(24 * 3600)
            try:
                from . import selfimprove
                selfimprove.run_cycle()
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True).start()


def main():
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
