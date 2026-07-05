from __future__ import annotations
"""SaathiAI FastAPI server — voice + text + files, serving the Siri-style web app."""
import base64
import time

from fastapi import Body, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, voice
from .agent import SaathiAgent

app = FastAPI(title="SaathiAI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


# ── BFF: one aggregated contract for the CEO Home screen (desktop + mobile) ──
@app.get("/api/executive/briefing")
@app.get("/api/v1/ceo/home")
def ceo_home_endpoint():
    from saathi.bff import ceo_home
    return ceo_home()


# ── Human Browser Driver: the Mac Agent polls these (authenticated, NOT
# whitelisted — requires SAATHI_TOKEN). The VM only relays signed jobs; it never
# drives the browser or holds a cookie.
@app.get("/api/v1/human/claim")
def human_claim():
    from saathi.infrastructure.human_browser import default_queue
    env = default_queue.claim()
    if env is None:
        from fastapi.responses import Response
        return Response(status_code=204)
    return {"envelope": {"job": env.job, "signature": env.signature}}


@app.post("/api/v1/human/complete")
async def human_complete(request: Request):
    from saathi.infrastructure.human_browser import default_queue
    from saathi.infrastructure.human_browser.queue import JobResult
    body = await request.json()
    default_queue.complete(JobResult(
        job_id=body["job_id"], ok=bool(body.get("ok")), data=body.get("data", {}),
        error=body.get("error", ""), screenshot_b64=body.get("screenshot_b64", "")))
    return {"ok": True}


@app.post("/api/v1/human/test")
async def human_test(request: Request):
    """Click-to-test: enqueue a benign 'open a page' job and wait for the Mac
    Agent's result. Proves the whole VM→signed-queue→agent→Chrome loop live.
    Token-gated (not whitelisted)."""
    import asyncio
    import json as _json
    import os as _osenv
    from saathi.infrastructure.human_browser import HumanBrowserProxy, default_queue
    raw = await request.body()
    body = _json.loads(raw) if raw else {}
    url = body.get("url", "https://example.com")
    secret = _osenv.getenv("HUMAN_BROWSER_SECRET", "")
    if not secret:
        return {"ok": False, "error": "HUMAN_BROWSER_SECRET not set on the VM"}
    proxy = HumanBrowserProxy(default_queue, secret=secret, timeout=15)
    try:
        result = await asyncio.to_thread(proxy.execute, "open",
                                         profile=body.get("profile", ""), url=url)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e),
                "hint": "start the Mac Agent: bash ~/SaathiAI/run_human_agent.sh"}


@app.get("/api/v1/human/automation")
async def human_automation():
    """Automation Center status + Browser Health Score + recent runs (flight recorder)."""
    import asyncio
    from saathi.infrastructure.human_browser.automation import status
    return await asyncio.to_thread(status)


def _teacher():
    from saathi.infrastructure.human_browser import default_teacher
    from saathi.events import bus as _b
    t = default_teacher()
    t._bus = _b
    return t


@app.post("/api/v1/human/report-run")
async def human_report_run(request: Request):
    """The Mac's daily publisher reports a run here so the flight recorder +
    Maturity dashboard reflect real Applications activity. Token-gated."""
    import json as _json
    from saathi.infrastructure.human_browser.run_store import default_store
    from saathi.events import bus as _bus
    raw = await request.body()
    r = _json.loads(raw) if raw else {}
    default_store().record(
        workflow=r.get("workflow", "youtube_upload"), capability=r.get("capability", "publish_video"),
        title=r.get("title", ""), ok=bool(r.get("ok")), error=r.get("error", ""),
        video_url=r.get("video_url", ""), duration_ms=int(r.get("duration_ms", 0)),
        started=float(r.get("started", 0) or 0), timeline=r.get("timeline", []))
    try:
        _bus.publish_sync("browser.published" if r.get("ok") else "browser.failed",
                          {"title": r.get("title"), "video_url": r.get("video_url"), "ok": bool(r.get("ok"))})
    except Exception:
        pass
    return {"ok": True}


@app.get("/api/v1/human/teach")
async def teach_pending():
    """Open Teach sessions the operator can take control of (whitelisted read)."""
    return {"sessions": [s.as_dict() for s in _teacher().store.pending()]}


@app.post("/api/v1/human/teach/{sid}/{action}")
async def teach_action(sid: str, action: str, request: Request):
    """Drive the Teach loop: take_control · capture · confirm · learn · abort.
    Token-gated (the Mac Agent posts `capture`; the operator confirms/learns)."""
    import json as _json
    from saathi.infrastructure.human_browser import TeachCapture
    t = _teacher()
    raw = await request.body()
    body = _json.loads(raw) if raw else {}
    try:
        if action == "take_control":
            s = t.take_control(sid)
        elif action == "capture":
            s = t.submit_capture(sid, TeachCapture(**{**{"key": t.store.get(sid).key}, **body}))
        elif action == "confirm":
            s = t.confirm(sid, selector=body.get("selector"))
        elif action == "learn":
            s = t.learn(sid, operator=body.get("operator", "Ajay"))
        elif action == "abort":
            s = t.abort(sid)
        else:
            return {"error": f"unknown action {action}"}
        return s.as_dict()
    except (KeyError, ValueError) as e:
        return {"error": str(e)}


@app.get("/api/v1/human/selectors")
async def human_selectors():
    """Automation Knowledge Graph — every element SaathiAI has learned, with
    confidence + how many strategies it knows."""
    from saathi.infrastructure.human_browser import default_selector_registry
    return {"elements": default_selector_registry().overview()}


@app.get("/api/v1/human/selectors/{key:path}")
async def human_selector_detail(key: str):
    from saathi.infrastructure.human_browser import default_selector_registry
    from dataclasses import asdict
    return {"key": key, "selectors": [asdict(k) for k in default_selector_registry().known(key)]}


@app.get("/api/v1/human/runs/{run_id}")
async def human_run(run_id: str):
    """One run's full record for the Replay viewer (timeline + artifacts)."""
    from saathi.infrastructure.human_browser.run_store import default_store
    run = default_store().get(run_id)
    return run or {"error": "run not found"}


@app.get("/api/v1/ceo/os")
async def ceo_operating_system():
    """Today's Operating System — one aggregated call for the home screen
    (dream · rule · automation · learning · revenue · needs-you), all real."""
    import asyncio
    from saathi.ceo_os import snapshot
    return await asyncio.to_thread(snapshot)


@app.get("/api/v1/studio/queue")
async def studio_queue():
    """Production Queue — content-factory bird's-eye view + recent runs with
    confidence / cost / time / structured failure."""
    from saathi.studio_store import default_store
    st = default_store()
    return {"counts": st.queue_counts(), "recent": st.recent(12)}


@app.get("/api/v1/mission")
async def daily_mission_get():
    """Today's zero-choice IELTS Mission from the curriculum + study streak
    (whitelisted read)."""
    from saathi.daily_mission import mission
    return mission()


@app.post("/api/v1/mission/complete")
async def daily_mission_complete(request: Request):
    """Mark a mission item done (lesson/speaking/writing/quiz). Token-gated."""
    body = await request.json()
    item = (body or {}).get("item", "")
    done = (body or {}).get("done", True)
    from saathi.daily_mission import mark, mission, ITEMS
    if item not in {k for k, _ in ITEMS}:
        return {"ok": False, "error": f"unknown item {item!r}"}
    mark(item, bool(done))
    return {"ok": True, "mission": mission()}


@app.get("/api/v1/lab/prompts")
async def lab_prompts():
    """AI Lab — Prompt Library catalog: every prompt with active version + best
    score (whitelisted read)."""
    from saathi.ai_lab import default_registry
    return {"prompts": default_registry().catalog()}


@app.get("/api/v1/lab/prompts/{name}")
async def lab_prompt_detail(name: str):
    """One prompt: version changelog + leaderboard (whitelisted read)."""
    from saathi.ai_lab import default_registry
    reg = default_registry()
    return {"name": name, "versions": reg.versions(name), "leaderboard": reg.leaderboard(name)}


@app.post("/api/v1/lab/prompts")
async def lab_register(request: Request):
    """Register a new prompt version (becomes active). Auth-gated."""
    b = await request.json()
    from saathi.ai_lab import default_registry
    if not b.get("name") or not b.get("template"):
        return {"ok": False, "error": "name and template required"}
    v = default_registry().register(b["name"], b["template"], purpose=b.get("purpose", ""),
                                    author=b.get("author", "Ajay"), project=b.get("project", ""),
                                    notes=b.get("notes", ""))
    return {"ok": True, "version": v}


@app.post("/api/v1/lab/prompts/{name}/eval")
async def lab_eval(name: str, request: Request):
    """Record an evaluation result for a prompt version. Auth-gated."""
    b = await request.json()
    from saathi.ai_lab import default_registry
    default_registry().record_eval(name, int(b.get("version", 1)), score=float(b.get("score", 0)),
                                   latency_ms=int(b.get("latency_ms", 0)), cost=float(b.get("cost", 0)),
                                   failures=int(b.get("failures", 0)), notes=b.get("notes", ""))
    return {"ok": True}


@app.post("/api/v1/lab/prompts/{name}/rollback")
async def lab_rollback(name: str, request: Request):
    """Redeploy an older version as active. Auth-gated."""
    b = await request.json()
    from saathi.ai_lab import default_registry
    ok = default_registry().rollback(name, int(b.get("version", 1)))
    return {"ok": ok}


# ── Client Intake — "Create New Project" ─────────────────────────────────────
def _share_url(request: Request, token: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/project/create/{token}"


@app.get("/api/v1/intake/projects")
async def intake_list():
    """All client-intake projects (whitelisted read)."""
    from saathi.client_intake import default_store
    return {"projects": default_store().list()}


@app.post("/api/v1/intake/projects")
async def intake_create(request: Request):
    """Create a new project (optionally with initial company data). Returns the
    share link for the smart-form capture path."""
    body = await request.json()
    from saathi.client_intake import default_store
    p = default_store().create(body or {})
    p["share_url"] = _share_url(request, p["token"])
    return p


@app.get("/api/v1/intake/projects/{pid}")
async def intake_get(pid: str, request: Request):
    from saathi.client_intake import default_store
    p = default_store().get(pid)
    if not p:
        return JSONResponse({"error": "not found"}, status_code=404)
    p["share_url"] = _share_url(request, p["token"])
    return p


@app.patch("/api/v1/intake/projects/{pid}")
async def intake_update(pid: str, request: Request):
    body = await request.json()
    from saathi.client_intake import default_store
    p = default_store().update(pid, body.get("data", body), status=body.get("status"))
    return p or JSONResponse({"error": "not found"}, status_code=404)


@app.post("/api/v1/intake/projects/{pid}/research")
async def intake_research(pid: str):
    """Run AI research → strategy, mark the project ready."""
    import asyncio
    from saathi.client_intake import default_store, research_project
    store = default_store()
    p = store.get(pid)
    if not p:
        return JSONResponse({"error": "not found"}, status_code=404)
    store.set_status(pid, "researching")
    research, strategy = await asyncio.to_thread(research_project, p)
    return store.set_output(pid, research, strategy)


@app.get("/api/v1/intake/projects/{pid}/studio-topics")
async def intake_studio_topics(pid: str):
    """Wire → AI Studio: the project's strategy content ideas as production topics."""
    from saathi.client_intake import default_store, studio_topics
    p = default_store().get(pid)
    if not p:
        return JSONResponse({"error": "not found"}, status_code=404)
    return studio_topics(p)


# public smart-form path (whitelisted; token IS the credential)
@app.get("/api/v1/intake/form/{token}")
async def intake_form_get(token: str):
    from saathi.client_intake import default_store
    p = default_store().get_by_token(token)
    if not p:
        return JSONResponse({"error": "invalid link"}, status_code=404)
    return {"id": p["id"], "status": p["status"], "data": p["data"]}


@app.post("/api/v1/intake/form/{token}")
async def intake_form_submit(token: str, request: Request):
    body = await request.json()
    from saathi.client_intake import default_store
    store = default_store()
    p = store.get_by_token(token)
    if not p:
        return JSONResponse({"error": "invalid link"}, status_code=404)
    updated = store.update(p["id"], body.get("data", body), status="submitted")
    return {"ok": True, "status": updated["status"]}


@app.get("/api/v1/platform/maturity")
async def platform_maturity():
    """Honest platform-maturity mirror (Infrastructure vs Applications vs Real
    Data vs Learning). Deliberately computed from real signals."""
    import asyncio
    from saathi.platform_maturity import snapshot
    return await asyncio.to_thread(snapshot)


@app.get("/api/v1/infrastructure/health")
async def infrastructure_health():
    """Unified infra diagnostics for the CEO dashboard's Infrastructure panel
    (Models · Browser · Connectors · Conversation + a health score). Runs in a
    thread — connector health checks may touch the network."""
    import asyncio
    from saathi.infrastructure.diagnostics import snapshot
    return await asyncio.to_thread(snapshot)


# loop-safe event publisher: inside FastAPI's running loop we can't use
# bus.publish_sync, so fire-and-forget an awaitable task instead.
def _loop_safe_publish(name, payload):
    import asyncio
    from saathi.events import bus
    try:
        asyncio.get_running_loop().create_task(bus.publish(name, payload))
    except RuntimeError:
        bus.publish_sync(name, payload)


# ── Autonomous Content Factory — thin endpoints for n8n (SaathiAI = intelligence) ──
# n8n only orchestrates + calls external generators; every call here records an Episode.
def _factory():
    from saathi.content_pipeline import ContentFactoryPipeline
    return ContentFactoryPipeline(publish_event=_loop_safe_publish)

@app.post("/api/v1/factory/discover")
async def factory_discover(body: dict = Body(...)):
    from saathi.content_pipeline import ContentRun
    run = ContentRun()
    topics = _factory().rank_topics(run, body.get("signals", []), top=body.get("top", 20))
    return {"topics": [{"title": t.title, "source": t.source, "score": t.score} for t in topics],
            "episodes": run.episodes}

@app.post("/api/v1/factory/research")
async def factory_research(body: dict = Body(...)):
    from saathi.content_pipeline import ContentRun, Topic
    run = ContentRun(); t = body.get("topic", {})
    conf = _factory().research_topic(run, Topic(
        title=t.get("title", ""), source=t.get("source", "unknown"),
        relevance=t.get("relevance", 0.5), evidence=t.get("evidence", 0)))
    return {"confidence": conf, "episodes": run.episodes}

@app.post("/api/v1/factory/script/validate")
async def factory_script(body: dict = Body(...)):
    from saathi.content_pipeline import ContentRun
    run = ContentRun(); ok = _factory().validate_script(run, body.get("script", {}))
    return {"ok": ok, "issues": run.script_issues, "episodes": run.episodes}

@app.post("/api/v1/factory/scenes")
async def factory_scenes(body: dict = Body(...)):
    from saathi.content_pipeline import ContentRun
    run = ContentRun()
    scenes = _factory().plan_scenes(run, body.get("script", {}))
    return {"scenes": [{"text": s.text, "image_prompt": s.image_prompt} for s in scenes],
            "episodes": run.episodes}

@app.post("/api/v1/factory/gate")
async def factory_gate(body: dict = Body(...)):
    from saathi.content_pipeline import ContentRun
    run = ContentRun(); run.metadata = body.get("metadata", {})
    passed = _factory().gate(run)
    return {"passed": passed, "blockers": run.gate_blockers, "status": run.status,
            "episodes": run.episodes}

@app.post("/api/v1/factory/failure")
async def factory_failure(body: dict = Body(...)):
    from saathi.content_pipeline import Stage
    stage = Stage(body.get("stage", "render"))
    return _factory().record_failure(stage, body.get("error", "unknown"), topic=body.get("topic", ""))


# ── Content Intelligence — Analytics → Learning (self-improving AI Studio) ──
def _content_intel():
    import os
    from saathi.content_intelligence import ContentIntelligence
    data = os.path.join(os.path.dirname(__file__), "..", "data")
    try:
        from saathi.learning.registry import CapabilityImprovementRegistry
        imp = CapabilityImprovementRegistry(os.path.join(data, "improvements.db"))
    except Exception:
        imp = None
    return ContentIntelligence(os.path.join(data, "content_intel.db"),
                               improvement_registry=imp, publish=_loop_safe_publish)

@app.post("/api/content/analytics")
async def content_analytics(body: dict = Body(...)):
    from saathi.content_intelligence import normalize
    a = normalize(body.get("platform", "youtube"), body.get("analytics", body))
    return _content_intel().ingest(a)

@app.post("/api/content/compare")
async def content_compare(body: dict = Body(...)):
    return _content_intel().compare(body["a"], body["b"])

@app.get("/api/content/recommendations")
async def content_recommendations(top: int = 5):
    ci = _content_intel()
    return {"recommendations": ci.recommendations(top), "briefing": ci.content_briefing()}

@app.get("/api/content/leaderboard")
async def content_leaderboard(top: int = 5):
    return {"leaderboard": _content_intel().leaderboard(top)}

@app.get("/api/content/experiments")
async def content_experiments():
    return {"experiments": _content_intel().experiments()}


# ── Saathi Coach — IELTS as the daily Learn box (conversational, own-project topics) ──
def _coach():
    import os
    from saathi.coach import SaathiCoach, BandPredictor
    data = os.path.join(os.path.dirname(__file__), "..", "data")
    return SaathiCoach(BandPredictor(os.path.join(data, "coach.db")), publish=_loop_safe_publish)

@app.get("/api/v1/coach/challenge")
async def coach_challenge():
    from saathi.coach import daily_challenge
    c = daily_challenge()
    return {"skill": c.skill, "topic": c.topic, "minutes": c.minutes,
            "expected_band_gain": c.expected_band_gain, "reason": c.reason, "text": c.render()}

@app.post("/api/v1/coach/score")
async def coach_score(body: dict = Body(...)):
    out = _coach().practice_speaking(body.get("transcript", ""), topic=body.get("topic", ""),
                                     pronunciation_hint=body.get("pronunciation_hint"))
    s = out["score"]
    return {"band": s.band, "grammar": s.grammar, "vocabulary": s.vocabulary,
            "fluency": s.fluency, "pronunciation": s.pronunciation, "weakness": s.weakness,
            "prediction": out["prediction"]}

@app.get("/api/v1/coach/prediction")
async def coach_prediction(days_left: int = 11):
    import os
    from saathi.coach import BandPredictor
    data = os.path.join(os.path.dirname(__file__), "..", "data")
    return BandPredictor(os.path.join(data, "coach.db")).predict(days_left=days_left)


# ── Telegram CEO Companion — push the morning briefing ──
@app.post("/api/v1/ceo/telegram/brief")
async def ceo_telegram_brief():
    from saathi.telegram_ceo import briefing_text
    from saathi.bff import ceo_home
    try:
        from saathi.daily_scorecard import today_scorecard
        sc = today_scorecard().render()
    except Exception:
        sc = None
    text = briefing_text(ceo_home(), scorecard=sc)
    try:
        from saathi.telegram_bot import _send
        _send(text)
        sent = True
    except Exception:
        sent = False
    return {"sent": sent, "text": text}


# ── Live event stream (SSE) — the platform breathing to every client ──
@app.get("/api/events/stream")
async def events_stream(demo: int = 0):
    from fastapi.responses import StreamingResponse
    from saathi.eventstream import sse_stream
    return StreamingResponse(
        sse_stream(demo=bool(demo)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"})

try:
    from .tools.r2_storage import cleanup_old_local_dirs
    cleanup_old_local_dirs()
except Exception:
    pass

try:
    from .tools.ielts_endpoints import router as ielts_router
    app.include_router(ielts_router)
except Exception:
    pass

try:
    from .agents.router import router as bma_router
    app.include_router(bma_router)
except Exception:
    pass

try:
    from .tools.hcg_voice import router as hcg_voice_router
    app.include_router(hcg_voice_router)
except Exception as _e:
    print(f"[saathi] hcg_voice router unavailable: {_e}")

# Simple access key for remote/tunnel use. Local requests (the Mac itself)
# are always allowed; remote requests must send X-Saathi-Token.
import os as _os
import hashlib as _hashlib
import secrets as _secrets

ACCESS_TOKEN = _os.getenv("SAATHI_TOKEN", "")
_SERVER_START = time.time()
_RAW_PASSWORD = _os.getenv("BAADAR_PASSWORD", "")
_PASSWORD_HASH = _hashlib.sha256(_RAW_PASSWORD.encode()).hexdigest() if _RAW_PASSWORD else ""


def _session_token() -> str:
    """Deterministic session token. Seeded from the password hash when a password
    is set, otherwise from SAATHI_TOKEN — so a login is possible (and the session
    cookie is honoured) even when BAADAR_PASSWORD isn't configured. Stateless."""
    seed = _PASSWORD_HASH or ACCESS_TOKEN or ""
    return _hashlib.sha256((seed + ":baadar-session").encode()).hexdigest()


def _is_local(request) -> bool:
    """True only for genuine on-box requests (Mac dev, on-VM curl, loopback).

    Behind our Caddy reverse proxy every hop arrives from 127.0.0.1, so the peer
    address alone cannot distinguish an external visitor from a truly local
    caller. Caddy (like every sane proxy) stamps X-Forwarded-For on proxied
    traffic; genuine loopback requests never carry it. Requiring BOTH a loopback
    peer AND no forwarding header is what makes "local = trusted" safe on a
    public deployment."""
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost"):
        return False
    if request.headers.get("x-forwarded-for") or request.headers.get("x-forwarded-host"):
        return False
    return True


def _is_authed(request) -> bool:
    """Authorize via session cookie, session header, or the raw SAATHI_TOKEN."""
    # a valid session cookie/header (issued by /auth/login) is always accepted
    cookies = getattr(request, "cookies", None) or {}
    token = (cookies.get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    if token and token == _session_token():
        return True
    # the raw platform token also authorizes (API clients)
    if ACCESS_TOKEN and request.headers.get("x-saathi-token") == ACCESS_TOKEN:
        return True
    # no password configured → trust genuine local callers (unchanged contract)
    if not _PASSWORD_HASH:
        return _is_local(request)
    return False


@app.middleware("http")
async def _auth(request, call_next):
    from fastapi.responses import JSONResponse
    path = request.url.path
    # Always allow: login endpoint, OAuth callbacks, static assets, and
    # endpoints that enforce their own bearer auth (BAADAR_API_KEY).
    if (path == "/api/v1/auth/login"
            or path == "/api/executive/briefing"
            or path == "/api/v1/ceo/home"
            or path == "/api/v1/ceo/os"
            or path == "/api/v1/infrastructure/health"
            or path == "/api/v1/platform/maturity"
            or path == "/api/v1/studio/queue"
            or path == "/api/v1/mission"
            or path == "/api/v1/mission/complete"
            or path == "/api/v1/agent/chat"
            or path == "/api/v1/lab/prompts"
            or path.startswith("/api/v1/lab/prompts/")
            or path == "/api/v1/intake/projects"
            or path.startswith("/api/v1/intake/projects/")
            or path.startswith("/api/v1/intake/form/")
            or path == "/api/v1/human/automation"
            or path == "/api/v1/human/teach"
            or path.startswith("/api/v1/human/runs/")
            or path.startswith("/api/v1/human/selectors")
            or path == "/api/events/stream"
            or path == "/api/content/recommendations"
            or path == "/api/content/leaderboard"
            or path == "/api/content/experiments"
            or path == "/api/v1/coach/challenge"
            or path == "/api/v1/coach/prediction"
            or path == "/api/v1/linkedin/callback"
            or path == "/api/v1/tiktok/callback"
            or path == "/api/v1/tiktok/auth"
            or path == "/api/v1/tiktok/status"
            or path == "/api/v1/evaluate/writing"
            or path == "/api/v1/evaluate/speaking"
            or path == "/api/v1/notify/new-user"
            or path == "/api/v1/voice/transcribe"
            or not path.startswith("/api/")):
        return await call_next(request)
    # Legacy remote token (backward compat)
    if ACCESS_TOKEN and request.headers.get("x-saathi-token") == ACCESS_TOKEN:
        return await call_next(request)
    # Stage 2 — Logto access token (JWT / RBAC). Additive; inert until LOGTO_ENDPOINT set.
    try:
        from saathi.auth_logto import enabled as _logto_on, authorize as _logto_authz, AuthError as _LErr
        if _logto_on() and request.headers.get("authorization"):
            try:
                request.state.principal = _logto_authz(request.headers.get("authorization"))
                return await call_next(request)
            except _LErr:
                pass  # fall through to session auth
    except Exception:
        pass
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

class LoginIn(BaseModel):
    password: str

@app.post("/api/v1/auth/login")
def login(body: LoginIn):
    from fastapi.responses import JSONResponse
    import hashlib
    given = hashlib.sha256(body.password.encode()).hexdigest()
    # accept the configured password OR the SAATHI_TOKEN (so login works even when
    # BAADAR_PASSWORD isn't set — the previous behaviour issued a cookie that was
    # then ignored, causing an endless re-login loop).
    ok = (_PASSWORD_HASH and given == _PASSWORD_HASH) or (ACCESS_TOKEN and body.password == ACCESS_TOKEN)
    if not ok:
        if not (_PASSWORD_HASH or ACCESS_TOKEN):
            ok = True  # nothing configured — let the owner in
        else:
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


# lightweight brain rate limit — chat is open (no login) but the LLM quota is
# protected: per-caller and global sliding windows.
_CHAT_HITS: dict = {}
_CHAT_GLOBAL: list = []
_CHAT_PER_IP, _CHAT_GLOBAL_MAX, _CHAT_WINDOW = 30, 240, 600.0   # per-IP / global per 10 min


def _rate_ok(request: Request) -> bool:
    now = time.time()
    key = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
           or (request.client.host if request.client else "local"))
    _CHAT_GLOBAL[:] = [t for t in _CHAT_GLOBAL if now - t < _CHAT_WINDOW]
    hits = [t for t in _CHAT_HITS.get(key, []) if now - t < _CHAT_WINDOW]
    if len(hits) >= _CHAT_PER_IP or len(_CHAT_GLOBAL) >= _CHAT_GLOBAL_MAX:
        _CHAT_HITS[key] = hits
        return False
    hits.append(now); _CHAT_HITS[key] = hits; _CHAT_GLOBAL.append(now)
    return True


@app.post("/api/v1/agent/chat")
def chat(body: ChatIn, request: Request):
    if not _rate_ok(request):
        return {"reply": "I'm getting a lot of requests right now — give me a minute and try again."}
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


@app.get("/api/v1/social/dashboard")
def social_dashboard():
    """Live social stats + monetization progress for YouTube, Instagram, Facebook, TikTok."""
    from .tools.social_dashboard import get_dashboard
    return get_dashboard()


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


@app.post("/api/v1/trends/fuse")
async def trends_fuse(request: Request):
    """Fuse a trending format with an IELTS topic to generate a viral hook."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "IELTS Speaking")
    trend_format = body.get("format", "")
    try:
        import asyncio
        from .tools.content_studio import fuse_trend
        result = await asyncio.get_event_loop().run_in_executor(None, fuse_trend, topic, trend_format)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}

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
    shimmy_ready = False
    try:
        import urllib.request as _ur
        _ur.urlopen(config.SHIMMY_URL.rstrip("/") + "/models", timeout=2)
        shimmy_ready = True
    except Exception:
        pass
    if config.LLM_PROVIDER == "groq":
        model = config.GROQ_MODEL
    elif config.LLM_PROVIDER == "gemini":
        model = config.GEMINI_MODEL
    elif config.LLM_PROVIDER == "shimmy":
        model = config.SHIMMY_MODEL
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
        "shimmy_ready": shimmy_ready,
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
# REFERRAL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/referral/check")
async def referral_check(request: Request):
    """Manually trigger a referral check for a specific user."""
    body = await request.json()
    uid = body.get("uid", "")
    old_score = float(body.get("old_score", 0))
    new_score = float(body.get("new_score", 0))
    if not uid:
        return {"ok": False, "error": "uid required"}
    from .tools.referral import check_and_trigger_referral
    result = check_and_trigger_referral(uid, old_score, new_score)
    return {"ok": True, **result}


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
    format: str = "short"           # short | long
    pillar: str = "horror_story"    # horror_story | before_after | dont_say | quiz | interview
    use_chatgpt: bool = True        # True = ChatGPT in Brave first, False = Groq/Gemini

@app.post("/api/v1/studio/script")
async def studio_script(body: ScriptIn, request: Request):
    """Generate Mr. Yeti YouTube script. Uses ChatGPT in Brave by default, falls back to Groq/Gemini."""
    try:
        if body.use_chatgpt:
            from .tools.chatgpt_browser import ask_chatgpt_for_script
            result = ask_chatgpt_for_script(body.topic, body.pillar, body.content_type, body.format)
            if result.get("ok"):
                return result
            # Fall through to API-based fallback
        from .tools.script_writer import generate_script
        return generate_script(body.topic, body.content_type, body.format, body.pillar)
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/v1/studio/script/chatgpt")
async def studio_script_chatgpt(body: ScriptIn, request: Request):
    """Direct ChatGPT-in-Brave script generation — no API fallback."""
    from .tools.chatgpt_browser import ask_chatgpt_for_script
    try:
        return ask_chatgpt_for_script(body.topic, body.pillar, body.content_type, body.format)
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

# Task 5 — Mr. Yeti Character Engine
@app.get("/api/v1/yeti/persona")
async def yeti_persona_get():
    """Get current Mr. Yeti persona traits and configuration."""
    from .tools.script_writer import load_persona
    return {"ok": True, "persona": load_persona()}

@app.post("/api/v1/yeti/persona")
async def yeti_persona_update(request: Request):
    """Update one or more fields in yeti_persona.json."""
    import json as _json
    from pathlib import Path
    body = await request.json()
    persona_path = config.ROOT / "data" / "yeti_persona.json"
    current = {}
    if persona_path.exists():
        current = _json.loads(persona_path.read_text())
    current.update(body)
    persona_path.write_text(_json.dumps(current, indent=2, ensure_ascii=False))
    return {"ok": True, "persona": current}

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
    if not _is_local(request) and not _is_authed(request):
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
async def studio_thumbnail(request: Request):
    """Generate 5 thumbnail concepts, AI-score them, return best + all ranked."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "IELTS tip")
    title = body.get("title", "")
    try:
        import asyncio
        from .tools.thumbnail import generate_and_score
        result = await asyncio.get_event_loop().run_in_executor(None, generate_and_score, topic, title)
        return {"ok": True, **result}
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
    if not _is_local(request) and not _is_authed(request):
        raise HTTPException(401, "unauthorized")
    p = Path(path)
    if not p.exists() or not str(p).startswith(str(Path.home() / "SaathiAI" / "reels_output")):
        raise HTTPException(404, "not found")
    return FileResponse(str(p), media_type="video/mp4", filename=p.name)


# ── GitHub Actions status proxy ──────────────────────────────────────────────
import httpx as _httpx

_GH_TOKEN  = _os.getenv("GITHUB_TOKEN", "")
_GH_REPO   = _os.getenv("GITHUB_REPO", "chaulagainazay-dot/SaathiAI")

# Map workflow filename → platform key
_WF_MAP = {
    "post_am.yml":    "facebook_am",
    "post_pm.yml":    "facebook_pm",
    "post_video.yml": "youtube",
}

# Which steps represent which "agent"
_STEP_AGENTS = {
    "Checkout repo":          {"agent": "Git",          "icon": "📦"},
    "Set up Python 3.12":     {"agent": "Python",       "icon": "🐍"},
    "Install dependencies":   {"agent": "Pip",          "icon": "📥"},
    "Install system deps":    {"agent": "System",       "icon": "🔧"},
    "Run AM autopost":        {"agent": "Groq LLM → Meta API", "icon": "🤖"},
    "Run PM autopost":        {"agent": "Groq LLM → Meta API", "icon": "🤖"},
    "Run VIDEO autopost":     {"agent": "Groq LLM → YouTube API", "icon": "🎬"},
}

@app.get("/api/v1/github/actions")
async def github_actions_status():
    """Fetch latest GitHub Actions run status for all 3 posting workflows."""
    token = _GH_TOKEN or _os.popen("gh auth token 2>/dev/null").read().strip()
    if not token:
        return {"error": "No GitHub token — set GITHUB_TOKEN in .env", "runs": {}}

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    result = {}

    async with _httpx.AsyncClient(timeout=8) as client:
        for wf_file, platform in _WF_MAP.items():
            try:
                # Get latest run for this workflow (via the GitHub connector)
                import asyncio as _asyncio
                from saathi.infrastructure.connectors import default_registry as _dreg
                r = await _asyncio.to_thread(
                    _dreg().execute, capability="list_workflow_runs", connector_id="github",
                    repo_full=_GH_REPO, workflow=wf_file, per_page=1)
                runs = r.get("workflow_runs", [])
                if not runs:
                    result[platform] = {"status": "never_run"}
                    continue

                run = runs[0]
                run_id   = run["id"]
                status   = run["status"]       # queued | in_progress | completed
                conclusion = run.get("conclusion")  # success | failure | None
                updated  = run["updated_at"]
                html_url = run["html_url"]

                # Get job steps for live agent visibility
                steps = []
                try:
                    jr = await _asyncio.to_thread(
                        _dreg().execute, capability="list_run_jobs", connector_id="github",
                        repo_full=_GH_REPO, run_id=run_id)
                    jobs = jr.get("jobs", [])
                    if jobs:
                        raw_steps = jobs[0].get("steps", [])
                        for s in raw_steps:
                            name = s["name"]
                            agent_info = _STEP_AGENTS.get(name, {"agent": name, "icon": "⚙️"})
                            steps.append({
                                "name":       name,
                                "agent":      agent_info["agent"],
                                "icon":       agent_info["icon"],
                                "status":     s["status"],
                                "conclusion": s.get("conclusion"),
                            })
                except Exception:
                    pass

                # Find current active step
                active_step = next(
                    (s for s in steps if s["status"] == "in_progress"), None
                )
                last_step = next(
                    (s for s in reversed(steps) if s["conclusion"] == "success"), None
                )

                result[platform] = {
                    "run_id":      run_id,
                    "status":      status,
                    "conclusion":  conclusion,
                    "updated_at":  updated,
                    "html_url":    html_url,
                    "steps":       steps,
                    "active_step": active_step,
                    "last_step":   last_step,
                }
            except Exception as e:
                result[platform] = {"status": "error", "error": str(e)}

    return {"runs": result}

# ── n8n status proxy (avoids CORS — browser can't hit localhost:5678 directly) ──

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


@app.get("/api/v1/skills")
async def list_skills_endpoint(request: Request):
    """List all installed Claude Code skills."""
    from .tools.skills_dispatch import list_skills, search_skills
    q = request.query_params.get("q", "")
    skills = search_skills(q) if q else list_skills()
    return {"skills": skills, "count": len(skills)}

@app.post("/api/v1/skills/dispatch")
async def dispatch_skill(request: Request):
    """Auto-pick the best skill for a task description."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    task = body.get("task", "")
    if not task:
        return {"error": "task required"}
    from .tools.skills_dispatch import auto_dispatch
    return auto_dispatch(task)

@app.post("/api/v1/studio/google_flow_video")
async def google_flow_video(request: Request):
    """Generate a Veo 2 3D video via Google Flow and return metadata + file path."""
    # auth handled by middleware — no duplicate check needed
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic   = body.get("topic", "")
    use_veo = bool(body.get("use_veo", True))
    try:
        from .tools.google_flow import generate_full_video
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: generate_full_video(topic=topic, use_veo=use_veo)
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/v1/studio/google_flow_video/status")
async def google_flow_status(request: Request):
    """Return the latest Google Flow video file in videos_output/."""
    out_dir = config.ROOT / "videos_output"
    videos  = sorted(out_dir.glob("google_flow_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not videos:
        return {"ok": True, "latest": None}
    latest = videos[0]
    return {
        "ok":      True,
        "latest":  latest.name,
        "size_kb": latest.stat().st_size // 1024,
        "mtime":   latest.stat().st_mtime,
        "count":   len(videos),
    }


# ══════════════════════════════════════════════════════════════════════════════
# AUTO IMPROVE + AUTO DEVELOP — Baadar analyzes & extends itself
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/auto_improve/suggestions")
async def auto_improve_suggestions(request: Request):
    """Use LLM to analyze Baadar state and return improvement suggestions."""
    from .tools._llm_helper import ask_llm, extract_json

    # Gather context: disconnected platforms, etc.
    ctx_parts = []
    try:
        from . import connections as _conn
        conns = _conn.get_all()
        disconnected = [k for k, v in conns.items() if not v.get("connected")]
        if disconnected:
            ctx_parts.append(f"Disconnected platforms: {', '.join(disconnected)}")
    except Exception:
        pass

    context = "; ".join(ctx_parts) or "All systems nominal"

    prompt = f"""You are analyzing the Baadar AI social media automation system for pielts IELTS app.
Current state: {context}

Return JSON array of 5 improvement suggestions, each with:
- id: string slug
- priority: "high" | "medium" | "low"
- title: short title (under 8 words)
- description: what to improve and why (under 40 words)
- suggested_skill: one of [ralph, brainstorming, systematic-debugging, hyperframes, ckm-banner-design, ui-ux-pro-max, seo-audit, general-video, prd]
- action: "auto" | "manual"

Focus on: content quality, posting consistency, engagement rate, SEO, video production, UI improvements.
Return ONLY valid JSON array."""

    try:
        raw = ask_llm(prompt, system="Return only valid JSON array.", timeout=30)
        suggestions = extract_json(raw)
    except Exception:
        suggestions = None
    if not isinstance(suggestions, list):
        suggestions = [
            {"id": "add-captions", "priority": "high", "title": "Add captions to Mr. Yeti videos", "description": "Captions increase watch time by 40% on Instagram Reels and YouTube Shorts.", "suggested_skill": "embedded-captions", "action": "auto"},
            {"id": "seo-audit", "priority": "high", "title": "Run SEO audit on pielts.web.app", "description": "Monthly SEO audit catches ranking drops and technical issues early.", "suggested_skill": "seo-audit", "action": "auto"},
            {"id": "banner-refresh", "priority": "medium", "title": "Refresh social media banners", "description": "Update Facebook/Instagram profile banners with new IELTS season branding.", "suggested_skill": "ckm-banner-design", "action": "auto"},
            {"id": "video-pipeline", "priority": "medium", "title": "Build faceless explainer videos", "description": "Add text-to-video explainer pipeline for IELTS grammar topics.", "suggested_skill": "faceless-explainer", "action": "manual"},
            {"id": "prd-next", "priority": "low", "title": "Write PRD for next Baadar features", "description": "Document premium tier, affiliate system, and multi-language support.", "suggested_skill": "prd", "action": "manual"},
        ]
    return {"ok": True, "suggestions": suggestions, "context": context}


@app.post("/api/v1/auto_develop")
async def auto_develop(request: Request):
    """Auto-route a development task to the best skill."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    task = body.get("task", "")
    if not task:
        return {"error": "task required"}
    from .tools.skills_dispatch import auto_dispatch
    result = auto_dispatch(task)
    # Also get skill description from SKILL.md first line
    skill_desc = ""
    if result.get("prompt"):
        for line in result["prompt"].splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("name:") and not line.startswith("description:"):
                skill_desc = line[:120]
                break
    result["skill_description"] = skill_desc
    return result


# ═══════════════════════════════════════════════════════════════
# PIELTS MARKET INTEL + AUTO-IMPROVE AGENT
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/pielts/research")
async def pielts_research(request: Request):
    """Trigger full market intelligence research pipeline (async, takes ~2-3 min)."""
    import asyncio, threading
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    force = body.get("force", False)

    # Check if recent (< 6 hours old) report exists
    from .tools.market_intel import get_latest, INTEL_DIR
    from datetime import datetime, timedelta
    latest = get_latest()
    if latest and not force:
        gen_at = latest.get("generated_at", "")
        try:
            age = datetime.now() - datetime.fromisoformat(gen_at)
            if age < timedelta(hours=6):
                return {"status": "cached", "message": "Using recent report (< 6h old)",
                        "report_date": latest.get("date"), "summary": latest.get("summary", {})}
        except Exception:
            pass

    # Run in background thread (takes 2-3 min)
    def _run():
        try:
            from .tools.market_intel import run_full_research
            run_full_research(save=True)
        except Exception as e:
            print(f"[market intel error] {e}")
    threading.Thread(target=_run, daemon=True).start()

    return {"status": "started", "message": "Market research running in background (~2-3 min). Check /api/v1/pielts/intel for results."}


@app.get("/api/v1/pielts/intel")
async def pielts_intel(request: Request):
    """Get the latest market intelligence report."""
    from .tools.market_intel import get_latest
    latest = get_latest()
    if not latest:
        return {"status": "none", "message": "No research yet. POST /api/v1/pielts/research to start."}
    return {
        "status": "ok",
        "date": latest.get("date"),
        "summary": latest.get("summary", {}),
        "goal_plan": latest.get("goal_plan", {}),
        "top_improvements": latest.get("improvement_tasks", [])[:5],
        "pain_points": latest.get("reddit_signals", {}).get("pain_points", [])[:5],
        "market_gaps": latest.get("competitor_intel", {}).get("market_gaps", [])[:5],
        "trending": latest.get("trend_signals", {}).get("rising_topics", [])[:5],
        "competitors": latest.get("competitor_intel", {}).get("top_competitors", [])[:4],
    }


@app.post("/api/v1/pielts/improve")
async def pielts_improve(request: Request):
    """Generate concrete improvement tasks from latest market intel."""
    import threading
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    max_tasks = int(body.get("max_tasks", 5))

    def _run():
        try:
            from .tools.pielts_improver import run_improvement_cycle
            run_improvement_cycle(max_tasks=max_tasks)
        except Exception as e:
            print(f"[pielts improver error] {e}")
    threading.Thread(target=_run, daemon=True).start()

    return {"status": "started", "message": f"Generating {max_tasks} improvement tasks. Check /api/v1/pielts/queue."}


@app.get("/api/v1/pielts/queue")
async def pielts_queue(request: Request):
    """Get the current pending improvement queue."""
    from .tools.pielts_improver import get_pending_queue
    queue = get_pending_queue()
    if not queue:
        return {"status": "empty", "message": "No improvements queued. POST /api/v1/pielts/improve first."}
    return {
        "status": "ok",
        "generated_at": queue.get("generated_at"),
        "count": len(queue.get("improvements", [])),
        "improvements": [
            {
                "index": i,
                "title": imp.get("task", {}).get("title", imp.get("feature_name", "?")),
                "summary": imp.get("summary", imp.get("user_story", "")),
                "category": imp.get("task", {}).get("category", "?"),
                "impact": imp.get("task", {}).get("impact", "?"),
                "effort": imp.get("task", {}).get("effort", "?"),
                "files": imp.get("files_to_modify", []),
            }
            for i, imp in enumerate(queue.get("improvements", []))
        ],
    }


@app.post("/api/v1/pielts/apply")
async def pielts_apply(request: Request):
    """Apply a specific improvement from the queue to the pielts codebase."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    idx = int(body.get("index", 0))
    from .tools.pielts_improver import apply_improvement
    return apply_improvement(idx)


@app.get("/api/v1/pielts/roadmap")
async def pielts_roadmap(request: Request):
    """Get the strategic 90-day roadmap to become #1 IELTS app."""
    from .tools.market_intel import get_latest
    latest = get_latest()
    if not latest:
        return {"status": "none"}
    return {
        "status": "ok",
        "date": latest.get("date"),
        "goal_plan": latest.get("goal_plan", {}),
        "all_improvements": latest.get("improvement_tasks", []),
        "competitor_advantages": latest.get("competitor_intel", {}).get("pielts_competitive_advantages", []),
        "pielts_gaps": latest.get("competitor_intel", {}).get("pielts_missing_vs_competitors", []),
    }


@app.get("/api/v1/reddit/status")
async def reddit_status(request: Request):
    """Check Reddit credentials and queue summary."""
    from .tools.reddit_outreach import creds_status, get_queue
    status = creds_status()
    drafts = get_queue("draft")
    sent = get_queue("sent")
    return {**status, "drafts": len(drafts), "sent_total": len(sent)}


_reddit_scan_running = False

@app.post("/api/v1/reddit/scan")
async def reddit_scan(request: Request):
    """Scan Reddit for IELTS questions and draft replies (runs in background)."""
    global _reddit_scan_running
    if _reddit_scan_running:
        return {"status": "already_running"}
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    max_new = int(body.get("max_new", 8))

    def _run():
        global _reddit_scan_running
        _reddit_scan_running = True
        try:
            from .tools.reddit_outreach import scan_and_draft
            scan_and_draft(max_new=max_new)
        finally:
            _reddit_scan_running = False

    import threading
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "message": "Scanning Reddit and drafting replies in background…"}


@app.get("/api/v1/reddit/queue")
async def reddit_queue(request: Request):
    """Return current draft (or all) queue entries."""
    from .tools.reddit_outreach import get_queue
    status = request.query_params.get("status", "draft")
    items = get_queue(status)
    return {"ok": True, "items": items, "count": len(items), "scanning": _reddit_scan_running}


@app.post("/api/v1/reddit/send")
async def reddit_send(request: Request):
    """
    Mark a draft as sent (actual posting happens browser-side via same-origin fetch).
    Accepts: { post_id, comment_id, comment_url }
    """
    body = await request.json()
    post_id = body.get("post_id", "")
    if not post_id:
        return {"ok": False, "error": "post_id required"}
    from .tools.reddit_outreach import _load_queue, _save_queue
    from datetime import datetime
    queue = _load_queue()
    for item in queue:
        if item["post_id"] == post_id:
            item["status"] = "sent"
            item["sent_at"] = datetime.now().isoformat()
            item["comment_id"] = body.get("comment_id", "")
            item["comment_url"] = body.get("comment_url", "")
            break
    _save_queue(queue)
    return {"ok": True}


@app.post("/api/v1/reddit/skip")
async def reddit_skip(request: Request):
    body = await request.json()
    from .tools.reddit_outreach import skip_post
    return skip_post(body.get("post_id", ""))


@app.post("/api/v1/reddit/update_draft")
async def reddit_update_draft(request: Request):
    body = await request.json()
    from .tools.reddit_outreach import update_draft
    return update_draft(body.get("post_id", ""), body.get("draft", ""))


@app.get("/api/v1/reddit/daily")
async def reddit_daily_pending(request: Request):
    """Return today's pending Reddit submission (if any)."""
    from .tools.reddit_outreach import get_pending_daily_posts
    posts = get_pending_daily_posts()
    return {"ok": True, "posts": posts, "count": len(posts)}


@app.post("/api/v1/reddit/daily/queue")
async def reddit_daily_queue(request: Request):
    """Manually trigger drafting of today's Reddit post."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    from .tools.reddit_outreach import queue_daily_post
    return queue_daily_post(body.get("cal_post"))


@app.post("/api/v1/reddit/daily/sent")
async def reddit_daily_sent(request: Request):
    """Mark today's Reddit post as sent (called from browser after posting)."""
    body = await request.json()
    from .tools.reddit_outreach import mark_daily_post_sent
    return mark_daily_post_sent(body.get("date", ""), body.get("post_url", ""))


@app.post("/api/v1/reddit/daily/skip")
async def reddit_daily_skip(request: Request):
    body = await request.json()
    from .tools.reddit_outreach import skip_daily_post
    return skip_daily_post(body.get("date", ""))



# ── LinkedIn endpoints ────────────────────────────────────────────────────────

@app.get("/api/v1/linkedin/status")
async def linkedin_status():
    from .tools.linkedin_post import status
    return status()


@app.get("/api/v1/linkedin/auth")
async def linkedin_auth(request: Request):
    from .tools.linkedin_post import get_auth_url, app_configured
    if not app_configured():
        return JSONResponse({"error": "Add LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET to .env first"}, status_code=400)
    url = get_auth_url()
    return RedirectResponse(url)


@app.get("/api/v1/linkedin/callback")
async def linkedin_callback(code: str = "", error: str = "", state: str = ""):
    from .tools.linkedin_post import exchange_code
    if error:
        return HTMLResponse(f"<h3>LinkedIn auth failed: {error}</h3><p>Close this tab and try again.</p>")
    if not code:
        return HTMLResponse("<h3>No code returned</h3>")
    result = exchange_code(code)
    if result.get("ok"):
        urn = result.get("person_urn") or "Not retrieved (see below)"
        extra = "" if result.get("person_urn") else (
            "<p style='color:orange'>⚠️ Could not fetch Person URN automatically. "
            "Token is saved — posting will work once URN is set. "
            "You can find your LinkedIn member ID at: "
            "<a href='https://www.linkedin.com/in/me/' target='_blank'>linkedin.com/in/me</a> "
            "→ check the URL after redirect → copy the numeric ID from the source.</p>"
        )
        return HTMLResponse(
            "<h3>✅ LinkedIn connected!</h3>"
            f"<p>Person URN: {urn}</p>"
            f"{extra}"
            "<p>You can close this tab. Baadar will post daily at 10am.</p>"
        )
    return HTMLResponse(f"<h3>❌ Error</h3><pre>{result}</pre>")


@app.get("/api/v1/linkedin/daily")
async def linkedin_daily():
    from .tools.linkedin_post import get_pending, _load_daily
    return {"pending": get_pending(), "all_today": get_pending()}


@app.post("/api/v1/linkedin/daily/queue")
async def linkedin_daily_queue():
    from .tools.linkedin_post import queue_daily_post
    return queue_daily_post()


@app.post("/api/v1/linkedin/post")
async def linkedin_post_now(request: Request):
    body = await request.json()
    date = body.get("date", "")
    text = body.get("text", "")
    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)
    from .tools.linkedin_post import post_and_mark
    return post_and_mark(date, text)


@app.post("/api/v1/linkedin/daily/skip")
async def linkedin_daily_skip(request: Request):
    body = await request.json()
    from .tools.linkedin_post import skip_today
    return skip_today(body.get("date", ""))


# ── TikTok Webhook ────────────────────────────────────────────────────────────

@app.post("/api/v1/tiktok/webhook")
async def tiktok_webhook(request: Request):
    """Receive TikTok post-status notifications (publish success/failure)."""
    import hmac, hashlib, json as _json
    body_bytes = await request.body()

    # Verify signature if secret available
    secret = _os.getenv("TIKTOK_CLIENT_SECRET", "")
    sig = request.headers.get("x-tiktok-signature", "")
    if secret and sig:
        expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return JSONResponse({"error": "invalid signature"}, status_code=401)

    try:
        data = _json.loads(body_bytes)
    except Exception:
        data = {}

    event   = data.get("event", "")
    status  = data.get("data", {}).get("status", "")
    pub_id  = data.get("data", {}).get("publish_id", "")
    share_url = data.get("data", {}).get("share_url", "")

    # Log it
    print(f"📱 TikTok webhook: event={event} status={status} publish_id={pub_id}")

    # Notify via Telegram
    if event or status:
        try:
            from .tools.n8n_tools import send_telegram
            icon = "✅" if status in ("PUBLISH_COMPLETE", "SUCCESS") else "⚠️"
            msg  = (f"{icon} TikTok webhook: {event or status}\n"
                    f"Publish ID: {pub_id}\n"
                    + (f"🔗 {share_url}" if share_url else ""))
            send_telegram(msg)
        except Exception:
            pass

    # TikTok expects a 200 with specific body
    return JSONResponse({"code": 0, "message": "success"})


@app.get("/api/v1/tiktok/webhook")
async def tiktok_webhook_verify(request: Request):
    """Handle TikTok webhook URL verification challenge."""
    challenge = request.query_params.get("challenge", "")
    if challenge:
        return JSONResponse({"challenge": challenge})
    return JSONResponse({"status": "ok"})


# ── HyperFrames endpoints ─────────────────────────────────────────────────────

@app.post("/api/v1/hyperframes/render")
async def hyperframes_render(request: Request):
    """Render arbitrary HTML or a Mr. Yeti topic to MP4 via HyperFrames."""
    body = await request.json()
    html    = body.get("html", "")
    topic   = body.get("topic", "")
    slug    = body.get("slug", "")
    quality = body.get("quality", "standard")

    import threading
    result_box = {}

    def _run():
        from .tools import hyperframes as hf
        if html:
            result_box.update(hf.render_html(html, slug=slug, quality=quality))
        else:
            result_box.update(hf.generate_and_render(topic=topic))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=310)

    if result_box.get("ok"):
        return JSONResponse(result_box)
    return JSONResponse(result_box or {"ok": False, "error": "Render timed out"}, status_code=500)


@app.get("/api/v1/hyperframes/preview")
async def hyperframes_preview():
    """Return recent HyperFrames renders for the UI."""
    from pathlib import Path as _P
    out_dir = _P(str(config.ROOT)) / "videos_output"
    files = sorted(out_dir.glob("hf_*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True)
    return {"renders": [{"name": f.name, "size_kb": f.stat().st_size // 1024,
                         "path": str(f)} for f in files[:10]]}


# ── TikTok endpoints ──────────────────────────────────────────────────────────

@app.get("/api/v1/tiktok/status")
async def tiktok_status():
    from .tools.tiktok_post import status
    return status()


@app.get("/api/v1/tiktok/auth")
async def tiktok_auth():
    from .tools.tiktok_post import get_auth_url, app_configured
    if not app_configured():
        return JSONResponse({"error": "Add TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET to .env first"}, status_code=400)
    return RedirectResponse(get_auth_url())


@app.get("/api/v1/tiktok/callback")
async def tiktok_callback(code: str = "", error: str = "", state: str = ""):
    from .tools.tiktok_post import exchange_code
    if error:
        return HTMLResponse(f"<h3>TikTok auth failed: {error}</h3><p>Close this tab and try again.</p>")
    if not code:
        return HTMLResponse("<h3>No code returned</h3>")
    result = exchange_code(code)
    if result.get("ok"):
        return HTMLResponse(
            "<h3>✅ TikTok connected!</h3>"
            f"<p>Open ID: {result.get('open_id', '')}</p>"
            "<p>Baadar will auto-post Mr. Yeti videos daily at 8am. Close this tab.</p>"
        )
    return HTMLResponse(f"<h3>❌ Error</h3><pre>{result}</pre>")


# ── Mr. Yeti video pipeline endpoints ─────────────────────────────────────────

@app.get("/api/v1/yeti/queue")
async def yeti_queue():
    from .tools.mr_yeti_pipeline import get_today_queue, _load_queue
    return {"today": get_today_queue(), "recent": _load_queue()[-7:]}


@app.post("/api/v1/yeti/generate")
async def yeti_generate(request: Request):
    body = await request.json()
    topic = body.get("topic", "")
    import threading
    result_box = {}
    def _run():
        from .tools.mr_yeti_pipeline import queue_for_review
        result_box.update(queue_for_review(topic=topic))
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "generating", "message": "Generating Mr. Yeti video in background. You'll get a Telegram when it's ready."}


@app.post("/api/v1/yeti/post")
async def yeti_post_now():
    from .tools.mr_yeti_pipeline import post_queued_today
    return post_queued_today()


@app.post("/api/v1/yeti/run_pipeline")
async def yeti_run_pipeline(request: Request):
    body = await request.json()
    topic = body.get("topic", "")
    force = body.get("force", False)
    import threading
    def _run():
        from .tools.mr_yeti_pipeline import run_pipeline
        run_pipeline(topic=topic, force=force)
    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "message": "Pipeline running in background — Telegram notification when done."}


@app.get("/api/v1/serve/{filename}")
async def serve_reel_file(filename: str):
    """Serve staged Reel video files publicly for Meta Graph API ingestion."""
    from fastapi.responses import FileResponse
    serve_dir = config.ROOT / "data" / "serve"
    fpath = serve_dir / filename
    if not fpath.exists() or not fpath.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(fpath), media_type="video/mp4")


@app.get("/api/v1/leads")
async def get_leads(request: Request):
    """Return email leads captured from pielts.web.app lead magnet."""
    try:
        import firebase_admin
        from firebase_admin import firestore as _fs
        db = _fs.client()
        docs = db.collection("leads").order_by("createdAt", direction=_fs.Query.DESCENDING).limit(200).stream()
        leads = []
        for d in docs:
            data = d.to_dict()
            leads.append({
                "email": data.get("email", ""),
                "source": data.get("source", ""),
                "createdAt": str(data.get("createdAt", "")),
            })
        return {"ok": True, "count": len(leads), "leads": leads}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ══════════════════════════════════════════════════════════════════════════════
# FLOW 8 — Master Orchestrator endpoints
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/studio/topics")
async def studio_topics(request: Request):
    """Generate Mr. Yeti IELTS video topic ideas via LLM."""
    import json as _json
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    count = int(body.get("count", 100))
    niche = body.get("niche", "IELTS")
    from .tools._llm_helper import ask_llm
    prompt = (
        f"Generate {count} unique YouTube video topic ideas for the Mr. Yeti channel — "
        f"a 3D animated Yeti character teaching {niche}. "
        f"Use these 5 content pillars (mix them roughly evenly): "
        f"horror_story (scary exam situations), before_after (transformation stories), "
        f"dont_say (common mistakes), quiz (interactive challenges), interview (mock interviews). "
        f"Return ONLY a JSON array of {count} topic strings, no extra text, no numbering."
    )
    try:
        raw = ask_llm(prompt)
        # Parse JSON array from response
        import re as _re
        match = _re.search(r'\[.*\]', raw, _re.DOTALL)
        if match:
            topics = _json.loads(match.group())
        else:
            # Fallback: split by newlines
            topics = [line.strip().strip('",') for line in raw.splitlines() if line.strip()]
        # Save to data file
        data_dir = config.ROOT / "data"
        data_dir.mkdir(exist_ok=True)
        with open(data_dir / "mr_yeti_topics.json", "w") as f:
            _json.dump({"topics": topics, "count": len(topics)}, f, indent=2)
        return {"ok": True, "topics": topics, "count": len(topics)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/studio/scenes")
async def studio_scenes(request: Request):
    """Break a script into Veo/Google Flow scene prompts."""
    import json as _json
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    script = body.get("script", {})
    yeti_library = body.get("yeti_library", ["walking", "pointing", "thinking", "celebrating", "surprised", "explaining"])
    from .tools._llm_helper import ask_llm
    script_text = _json.dumps(script) if isinstance(script, dict) else str(script)
    prompt = (
        f"You are a video director for Mr. Yeti, a 3D animated Yeti character teaching IELTS. "
        f"Break the following script into 4-6 scenes for Veo/Google Flow video generation.\n\n"
        f"Script: {script_text}\n\n"
        f"Available Yeti poses: {yeti_library}\n\n"
        f"Return a JSON array of scene objects. Each scene must have:\n"
        f"- scene: integer (1-based)\n"
        f"- duration_sec: integer (6-12 seconds)\n"
        f"- prompt: string (Veo-style visual prompt starting with 'Mr. Yeti 3D animated...')\n"
        f"- yeti_pose: one of the available poses\n"
        f"- text_overlay: short text to display on screen\n\n"
        f"Return ONLY the JSON array, no extra text."
    )
    try:
        raw = ask_llm(prompt)
        import re as _re
        match = _re.search(r'\[.*\]', raw, _re.DOTALL)
        scenes = _json.loads(match.group()) if match else []
        total_duration = sum(s.get("duration_sec", 8) for s in scenes)
        return {"ok": True, "scenes": scenes, "total_duration_sec": total_duration}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/studio/generate-video")
async def studio_generate_video(request: Request):
    """Generate video via Veo/Google Flow or return pending stub."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    prompts = body.get("prompts", [])
    method = body.get("method", "veo")
    duration = body.get("duration", 480)
    topic = prompts[0].get("prompt", "") if prompts else ""
    try:
        from .tools.google_flow import generate_full_video
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: generate_full_video(topic=topic, use_veo=True)
        )
        return result
    except Exception:
        return {
            "ok": True,
            "video_path": "",
            "method": "pending",
            "message": "Veo not configured — add video manually to queue",
        }


@app.post("/api/v1/studio/stitch-video")
async def studio_stitch_video(request: Request):
    """Stitch Veo scene clips into master video using full FFmpeg pipeline."""
    import datetime as _dt
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    slug  = body.get("slug") or _dt.date.today().strftime("%Y%m%d")
    clips = body.get("clips", [])   # list of file paths

    # Auto-discover today's scene clips if none provided
    if not clips:
        scenes_dir = config.ROOT / "data" / "mr_yeti_scenes" / slug
        if scenes_dir.exists():
            clips = sorted(str(p) for p in scenes_dir.glob("*.mp4"))
    if not clips:
        return {"ok": False, "error": "No clips provided or found for slug: " + slug}

    try:
        from .tools.video_editor import stitch_scenes
        result = stitch_scenes(clips, str(config.ROOT / "data" / "mr_yeti_videos" / f"{slug}_master.mp4"))
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


@app.post("/api/v1/studio/extract-clips")
async def studio_extract_clips(request: Request):
    """Extract 6 Shorts from master video with overlays + BGM."""
    import datetime as _dt
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    slug       = body.get("slug") or _dt.date.today().strftime("%Y%m%d")
    video_path = body.get("video_path", "")
    add_music  = body.get("add_music", True)

    if not video_path:
        master = config.ROOT / "data" / "mr_yeti_videos" / f"{slug}_master.mp4"
        captioned = config.ROOT / "data" / "mr_yeti_videos" / f"{slug}_captioned.mp4"
        video_path = str(captioned) if captioned.exists() else str(master)

    from pathlib import Path as _P
    if not _P(video_path).exists():
        return {"ok": False, "error": f"Video not found: {video_path}"}

    try:
        from .tools.video_editor import extract_shorts
        shorts = extract_shorts(video_path, slug=slug, add_music=add_music)
        return {"ok": True, "shorts": shorts, "count": len(shorts)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


@app.post("/api/v1/studio/transcribe")
async def studio_transcribe(request: Request):
    """Transcribe video audio → SRT file (Whisper local or OpenAI API)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    video_path  = body.get("video_path", "")
    model_size  = body.get("model", "base")
    if not video_path:
        return {"ok": False, "error": "video_path required"}
    try:
        from .tools.video_editor import transcribe_audio
        return transcribe_audio(video_path, model_size=model_size)
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


@app.post("/api/v1/studio/burn-captions")
async def studio_burn_captions(request: Request):
    """Burn SRT subtitles into video (TikTok-style bold centered text)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    video_path = body.get("video_path", "")
    srt_path   = body.get("srt_path", "")
    output     = body.get("output_path", video_path.replace(".mp4", "_captioned.mp4"))
    if not video_path or not srt_path:
        return {"ok": False, "error": "video_path and srt_path required"}
    try:
        from .tools.video_editor import burn_captions
        return burn_captions(video_path, srt_path, output)
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


@app.post("/api/v1/studio/add-music")
async def studio_add_music(request: Request):
    """Mix background music under video audio at low volume."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    video_path = body.get("video_path", "")
    output     = body.get("output_path", video_path.replace(".mp4", "_music.mp4"))
    volume     = float(body.get("volume", 0.18))
    if not video_path:
        return {"ok": False, "error": "video_path required"}
    try:
        from .tools.video_editor import add_background_music
        return add_background_music(video_path, output, volume=volume)
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


@app.post("/api/v1/studio/full-pipeline")
async def studio_full_pipeline(request: Request):
    """
    Run the complete editing pipeline on a set of raw Veo scene clips.
    Body: { "slug": "20260623", "clips": ["path1.mp4", ...], "srt_path": null }
    Returns paths to master, captioned, shorts, thumbnail.
    """
    import datetime as _dt
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    slug   = body.get("slug") or _dt.date.today().strftime("%Y%m%d")
    clips  = body.get("clips", [])
    srt    = body.get("srt_path")

    if not clips:
        scenes_dir = config.ROOT / "data" / "mr_yeti_scenes" / slug
        if scenes_dir.exists():
            clips = sorted(str(p) for p in scenes_dir.glob("*.mp4"))
    if not clips:
        return {"ok": False, "error": "No clips provided or found"}

    try:
        from .tools.video_editor import run_full_edit_pipeline
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: run_full_edit_pipeline(clips, slug, srt_path=srt)
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}


@app.get("/api/v1/studio/asset-status")
async def studio_asset_status(request: Request):
    """Check which editing assets (BGM, intro, outro, FFmpeg) are available."""
    try:
        from .tools.video_editor import asset_status
        return {"ok": True, **asset_status()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/studio/download-bgm")
async def studio_download_bgm(request: Request):
    """Download a free CC0 background music track for video editing."""
    try:
        from .tools.video_editor import download_free_bgm
        return download_free_bgm()
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/studio/captions")
async def studio_captions(request: Request):
    """Generate per-platform captions for each clip type via LLM."""
    import json as _json
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    clips = body.get("clips", {})
    platforms = body.get("platforms", ["youtube", "tiktok", "instagram", "facebook"])
    from .tools._llm_helper import ask_llm
    captions = {}
    for clip_type, clip_path in clips.items():
        prompt = (
            f"Generate social media captions for a Mr. Yeti IELTS video clip type: '{clip_type}'.\n"
            f"Mr. Yeti is a friendly 3D animated Yeti character who teaches IELTS tips.\n\n"
            f"Generate captions for these platforms: {platforms}\n\n"
            f"For YouTube: include title (max 100 chars), description (2-3 paragraphs), and tags (list of 10).\n"
            f"For TikTok, Instagram, Facebook: include a short punchy caption (max 150 chars) and hashtags (list of 8).\n\n"
            f"Return ONLY a JSON object with platform names as keys. Example:\n"
            f'{{"youtube": {{"title": "...", "description": "...", "tags": [...]}}, '
            f'"tiktok": {{"caption": "...", "hashtags": [...]}}}}'
        )
        try:
            raw = ask_llm(prompt)
            import re as _re
            match = _re.search(r'\{.*\}', raw, _re.DOTALL)
            platform_captions = _json.loads(match.group()) if match else {}
            captions[clip_type] = platform_captions
        except Exception as e:
            captions[clip_type] = {"error": str(e)}
    return {"ok": True, "captions": captions}


@app.post("/api/v1/telegram/send")
async def telegram_send(request: Request):
    """Send a Telegram message via n8n_tools."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    text = body.get("text", "")
    if not text:
        return {"ok": False, "error": "text required"}
    try:
        from .tools.n8n_tools import send_telegram
        send_telegram(text)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/notify/new-user")
async def notify_new_user(request: Request):
    """Called by pielts frontend when a new user registers — sends Telegram notification."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    uid = body.get("uid", "?")
    name = body.get("name", "(no name)")
    email = body.get("email", "(no email)")
    phone = body.get("phone", "")
    account_type = body.get("accountType", "individual")
    from datetime import datetime, timezone, timedelta
    npt = datetime.now(timezone(timedelta(hours=5, minutes=45)))
    time_str = npt.strftime("%b %d, %Y %I:%M %p NPT")
    phone_line = f"\n📞 Phone: {phone}" if phone else ""
    msg = (
        f"🎉 New pielts.web.app Registration!\n\n"
        f"👤 Name: {name}\n"
        f"📧 Email: {email}{phone_line}\n"
        f"🔑 Type: {account_type}\n"
        f"🕐 Time: {time_str}\n"
        f"🆔 UID: {uid}"
    )
    try:
        from .tools.n8n_tools import send_telegram
        send_telegram(msg)
    except Exception:
        pass
    return {"ok": True}


# ── Intelligence Layer: Flows 9–12 ────────────────────────────────────────────

@app.post("/api/v1/analytics/run")
async def analytics_run(request: Request):
    """Flow 9: Pull analytics, score videos, update content weights."""
    try:
        from .tools.analytics_loop import run_analytics_loop
        result = run_analytics_loop()
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/analytics/retention")
async def analytics_retention(platform: str = None):
    """Return all stored retention data, optionally filtered by platform."""
    try:
        from .tools.intelligence import get_all_retention
        return {"ok": True, "data": get_all_retention(platform)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/analytics/retention")
async def analytics_retention_save(request: Request):
    """Store/update retention data for a video."""
    try:
        body = await request.json()
        from .tools.intelligence import upsert_retention
        result = upsert_retention(
            body["video_id"], body["platform"],
            body.get("ret_3s", 0), body.get("ret_10s", 0), body.get("ret_30s", 0),
            body.get("avg_watch_sec", 0), body["completion_pct"]
        )
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/analytics/insights")
async def analytics_insights(request: Request):
    """Return current analytics weights + insight summary."""
    try:
        from .tools.analytics_loop import get_weights, _generate_insight
        w = get_weights()
        return {"ok": True, "weights": w, "insight": _generate_insight(w)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/analytics/patterns")
async def analytics_patterns():
    """Return avg retention per format type and top performing formats."""
    try:
        from .tools.intelligence import get_format_avg_retention, get_top_formats
        avgs = get_format_avg_retention()
        tops = get_top_formats(3)
        return {"ok": True, "avg_by_format": avgs, "top_formats": tops}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/analytics/patterns")
async def analytics_patterns_save(request: Request):
    """Save a viral pattern data point."""
    try:
        body = await request.json()
        from .tools.intelligence import save_viral_pattern
        save_viral_pattern(
            body.get("hook", ""), body.get("topic", ""), body.get("format_type", "tip"),
            body.get("retention_pct", 0), body.get("views", 0),
            body.get("shares", 0), body.get("saves", 0), body.get("platform", "youtube")
        )
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/comments/mine")
async def comments_mine(request: Request):
    """Flow 10: Pull YouTube comments, extract video ideas."""
    try:
        from .tools.comment_miner import run_comment_miner
        return run_comment_miner()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/comments/ideas")
async def comments_ideas(request: Request):
    """Return saved comment-derived video ideas."""
    try:
        from .tools.comment_miner import get_top_ideas
        return {"ok": True, "ideas": get_top_ideas(n=10)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/comments/video-ideas")
async def comments_video_ideas(n: int = 10):
    """Return top video ideas extracted from comments."""
    try:
        from .tools.intelligence import get_video_ideas_from_comments
        return {"ok": True, "ideas": get_video_ideas_from_comments(n)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/comments/classify")
async def comments_classify(request: Request):
    """Classify a batch of comments and save to DB."""
    try:
        body = await request.json()
        comments = body.get("comments", [])
        from .tools.intelligence import classify_comments
        return {"ok": True, "results": classify_comments(comments)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/competitors/scan")
async def competitors_scan():
    """Fetch top 5 videos from each competitor channel."""
    from .tools.intelligence import scan_competitors
    import asyncio
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, scan_competitors)
        return {"ok": True, "results": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/competitors/insights")
async def competitors_insights():
    """Return pattern analysis from competitor data."""
    from .tools.intelligence import get_competitor_insights
    import asyncio
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, get_competitor_insights)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/trends/scan")
async def trends_scan(request: Request):
    """Flow 11: Scan Reddit + YouTube trends, generate topic ideas."""
    try:
        from .tools.trend_hunter import run_trend_hunter
        return run_trend_hunter()
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/trends/topics")
async def trends_topics(request: Request):
    """Return current trending topic ideas."""
    try:
        from .tools.trend_hunter import get_trending_topics
        return {"ok": True, "topics": get_trending_topics(n=10)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/hooks/generate")
async def hooks_generate(request: Request):
    """Generate 20 hooks for a topic, score them, return top 3."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "IELTS tips")
    try:
        from .tools.content_studio import generate_hooks
        result = generate_hooks(topic)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/v1/thumbnails/generate")
async def thumbnails_generate(request: Request):
    """Flow 12: Generate 5 thumbnail variants sorted by predicted CTR."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    topic = body.get("topic", "")
    title = body.get("video_title", topic)
    n     = int(body.get("n", 5))
    if not topic:
        return {"ok": False, "error": "topic required"}
    try:
        from .tools.ab_tester import generate_thumbnail_variants
        thumbnails = generate_thumbnail_variants(topic, title, n=n)
        return {"ok": True, "thumbnails": thumbnails}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.post("/api/v1/ab/record")
async def ab_record(request: Request):
    """Record an A/B test result (views_a, views_b, test_id)."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    test_id = body.get("test_id", "")
    views_a = int(body.get("views_a", 0))
    views_b = int(body.get("views_b", 0))
    if not test_id:
        return {"ok": False, "error": "test_id required"}
    try:
        from .tools.ab_tester import record_result
        record_result(test_id, views_a, views_b)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/ab/patterns")
async def ab_patterns(request: Request):
    """Return winning hook patterns from completed A/B tests."""
    try:
        from .tools.ab_tester import get_winning_patterns
        return {"ok": True, **get_winning_patterns()}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/v1/mailerlite/subscribers")
async def mailerlite_subscriber_count(request: Request):
    """Return total active subscriber count + per-group breakdown from MailerLite."""
    try:
        from .tools.mailerlite import list_groups, list_subscribers
        groups_result = list_groups()
        if "error" in groups_result:
            return {"ok": False, "error": groups_result["error"]}
        groups = groups_result.get("groups", [])
        total_active = sum(g.get("count", 0) for g in groups)
        # Also get overall subscriber count from the API meta
        from .tools.mailerlite import _h, BASE
        import httpx as _hx
        meta_total = None
        try:
            r = _hx.get(f"{BASE}/subscribers", headers=_h(), params={"limit": 1}, timeout=10)
            r.raise_for_status()
            meta_total = r.json().get("meta", {}).get("total")
        except Exception:
            pass
        return {
            "ok": True,
            "total": meta_total if meta_total is not None else total_active,
            "active": total_active,
            "groups": [{"id": g["id"], "name": g["name"], "count": g["count"]} for g in groups],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


# ---------------------------------------------------------------------------
# IELTS Writing Evaluator (public — no auth required, read-only AI call)
# ---------------------------------------------------------------------------
class WritingEvalIn(BaseModel):
    essay: str
    task_type: str = "task2"   # "task1" | "task2"
    prompt: str = ""

@app.post("/api/v1/evaluate/writing")
async def evaluate_writing(body: WritingEvalIn):
    """Gemini-powered IELTS essay scorer. Falls back to heuristic if key missing."""
    from .tools.writing_eval import evaluate_essay
    try:
        result = evaluate_essay(body.essay, body.task_type, body.prompt)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


@app.post("/api/v1/evaluate/speaking")
async def evaluate_speaking_endpoint(
    question: str = Form(""),
    part: int = Form(1),
    transcript: str = Form(""),
    duration_seconds: float = Form(None),
    audio: UploadFile = File(None),
):
    from .tools.speaking_eval import transcribe_and_evaluate, evaluate_speaking
    try:
        if audio and audio.filename:
            audio_bytes = await audio.read()
            mime_type = audio.content_type or "audio/webm"
            result = transcribe_and_evaluate(audio_bytes, mime_type, question, part, duration_seconds)
        else:
            result = evaluate_speaking(transcript or "", question, part, duration_seconds)
            result["transcript"] = transcript
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:400]}


# ── Auto-Dev Agent ───────────────────────────────────────────────────────────

@app.post("/api/v1/dev/auto")
async def auto_dev_endpoint(request: Request):
    """
    Spec → Build → Review → Deploy loop.
    Body: {"task": str, "project": "baadar|pielts", "deploy": bool}
    Reference: ~/.claude/skills/auto-dev/README.md
    Patterns: ~/awesome-llm-apps/
    """
    try:
        body = await request.json()
        task = body.get("task", "")
        project = body.get("project", "baadar")
        deploy = body.get("deploy", False)
        if not task:
            return {"ok": False, "error": "task is required"}
        from .tools.auto_dev import run_auto_dev
        result = await run_auto_dev(task, project, deploy)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)[:500]}


# ── Dashboard API ────────────────────────────────────────────────────────────

_ceo_cache: dict = {"ts": 0, "data": None}


@app.get("/api/v1/dashboard/status")
def dashboard_status(request: Request):
    if not _is_authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from .scheduler import JOBS as SCHEDULER_JOBS
    # Scheduler jobs
    jobs = []
    for hh, mm, wd, fn in SCHEDULER_JOBS:
        jobs.append({"time": f"{hh:02d}:{mm:02d}", "name": fn.__name__, "weekday": wd})
    # DB stats
    import sqlite3
    db_stats = {"total_hooks": 0, "total_patterns": 0, "total_referral_events": 0}
    try:
        con = sqlite3.connect(str(config.DB_PATH))
        try:
            db_stats["total_hooks"] = con.execute("SELECT COUNT(*) FROM hooks").fetchone()[0]
        except Exception:
            pass
        try:
            db_stats["total_patterns"] = con.execute("SELECT COUNT(*) FROM viral_patterns").fetchone()[0]
        except Exception:
            pass
        try:
            db_stats["total_referral_events"] = con.execute("SELECT COUNT(*) FROM referral_events").fetchone()[0]
        except Exception:
            pass
        con.close()
    except Exception:
        pass
    return {"scheduler_jobs": jobs, "db_stats": db_stats, "server_uptime_seconds": time.time() - _SERVER_START}


@app.get("/api/v1/dashboard/ceo")
def dashboard_ceo(request: Request):
    if not _is_authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    global _ceo_cache
    if time.time() - _ceo_cache["ts"] < 300 and _ceo_cache["data"] is not None:
        return {"ok": True, "dashboard": _ceo_cache["data"]}
    try:
        from .tools.intelligence import build_ceo_dashboard
        result = build_ceo_dashboard()
        _ceo_cache = {"ts": time.time(), "data": result}
        return {"ok": True, "dashboard": result}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


class TriggerIn(BaseModel):
    job: str


@app.post("/api/v1/dashboard/trigger")
def dashboard_trigger(body: TriggerIn, request: Request):
    if not _is_authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    from .scheduler import JOBS as SCHEDULER_JOBS
    import threading
    for hh, mm, wd, fn in SCHEDULER_JOBS:
        if fn.__name__ == body.job:
            threading.Thread(target=fn, daemon=True).start()
            return {"ok": True, "job": body.job}
    return JSONResponse({"error": f"Job '{body.job}' not found"}, status_code=404)


# ── System monitoring ─────────────────────────────────────────────────────────

@app.get("/api/v1/system/disk")
async def system_disk(request: Request):
    """Returns local disk usage — helps monitor if disk is filling up."""
    if not _is_authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    import shutil
    total, used, free = shutil.disk_usage("/")
    gb = 1024**3
    return {
        "total_gb": round(total / gb, 1),
        "used_gb": round(used / gb, 1),
        "free_gb": round(free / gb, 1),
        "used_pct": round(used / total * 100, 1),
    }


@app.post("/api/v1/system/cleanup-disk")
async def cleanup_disk(request: Request):
    """Delete local video/reel/thumbnail dirs to free disk space."""
    if not _is_authed(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    import shutil
    from . import config as _config
    cleaned = []
    for dirname in ("videos_output", "reels_output", "thumbnails"):
        d = _config.ROOT / dirname
        if d.exists():
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            shutil.rmtree(d, ignore_errors=True)
            cleaned.append({"dir": dirname, "freed_mb": round(size / 1024**2, 1)})
    return {"ok": True, "cleaned": cleaned}


# ── Opik observability ───────────────────────────────────────────────────────

@app.get("/api/v1/opik/status")
def opik_status():
    """Return Opik tracing status and dashboard link."""
    try:
        import opik
        return {
            "enabled": True,
            "project": "baadar",
            "dashboard": "https://www.comet.com/opik",
            "sdk_version": opik.__version__,
        }
    except Exception as e:
        return {"enabled": False, "error": str(e)}


# ── Static client ─────────────────────────────────────────────────────────────

# IELTS static assets (mr-yeti.css, mr-yeti.js, writing-editor.html)
_ielts_static = config.ROOT / "static" / "ielts"
if _ielts_static.exists():
    app.mount("/ielts", StaticFiles(directory=str(_ielts_static)), name="ielts_static")

app.mount("/", StaticFiles(directory=str(config.ROOT / "client"), html=True),
          name="client")


@app.on_event("startup")
def _start_background():
    """Daily self-improvement cycle + the proactive scheduler."""
    import threading

    # Initialize intelligence database tables
    try:
        from .tools.intelligence import init_db as _init_intelligence_db
        _init_intelligence_db()
    except Exception:
        pass

    # M5.1 infrastructure wiring: infra events → Episodes, and register the
    # reasoning brain so the Conversation Engine has Executive Intelligence
    # without infrastructure importing a department.
    try:
        from .events import bus as _bus
        from . import episode_bridge
        episode_bridge.install(_bus)
    except Exception:
        pass
    # seed the Selector Registry with the YouTube page-object defaults so the
    # Automation Knowledge Graph is populated from first boot
    try:
        from .infrastructure.human_browser import default_selector_registry
        from .infrastructure.human_browser.pages import youtube as _yt, linkedin as _li, tiktok as _tt
        reg = default_selector_registry()
        _yt.seed(reg); _li.seed(reg); _tt.seed(reg)
    except Exception:
        pass
    # seed the AI Lab Prompt Library with the real prompts from the codebase
    try:
        from .ai_lab import seed_defaults
        seed_defaults()
    except Exception:
        pass
    try:
        from .infrastructure.conversation import register_default_brain
        from .agent import SaathiAgent
        _agent = SaathiAgent()
        register_default_brain(
            lambda message, session: _agent.respond(
                message, session_id=session.session_id, speaker_verified=True))
    except Exception:
        pass

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
    # Two-way Telegram — the phone conversation surface. start() is inert unless
    # TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set, so this is safe to always call.
    try:
        from . import telegram_bot
        telegram_bot.start()
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
