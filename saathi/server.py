"""SaathiAI FastAPI server — voice + text + files, serving the Siri-style web app."""
import base64
import time

from fastapi import FastAPI, File, Form, Request, UploadFile
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
import hashlib as _hashlib
import secrets as _secrets

ACCESS_TOKEN = _os.getenv("SAATHI_TOKEN", "")
_RAW_PASSWORD = _os.getenv("BAADAR_PASSWORD", "")
_PASSWORD_HASH = _hashlib.sha256(_RAW_PASSWORD.encode()).hexdigest() if _RAW_PASSWORD else ""


def _session_token() -> str:
    """Deterministic session token derived from the current password hash.
    Stateless — survives server restarts. Changing the password invalidates
    every existing session automatically (recomputes to a new value)."""
    return _hashlib.sha256((_PASSWORD_HASH + ":baadar-session").encode()).hexdigest()


def _is_authed(request) -> bool:
    """Check session token from cookie or header."""
    if not _PASSWORD_HASH:
        return True
    token = (request.cookies.get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    return token == _session_token()


@app.middleware("http")
async def _auth(request, call_next):
    from fastapi.responses import JSONResponse
    path = request.url.path
    # Always allow: login endpoint, static assets, manifest, icons
    if (path == "/api/v1/auth/login"
            or not path.startswith("/api/")):
        return await call_next(request)
    # Legacy remote token (backward compat)
    if ACCESS_TOKEN and request.headers.get("x-saathi-token") == ACCESS_TOKEN:
        return await call_next(request)
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

class LoginIn(BaseModel):
    password: str

@app.post("/api/v1/auth/login")
def login(body: LoginIn):
    from fastapi.responses import JSONResponse
    import hashlib
    if _PASSWORD_HASH:
        given = hashlib.sha256(body.password.encode()).hexdigest()
        if given != _PASSWORD_HASH:
            return JSONResponse({"ok": False, "error": "Wrong password"}, status_code=401)
    token = _session_token()
    r = JSONResponse({"ok": True, "token": token})
    r.set_cookie("baadar_session", token, httponly=True, samesite="lax", max_age=30*24*3600)
    return r

class ChangePasswordIn(BaseModel):
    current: str
    new_password: str

@app.post("/api/v1/auth/change-password")
def change_password(body: ChangePasswordIn):
    global _PASSWORD_HASH, _RAW_PASSWORD
    import hashlib, re
    from fastapi.responses import JSONResponse
    if _PASSWORD_HASH and hashlib.sha256(body.current.encode()).hexdigest() != _PASSWORD_HASH:
        return JSONResponse({"ok": False, "error": "Current password is wrong"}, status_code=400)
    if len(body.new_password) < 4:
        return JSONResponse({"ok": False, "error": "Password must be at least 4 characters"}, status_code=400)
    _RAW_PASSWORD = body.new_password
    _PASSWORD_HASH = hashlib.sha256(body.new_password.encode()).hexdigest()
    env_path = config.ROOT / ".env"
    text = env_path.read_text()
    text = re.sub(r'^BAADAR_PASSWORD=.*$', f'BAADAR_PASSWORD={body.new_password}', text, flags=re.MULTILINE)
    env_path.write_text(text)
    return {"ok": True}

@app.post("/api/v1/auth/logout")
def logout(request: Request):
    from fastapi.responses import JSONResponse
    r = JSONResponse({"ok": True})
    r.delete_cookie("baadar_session")
    return r

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


@app.post("/api/v1/agent/chat_with_file")
async def chat_with_file(
    file: UploadFile = File(...),
    message: str = Form(default=""),
    session_id: str = Form(default="default"),
):
    """Chat with an attached file (PDF, image, text). Extracts content and sends to agent."""
    import io
    name = (file.filename or "file").replace("/", "_")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    data = await file.read()

    extracted = ""
    file_note = f"[Attached: {name}]"

    if ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(data))
            pages = [p.extract_text() or "" for p in reader.pages[:20]]
            extracted = "\n\n".join(p for p in pages if p.strip())
            file_note = f"[PDF: {name}, {len(reader.pages)} pages]"
        except Exception as e:
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    extracted = "\n\n".join(p.extract_text() or "" for p in pdf.pages[:20])
                file_note = f"[PDF: {name}]"
            except Exception:
                extracted = f"(Could not extract PDF text: {e})"
    elif ext in ("jpg", "jpeg", "png", "webp", "gif", "bmp"):
        # Save image to files dir so agent's look_at_screen / read_mac_file can see it
        dest = FILES_DIR / name
        dest.write_bytes(data)
        b64 = base64.b64encode(data).decode()
        # Include base64 inline for vision-capable models
        extracted = f"[IMAGE DATA base64:{ext}:{b64[:200]}…]"
        file_note = f"[Image: {name}, saved to files]"
    elif ext in ("txt", "md", "csv", "json", "py", "js", "ts", "html", "css"):
        try:
            extracted = data.decode("utf-8", errors="replace")[:8000]
            file_note = f"[File: {name}]"
        except Exception:
            extracted = "(Could not read file)"
    else:
        # Save anything else to files dir
        dest = FILES_DIR / name
        dest.write_bytes(data)
        extracted = f"(Binary file saved — ask me about {name})"
        file_note = f"[File: {name} saved]"

    user_msg = message.strip() or "Please read and summarize this."
    full_prompt = f"{file_note}\n\n{extracted[:6000]}\n\n{user_msg}" if extracted else f"{file_note}\n\n{user_msg}"

    reply = _safe_respond(full_prompt, session_id, speaker_verified=False)
    return {"reply": reply, "file": name, "extracted_chars": len(extracted)}


@app.get("/api/v1/agent/activity")
def agent_activity(session_id: str = "default", after: int = 0):
    """Live step-by-step mirror of what Baadar is doing right now (polled by the UI)."""
    from . import activity
    return {"events": activity.since(session_id, after)}


@app.get("/api/v1/progress")
def get_progress():
    """Your content journey: which day you're on (Day 1 = first content), how many
    video plans + posts done, and progress toward a 30-day goal."""
    import re
    from datetime import date
    cdir = config.ROOT / "data" / "content"
    plans = sorted(cdir.glob("flow-*.json")) if cdir.exists() else []
    packs = sorted(cdir.glob("[0-9]*.json")) if cdir.exists() else []
    videos = list((cdir / "videos").glob("*.mp4")) if (cdir / "videos").exists() else []
    # earliest dated file marks Day 1
    dates = []
    for f in plans + packs:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", f.name)
        if m:
            try: dates.append(date(*map(int, m.groups())))
            except ValueError: pass
    start = min(dates) if dates else date.today()
    day = (date.today() - start).days + 1
    GOAL = 30
    return {"day": day, "goal": GOAL,
            "plans": len(plans), "videos": len(videos),
            "start": start.isoformat(),
            "pct": round(min(day / GOAL, 1.0) * 100)}


@app.get("/api/v1/tasks")
def get_tasks(include_done: bool = False):
    """In-app notifications + to-do list (with links) so Ajay never needs Telegram/browser."""
    from . import tasks
    return {"items": tasks.list_items(include_done)}


@app.post("/api/v1/tasks/{tid}/done")
def task_done(tid: int):
    from . import tasks
    return {"ok": tasks.mark_done(tid)}


@app.post("/api/v1/tasks/clear-done")
def task_clear_done():
    from . import tasks
    tasks.clear_done()
    return {"ok": True}


@app.get("/api/v1/pielts/dashboard")
def pielts_dashboard():
    """PIELTS project dashboard — uploads, growth targets, money goal."""
    from . import pielts
    return pielts.dashboard()


class TargetIn(BaseModel):
    subscribers_goal: int | None = None
    views_goal: int | None = None
    monthly_revenue_goal_usd: int | None = None


@app.post("/api/v1/pielts/targets")
def pielts_set_targets(body: TargetIn):
    from . import pielts
    return {"saved": pielts.set_targets(**body.dict())}


@app.get("/api/v1/connections")
def get_connections():
    from . import connections
    return {"connections": connections.get_all()}


class ConnIn(BaseModel):
    platform: str
    connected: bool | None = None
    method: str | None = None
    handle: str | None = None
    webhook: str | None = None


@app.post("/api/v1/connections")
def set_connection(body: ConnIn):
    from . import connections
    cfg = {k: v for k, v in body.dict().items() if k != "platform" and v is not None}
    return {"saved": connections.save_one(body.platform, cfg)}


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


_PENDING_DRAFT: dict = {}

class DraftStageIn(BaseModel):
    platform: str
    content: str
    title: str = ""
    platforms: list[str] = []

class ApproveIn(BaseModel):
    platform: str
    content: str
    title: str = ""
    post_all: bool = False

@app.get("/api/v1/content/pending")
def get_pending():
    return _PENDING_DRAFT if _PENDING_DRAFT else {"pending": False}

@app.post("/api/v1/content/stage")
def stage_draft(body: DraftStageIn):
    global _PENDING_DRAFT
    _PENDING_DRAFT = {"pending": True, "platform": body.platform,
                      "content": body.content, "title": body.title,
                      "platforms": body.platforms}
    return {"ok": True}

@app.post("/api/v1/content/approve")
def approve_draft(body: ApproveIn):
    global _PENDING_DRAFT
    from .tools import content as _content
    if body.post_all:
        result = _content.post_all(body.content, body.title)
    else:
        result = _content.post(body.platform, body.content, body.title)
    _PENDING_DRAFT = {}
    return result

@app.delete("/api/v1/content/pending")
def discard_draft():
    global _PENDING_DRAFT
    _PENDING_DRAFT = {}
    return {"ok": True}

@app.get("/api/v1/baadar/status")
def baadar_status():
    import time as _time
    online = False
    try:
        import urllib.request
        urllib.request.urlopen("https://api.groq.com", timeout=3)
        online = True
    except Exception:
        pass
    ollama_ready = False
    try:
        import urllib.request as _ur
        _ur.urlopen(config.OLLAMA_URL.replace("/v1", "") + "/api/tags", timeout=2)
        ollama_ready = True
    except Exception:
        pass
    if config.LLM_PROVIDER == "groq":
        model = config.GROQ_MODEL
    elif config.LLM_PROVIDER == "gemini":
        model = config.GEMINI_MODEL
    elif config.LLM_PROVIDER == "ollama":
        model = config.OLLAMA_MODEL
    else:
        model = config.CLAUDE_MODEL
    tools_count = 0
    try:
        from .tools.registry import TOOL_SCHEMAS
        tools_count = len(TOOL_SCHEMAS)
    except Exception:
        pass
    return {
        "provider": config.LLM_PROVIDER,
        "model": model,
        "online": online,
        "ollama_ready": ollama_ready,
        "tools": tools_count,
    }


@app.get("/api/v1/hcgms/dashboard")
def hcgms_dashboard():
    from .tools import canteen
    sales = {}
    reports = {}
    credits = {}
    hygiene = {}
    try: sales = canteen.query("sales_today")
    except Exception as e: sales = {"error": str(e)}
    try: reports = canteen.query("missing_reports")
    except Exception as e: reports = {"error": str(e)}
    try: credits = canteen.query("credit_alerts")
    except Exception as e: credits = {"error": str(e)}
    try: hygiene = canteen.query("hygiene_status")
    except Exception as e: hygiene = {"error": str(e)}
    return {"sales": sales, "reports": reports, "credits": credits, "hygiene": hygiene}


PROJECT_ROOT = config.ROOT
SKIP = {"__pycache__", ".git", ".venv", "venv", "node_modules", "dist", "build",
        ".next", "saathiai.egg-info", ".mypy_cache"}


def _safe_project_path(rel: str) -> "Path | None":
    from pathlib import Path
    p = (PROJECT_ROOT / rel).resolve()
    if not str(p).startswith(str(PROJECT_ROOT.resolve())):
        return None
    return p


@app.get("/api/v1/project/tree")
def project_tree(rel: str = ""):
    from pathlib import Path
    root = _safe_project_path(rel) if rel else PROJECT_ROOT
    if not root or not root.is_dir():
        from fastapi import HTTPException
        raise HTTPException(404, "not found")
    entries = []
    try:
        for p in sorted(root.iterdir()):
            if p.name.startswith(".") and p.name not in (".env",):
                continue
            if p.name in SKIP:
                continue
            relpath = str(p.relative_to(PROJECT_ROOT))
            entries.append({
                "name": p.name,
                "path": relpath,
                "type": "dir" if p.is_dir() else "file",
                "size": p.stat().st_size if p.is_file() else None,
                "ext": p.suffix.lower() if p.is_file() else None,
            })
    except PermissionError:
        pass
    return {"entries": entries, "current": str(root.relative_to(PROJECT_ROOT)) if root != PROJECT_ROOT else ""}


TEXT_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".md", ".txt", ".yaml",
             ".yml", ".html", ".css", ".sh", ".env", ".toml", ".cfg", ".ini",
             ".sql", ".csv", ".log", ".plist", ".xml"}

@app.get("/api/v1/project/file")
def read_project_file(rel: str):
    p = _safe_project_path(rel)
    if not p or not p.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "not found")
    if p.is_dir():
        from fastapi import HTTPException
        raise HTTPException(400, "is a directory")
    if p.suffix.lower() not in TEXT_EXTS or p.stat().st_size > 500_000:
        return {"binary": True, "size": p.stat().st_size, "name": p.name}
    return {"content": p.read_text(errors="replace"), "name": p.name, "path": rel}


class FileWriteIn(BaseModel):
    rel: str
    content: str

@app.post("/api/v1/project/file")
def write_project_file(body: FileWriteIn):
    p = _safe_project_path(body.rel)
    if not p:
        from fastapi import HTTPException
        raise HTTPException(403, "path outside project")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.content)
    return {"ok": True, "path": body.rel, "bytes": len(body.content.encode())}


class FileDeleteIn(BaseModel):
    rel: str

@app.delete("/api/v1/project/file")
def delete_project_file(body: FileDeleteIn):
    p = _safe_project_path(body.rel)
    if not p or not p.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "not found")
    if p.is_dir():
        import shutil
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True, "deleted": body.rel}


# ══════════════════════════════════════════════════════════════════
#  MAC FILE MANAGER — browse/read/write/delete anywhere in ~/
# ══════════════════════════════════════════════════════════════════
from pathlib import Path as _Path

_MAC_ROOT = _Path.home()
_MAC_SKIP = {"__pycache__", ".Trash", ".Spotlight-V100", ".fseventsd",
             ".DS_Store", ".localized", "Library"}
_MAC_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
_MAC_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
_MAC_TEXT_EXTS  = {".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".md", ".txt",
                   ".yaml", ".yml", ".html", ".css", ".sh", ".env", ".toml",
                   ".cfg", ".ini", ".sql", ".csv", ".log", ".xml", ".plist"}


def _safe_mac_path(path_str: str) -> "_Path | None":
    try:
        p = _Path(path_str).expanduser().resolve()
        if not str(p).startswith(str(_MAC_ROOT)):
            return None
        return p
    except Exception:
        return None


@app.get("/api/v1/mac/tree")
def mac_tree(path: str = ""):
    root = _safe_mac_path(path) if path else _MAC_ROOT
    if not root or not root.is_dir():
        from fastapi import HTTPException
        raise HTTPException(404, "not found")
    entries = []
    try:
        for p in sorted(root.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            if p.name.startswith(".") and p.name not in (".env",):
                continue
            if p.name in _MAC_SKIP:
                continue
            ext = p.suffix.lower() if p.is_file() else None
            is_img = ext in _MAC_IMAGE_EXTS if ext else False
            is_vid = ext in _MAC_VIDEO_EXTS if ext else False
            try:
                size = p.stat().st_size if p.is_file() else None
            except Exception:
                size = None
            entries.append({
                "name": p.name,
                "path": str(p),
                "type": "dir" if p.is_dir() else "file",
                "size": size,
                "ext": ext,
                "is_image": is_img,
                "is_video": is_vid,
            })
    except PermissionError:
        pass
    parent = str(root.parent) if root != _MAC_ROOT else None
    return {"entries": entries, "current": str(root), "parent": parent,
            "home": str(_MAC_ROOT)}


@app.get("/api/v1/mac/file")
def mac_read_file(path: str):
    p = _safe_mac_path(path)
    if not p or not p.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "not found")
    if p.is_dir():
        from fastapi import HTTPException
        raise HTTPException(400, "is a directory")
    ext = p.suffix.lower()
    if ext in _MAC_IMAGE_EXTS:
        import base64
        data = p.read_bytes()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(
                ext.lstrip("."), "application/octet-stream")
        return {"image": True, "b64": base64.b64encode(data).decode(),
                "mime": mime, "name": p.name, "size": len(data)}
    if ext not in _MAC_TEXT_EXTS or p.stat().st_size > 1_000_000:
        return {"binary": True, "size": p.stat().st_size, "name": p.name, "ext": ext}
    return {"content": p.read_text(errors="replace"), "name": p.name, "path": str(p)}


class MacFolderIn(BaseModel):
    path: str

@app.post("/api/v1/mac/folder")
def mac_create_folder(body: MacFolderIn):
    p = _safe_mac_path(body.path)
    if not p:
        from fastapi import HTTPException
        raise HTTPException(403, "path outside home")
    p.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(p)}


class MacDeleteIn(BaseModel):
    path: str

@app.delete("/api/v1/mac/item")
def mac_delete_item(body: MacDeleteIn):
    import shutil
    p = _safe_mac_path(body.path)
    if not p or not p.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "not found")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True}


class MacRenameIn(BaseModel):
    src: str
    dst: str

@app.post("/api/v1/mac/rename")
def mac_rename_item(body: MacRenameIn):
    src = _safe_mac_path(body.src)
    dst = _safe_mac_path(body.dst)
    if not src or not dst:
        from fastapi import HTTPException
        raise HTTPException(403, "path outside home")
    if not src.exists():
        from fastapi import HTTPException
        raise HTTPException(404, "source not found")
    src.rename(dst)
    return {"ok": True, "new_path": str(dst)}


@app.get("/api/v1/health")
def health():
    return {"ok": True, "provider": config.LLM_PROVIDER}


# ══════════════════════════════════════════════════════════════════════════════
# CONTENT STUDIO — 9-Stage Automation Pipeline
# ══════════════════════════════════════════════════════════════════════════════

# Stage 1 — Content Research
@app.post("/api/v1/studio/research")
async def studio_research(request: Request):
    """Fetch trending IELTS topics from Reddit + YouTube + Google Trends."""
    from .tools.content_research import research_daily_topics
    try:
        return research_daily_topics()
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/v1/studio/research/latest")
async def studio_research_latest():
    from .tools.content_research import get_latest_research
    return get_latest_research()

# Stage 2 — Script Writing
class ScriptIn(BaseModel):
    topic: str
    content_type: str = "tip"
    format: str = "short"  # short | long

@app.post("/api/v1/studio/script")
async def studio_script(body: ScriptIn, request: Request):
    """Generate YouTube script with hook, lesson, CTA."""
    from .tools.script_writer import generate_script
    try:
        return generate_script(body.topic, body.content_type, body.format)
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/v1/studio/script/latest")
async def studio_script_latest():
    from .tools.script_writer import get_latest_script
    return get_latest_script()

# Stage 3 — Voice Generation
class VoiceIn(BaseModel):
    text: str
    accent: str = "co.uk"  # co.uk=British | com.au=Australian | com=American

@app.post("/api/v1/studio/voice")
async def studio_voice(body: VoiceIn, request: Request):
    """Generate voice narration using gTTS (British/Australian/American accent)."""
    import tempfile, time as _time
    from pathlib import Path as _Path
    voices_dir = _Path.home() / "SaathiAI" / "voices_output"
    voices_dir.mkdir(exist_ok=True)
    output_path = voices_dir / f"voice_{int(_time.time())}.mp3"
    try:
        from gtts import gTTS
        tts = gTTS(text=body.text[:1000], lang="en", tld=body.accent, slow=False)
        tts.save(str(output_path))
        return {"ok": True, "voice_path": str(output_path), "accent": body.accent}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/v1/studio/voice/download")
async def studio_voice_download(path: str):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse as _FR
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "not found")
    return _FR(str(p), media_type="audio/mpeg", filename=p.name)

# Stage 4 — Yeti Pose (warm up / pre-cache all poses)
@app.post("/api/v1/studio/yeti_pose")
async def studio_yeti_pose(request: Request):
    """Pre-generate or return cached Yeti pose image."""
    body = await request.json()
    pose = body.get("pose", "teaching")
    try:
        from .tools.reel_maker import _get_yeti_pose
        path = _get_yeti_pose(pose)
        return {"ok": True, "pose": pose, "path": str(path)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/v1/studio/yeti_warmup")
async def studio_yeti_warmup(request: Request):
    """Pre-generate ALL 6 Yeti poses for consistent use. Run once."""
    from .tools.reel_maker import _get_yeti_pose, _YETI_POSES
    results = {}
    for pose in _YETI_POSES:
        try:
            path = _get_yeti_pose(pose)
            results[pose] = {"ok": True, "path": str(path)}
        except Exception as e:
            results[pose] = {"ok": False, "error": str(e)}
    return results

# Stage 5 — Full Short Video (image + voice + music → MP4)
class ShortVideoIn(BaseModel):
    topic: str = ""
    script_path: str = ""
    pose: str = "teaching"
    with_voice: bool = True
    slot: str = "auto"

@app.post("/api/v1/studio/short_video")
async def studio_short_video(body: ShortVideoIn, request: Request):
    """Create a complete YouTube Short from script."""
    from .tools.video_editor import create_short_video
    from .tools.script_writer import get_latest_script
    import json as _json

    if body.script_path:
        try:
            script = _json.loads(Path(body.script_path).read_text())
        except Exception:
            script = get_latest_script()
    elif body.topic:
        from .tools.script_writer import generate_script
        script = generate_script(body.topic, format="short")
    else:
        script = get_latest_script()

    try:
        return create_short_video(script, pose=body.pose, with_voice=body.with_voice)
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Stage 6 — Serve any video/audio file to n8n
@app.get("/api/v1/studio/download")
async def studio_download(path: str, request: Request):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse as _FR
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost") and not _is_authed(request):
        raise HTTPException(401, "unauthorized")
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"not found: {path}")
    ext = p.suffix.lower()
    mtype = {"mp4": "video/mp4", "mp3": "audio/mpeg", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext[1:], "application/octet-stream")
    return _FR(str(p), media_type=mtype, filename=p.name)

# Stage 7 — Thumbnail
class ThumbIn(BaseModel):
    title: str
    thumbnail_text: str
    style: str = "shocked"

@app.post("/api/v1/studio/thumbnail")
async def studio_thumbnail(body: ThumbIn, request: Request):
    from .tools.thumbnail_maker import generate_thumbnail
    try:
        return generate_thumbnail(body.title, body.thumbnail_text, body.style)
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Stage 8 — SEO Package
class SeoIn(BaseModel):
    topic: str
    hook: str = ""
    script_path: str = ""

@app.post("/api/v1/studio/seo")
async def studio_seo(body: SeoIn, request: Request):
    from .tools.seo_optimizer import generate_seo_package
    try:
        return generate_seo_package(body.topic, body.hook, body.script_path)
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Stage 8b — Log video performance (self-improvement)
class PerfIn(BaseModel):
    video_id: str
    platform: str
    views: int
    likes: int = 0
    hashtags: list[str] = []

@app.post("/api/v1/studio/log_performance")
async def studio_log_performance(body: PerfIn):
    from .tools.seo_optimizer import log_video_performance
    return log_video_performance(body.video_id, body.platform, body.views, body.likes, body.hashtags)

# Stage 9 — Full pipeline: research → script → video → SEO → ready to post
@app.post("/api/v1/studio/full_pipeline")
async def studio_full_pipeline(request: Request):
    """Run complete 9-stage pipeline. Returns all assets ready for posting."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    slot = body.get("slot", "auto")
    import datetime as _dt
    hour = _dt.datetime.now().hour
    if slot == "auto":
        slot = "morning" if hour < 14 else "evening"

    results = {"slot": slot, "stages": {}}

    # Stage 1: Use daily reel for shorts OR research for content ideas
    try:
        from .tools.reel_maker import make_daily_reel
        reel = make_daily_reel(slot)
        results["stages"]["reel"] = reel
        results["video_path"] = reel.get("video_path")
        results["title"] = reel.get("title")
        results["description"] = reel.get("description")
        results["tags"] = reel.get("tags")
    except Exception as e:
        results["stages"]["reel"] = {"ok": False, "error": str(e)}

    # Stage 7: Thumbnail
    try:
        from .tools.thumbnail_maker import generate_thumbnail
        thumb = generate_thumbnail(
            results.get("title","IELTS Tips"),
            results.get("title","Band 7\nSecret")[:30],
            style="shocked"
        )
        results["stages"]["thumbnail"] = thumb
        results["thumbnail_path"] = thumb.get("thumbnail_path")
    except Exception as e:
        results["stages"]["thumbnail"] = {"ok": False, "error": str(e)}

    # Stage 8: SEO
    try:
        from .tools.seo_optimizer import generate_seo_package
        seo = generate_seo_package(results.get("title","IELTS Tips"))
        results["stages"]["seo"] = seo
        results["seo"] = seo
    except Exception as e:
        results["stages"]["seo"] = {"ok": False, "error": str(e)}

    results["ok"] = bool(results.get("video_path"))
    return results


# ── Auto-reel: generate daily YouTube Short ────────────────────────────────────
from fastapi.responses import FileResponse

@app.post("/api/v1/auto_reel")
async def auto_reel(request: Request):
    """Generate a Mr. Yeti YouTube Short (image + music → MP4) and return metadata.
    Called by n8n cron twice daily; middleware handles auth."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    slot = body.get("slot", "auto")

    try:
        from .tools.reel_maker import make_daily_reel
        result = make_daily_reel(slot)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/v1/auto_reel/download")
async def auto_reel_download(path: str, request: Request):
    """Serve the generated reel video file to n8n for upload."""
    from fastapi import HTTPException
    # allow internal calls from n8n (localhost) without auth
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1", "localhost") and not _is_authed(request):
        raise HTTPException(401, "unauthorized")
    p = Path(path)
    if not p.exists() or not str(p).startswith(str(Path.home() / "SaathiAI" / "reels_output")):
        raise HTTPException(404, "not found")
    return FileResponse(str(p), media_type="video/mp4", filename=p.name)


# ── n8n status proxy (avoids CORS — browser can't hit localhost:5678 directly) ──
import httpx as _httpx

N8N_BASE_URL = _os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678")

@app.get("/api/v1/n8n/status")
def n8n_status():
    """Read n8n workflow status directly from SQLite — no API key needed."""
    import sqlite3 as _sqlite3
    import pathlib as _pathlib

    db_path = _pathlib.Path.home() / ".n8n" / "database.sqlite"
    try:
        con = _sqlite3.connect(str(db_path), timeout=3)
        rows = con.execute(
            "SELECT id, name, active FROM workflow_entity ORDER BY name"
        ).fetchall()
        con.close()
        workflows = [{"id": r[0], "name": r[1], "active": bool(r[2])} for r in rows]
        return {"ok": True, "workflows": workflows}
    except Exception as e:
        # fallback: try n8n healthz at least
        try:
            r = _httpx.get(f"{N8N_BASE_URL}/healthz", timeout=3)
            return {"ok": r.is_success, "workflows": [], "error": str(e)}
        except Exception:
            return {"ok": False, "workflows": [], "error": str(e)}


# ── Image generation (Gemini Imagen) ─────────────────────────────────────────
class ImageGenIn(BaseModel):
    prompt: str
    style: str = "social_media"  # social_media | logo | thumbnail

_YETI_CHARACTER = (
    "Mr. Yeti character — EXACT locked look: large broad-shouldered yeti, "
    "fluffy shaggy white/off-white realistic fur, wide warm smile showing teeth, "
    "large dark-brown eyes, round black-rimmed glasses on a broad flat nose, "
    "brown herringbone tweed blazer, light-blue oxford collared shirt, "
    "navy-blue polka-dot tie. "
    "Photorealistic cinematic 3D render, detailed fur simulation, warm studio lighting, "
    "Pixar/DreamWorks movie-character quality. Same face and outfit every time. "
)

_STYLE_PREFIX = {
    "social_media": (
        "Square (1:1) social media post image. "
        "Modern clean professional design, bold typography, navy blue and orange brand colours. "
    ),
    "thumbnail": (
        "YouTube thumbnail image (16:9 widescreen). "
        "Bold text overlay, high contrast, eye-catching composition. "
    ),
    "logo": (
        "Simple flat logo/icon. Minimal, clean, memorable, navy blue and orange palette. "
    ),
    "yeti_post": (
        "Square (1:1) social media post featuring Mr. Yeti. " + _YETI_CHARACTER +
        "Mr. Yeti is in the foreground, expressive pose. "
        "Bold white text overlay with the IELTS tip. pielts.web.app at the bottom. "
        "Navy blue background. Warm cinematic lighting. "
    ),
    "yeti_thumbnail": (
        "YouTube thumbnail (16:9) featuring Mr. Yeti. " + _YETI_CHARACTER +
        "Mr. Yeti in expressive reaction pose (shocked, excited, or pointing). "
        "Bold high-contrast text overlay. Eye-catching. pielts.web.app watermark. "
    ),
}

@app.post("/api/v1/generate_image")
async def generate_image(body: ImageGenIn, request: Request):
    if not _is_authed(request):
        from fastapi import HTTPException
        raise HTTPException(401, "unauthorized")

    full_prompt = _STYLE_PREFIX.get(body.style, "") + body.prompt

    try:
        import urllib.parse
        import httpx as _httpx

        w, h = (1024, 1024) if body.style != "thumbnail" else (1280, 720)
        encoded = urllib.parse.quote(full_prompt)
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={w}&height={h}&model=flux&nologo=true&seed={int(time.time())}"
        )
        resp = _httpx.get(url, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
        img_b64 = base64.b64encode(resp.content).decode()
        return {"ok": True, "image": img_b64, "mime": mime}
    except Exception as e:
        return {"ok": False, "error": str(e)}


app.mount("/", StaticFiles(directory=str(config.ROOT / "client"), html=True),
          name="client")


@app.on_event("startup")
def _start_background():
    """Daily self-improvement cycle + the proactive scheduler."""
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
    try:
        from . import scheduler
        scheduler.start()  # morning briefing, 9pm canteen summary, weekly backup
    except Exception:
        pass
    # Auto-register known projects so Baadar can access their files by name
    try:
        from .tools.projects import register_project
        import os as _os
        _home = _os.path.expanduser("~")
        for _name, _path in [
            ("baadar",  str(config.ROOT)),
            ("saathai", str(config.ROOT)),
            ("pielts",  f"{_home}/Downloads/ielts-practice-app"),
            ("hcgms",   f"{_home}/Downloads/hcgms"),
        ]:
            import pathlib as _pl
            if _pl.Path(_path).is_dir():
                register_project(_name, _path)
    except Exception:
        pass


def main():
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
