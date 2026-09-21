"""SaathiAI FastAPI server — voice + text + files, serving the Siri-style web app."""
import base64
import json
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
import os as _os
from fastapi import Body, Depends, FastAPI, File, Form, Request, UploadFile


from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, voice
from .agent import SaathiAgent

app = FastAPI(title="SaathiAI")
# CORS — strict origin whitelist (M47.6). NO wildcard with credentials.
# Production/staging fail closed unless SAATHI_CORS_ORIGINS is set.
from .cors_policy import (  # noqa: E402
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    resolve_cors_origins,
)

_origins = resolve_cors_origins()
# NOTE: CORSMiddleware is deliberately NOT registered here. Starlette builds the
# middleware stack outermost-first from the reverse of the registration order, so
# registering CORS at import time would bury it beneath the `_auth` gate defined
# further down this module. It is registered at the bottom of the file instead —
# see `_install_outermost_cors()` — so that CORS is the outermost layer and an
# authentication rejection still leaves the origin correctly labelled.


# ── Security Headers Middleware (Phase 7) ───────────────────────────────────
from starlette.middleware.base import BaseHTTPMiddleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # CSP — strict but allowing inline scripts/styles for Next.js dev builds
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(RequestValidationError)
async def _validation_error_without_secrets(request, exc):
    """422 responses must never echo the credential that was submitted.

    FastAPI's default handler puts the offending `input` verbatim into the error
    body. A login endpoint therefore answers a malformed request by REFLECTING
    the password back to the caller, which then lands in terminal scrollback,
    proxy logs, browser devtools and any error tracker in the path. This was
    observed live: POSTing to /api/v1/platform/auth/login without the required
    field returned the submitted password in the 422 body.

    The fix is at the boundary, not per-endpoint. Every route that takes a body
    inherits this handler, so a new endpoint cannot reintroduce the leak by
    forgetting about it, and the field list is the repo's existing certified
    secret detector rather than a second copy that would drift from it.

    `loc` is kept: a field NAME is what makes the error actionable, and naming
    "password" is not disclosing one.
    """
    from fastapi.encoders import jsonable_encoder

    from saathi.tool_runtime.secrets import REDACTED, is_secret_key, redact

    def _safe(value):
        """Redacted AND serialisable.

        A malformed body arrives here as raw BYTES, which json cannot encode. An
        exception raised inside this handler does not become a 422 — it escapes
        as an unhandled error, so a handler that can throw turns the bug it was
        written to fix into a 500. Everything is coerced through
        `jsonable_encoder`, and anything that still resists becomes its repr.
        """
        try:
            return jsonable_encoder(redact(value))
        except Exception:
            try:
                return repr(value)[:200]
            except Exception:
                return REDACTED

    safe = []
    for err in exc.errors():
        e = dict(err)
        loc = e.get("loc") or ()
        # The value that failed validation, under a key that names a credential.
        leaf = str(loc[-1]) if loc else ""
        if "input" in e:
            e["input"] = REDACTED if is_secret_key(leaf) else _safe(e["input"])
        if "ctx" in e:
            e["ctx"] = _safe(e["ctx"])
        # Pydantic's url points at its docs; harmless, but nothing needs it.
        e.pop("url", None)
        try:
            e["loc"] = [str(x) for x in loc]
        except Exception:
            e["loc"] = []
        safe.append(e)
    return JSONResponse({"detail": safe}, status_code=422)




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
    Token-gated (not whitelisted).

    M17.24: records a governed browser intent first; raw human-browser enqueue
    requires SAATHI_ALLOW_RAW_BROWSER=1 or an explicit approval_id.
    """
    import asyncio
    import json as _json
    import os as _osenv
    from saathi.infrastructure.human_browser import HumanBrowserProxy, default_queue
    from saathi.browser.guard import raw_browser_env_enabled
    raw = await request.body()
    body = _json.loads(raw) if raw else {}
    url = body.get("url", "https://example.com")
    actor = body.get("actor") or "user:api"
    approval_id = body.get("approval_id") or ""
    # Governed intent (domain policy + risk + ledger)
    try:
        from saathi.browser.governed import default_governed_browser
        rec = default_governed_browser().execute(
            action="navigate",
            url=url,
            actor=actor,
            approval_id=approval_id,
            approval_pre_resolved=bool(approval_id),
            request_source="api",
            mission_id=body.get("mission_id") or "human_browser_test",
            mission_run_id=body.get("mission_run_id") or "human-test",
            environment=body.get("environment") or "dev",
        )
        if rec.status in ("denied", "failed") and rec.failure_category in (
            "domain", "domain_not_allowlisted", "dangerous_or_unsupported_scheme",
            "missing_actor", "mission_cancelled",
        ):
            return {
                "ok": False,
                "error": "governance_denied",
                "status": rec.status,
                "execution_id": rec.execution_id,
                "failure_category": rec.failure_category,
                "governed": True,
            }
        gov_exec_id = rec.execution_id
    except Exception as e:
        return {"ok": False, "error": f"governance_error: {e}", "governed": True}

    if not raw_browser_env_enabled() and not approval_id:
        return {
            "ok": False,
            "error": "raw_human_browser_disabled",
            "execution_id": gov_exec_id,
            "message": "Human-browser enqueue requires approval_id or "
                       "SAATHI_ALLOW_RAW_BROWSER=1 after governed intent succeeds",
            "governed": True,
        }

    secret = _osenv.getenv("HUMAN_BROWSER_SECRET", "")
    if not secret:
        return {"ok": False, "error": "HUMAN_BROWSER_SECRET not set on the VM",
                "execution_id": gov_exec_id, "governed": True}
    proxy = HumanBrowserProxy(default_queue, secret=secret, timeout=15)
    try:
        result = await asyncio.to_thread(proxy.execute, "open",
                                         profile=body.get("profile", ""), url=url)
        return {"ok": True, "result": result, "execution_id": gov_exec_id, "governed": True}
    except Exception as e:
        return {"ok": False, "error": str(e), "execution_id": gov_exec_id, "governed": True,
                "hint": "start the Mac Agent: bash ~/SaathiAI/run_human_agent.sh"}


_SAATHIOS_BROWSER = None
_SAATHIOS_BROWSER_LOCK = threading.Lock()


def _saathios_browser():
    """The browser behind the SaathiOS Browser surface.

    Real network access is OPT-IN via SAATHI_BROWSER_LIVE=1. Without it this runs
    the deterministic fake, so the surface, its policy denials and its UI are all
    exercisable without a single outbound request. The process-wide
    default_governed_browser() singleton is deliberately left alone: it defaults to
    the fake, and every existing caller and test depends on that.
    """
    global _SAATHIOS_BROWSER
    with _SAATHIOS_BROWSER_LOCK:
        if _SAATHIOS_BROWSER is None:
            from saathi.browser.governed import GovernedBrowser
            from saathi.browser.policy import DEFAULT_ALLOWED_HOST_SUFFIXES
            live = _os.getenv("SAATHI_BROWSER_LIVE", "").strip() in ("1", "true", "yes")
            # The adapter re-checks the domain itself (defence in depth) with its
            # OWN host list, which does not consult the environment. Pass the
            # configured hosts explicitly or an allowlisted host is still refused
            # at the second check. The deny list applies regardless of this list.
            extra = [h.strip().lower() for h in
                     _os.getenv("SAATHI_BROWSER_ALLOWED_DOMAINS", "").split(",") if h.strip()]
            hosts = list(DEFAULT_ALLOWED_HOST_SUFFIXES) + extra
            _SAATHIOS_BROWSER = GovernedBrowser(
                mode="service" if live else "fake", allowed_hosts=hosts,
            )
        return _SAATHIOS_BROWSER


class BrowserFetchIn(BaseModel):
    url: str
    action: str = "read"          # read | extract | navigate | screenshot
    selector: str = ""
    timeout: int = 30
    actor: str = "user:api"


@app.post("/api/v1/browser/fetch")
async def browser_fetch(body: BrowserFetchIn):
    """Read a page through the GOVERNED browser (SaathiOS Browser surface).

    Every request passes domain policy, risk classification, approval and the
    ExecutionGateway before any network call — this endpoint adds a surface, never
    a bypass. Only non-side-effecting actions are accepted here: reading a page is
    not the same authority as clicking or submitting on one, and mixing them behind
    one endpoint is how a read surface quietly becomes an action surface.

    Page text comes back marked UNTRUSTED. It is third-party content that reaches a
    model and a browser, so injection hits are reported alongside it and the caller
    is expected to treat it as data.
    """
    import asyncio

    READ_ONLY = {"read", "extract", "navigate", "open", "screenshot"}
    action = (body.action or "read").strip().lower()
    if action not in READ_ONLY:
        return {"ok": False, "error": "action_not_permitted",
                "message": f"{action} can change a page; this endpoint is read-only",
                "permitted": sorted(READ_ONLY)}

    url = (body.url or "").strip()
    if not url:
        return {"ok": False, "error": "missing_url"}

    try:
        gb = _saathios_browser()
        rec = await asyncio.to_thread(
            gb.execute,
            action=action,
            url=url,
            selector=(body.selector or "").strip(),
            actor=body.actor or "user:api",
            request_source="api",
            mission_id="saathios_browser",
            mission_run_id="browser-surface",
            environment=_os.getenv("SAATHI_ENV", "dev"),
            payload={"timeout": max(1, min(int(body.timeout or 30), 60))},
            # Reads are not side-effecting, so re-reading a page is a legitimate
            # act rather than a duplicate one. Without a fresh key the gateway's
            # idempotency guard — which exists to stop a click or a submit being
            # replayed — refuses the second read of the same URL.
            idempotency_key=uuid.uuid4().hex,
        )
    except Exception as e:  # governance itself failed — never fall through to a raw fetch
        return {"ok": False, "error": "governance_error", "detail": str(e)[:300]}

    if rec.status not in ("succeeded", "completed", "ok"):
        # A denial is an answer, not an error: say which rule refused and why.
        return {
            "ok": False,
            "error": "denied",
            "status": rec.status,
            "failure_category": getattr(rec, "failure_category", "") or "",
            "execution_id": rec.execution_id,
            "url": url,
            "governed": True,
        }

    body_out = gb.take_content(rec.execution_id) or {}
    return {
        "ok": True,
        "governed": True,
        "execution_id": rec.execution_id,
        "url": url,
        "action": action,
        "final_origin": body_out.get("final_origin", ""),
        "page_title": body_out.get("page_title", ""),
        "content": body_out.get("content", ""),
        "truncated": bool(body_out.get("truncated", False)),
        "injection_hits": body_out.get("injection_hits", []),
        "trust": "UNTRUSTED_EXTERNAL_CONTENT",
        "summary": getattr(rec, "result_summary", "") or "",
    }


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


@app.get("/", include_in_schema=False)
async def _root_to_saathi_os():
    """Retire the legacy 'Baadar' static UI: the local instance now opens the
    same SaathiAI OS dashboard. On the VM, Caddy serves '/' → Next, so this is
    only hit locally. SAATHI_OS_URL overrides the target."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(_os.getenv("SAATHI_OS_URL", "http://localhost:3000"), status_code=307)


@app.post("/api/v1/studio/report")
async def studio_report(request: Request):
    """The Mac worker reports a completed AI Studio run so the VM's Production
    Queue + Today's Factory reflect real Mac production. Token-gated."""
    body = await request.json()
    from saathi.studio_store import default_store
    rid = default_store().record_payload(body or {})
    # Content Memory: remember every published piece so the Studio Planner dedups
    if (body or {}).get("status") == "published" and body.get("topic"):
        try:
            from saathi.content_memory import default_memory
            default_memory().record(topic=body["topic"], run_id=body.get("run_id", ""),
                                    video_url=body.get("video_url", ""),
                                    project_id=body.get("project_id", ""))
        except Exception:
            pass
    return {"ok": True, "id": rid}


@app.get("/api/v1/studio/plan")
async def studio_plan():
    """SaathiAI Studio Director — today's production brief (curriculum + memory
    dedup + Mr. Yeti reference). Whitelisted read."""
    from saathi.studio import plan_today
    from saathi.content_memory import default_memory
    b = plan_today()
    d = b.as_dict()
    d["memory_count"] = default_memory().count()
    d["skills_this_week"] = default_memory().skills_this_week()
    return d


@app.get("/api/v1/studio/produce")
async def studio_produce():
    """Studio Executive — run the full department pipeline (Research → Creative →
    Script), return every structured artifact + ready/revision status. Whitelisted."""
    import asyncio
    from saathi.studio_directors import default_executive
    p = await asyncio.to_thread(default_executive().produce)
    return p.as_dict()


@app.get("/api/v1/studio/render-plan")
async def studio_render_plan():
    """Production Planner (gate) + Render Director → Render Package manifest. Whitelisted."""
    import asyncio
    from saathi.studio import plan_today
    from saathi.script_director import build_brief, write_script
    from saathi.studio_visual import scene_package
    from saathi.production_planner import validate
    from saathi.render_director import plan, available_adapters
    p = plan_today().as_dict()
    doc = await asyncio.to_thread(write_script, build_brief(p))
    pkg = await asyncio.to_thread(scene_package, doc.as_dict())
    check = validate(pkg)
    rp = plan(pkg, episode=p["episode"]) if check["ok"] else {}
    return {"plan_check": check, "render_plan": rp, "adapters_available": available_adapters()}


@app.get("/api/v1/studio/publish-plan")
async def studio_publish_plan():
    """Publishing Director → per-platform Publishing Package. Whitelisted."""
    import asyncio
    from saathi.studio import plan_today
    from saathi.script_director import build_brief, write_script
    from saathi.publishing_director import package, PLATFORMS
    p = plan_today().as_dict()
    doc = await asyncio.to_thread(write_script, build_brief(p))
    pkg = package(doc.as_dict(), plan=p, episode=p["episode"])
    return {"publish_plan": pkg, "platforms_supported": sorted(PLATFORMS)}


@app.get("/api/v1/connectors/providers")
async def connectors_providers():
    """Provider + capability catalog (what SaathiOS can connect to). Whitelisted read."""
    from saathi.connectors.catalog import catalog, CAPABILITIES
    return {"providers": catalog(), "capabilities": CAPABILITIES}


@app.get("/api/v1/connectors/accounts")
async def connectors_accounts(provider: str = "", mission: str = ""):
    """Connected accounts (never returns secrets) + health. Whitelisted read."""
    from saathi.connectors.accounts import default_store
    st = default_store()
    return {"accounts": st.list(provider=provider or "", mission=mission or ""), "health": st.health()}


@app.post("/api/v1/connectors/accounts")
async def connectors_account_add(request: Request):
    """Register an account (secret encrypted at rest, never stored in Git). Token-gated."""
    body = await request.json()
    from saathi.connectors.accounts import default_store
    if not body.get("provider"):
        return {"ok": False, "error": "provider required"}
    # A caller registering an account cannot declare the provider accepted it.
    # `status` is deliberately NOT read from the body: the store refuses
    # CONNECTED at creation, and letting the request pick any other state would
    # just move the same false claim one field along.
    from saathi.connectors.accounts import AccountStatus
    try:
        a = default_store().add(provider=body["provider"], display_name=body.get("display_name", ""),
                                email=body.get("email", ""), scopes=body.get("scopes") or [],
                                secret=body.get("secret") or None)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    a.pop("secret", None)
    return {
        "ok": True,
        "account": a,
        # Said outright so a UI cannot read a successful write as a live
        # connection: storing a credential is configuration, not confirmation.
        "verified": False,
        "next": f"status is {AccountStatus.AUTH_REQUIRED.value} until the provider verifies it",
    }


@app.post("/api/v1/connectors/accounts/{aid}/mission")
async def connectors_link_mission(aid: str, request: Request):
    """Link/unlink an account to a Mission. Token-gated."""
    body = await request.json()
    from saathi.connectors.accounts import default_store
    ok = default_store().link_mission(aid, body.get("mission", ""), bool(body.get("on", True)))
    return {"ok": ok}


@app.delete("/api/v1/connectors/accounts/{aid}")
async def connectors_account_delete(aid: str):
    """Remove an account (and its encrypted secret). Token-gated."""
    from saathi.connectors.accounts import default_store
    return {"ok": default_store().delete(aid)}


@app.post("/api/v1/connectors/execute")
async def connectors_execute(request: Request):
    """Run a capability through the Connector Manager (emits an event → Evidence). Token-gated."""
    import asyncio
    body = await request.json()
    from saathi.connectors.manager import execute
    return await asyncio.to_thread(execute, body.get("account", ""), body.get("capability", ""),
                                   body.get("params") or {}, mission=body.get("mission", ""))


@app.get("/api/v1/knowledge/library")
async def knowledge_library(q: str = "", category: str = "", tag: str = "", director: str = ""):
    """Knowledge Library — search sources (books/github/papers/docs) by any Director. Whitelisted read."""
    from saathi.knowledge_library.store import default_store
    st = default_store()
    if q or tag or director or category:
        items = st.search(q, tag=tag, director=director, category=category)
    else:
        items = st.list()
    return {"sources": items, "categories": st.categories()}


@app.get("/api/v1/automation/credits")
async def automation_credits():
    """Credit Manager — what each generation provider can do today. Whitelisted read."""
    from saathi.production_automation.credits import default_manager
    return {"providers": default_manager().status()}


@app.post("/api/v1/automation/credits/refresh")
async def automation_credits_refresh():
    """Reset daily credits + re-check API keys (midnight-style). Token-gated."""
    from saathi.production_automation.credits import default_manager
    default_manager().refresh()
    return {"ok": True, "providers": default_manager().status()}


@app.get("/api/v1/automation/plan")
async def automation_plan():
    """Production Automation — build today's Production Plan: provider-per-scene (credit-aware,
    cost-optimised), character verification, quality gate, approval mode. Whitelisted read."""
    import asyncio
    from saathi.studio import plan_today
    from saathi.script_director import build_brief, write_script
    from saathi.studio_visual import scene_package
    from saathi.render_director import plan as render_plan_fn
    from saathi.production_automation.pipeline import build_plan, default_store

    p = plan_today().as_dict()
    doc = await asyncio.to_thread(write_script, build_brief(p))
    pkg = await asyncio.to_thread(scene_package, doc.as_dict())
    rp = render_plan_fn(pkg, episode=p["episode"]) if pkg.get("scenes") else {}
    bible = p.get("character") or {}
    mode = default_store().approval_mode()
    plan = build_plan(pkg, render_plan=rp, script=doc.as_dict(), bible=bible,
                      approval_mode=mode, reserve=False)
    plan["episode"] = p["episode"]
    return {"production_plan": plan}


@app.get("/api/v1/automation/settings")
async def automation_settings():
    """Approval mode + recent production runs. Whitelisted read."""
    from saathi.production_automation.pipeline import default_store, APPROVAL_MODES
    st = default_store()
    return {"approval_mode": st.approval_mode(), "modes": list(APPROVAL_MODES),
            "recent_runs": st.recent_runs()}


@app.post("/api/v1/automation/settings")
async def automation_settings_set(request: Request):
    """Set approval mode (auto/semi/manual). Token-gated."""
    body = await request.json()
    from saathi.production_automation.pipeline import default_store
    return {"ok": default_store().set_approval_mode(body.get("approval_mode", ""))}


@app.get("/api/v1/skills")
async def skills_list(q: str = "", director: str = "", category: str = ""):
    """Skill Library — reusable skills any Director can find/call. Whitelisted read."""
    from saathi.skills_library.store import default_store
    st = default_store()
    items = st.search(q, director=director, category=category) if (q or director or category) else st.list()
    return {"skills": items, "categories": st.categories()}


@app.get("/api/v1/skills/{slug}")
async def skill_get(slug: str):
    """One skill (latest version) by slug. Whitelisted read."""
    from saathi.skills_library.store import default_store
    s = default_store().get_by_slug(slug)
    return {"skill": s} if s else {"error": "skill not found"}


@app.post("/api/v1/skills")
async def skill_register(request: Request):
    """Register a new skill version (name/owner_director/inputs/outputs/prompt_template…). Token-gated."""
    body = await request.json()
    from saathi.skills_library.store import default_store
    if not body.get("slug") or not body.get("name"):
        return {"ok": False, "error": "slug and name required"}
    s = default_store().register(**{k: v for k, v in body.items() if k in (
        "slug", "name", "owner_director", "category", "description", "inputs", "outputs",
        "prompt_template", "examples", "tools", "evaluation", "related_directors", "trust")})
    return {"ok": True, "skill": s}


@app.get("/api/v1/knowledge/library/consult")
async def knowledge_consult(q: str = "", director: str = "", limit: int = 5):
    """Manual retrieval — a Director deliberately consults the Library (records influence).
    This is the toggle path before automatic retrieval is enabled. Whitelisted read."""
    from saathi.knowledge_library.store import default_store
    return {"sources": default_store().consult(q, director=director, limit=min(limit, 20))}


@app.get("/api/v1/knowledge/queue")
async def knowledge_queue(status: str = ""):
    """Reading Queue — the AI-engineering curriculum backlog. Whitelisted read."""
    from saathi.knowledge_library.queue import default_store
    return {"queue": default_store().list(status=status or None if status else "")}


@app.post("/api/v1/knowledge/queue")
async def knowledge_queue_add(request: Request):
    """Add a source to the reading backlog. Token-gated."""
    body = await request.json()
    from saathi.knowledge_library.queue import default_store
    if not body.get("title"):
        return {"ok": False, "error": "title required"}
    q = default_store().add(body["title"], url=body.get("url", ""), category=body.get("category", ""),
                            priority=int(body.get("priority", 3)), status=body.get("status", "pending"))
    return {"ok": True, "item": q}


@app.post("/api/v1/knowledge/library/{sid}/rate")
async def knowledge_rate(sid: str, request: Request):
    """Rate a source's usefulness for a Director, set trust, or advance its lifecycle status. Token-gated."""
    body = await request.json()
    from saathi.knowledge_library.store import default_store
    st = default_store()
    done = {}
    if body.get("director") and body.get("stars") is not None:
        done["rated"] = st.rate_director(sid, body["director"], int(body["stars"]))
    if body.get("trust") is not None:
        done["trust"] = st.set_trust(sid, int(body["trust"]))
    if body.get("status"):
        done["status"] = st.set_status(sid, body["status"])
    return {"ok": any(done.values()), **done, "source": st.get(sid)}


@app.post("/api/v1/knowledge/library/import")
async def knowledge_library_import(request: Request):
    """Knowledge Importer — ingest a GitHub repo (reads its real README). Token-gated."""
    import asyncio
    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return {"ok": False, "error": "url required"}
    from saathi.knowledge_library.importer import import_repo
    res = await asyncio.to_thread(import_repo, url, category=body.get("category", "AI Engineering"))
    # if this url was on the reading backlog, mark it imported
    try:
        from saathi.knowledge_library.queue import default_store as q_store
        qs = q_store()
        for item in qs.list():
            if item["url"] and item["url"].rstrip("/").rstrip(".git") == url.rstrip("/").rstrip(".git"):
                qs.set_status(item["id"], "imported")
    except Exception:
        pass
    return res


@app.post("/api/v1/knowledge/library")
async def knowledge_library_add(request: Request):
    """Manually add a source (book/paper/doc/sop) to the library. Token-gated."""
    body = await request.json()
    from saathi.knowledge_library.store import default_store
    if not body.get("title"):
        return {"ok": False, "error": "title required"}
    src = default_store().add(**{k: v for k, v in body.items() if k in (
        "title", "url", "author", "license", "category", "source_type", "difficulty",
        "summary", "tags", "related_directors", "key_lessons", "quality")})
    return {"ok": True, "source": src}


@app.get("/api/v1/missions")
async def missions_list(status: str = ""):
    """All Missions — the CEO OS dashboard of every business. Whitelisted read."""
    from saathi.missions.store import default_store
    return {"missions": default_store().list(status=status or None)}


@app.get("/api/v1/missions/{mission_id}")
async def mission_detail(mission_id: str):
    """One Mission's Executive Dashboard (identity + KPIs + evidence + learning + events).
    Whitelisted read."""
    import asyncio
    from saathi.missions.store import default_store
    from saathi.missions.overview import overview
    m = default_store().get(mission_id) or default_store().get_by_key(mission_id)
    if not m:
        return {"error": "mission not found", "id": mission_id}
    return await asyncio.to_thread(overview, m)


@app.post("/api/v1/missions")
async def mission_create(request: Request):
    """Create a new Mission (＋ New Mission). Token-gated."""
    body = await request.json()
    from saathi.missions.store import Mission, default_store, TYPES
    key = body.get("key", "").strip()
    name = body.get("name", "").strip()
    if not key or not name:
        return {"ok": False, "error": "key and name required"}
    mtype = body.get("type", "business")
    m = Mission(key=key, name=name, type=mtype if mtype in TYPES else "business",
                department=body.get("department", ""), identity=body.get("identity") or {},
                objectives=body.get("objectives") or [], kpis=body.get("kpis") or {},
                directors=body.get("directors") or [])
    mid = default_store().create_if_absent(m)
    return {"ok": True, "id": mid, "key": key}


@app.post("/api/v1/missions/twin")
async def mission_create_twin(request: Request):
    """＋ New Mission — create a Business Digital Twin: mission + AI research +
    departments + executive briefing + 30-day roadmap + timeline. Token-gated."""
    import asyncio
    body = await request.json()
    from saathi.missions.store import Mission, default_store, TYPES
    from saathi.missions.timeline import default_store as tl_store
    from saathi.missions import twin as twin_mod
    name = (body.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}
    key = (body.get("key") or name.lower().replace(" ", "_"))[:40]
    mtype = body.get("type", "business")
    identity = body.get("identity") or {}
    for f in ("website", "industry", "country", "target_market", "services"):
        if body.get(f):
            identity.setdefault(f, body[f])
    m = Mission(key=key, name=name, type=mtype if mtype in TYPES else "business",
                department=body.get("department", ""), identity=identity,
                objectives=body.get("objectives") or ([body["goals"]] if body.get("goals") else []))
    st = default_store()
    if st.get_by_key(key):
        return {"ok": False, "error": f"mission '{key}' already exists"}
    mid = st.create(m)
    tl_store().record(mid, "created", f"Mission created: {name}", detail=f"type={m.type}")
    md = st.get(mid)
    twin = await asyncio.to_thread(twin_mod.build, md, body)
    return {"ok": True, "id": mid, "key": key, "twin": twin}


@app.post("/api/v1/missions/{mission_id}/intake")
async def mission_intake(mission_id: str, request: Request):
    """Mission Intake — apply a structured onboarding payload into the Knowledge Graph
    (accounts, social stats, revenue, services, customers, goals). Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.intake import apply_intake
    from saathi.missions.timeline import default_store as tl
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    res = apply_intake(m["id"], body)
    tl().record(m["id"], "connected", "Intake applied",
                detail=f"{res['nodes_added']} nodes · coverage {int(res['coverage']*100)}%")
    return {"ok": True, **res}


@app.post("/api/v1/missions/{mission_id}/document")
async def mission_document(mission_id: str, request: Request):
    """Paste a document — extract prices/emails/phones into the Knowledge Graph. Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.intake import extract_document
    from saathi.missions.timeline import default_store as tl
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    res = extract_document(m["id"], body.get("text", ""), title=body.get("title", ""))
    tl().record(m["id"], "connected", f"Document extracted: {body.get('title', 'untitled')}",
                detail=f"{res['nodes_added']} nodes")
    return {"ok": True, **res}


@app.get("/api/v1/missions/{mission_id}/brand")
async def mission_brand(mission_id: str):
    """Brand Identity + Voice Registry for a Mission (voice = reusable asset). Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.brand import default_store as b_store, default_brand, SAMPLE_PROMPTS, PURPOSES
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    bs = b_store()
    return {"brand": bs.get_brand(m["id"]) or default_brand(m), "voices": bs.list_voices(m["id"]),
            "active_voice": bs.active_voice(m["id"]), "sample_prompts": SAMPLE_PROMPTS,
            "purposes": list(PURPOSES)}


@app.post("/api/v1/missions/{mission_id}/brand")
async def mission_brand_save(mission_id: str, request: Request):
    """Save brand identity fields (logo/colors/fonts/writing_style/character/guidelines…). Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.brand import default_store as b_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    b_store().save_brand(m["id"], body)
    return {"ok": True, "brand": b_store().get_brand(m["id"])}


@app.post("/api/v1/missions/{mission_id}/voices")
async def mission_voice_register(mission_id: str, request: Request):
    """Register a voice profile version (name + purpose/language/accent/style/emotion/speed/pitch/
    provider/samples). Versioned like the Prompt Registry. Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.brand import default_store as b_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    name = body.get("name", "").strip()
    if not name:
        return {"ok": False, "error": "voice name required"}
    v = b_store().register_voice(m["id"], name, body)
    b_store().set_active_voice(m["id"], v["id"])   # newest becomes active
    try:
        from saathi.missions.timeline import default_store as tl
        tl().record(m["id"], "decision", f"Voice registered: {name} v{v['version']} (active)",
                    detail=f"{v.get('provider', '')} · {v.get('style', '')}")
    except Exception:
        pass
    return {"ok": True, "voice": v}


@app.get("/api/v1/missions/{mission_id}/voice/package")
async def mission_voice_package(mission_id: str, emotion: str = "", objective: str = "", provider: str = ""):
    """Voice Director — active voice + scene emotion + objective → provider-agnostic
    Voice Package (what TTS adapters consume). Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.voice_director import package
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    return {"voice_package": package(m["id"], scene_emotion=emotion, objective=objective,
                                     prefer_provider=provider)}


@app.get("/api/v1/missions/{mission_id}/voice/experiments")
async def mission_voice_experiments(mission_id: str):
    """List voice A/B experiments (voice choice by evidence, not opinion). Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.brand import default_store as b_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    return {"experiments": b_store().experiments(m["id"])}


@app.post("/api/v1/missions/{mission_id}/voice/experiments")
async def mission_voice_experiment_create(mission_id: str, request: Request):
    """Start a voice A/B experiment (episode, voice_a, voice_b, split). Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.brand import default_store as b_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    exp = b_store().create_experiment(m["id"], episode=body.get("episode", ""),
                                      voice_a=body.get("voice_a", ""), voice_b=body.get("voice_b", ""),
                                      split=int(body.get("split", 50)))
    return {"ok": True, "experiment": exp}


@app.post("/api/v1/missions/{mission_id}/voice/experiments/{eid}/result")
async def mission_voice_experiment_result(mission_id: str, eid: str, request: Request):
    """Record the winning voice + metrics; a Learning-Director-style recommendation can act on it. Token-gated."""
    body = await request.json()
    from saathi.missions.brand import default_store as b_store
    ok = b_store().resolve_experiment(eid, body.get("winner", ""), body.get("metrics") or {})
    return {"ok": ok}


@app.post("/api/v1/missions/{mission_id}/voices/{voice_id}/activate")
async def mission_voice_activate(mission_id: str, voice_id: str):
    """Set a voice as the Mission's active voice (what Directors read). Token-gated."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.brand import default_store as b_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    return {"ok": b_store().set_active_voice(m["id"], voice_id)}


@app.get("/api/v1/missions/{mission_id}/workflows")
async def mission_workflows(mission_id: str):
    """Workflows + tasks for a Mission (Director → Workflow → Task). Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.workflow import default_store as wf_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    ws = wf_store()
    return {"workflows": ws.list(m["id"]), "templates": list(__import__(
        "saathi.missions.workflow", fromlist=["TEMPLATES"]).TEMPLATES.keys())}


@app.post("/api/v1/missions/{mission_id}/workflows")
async def mission_workflow_create(mission_id: str, request: Request):
    """Create a workflow from a template/director. Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.workflow import default_store as wf_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    wf = wf_store().create(m["id"], director=body.get("director", ""),
                           department=body.get("department", ""), template=body.get("template", ""),
                           name=body.get("name", ""))
    return {"ok": True, "workflow": wf}


@app.post("/api/v1/missions/{mission_id}/tasks/{task_id}")
async def mission_task_update(mission_id: str, task_id: str, request: Request):
    """Update a task status (todo/doing/done/blocked). Token-gated."""
    body = await request.json()
    from saathi.missions.workflow import default_store as wf_store
    ok = wf_store().set_task(task_id, body.get("status", ""))
    return {"ok": ok, "task_id": task_id, "status": body.get("status", "")}


@app.get("/api/v1/missions/{mission_id}/health")
async def mission_health_get(mission_id: str):
    """Mission Health — per-function scores (where the business is weak). Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.health import mission_health
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    return mission_health(m)


@app.get("/api/v1/missions/{mission_id}/knowledge")
async def mission_knowledge(mission_id: str, type: str = ""):
    """Mission Knowledge Graph — nodes + coverage (the business memory). Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.knowledge import default_graph
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    g = default_graph()
    return {"nodes": g.nodes(m["id"], node_type=type or None), "coverage": g.coverage(m["id"]),
            "counts": g.counts(m["id"])}


@app.post("/api/v1/missions/{mission_id}/knowledge")
async def mission_knowledge_write(mission_id: str, request: Request):
    """Write a node into the Business Memory — used by connectors, uploads, and
    Directors. Body: {type, key, label?, data?, source?}. Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store as m_store
    from saathi.missions.knowledge import default_graph
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    ntype = body.get("type", "")
    key = body.get("key", "")
    if not ntype or not key:
        return {"ok": False, "error": "type and key required"}
    nid = default_graph().upsert(m["id"], ntype, key, label=body.get("label", ""),
                                 data=body.get("data") or {}, source=body.get("source", "api"))
    return {"ok": True, "id": nid, "coverage": default_graph().coverage(m["id"])["overall"]}


@app.post("/api/v1/missions/{mission_id}/reference")
async def mission_reference(mission_id: str, request: Request):
    """Reference Intelligence — analyse N references of any kind (website/video/social/
    github/…), extract patterns → Knowledge Graph + Research Library, generate an
    original Mission-branded design system. Token-gated."""
    import asyncio
    body = await request.json()
    urls = body.get("urls") or ([body["url"]] if body.get("url") else [])
    if not urls:
        return {"ok": False, "error": "urls required"}
    from saathi.missions.reference import analyze_many
    rep = await asyncio.to_thread(analyze_many, urls, mission_key=mission_id,
                                  generate=bool(body.get("generate", True)))
    return {"ok": True, **rep}


@app.post("/api/v1/missions/{mission_id}/website")
async def mission_website(mission_id: str, request: Request):
    """Website Intelligence & Design Director — analyse a site (+ optional client site),
    generate an original Mission-branded design system + blueprint, store in the graph.
    Token-gated."""
    import asyncio
    body = await request.json()
    url = (body.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url required"}
    from saathi.missions.website import intelligence
    rep = await asyncio.to_thread(intelligence, mission_id, url, compare_url=body.get("compare_url", ""))
    return {"ok": True, **rep}


@app.post("/api/v1/missions/{mission_id}/proposal")
async def mission_proposal_generate(mission_id: str):
    """Proposal Director — build the full Proposal Package from the Mission twin.
    Token-gated (creates a client artifact)."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.twin import default_store as twin_store
    from saathi.missions.proposal import build, default_store as p_store
    from saathi.missions.timeline import default_store as tl_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    twin = twin_store().get(m["id"])
    if not twin:
        return {"ok": False, "error": "no digital twin yet — create the mission twin first"}
    pkg = build(m, twin)
    p_store().save(pkg)
    tl_store().record(m["id"], "proposal", "Proposal package generated",
                      detail=f"{len(pkg['sections']['recommended_services'])} services · "
                             f"{pkg['sections']['pricing']['currency']} pricing")
    return {"ok": True, "proposal": pkg}


@app.get("/api/v1/missions/{mission_id}/proposal")
async def mission_proposal_get(mission_id: str):
    """Latest Proposal Package for a Mission. Whitelisted read."""
    from saathi.missions.store import default_store as m_store
    from saathi.missions.proposal import default_store as p_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    return {"proposal": p_store().latest(m["id"])}


@app.post("/api/v1/missions/{mission_id}/proposal/decide")
async def mission_proposal_decide(mission_id: str, request: Request):
    """Client/CEO accepts or rejects the proposal. On accept the Mission moves into
    execution (status=active) and the lifecycle milestone is recorded. Token-gated."""
    body = await request.json()
    accept = bool(body.get("accept", False))
    from saathi.missions.store import default_store as m_store
    from saathi.missions.proposal import default_store as p_store
    from saathi.missions.timeline import default_store as tl_store
    ms = m_store()
    m = ms.get(mission_id) or ms.get_by_key(mission_id)
    if not m:
        return {"ok": False, "error": "mission not found"}
    pkg = p_store().latest(m["id"])
    if not pkg:
        return {"ok": False, "error": "no proposal to decide on"}
    p_store().set_status(pkg["id"], "accepted" if accept else "rejected")
    if accept:
        ms.update(m["id"], {"status": "active"})
        tl_store().record(m["id"], "decision", "Proposal accepted — moving to execution",
                          detail="Mission status → active")
        tl_store().record(m["id"], "launch", "Execution started")
        # stand up the department workflows for this business type
        try:
            from saathi.missions.workflow import provision_execution, default_store as wf_store
            from saathi.missions.twin import default_store as twin_store
            tw = twin_store().get(m["id"]) or {}
            wfs = provision_execution(m["id"], tw.get("template", "generic"), store=wf_store())
            tl_store().record(m["id"], "note", f"{len(wfs)} department workflows provisioned",
                              detail=", ".join(w["name"] for w in wfs))
        except Exception:
            pass
    else:
        tl_store().record(m["id"], "decision", "Proposal rejected")
    return {"ok": True, "status": "accepted" if accept else "rejected"}


@app.get("/api/v1/missions/{mission_id}/timeline")
async def mission_timeline(mission_id: str, kind: str = "", limit: int = 100):
    """A Mission's append-only history (the business record). Whitelisted read."""
    from saathi.missions.store import default_store
    from saathi.missions.timeline import default_store as tl_store
    m = default_store().get(mission_id) or default_store().get_by_key(mission_id)
    if not m:
        return {"error": "mission not found"}
    return {"timeline": tl_store().list(m["id"], kind=kind or None, limit=min(limit, 500))}


@app.patch("/api/v1/missions/{mission_id}")
async def mission_update(mission_id: str, request: Request):
    """Update a Mission's identity/objectives/KPIs/status. Token-gated."""
    body = await request.json()
    from saathi.missions.store import default_store
    ok = default_store().update(mission_id, body)
    return {"ok": ok, "id": mission_id}


@app.post("/api/v1/events")
async def events_emit(request: Request):
    """Any product emits ONE event; the bus persists it and routes it into Evidence.
    Products know nothing about Evidence/Learning. Token-gated."""
    body = await request.json()
    etype = body.get("type", "")
    source = body.get("source", "")
    if not etype or not source:
        return {"ok": False, "error": "type and source required"}
    from saathi.events.bus import default_bus
    res = default_bus().emit(etype, source, body.get("payload") or {},
                             project=body.get("project", ""), subject=body.get("subject", ""))
    return {"ok": True, **res}


@app.get("/api/v1/events")
async def events_query(type: str = "", source: str = "", limit: int = 50):
    """Recent events (filter by type glob / source). Whitelisted read."""
    from saathi.events.bus import default_bus
    return {"events": default_bus().query(type=type or None, source=source or None, limit=min(limit, 200))}


@app.get("/api/v1/events/stats")
async def events_stats(days: int = 30):
    """Event volume by type + source, and the routing table. Whitelisted read."""
    import time as _t
    from saathi.events.bus import default_bus
    from saathi.events.routes import ROUTES
    since = _t.time() - days * 86400
    return {"stats": default_bus().stats(since=since), "total": default_bus().count(),
            "routes": [{"pattern": p, "department": d} for p, d in ROUTES]}


@app.get("/api/v1/learning/analyze")
async def learning_analyze():
    """Run all three Learning Directors over the Evidence Store → pending recommendations.
    Recommends only; never edits. Whitelisted read."""
    import asyncio
    from saathi.learning.directors import analyze_all
    return await asyncio.to_thread(analyze_all, persist=True)


@app.get("/api/v1/learning/recommendations")
async def learning_recommendations(category: str = "", status: str = "", limit: int = 50):
    """List recommendations (searchable by category/status). Whitelisted read."""
    from saathi.learning.recommendation import default_store
    st = default_store()
    return {"recommendations": st.list(category=category or None, status=status or None,
                                       limit=min(limit, 200)), "counts": st.counts()}


@app.post("/api/v1/learning/decide")
async def learning_decide(request: Request):
    """CEO accepts/rejects a recommendation. Nothing changes automatically — acceptance only
    records the decision (and the prompt version it will ship in). Token-gated."""
    body = await request.json()
    rec_id = body.get("id", "")
    accept = bool(body.get("accept", False))
    implemented_in = body.get("implemented_in", "")
    from saathi.learning.recommendation import default_store
    ok = default_store().decide(rec_id, accept, implemented_in=implemented_in)
    return {"ok": ok, "id": rec_id, "status": "accepted" if accept else "rejected"}


@app.get("/api/v1/evidence")
async def evidence_query(department: str = "", project: str = "", episode: str = "", limit: int = 50):
    """Evidence Service — query the company's shared memory. Whitelisted read."""
    from saathi.evidence.store import default_store
    st = default_store()
    return {"evidence": st.query(department=department or None, project=project or None,
                                 episode=episode or None, limit=min(limit, 200))}


@app.get("/api/v1/evidence/stats")
async def evidence_stats(days: int = 30):
    """CEO roll-up across all departments + latest AI Studio episodes. Whitelisted."""
    import time as _t
    from saathi.evidence.store import default_store
    st = default_store()
    since = _t.time() - days * 86400
    return {"stats": st.stats(since=since), "total": st.count(),
            "studio_episodes": st.episodes("ai_studio", limit=15)}


@app.post("/api/v1/evidence/record")
async def evidence_record(request: Request):
    """Any department feeds a native event; its adapter normalises + persists. Token-gated."""
    body = await request.json()
    dept = body.get("department", "")
    event = body.get("event", {})
    from saathi.evidence.adapters import ingest, ADAPTERS
    if dept not in ADAPTERS:
        return {"ok": False, "error": f"no adapter for '{dept}'", "adapters": sorted(ADAPTERS)}
    ids = ingest(dept, event)
    return {"ok": True, "recorded": len(ids), "ids": ids}


@app.get("/api/v1/studio/control-room")
async def studio_control_room():
    """AI Studio OS — the CEO Control Room report (full factory in one read). Whitelisted."""
    import asyncio
    from saathi.studio_control_room import report
    return await asyncio.to_thread(report)


@app.get("/api/v1/studio/storyboard")
async def studio_storyboard():
    """Visual Department — today's plan → script → Scene Package. Whitelisted."""
    import asyncio
    from saathi.studio import plan_today
    from saathi.script_director import build_brief, write_script
    from saathi.studio_visual import scene_package
    plan = plan_today().as_dict()
    doc = await asyncio.to_thread(write_script, build_brief(plan))
    pkg = await asyncio.to_thread(scene_package, doc.as_dict())
    return {"plan": {"day": plan["day"], "episode": plan["episode"], "topic": plan["topic"]}, "scene_package": pkg}


@app.get("/api/v1/directors/registry")
async def directors_registry(capability: str = "", quality: str = "balanced", cost: str = "any"):
    """Director Registry — capability→best director (provider-agnostic). Whitelisted."""
    from saathi.production.director_registry import default_registry
    reg = default_registry()
    if not capability:
        return {"capabilities": reg.capabilities(), "directors": reg.catalog()}
    best = reg.best(capability, quality=quality, cost=cost)
    return {"capability": capability, "best": best.info() if best else None,
            "chain": [s.info() for s in reg.route(capability, quality=quality, cost=cost)]}


@app.get("/api/v1/studio/script")
async def studio_script():
    """Script Director — today's plan → structured episode document. Whitelisted."""
    import asyncio
    from saathi.studio import plan_today
    from saathi.script_director import build_brief, write_script
    plan = plan_today().as_dict()
    brief = build_brief(plan)
    doc = await asyncio.to_thread(write_script, brief)
    return {"brief": brief, "script": doc.as_dict()}


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


@app.get("/api/v1/directors")
async def directors_list():
    """Director Library — imported agency Directors (slug/name/description). Whitelisted."""
    from saathi.production.director_library import list_directors
    return {"directors": list_directors()}


@app.post("/api/v1/directors/{slug}/run")
async def director_run(slug: str, request: Request):
    """Run a Director on a task via the Model Router. Token/local-gated."""
    import asyncio
    body = await request.json()
    from saathi.production.director_library import run
    task = (body or {}).get("task", "")
    if not task:
        return {"ok": False, "error": "task required"}
    ctx = {k: v for k, v in (body or {}).items() if k != "task"}
    return await asyncio.to_thread(run, slug, task, **ctx)


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


@app.get("/api/v1/code-memory/status")
async def code_memory_status():
    """Code Memory (codebase-memory-mcp) connector status + indexed projects."""
    import asyncio
    from saathi.infrastructure.connectors.drivers.code_memory import CodeMemoryConnector
    c = CodeMemoryConnector()
    h = c.health()
    installed = h.status.value == "ok"
    out = {"installed": installed, "detail": h.detail,
           "binary": h.metrics.get("binary", ""), "projects": [], "count": 0}
    if installed:
        try:
            res = await asyncio.to_thread(c.execute, "list_projects")
            projs = res.get("projects", []) if isinstance(res, dict) else []
            out["projects"] = projs
            out["count"] = len(projs)
        except Exception as e:
            out["detail"] = f"query failed: {str(e)[:80]}"
    return out


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
        # no-transform: the :3100 Next rewrite proxy otherwise gzip-compresses
        # (and so buffers) this stream — browsers received nothing live.
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive",
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

try:
    from .repair.api import router as repair_router
    app.include_router(repair_router)
except Exception as _e:
    print(f"[saathi] repair router unavailable: {_e}")

try:
    from .chat.api import router as chat_router
    app.include_router(chat_router)
except Exception as _e:
    print(f"[saathi] chat router unavailable: {_e}")

try:
    from .memory.api import router as memory_router
    app.include_router(memory_router)
except Exception as _e:
    print(f"[saathi] memory router unavailable: {_e}")

try:
    from .agent_runtime.api import router as agents_router
    app.include_router(agents_router)
except Exception as _e:
    print(f"[saathi] agent-runtime router unavailable: {_e}")

try:
    from .voice_os.api import router as voice_router
    app.include_router(voice_router)
except Exception as _e:
    print(f"[saathi] voice-os router unavailable: {_e}")

try:
    from .studio_os.api import router as studio_os_router
    app.include_router(studio_os_router)
except Exception as _e:
    print(f"[saathi] studio-os router unavailable: {_e}")

try:
    from .ceo.api import router as ceo_router
    app.include_router(ceo_router)
except Exception as _e:
    print(f"[saathi] ceo router unavailable: {_e}")

try:
    from .connectors.platform.api import router as connectors_platform_router
    app.include_router(connectors_platform_router)
except Exception as _e:
    print(f"[saathi] connectors-platform router unavailable: {_e}")

# M15.2 red-team report API — read-only, authenticated, disabled in production.
try:
    import os as _os2
    if _os2.getenv("SAATHI_ENV", "local").lower() != "production":
        from .security.redteam.api import router as redteam_router
        app.include_router(redteam_router)
except Exception as _e:
    print(f"[saathi] redteam router unavailable: {_e}")

# M16 Control Center — read-only aggregation API (authenticated).
try:
    from .control_center.api import router as control_center_router
    app.include_router(control_center_router)
except Exception as _e:
    print(f"[saathi] control-center router unavailable: {_e}")

# M50 Platform foundation — identity, RBAC, approvals, tenancy (on M49 runtime).
try:
    from .platform.api import router as platform_m50_router
    app.include_router(platform_m50_router)
except Exception as _e:
    print(f"[saathi] platform-m50 router unavailable: {_e}")

# AI Company — visual organization layer over existing runtimes (authenticated,
# read-mostly; missions run deterministic read-only probes, no execution authority).
try:
    from .organization.api import router as organization_router
    app.include_router(organization_router)
except Exception as _e:
    print(f"[saathi] organization router unavailable: {_e}")

# Simple access key for remote/tunnel use. Local requests (the Mac itself)
# are always allowed; remote requests must send X-Saathi-Token.
import os as _os
import hashlib as _hashlib
import secrets as _secrets

ACCESS_TOKEN = _os.getenv("SAATHI_TOKEN", "")
_SERVER_START = time.time()
_RAW_PASSWORD = _os.getenv("BAADAR_PASSWORD", "")
# Support both legacy bare-sha256 and new PBKDF2 hashes.
# BAADAR_PASSWORD_HASH takes precedence; if absent, derive from BAADAR_PASSWORD.
_PASSWORD_HASH = _os.getenv("BAADAR_PASSWORD_HASH", "")
if not _PASSWORD_HASH and _RAW_PASSWORD:
    _PASSWORD_HASH = _hashlib.sha256(_RAW_PASSWORD.encode()).hexdigest()


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
    """Authorize via session cookie, session header, SAATHI_TOKEN, or Token Registry."""
    # a valid session cookie/header (issued by /auth/login) is always accepted
    cookies = getattr(request, "cookies", None) or {}
    token = (cookies.get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    if token:
        # A session-store failure (e.g. SQLite lock) must not turn auth into a 500;
        # the deterministic stateless token check below still authorizes.
        try:
            from saathi import sessions
            if sessions.validate(token):
                return True
        except Exception:
            pass
        if token == _session_token():
            return True
    # Token Registry: named, permissioned API tokens
    raw_api_token = request.headers.get("x-saathi-token", "")
    if raw_api_token:
        # Legacy SAATHI_TOKEN backward compat FIRST — cheap, no DB, so a valid
        # service token authorizes even if the registry store is momentarily
        # unavailable (e.g. SQLite lock contention).
        if ACCESS_TOKEN and raw_api_token == ACCESS_TOKEN:
            return True
        # Named, permissioned API tokens. A registry/store failure must never turn
        # an auth check into a 500 — treat it as "not authorized via this path" and
        # fall through to the final decision.
        try:
            from saathi.security.registry import get_registry
            rec = get_registry().verify(raw_api_token)
            if rec:
                return True
        except Exception:
            pass
    # no password configured → trust genuine local callers
    if not _PASSWORD_HASH:
        return _is_local(request)
    return False


_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

def _csrf_ok(request) -> bool:
    """CSRF defense for BROWSER cookie-auth mutations (defense-in-depth atop
    SameSite=Lax). Same-origin Origin required on unsafe methods when the request
    carries the session cookie. Non-browser callers are unaffected: service-token
    (x-saathi-token) and header-only (x-baadar-session, no cookie) requests bypass,
    as they carry no ambient-cookie CSRF surface. Absent Origin is allowed because
    SameSite=Lax already blocks cross-site cookie POSTs."""
    if request.method in _CSRF_SAFE_METHODS:
        return True
    if request.headers.get("x-saathi-token"):
        return True
    cookies = getattr(request, "cookies", None) or {}
    if not cookies.get(_COOKIE_NAME):
        return True
    origin = request.headers.get("origin")
    if not origin:
        return True
    from urllib.parse import urlparse
    o = urlparse(origin).netloc.lower()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").lower()
    return bool(o) and o == host


def _owner_id() -> str:
    """Return the owner user_id from the Security Store."""
    from saathi.security.store import get_store
    return get_store().get_or_create_owner()


@app.middleware("http")
async def _auth(request, call_next):
    from fastapi.responses import JSONResponse
    path = request.url.path
    # Always allow: login endpoint, OAuth callbacks, static assets, and
    # endpoints that enforce their own bearer auth (BAADAR_API_KEY).
    #
    # There is no `OPTIONS` bypass here. CORSMiddleware is the outermost layer
    # (see `_install_outermost_cors()`), so a browser preflight is answered
    # before it ever reaches this gate. An `OPTIONS` request that is not a
    # preflight is an ordinary request and is authenticated like any other.
    if (path == "/api/v1/auth/login"
            or path == "/api/v1/auth/change-password"
            or path == "/api/v1/auth/logout"
            # Session validity probe — must be reachable WITHOUT auth so the
            # frontend can detect a stale/absent token cleanly (returns
            # {authenticated:false}, never a 401, never token material). Exact
            # match only: the plural /api/v1/auth/sessions* stays gated.
            or path == "/api/v1/auth/session"
            or path == "/api/v1/auth/forgot"
            or path.startswith("/api/v1/auth/reset")
            or path.startswith("/api/v1/auth/passkey")
            or path == "/api/v1/auth/providers"
            or path.startswith("/api/v1/auth/oauth")
            or path == "/api/executive/briefing"
            or path == "/api/v1/ceo/home"
            or path == "/api/v1/ceo/os"
            or path == "/api/v1/infrastructure/health"
            or path == "/api/v1/platform/maturity"
            # M50 platform foundation enforces its own session token (X-Platform-Token).
            or path.startswith("/api/v1/platform/")
            or path == "/api/v1/studio/queue"
            or path == "/api/v1/studio/plan"
            or path == "/api/v1/studio/script"
            or path == "/api/v1/studio/storyboard"
            or path == "/api/v1/studio/render-plan"
            or path == "/api/v1/studio/publish-plan"
            or path == "/api/v1/studio/control-room"
            or path == "/api/v1/evidence"
            or path == "/api/v1/evidence/stats"
            or path == "/api/v1/learning/analyze"
            or path == "/api/v1/learning/recommendations"
            or path == "/api/v1/events/stats"
            or (request.method == "GET" and (
                path == "/api/v1/events"
                or path == "/api/v1/missions"
                or path == "/api/v1/knowledge/library"
                or path == "/api/v1/connectors/providers"
                or path == "/api/v1/connectors/accounts"
                or path == "/api/v1/knowledge/library/consult"
                or path == "/api/v1/knowledge/queue"
                or path == "/api/v1/skills"
                or path.startswith("/api/v1/skills/")
                or path == "/api/v1/automation/credits"
                or path == "/api/v1/automation/plan"
                or path == "/api/v1/automation/settings"
                or path.startswith("/api/v1/missions/")))
            or path == "/api/v1/studio/produce"
            or path == "/api/v1/directors/registry"
            or path == "/api/v1/mission"
            or path == "/api/v1/mission/complete"
            or path == "/api/v1/agent/chat"
            or path == "/api/v1/workspace"
            # Voice auth policy (deliberate, not accidental): only the two
            # stateless, ephemeral endpoints used by the always-on mic are
            # exempt — /voice/command and /voice/transcribe. Everything else
            # under /api/v1/voice/* stays gated: /voice/enroll writes a
            # biometric voiceprint, and the voice_os router (/voice/sessions,
            # /turns, /preferences, …) carries conversation + authority state.
            # The frontend already authenticates those via afetch()
            # (lib/api.js enrollVoice, components/chat/VoiceControl.jsx), so do
            # NOT add them here — that would drop auth on sensitive operations.
            or path == "/api/v1/voice/command"
            or path == "/api/v1/code-memory/status"
            or path == "/api/v1/lab/prompts"
            or path.startswith("/api/v1/lab/prompts/")
            or path == "/api/v1/directors"
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
    if not _csrf_ok(request):
        return JSONResponse({"error": "bad origin"}, status_code=403)
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return await call_next(request)

class LoginIn(BaseModel):
    password: str
    remember_me: bool = True


# ── First-party HttpOnly session cookie (M — cookie-auth) ────────────────────
# Env-aware attributes: Secure only over HTTPS (so the cookie actually works on
# plain-http localhost:3100), SameSite=Lax (single-origin — Lax lets top-level
# navigations carry it while blocking cross-site POST cookies for CSRF defense),
# host-only (no Domain), Path=/. HttpOnly always — browser JS never reads it.
_COOKIE_NAME = "baadar_session"

def _req_https(request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto:
        return proto == "https"
    return (getattr(request.url, "scheme", "") or "").lower() == "https"

def _set_session_cookie(resp, request, token: str, max_age: int) -> None:
    resp.set_cookie(_COOKIE_NAME, token, httponly=True, samesite="lax",
                    secure=_req_https(request), max_age=max_age, path="/")

def _clear_session_cookie(resp, request) -> None:
    resp.delete_cookie(_COOKIE_NAME, samesite="lax", secure=_req_https(request), path="/")


@app.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request):
    from fastapi.responses import JSONResponse
    from saathi import sessions, authsec
    from saathi.security.store import get_store
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    # rate-limit brute-force attempts
    allowed, retry_after = authsec.rate_check(f"{ip}:login", limit=5, window=300)
    if not allowed:
        authsec.audit("login", ok=False, ip=ip, ua=ua, detail="rate_limited")
        return JSONResponse({"ok": False, "error": f"Too many attempts. Try again in {retry_after}s."}, status_code=429)
    # Accept the canonical owner's stored credential through the security-store
    # abstraction, while preserving legacy environment fallback credentials.
    store = get_store()
    has_stored_password = store.active_owner_has_password()
    stored_owner_ok = store.verify_active_owner_password(body.password)
    ok = (stored_owner_ok or
          (_PASSWORD_HASH and authsec.verify_password(body.password, _PASSWORD_HASH)) or
          (ACCESS_TOKEN and body.password == ACCESS_TOKEN))
    if not ok:
        if not (_PASSWORD_HASH or ACCESS_TOKEN or has_stored_password):
            ok = True  # nothing configured — let the owner in
        else:
            authsec.rate_hit(f"{ip}:login")
            authsec.audit("login", ok=False, ip=ip, ua=ua, detail="wrong_password")
            return JSONResponse({"ok": False, "error": "Wrong password"}, status_code=401)
    # Compute risk score
    from saathi.security.risk import RiskEngine
    from saathi import sessions
    browser, os_name = sessions.describe(ua)
    device_name = ("iPhone" if "iPhone" in ua else
                   "iPad" if "iPad" in ua else
                   "Mac" if "Mac OS X" in ua or "Macintosh" in ua else
                   "Android" if "Android" in ua else
                   "Windows" if "Windows" in ua else
                   "Linux" if "Linux" in ua else "Unknown")
    risk = RiskEngine()
    risk_score = risk.score(_owner_id(), browser=browser, ip=ip,
                            device_name=device_name, failed_attempts=0)
    token = sessions.create(ua=ua, ip=ip, kind="password", remember_me=body.remember_me)
    sid = sessions.session_id(token)
    # Opportunistic lifecycle hygiene: drain expired + revoked rows on each
    # login so the session table stays bounded without a background job.
    try:
        _p = sessions.prune()
        _LAST_PRUNE.update({"at": time.time(), **_p})
    except Exception:
        pass
    # Bounded concurrency: keep the newest N active sessions (LRU eviction),
    # never the one just minted. Prevents hundreds of live owner sessions.
    try:
        _evicted = sessions.enforce_cap_if_migrated(keep_token=token)
        if _evicted:
            authsec.audit("session_cap_evict", ok=True, ip=ip, ua=ua, detail=f"evicted_{_evicted}")
    except Exception:
        pass
    authsec.audit("login", ok=True, ip=ip, ua=ua, detail=f"session_{sid}")
    # Record security event
    from saathi.security.timeline import get_timeline
    get_timeline().record(_owner_id(), "login_success",
        title="Signed in with password",
        detail=f"{browser} on {device_name}",
        meta={"browser": browser, "os": os_name, "ip": ip, "risk_score": risk_score},
        ip=ip, ua=ua)
    r = JSONResponse({"ok": True, "token": token, "risk_score": risk_score})
    max_age = (30*24*3600) if body.remember_me else (24*3600)
    _set_session_cookie(r, request, token, max_age)
    return r

def _rp(request) -> tuple[str, str]:
    """Derive WebAuthn RP id (host, no port) + origin (scheme://host[:port]) from the request."""
    host = (request.headers.get("host") or request.url.netloc or "localhost")
    rp_id = host.split(":")[0]
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    return rp_id, f"{scheme}://{host}"


@app.get("/api/v1/auth/passkey/status")
def passkey_status(request: Request):
    """Auth setup status: is a password set, is a passkey registered, am I signed in. Whitelisted."""
    from saathi import passkey
    from saathi.security.store import get_store
    rp_id, _ = _rp(request)
    return {"has_passkey": passkey.has_passkey(rp_id), "rp_id": rp_id,
            "has_password": bool(_PASSWORD_HASH) or get_store().active_owner_has_password(),
            "signed_in": _is_authed(request) or _is_local(request)}


@app.post("/api/v1/auth/passkey/register/options")
async def passkey_register_options(request: Request):
    """Begin passkey registration (Touch ID / Face ID). Must already be signed in."""
    if not (_is_authed(request) or _is_local(request)):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "sign in first"}, status_code=401)
    from saathi import passkey
    rp_id, _ = _rp(request)
    return passkey.registration_options(rp_id)


@app.post("/api/v1/auth/passkey/register/verify")
async def passkey_register_verify(request: Request):
    """Finish passkey registration — stores the credential. Must be signed in."""
    if not (_is_authed(request) or _is_local(request)):
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False, "error": "sign in first"}, status_code=401)
    from saathi import passkey
    rp_id, origin = _rp(request)
    body = await request.json()
    ua = request.headers.get("user-agent", "")
    try:
        ok = passkey.verify_registration(body.get("credential") or body, rp_id, origin, ua)
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
    return {"ok": ok}


@app.post("/api/v1/auth/passkey/login/options")
async def passkey_login_options(request: Request):
    """Begin biometric unlock (unauthenticated — that's the point). Whitelisted."""
    from saathi import passkey
    rp_id, _ = _rp(request)
    return passkey.authentication_options(rp_id)


@app.post("/api/v1/auth/passkey/login/verify")
async def passkey_login_verify(request: Request):
    """Finish biometric unlock → issue a new random session cookie. Whitelisted."""
    from fastapi.responses import JSONResponse
    from saathi import passkey, sessions, authsec
    rp_id, origin = _rp(request)
    body = await request.json()
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    try:
        ok = passkey.verify_authentication(body.get("credential") or body, rp_id, origin)
    except Exception as e:
        authsec.audit("passkey_login", ok=False, ip=ip, ua=ua, detail=str(e)[:120])
        return JSONResponse({"ok": False, "error": str(e)[:120]}, status_code=400)
    if not ok:
        authsec.audit("passkey_login", ok=False, ip=ip, ua=ua, detail="verification_failed")
        return JSONResponse({"ok": False, "error": "unlock failed"}, status_code=401)
    remember_me = body.get("remember_me", True)
    from saathi.security.risk import RiskEngine
    from saathi import sessions
    browser, os_name = sessions.describe(ua)
    device_name = ("iPhone" if "iPhone" in ua else
                   "iPad" if "iPad" in ua else
                   "Mac" if "Mac OS X" in ua or "Macintosh" in ua else
                   "Android" if "Android" in ua else
                   "Windows" if "Windows" in ua else
                   "Linux" if "Linux" in ua else "Unknown")
    risk = RiskEngine()
    risk_score = risk.score(_owner_id(), browser=browser, ip=ip, device_name=device_name)
    token = sessions.create(ua=ua, ip=ip, kind="passkey", remember_me=remember_me)
    sid = sessions.session_id(token)
    # Same bounded-concurrency hygiene as password login.
    try:
        sessions.prune()
        _evicted = sessions.enforce_cap_if_migrated(keep_token=token)
        if _evicted:
            authsec.audit("session_cap_evict", ok=True, ip=ip, ua=ua, detail=f"evicted_{_evicted}")
    except Exception:
        pass
    authsec.audit("passkey_login", ok=True, ip=ip, ua=ua, detail=f"session_{sid}")
    from saathi.security.timeline import get_timeline
    get_timeline().record(_owner_id(), "login_success",
        title="Signed in with passkey",
        detail=f"{browser} on {device_name}",
        meta={"browser": browser, "os": os_name, "ip": ip, "risk_score": risk_score, "method": "passkey"},
        ip=ip, ua=ua)

    r = JSONResponse({"ok": True, "token": token, "risk_score": risk_score})
    max_age = (30*24*3600) if remember_me else (24*3600)
    _set_session_cookie(r, request, token, max_age)
    return r


class ChangePasswordIn(BaseModel):
    current: str
    new_password: str

@app.post("/api/v1/auth/change-password")
def change_password(body: ChangePasswordIn, request: Request):
    global _PASSWORD_HASH, _RAW_PASSWORD
    import hashlib, re
    from fastapi.responses import JSONResponse
    from saathi import sessions, authsec
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    # rate limit password changes
    allowed, retry_after = authsec.rate_check(f"{ip}:change-password", limit=3, window=600)
    if not allowed:
        authsec.audit("change_password", ok=False, ip=ip, ua=ua, detail="rate_limited")
        return JSONResponse({"ok": False, "error": f"Too many attempts. Try again in {retry_after}s."}, status_code=429)
    if _PASSWORD_HASH and not authsec.verify_password(body.current, _PASSWORD_HASH):
        authsec.audit("change_password", ok=False, ip=ip, ua=ua, detail="wrong_current")
        return JSONResponse({"ok": False, "error": "Current password is wrong"}, status_code=400)
    strength = authsec.password_strength(body.new_password)
    if strength["score"] < 2:
        authsec.audit("change_password", ok=False, ip=ip, ua=ua, detail="weak_password")
        return JSONResponse({"ok": False, "error": "Password too weak. Use 8+ chars with upper, lower, number and symbol."}, status_code=400)
    _RAW_PASSWORD = body.new_password
    _PASSWORD_HASH = authsec.hash_password(body.new_password)
    env_path = config.ROOT / ".env"
    text = env_path.read_text() if env_path.exists() else ""
    if re.search(r'^BAADAR_PASSWORD=', text, flags=re.MULTILINE):
        text = re.sub(r'^BAADAR_PASSWORD=.*$', f'BAADAR_PASSWORD={body.new_password}', text, flags=re.MULTILINE)
    else:
        text = (text.rstrip("\n") + "\n" if text else "") + f'BAADAR_PASSWORD={body.new_password}\n'
    env_path.write_text(text)
    # SECURITY: invalidate all existing sessions, then issue a fresh one
    cookies = getattr(request, "cookies", None) or {}
    old_token = (cookies.get("baadar_session") or request.headers.get("x-baadar-session", ""))
    sessions.revoke_all(except_token=old_token)
    sessions.revoke(sessions.session_id(old_token))
    token = sessions.create(ua=ua, ip=ip, kind="password")
    authsec.audit("change_password", ok=True, ip=ip, ua=ua, detail=f"new_session_{sessions.session_id(token)}")
    from saathi.security.timeline import get_timeline
    from saathi.security.store import get_store
    from saathi import sessions as _sessions
    _browser, _os_name = _sessions.describe(ua)
    get_timeline().record(get_store().get_or_create_owner(), "password_changed",
        title="Password changed",
        detail="From Security settings",
        meta={"browser": _browser, "os": _os_name, "ip": ip},
        ip=ip, ua=ua)
    r = JSONResponse({"ok": True, "token": token})
    _set_session_cookie(r, request, token, 30*24*3600)
    return r

@app.post("/api/v1/auth/logout")
def logout(request: Request):
    from fastapi.responses import JSONResponse
    from saathi import sessions, authsec
    cookies = getattr(request, "cookies", None) or {}
    token = (cookies.get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    if token:
        sessions.revoke(sessions.session_id(token))
    authsec.audit("logout", ok=True, ip=request.client.host if request.client else "", ua=request.headers.get("user-agent", ""))
    from saathi.security.timeline import get_timeline
    from saathi.security.store import get_store
    get_timeline().record(get_store().get_or_create_owner(), "logout",
        title="Signed out", ip=request.client.host if request.client else "",
        ua=request.headers.get("user-agent", ""))
    r = JSONResponse({"ok": True})
    _clear_session_cookie(r, request)
    return r

# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH v1.0 — Session Management, Passkey Management, Forgot Password,
#  Account Security, OAuth Architecture
# ═══════════════════════════════════════════════════════════════════════════════

# ── Phase 3: Session / Device Management ─────────────────────────────────────

@app.get("/api/v1/auth/sessions")
def list_sessions(request: Request):
    """List all active sessions for the owner (device, browser, OS, last seen)."""
    from fastapi.responses import JSONResponse
    from saathi import sessions
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    token = (getattr(request, "cookies", {}).get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    return {"sessions": sessions.listing(current_token=token)}


@app.delete("/api/v1/auth/sessions/{sid}")
def revoke_session(sid: str, request: Request):
    """Revoke a specific session by its public ID (logout that device)."""
    from fastapi.responses import JSONResponse
    from saathi import sessions, authsec
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    ok = sessions.revoke(sid)
    authsec.audit("revoke_session", ok=ok, ip=ip, ua=ua, detail=sid)
    return {"ok": ok}


@app.post("/api/v1/auth/sessions/revoke-all")
def revoke_all_sessions(request: Request):
    """Logout everywhere — invalidate all sessions except the caller's."""
    from fastapi.responses import JSONResponse
    from saathi import sessions, authsec
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    token = (getattr(request, "cookies", {}).get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    count = sessions.revoke_all(except_token=token)
    authsec.audit("revoke_all", ok=True, ip=ip, ua=ua, detail=f"revoked_{count}")
    return {"ok": True, "revoked": count}


@app.post("/api/v1/auth/session/rotate")
def rotate_session(request: Request):
    """Rotate the current session token — invalidate old, mint new."""
    from fastapi.responses import JSONResponse
    from saathi import sessions, authsec
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    token = (getattr(request, "cookies", {}).get("baadar_session")
             or request.headers.get("x-baadar-session", ""))
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    new_token = sessions.rotate(token, ua=ua, ip=ip)
    authsec.audit("rotate_session", ok=True, ip=ip, ua=ua, detail=f"new_{sessions.session_id(new_token)}")
    r = JSONResponse({"ok": True, "token": new_token})
    _set_session_cookie(r, request, new_token, 30*24*3600)
    return r


@app.post("/api/v1/auth/sessions/{sid}/rename")
async def rename_session(sid: str, request: Request):
    """Label a session (e.g., 'Work Mac', 'iPhone')."""
    from fastapi.responses import JSONResponse
    from saathi import sessions
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    label = (body.get("label") or "")[:60]
    return {"ok": sessions.rename(sid, label)}


# ── Session lifecycle & auth recovery (M — session-lifecycle milestone) ──────
def _bearer(request) -> str:
    """The caller's session token from cookie or header (never logged)."""
    cookies = getattr(request, "cookies", None) or {}
    return cookies.get("baadar_session") or request.headers.get("x-baadar-session", "")


# Tracks the last opportunistic/explicit prune result for owner diagnostics.
_LAST_PRUNE: dict = {"at": 0.0, "expired": 0, "revoked": 0}


@app.get("/api/v1/auth/session")
def auth_session(request: Request):
    """Validate the caller's current token and return NON-SECRET session metadata.

    Whitelisted so the frontend can check auth state on startup WITHOUT tripping
    the 401 gate. Returns `{authenticated: bool, session: {...}|null}` — an invalid
    or stale token yields `authenticated: false` (a clean signal), never a 401 and
    never any token material."""
    return _sessions_mod().status(_bearer(request))


def _sessions_mod():
    from saathi import sessions
    return sessions


@app.get("/api/v1/auth/sessions/diagnostics")
def sessions_diagnostics(request: Request):
    """Owner-facing session diagnostics — counts + current session + last prune.

    No raw tokens; `current.id` is a bounded irreversible fingerprint."""
    from fastapi.responses import JSONResponse
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    sessions = _sessions_mod()
    st = sessions.status(_bearer(request))
    return {
        "counts": sessions.counts(),
        "current": st.get("session"),
        "last_prune": dict(_LAST_PRUNE),
    }


@app.post("/api/v1/auth/sessions/prune")
def sessions_prune(request: Request):
    """Owner-triggered hard prune of expired + revoked sessions."""
    from fastapi.responses import JSONResponse
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    sessions = _sessions_mod()
    res = sessions.prune()
    _LAST_PRUNE.update({"at": time.time(), **res})
    from saathi import authsec
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    authsec.audit("session_prune", ok=True, ip=ip, ua=request.headers.get("user-agent", ""),
                  detail=f"expired_{res['expired']}_revoked_{res['revoked']}")
    return {"ok": True, "pruned": res, "counts": sessions.counts()}


@app.post("/api/v1/auth/sessions/revoke-all-including-current")
def revoke_all_including_current(request: Request):
    """Owner emergency: revoke EVERY session including the caller's own, then
    clear the caller's cookie. The caller must sign in again afterwards."""
    from fastapi.responses import JSONResponse
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    sessions = _sessions_mod()
    from saathi import authsec
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    count = sessions.revoke_all_including_current()
    authsec.audit("revoke_all_including_current", ok=True, ip=ip,
                  ua=request.headers.get("user-agent", ""), detail=f"revoked_{count}")
    r = JSONResponse({"ok": True, "revoked": count})
    _clear_session_cookie(r, request)
    return r


# ── Phase 2: Passkey Management ──────────────────────────────────────────────

@app.get("/api/v1/auth/passkeys")
def list_passkeys(request: Request):
    """List all registered passkeys (id, rp_id, creation info — no secrets)."""
    from fastapi.responses import JSONResponse
    from saathi import passkey
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    rp_id, _ = _rp(request)
    creds = passkey._load()
    out = []
    for c in creds:
        if not rp_id or c.get("rp_id") == rp_id:
            out.append({"id": c.get("id", ""), "rp_id": c.get("rp_id", ""),
                        "label": c.get("label", ""), "sign_count": c.get("sign_count", 0)})
    return {"passkeys": out}


@app.delete("/api/v1/auth/passkeys/{pid}")
def delete_passkey(pid: str, request: Request):
    """Remove a passkey credential by its ID."""
    from fastapi.responses import JSONResponse
    from saathi import passkey, authsec
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    creds = passkey._load()
    keep = [c for c in creds if c.get("id") != pid]
    ok = len(keep) != len(creds)
    passkey._save(keep)
    authsec.audit("delete_passkey", ok=ok, ip=ip, ua=ua, detail=pid)
    return {"ok": ok}


@app.patch("/api/v1/auth/passkeys/{pid}")
async def rename_passkey(pid: str, request: Request):
    """Rename a passkey (label)."""
    from fastapi.responses import JSONResponse
    from saathi import passkey, authsec
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    body = await request.json()
    label = (body.get("label") or "")[:60]
    creds = passkey._load()
    hit = next((c for c in creds if c.get("id") == pid), None)
    if not hit:
        return JSONResponse({"ok": False, "error": "passkey not found"}, status_code=404)
    hit["label"] = label
    passkey._save(creds)
    authsec.audit("rename_passkey", ok=True, ip=request.client.host if request.client else "", ua=request.headers.get("user-agent", ""), detail=pid)
    return {"ok": True}


# ── Phase 1: Forgot Password ─────────────────────────────────────────────────
# Reset tokens are stored in ~/.saathi/reset_tokens.json with 15-minute TTL.

_RESET_STORE = Path.home() / ".saathi" / "reset_tokens.json"
_RESET_TTL = 900  # 15 minutes


def _save_reset_tokens(rows: list[dict]) -> None:
    _RESET_STORE.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    _RESET_STORE.write_text(json.dumps([r for r in rows if r.get("expires", 0) > now]))


def _load_reset_tokens() -> list[dict]:
    try:
        now = time.time()
        rows = json.loads(_RESET_STORE.read_text())
        return [r for r in rows if r.get("expires", 0) > now]
    except Exception:
        return []


@app.post("/api/v1/auth/forgot")
async def forgot_password(request: Request):
    """Request a password reset email. Inert if email not configured (outbox.log fallback)."""
    from fastapi.responses import JSONResponse
    from saathi import mailer, authsec
    body = await request.json()
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    # rate limit: 3 requests per 15 min
    allowed, retry_after = authsec.rate_check(f"{ip}:forgot", limit=3, window=900)
    if not allowed:
        return JSONResponse({"ok": False, "error": f"Too many requests. Try again in {retry_after}s."}, status_code=429)
    email = (body.get("email") or "").strip().lower()
    authsec.rate_hit(f"{ip}:forgot")
    # Single-owner: we don't have a user database, so we accept any email attempt
    # and silently succeed to prevent enumeration. In production, this would lookup
    # the user's email. For now, we store the token and email it if SMTP configured.
    token = _secrets.token_urlsafe(32)
    rows = _load_reset_tokens()
    rows.append({"token": token, "email": email, "created": time.time(), "expires": time.time() + _RESET_TTL, "ip": ip, "used": False})
    _save_reset_tokens(rows)
    reset_link = f"{_rp(request)[1]}/reset-password?token={token}"
    subject = "SaathiOS — Reset your password"
    body_text = f"Someone requested a password reset for SaathiOS.\n\nIf this was you, click this link (expires in 15 minutes):\n{reset_link}\n\nIf not, ignore this email."
    result = mailer.send(email, subject, body_text)
    authsec.audit("forgot_password", ok=True, ip=ip, ua=ua, detail=f"email={email} delivered={result.get('delivered')}")
    # Always return success to prevent email enumeration
    return {"ok": True, "message": "If that email is registered, a reset link was sent."}


class ResetIn(BaseModel):
    token: str
    new_password: str


@app.post("/api/v1/auth/reset")
async def reset_password(body: ResetIn, request: Request):
    """Verify a reset token and set a new password."""
    from fastapi.responses import JSONResponse
    from saathi import authsec
    global _PASSWORD_HASH, _RAW_PASSWORD
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    ua = request.headers.get("user-agent", "")
    rows = _load_reset_tokens()
    match = next((r for r in rows if r.get("token") == body.token and not r.get("used")), None)
    if not match:
        authsec.audit("reset_password", ok=False, ip=ip, ua=ua, detail="invalid_or_expired_token")
        return JSONResponse({"ok": False, "error": "Invalid or expired reset link."}, status_code=400)
    strength = authsec.password_strength(body.new_password)
    if strength["score"] < 2:
        return JSONResponse({"ok": False, "error": "Password too weak. Use 8+ chars with upper, lower, number and symbol."}, status_code=400)
    # Invalidate the token
    match["used"] = True
    _save_reset_tokens(rows)
    # Update password
    _RAW_PASSWORD = body.new_password
    _PASSWORD_HASH = authsec.hash_password(body.new_password)
    env_path = config.ROOT / ".env"
    text = env_path.read_text() if env_path.exists() else ""
    if re.search(r'^BAADAR_PASSWORD=', text, flags=re.MULTILINE):
        text = re.sub(r'^BAADAR_PASSWORD=.*$', f'BAADAR_PASSWORD={body.new_password}', text, flags=re.MULTILINE)
    else:
        text = (text.rstrip("\n") + "\n" if text else "") + f'BAADAR_PASSWORD={body.new_password}\n'
    env_path.write_text(text)
    authsec.audit("reset_password", ok=True, ip=ip, ua=ua, detail="password_changed")
    return {"ok": True, "message": "Password updated. Sign in with your new password."}


# ── Phase 4: Audit / Login History ───────────────────────────────────────────

@app.get("/api/v1/auth/audit")
def auth_audit(request: Request, limit: int = 40):
    """Recent authentication events (login, logout, passkey, reset, revoke)."""
    from fastapi.responses import JSONResponse
    from saathi import authsec
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    return {"events": authsec.recent_audit(limit=min(limit, 100))}




# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH v1.2 — Security Platform Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/v1/security/timeline")
def security_timeline(request: Request, limit: int = 50, kind: str = ""):
    """Security Timeline — append-only event history."""
    from fastapi.responses import JSONResponse
    from saathi.security.timeline import get_timeline
    from saathi.security.store import get_store
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    user_id = get_store().get_or_create_owner()
    events = get_timeline().list(user_id, kind=kind or None, limit=min(limit, 200))
    return {"events": events}


@app.get("/api/v1/security/health")
def security_health(request: Request):
    """Password Health metrics — strength, age, rotation status."""
    from fastapi.responses import JSONResponse
    from saathi.security.health import PasswordHealth
    from saathi.security.store import get_store
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    user_id = get_store().get_or_create_owner()
    health = PasswordHealth()
    return {"health": health.metrics(user_id)}


@app.get("/api/v1/security/tokens")
def list_tokens(request: Request):
    """List all API tokens for the owner."""
    from fastapi.responses import JSONResponse
    from saathi.security.registry import get_registry
    from saathi.security.store import get_store
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    user_id = get_store().get_or_create_owner()
    tokens = get_registry().list(user_id)
    return {"tokens": tokens}


class CreateTokenIn(BaseModel):
    name: str
    purpose: str = ""
    permissions: list[str] | None = None
    expires_in_days: int | None = None

@app.post("/api/v1/security/tokens")
def create_token(body: CreateTokenIn, request: Request):
    """Create a new API token. Raw token is returned ONCE."""
    from fastapi.responses import JSONResponse
    from saathi.security.registry import get_registry
    from saathi.security.store import get_store
    from saathi.security.timeline import get_timeline
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    user_id = get_store().get_or_create_owner()
    reg = get_registry()
    tid, raw = reg.create(user_id, body.name, purpose=body.purpose,
                          permissions=body.permissions,
                          expires_in_days=body.expires_in_days)
    get_timeline().record(user_id, "token_created",
        title=f"API token created: {body.name}",
        detail=body.purpose or "No description",
        meta={"token_id": tid, "name": body.name})
    return {"ok": True, "token_id": tid, "token": raw}


@app.delete("/api/v1/security/tokens/{tid}")
def revoke_token(tid: str, request: Request):
    """Revoke an API token."""
    from fastapi.responses import JSONResponse
    from saathi.security.registry import get_registry
    from saathi.security.store import get_store
    from saathi.security.timeline import get_timeline
    if not _is_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    user_id = get_store().get_or_create_owner()
    ok = get_registry().revoke(tid)
    if ok:
        get_timeline().record(user_id, "token_revoked",
            title="API token revoked", detail=tid)
    return {"ok": ok}


@app.get("/api/v1/auth/providers")
def identity_providers(request: Request):
    """List available identity providers (OAuth / SSO)."""
    from saathi.security.identity import default_router
    router = default_router()
    return {
        "available": router.available(),
        "all": router.all_names(),
    }


@app.get("/api/v1/auth/passkey/diagnostics")
def passkey_diagnostics(request: Request, error: str = "", reason: str = ""):
    """Get human-readable diagnostic for a passkey error."""
    from saathi.security.diagnostics import passkey_diagnostic
    return {"message": passkey_diagnostic(error, reason)}


# ── Phase 5: OAuth Architecture (pluggable, no providers enabled yet) ─────────

class OAuthProvider:
    """Registry entry for a federated identity provider."""
    def __init__(self, name: str, display: str, authorize_url: str, scope: str, enabled: bool = False):
        self.name = name; self.display = display; self.authorize_url = authorize_url
        self.scope = scope; self.enabled = enabled


_OAUTH_PROVIDERS: dict[str, OAuthProvider] = {
    "google":   OAuthProvider("google",   "Google",   "https://accounts.google.com/o/oauth2/v2/auth",   "openid email profile", False),
    "apple":    OAuthProvider("apple",    "Apple",    "https://appleid.apple.com/auth/authorize",       "openid name email",    False),
    "github":   OAuthProvider("github",   "GitHub",   "https://github.com/login/oauth/authorize",       "read:user user:email", False),
    "microsoft":OAuthProvider("microsoft","Microsoft","https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "openid email profile", False),
    "facebook": OAuthProvider("facebook","Facebook","https://www.facebook.com/v18.0/dialog/oauth",      "email public_profile", False),
    "telegram": OAuthProvider("telegram", "Telegram", "", "", False),  # uses Bot API, not OAuth2
}


@app.get("/api/v1/auth/oauth/providers")
def oauth_providers(request: Request):
    """List available OAuth providers and their enabled status."""
    return {"providers": [{"name": p.name, "display": p.display, "enabled": p.enabled,
                           "configured": bool(_os.getenv(f"OAUTH_{p.name.upper()}_CLIENT_ID"))}
                          for p in _OAUTH_PROVIDERS.values()]}


@app.get("/api/v1/auth/oauth/{provider}/authorize")
def oauth_authorize(provider: str, request: Request, redirect_uri: str = ""):
    """Start OAuth flow for a provider. Returns the authorization URL to redirect to."""
    from fastapi.responses import JSONResponse
    p = _OAUTH_PROVIDERS.get(provider)
    if not p:
        return JSONResponse({"ok": False, "error": "Unknown provider"}, status_code=400)
    client_id = _os.getenv(f"OAUTH_{provider.upper()}_CLIENT_ID", "")
    if not client_id:
        return JSONResponse({"ok": False, "error": f"{p.display} OAuth not configured"}, status_code=400)
    # Generate a state token (CSRF protection)
    state = _secrets.token_urlsafe(16)
    # Store state → provider mapping (simple file, 10-min TTL)
    state_store = Path.home() / ".saathi" / "oauth_states.json"
    try:
        states = json.loads(state_store.read_text()) if state_store.exists() else {}
    except Exception:
        states = {}
    states[state] = {"provider": provider, "created": time.time(), "redirect_uri": redirect_uri}
    state_store.parent.mkdir(parents=True, exist_ok=True)
    state_store.write_text(json.dumps(states))
    # Build authorization URL
    cb = redirect_uri or f"{_rp(request)[1]}/api/v1/auth/oauth/callback"
    auth_url = f"{p.authorize_url}?client_id={client_id}&response_type=code&scope={p.scope}&redirect_uri={cb}&state={state}"
    return {"ok": True, "authorization_url": auth_url}


@app.get("/api/v1/auth/oauth/callback")
async def oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """OAuth callback — validates state, exchanges code for token (placeholder)."""
    from fastapi.responses import JSONResponse, RedirectResponse
    if error:
        return JSONResponse({"ok": False, "error": error}, status_code=400)
    state_store = Path.home() / ".saathi" / "oauth_states.json"
    try:
        states = json.loads(state_store.read_text()) if state_store.exists() else {}
    except Exception:
        states = {}
    ctx = states.pop(state, None)
    if state_store.exists():
        state_store.write_text(json.dumps(states))
    if not ctx or time.time() - ctx.get("created", 0) > 600:
        return JSONResponse({"ok": False, "error": "Invalid or expired state"}, status_code=400)
    provider = ctx.get("provider", "")
    # PLACEHOLDER: actual token exchange requires provider-specific code.
    # When a provider is enabled, this exchanges 'code' for an access token,
    # fetches the user's profile, and creates a session. For now, we return
    # a clear message so the architecture is ready.
    return JSONResponse({"ok": True, "message": f"OAuth callback received for {provider}. "
                         "Token exchange not yet implemented — enable the provider and add the exchange logic."})

# Lazy agent — avoid import-time API key requirements so pytest collection
# and CI ``--collect-only`` can import the app without ANTHROPIC_API_KEY /.env.
_agent_singleton: "SaathiAgent | None" = None


def get_agent() -> SaathiAgent:
    """Return the process-wide SaathiAgent, constructing it on first use."""
    global _agent_singleton
    if _agent_singleton is None:
        _agent_singleton = SaathiAgent()
    return _agent_singleton


class _LazyAgentProxy:
    """Module-level ``agent`` proxy preserved for existing call sites."""

    def __getattr__(self, name: str):
        return getattr(get_agent(), name)

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(get_agent(), name, value)


agent = _LazyAgentProxy()

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
    # Research questions answer from the unified, evidence-backed intelligence
    # snapshot (read-only) — never the LLM's memory. Non-research text falls
    # through to the normal agent. Failure here never blocks a reply.
    try:
        from saathi.research_surface import maybe_answer_chat
        r = maybe_answer_chat(text)
        if r is not None:
            return r["reply"]
    except Exception:
        pass
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


class NarrateIn(BaseModel):
    """Facts block for chart-analysis narration. The CLIENT NEVER SUPPLIES THE SYSTEM
    PROMPT — only the computed facts — so this endpoint cannot be repurposed as a
    general 'run my prompt' hole."""

    facts: str
    question: str = ""


# Fixed server-side. Not overridable by any caller.
_NARRATE_SYSTEM = (
    "You explain a chart analysis that has ALREADY been computed by a deterministic "
    "engine. HARD RULES: (1) Every number you use must appear verbatim in the FACTS. "
    "Never compute, round, extrapolate or invent a price, level, percentage or "
    "indicator value. (2) If something is marked unavailable, say it is unavailable; "
    "never estimate it. (3) Do not give investment advice, a buy/sell recommendation, "
    "or a position size — explain what the chart shows and what would change it. "
    "(4) Lead with what conflicts, not only what agrees. (5) If the verdict is AVOID "
    "or WAIT, say so plainly rather than finding something encouraging to say. "
    "Write 3-5 short paragraphs for an experienced swing trader."
)

_NARRATE_MAX_FACTS = 12000


@app.post("/api/v1/analysis/narrate")
def analysis_narrate(body: NarrateIn, request: Request):
    """Narrate a computed chart analysis. Explanation only — never a new number."""
    if not _rate_ok(request):
        return {"ok": False, "reason": "RATE_LIMITED"}
    facts = (body.facts or "").strip()
    if not facts:
        return {"ok": False, "reason": "NO_FACTS"}
    if len(facts) > _NARRATE_MAX_FACTS:
        return {"ok": False, "reason": "FACTS_TOO_LARGE"}

    # Server routes reach the model INDIRECTLY, through the registered
    # `tools_llm_helper` caller — the convention the `server_tools` caller policy
    # states outright ("no direct provider from server routes"). The earlier
    # version called the deprecated `llm.generate` facade with caller_id
    # "analysis_narrate", which is not a registered caller, so preflight denied
    # every request and this endpoint always answered LLM_UNAVAILABLE.
    #
    # RUNTIME-CONVERGENCE-1: the connectivity-governance branch resolved the same
    # dead route through `chat_generate`, which is the ChatEngine adapter — it
    # borrows caller_id "chat_engine" for a route that is not the chat engine,
    # and it returns a DICT, so this function's `getattr(res, "text", "")` read
    # the default and the endpoint answered ok:true with empty narration. The
    # helper below returns an LLMResult carrying both .text and the .model the
    # analysis UI displays.
    from saathi.tools._llm_helper import ask_llm_result

    prompt = facts if not body.question else f"{facts}\n\nQUESTION: {body.question}"
    try:
        res = ask_llm_result(prompt, _NARRATE_SYSTEM, timeout=60, max_tokens=900)
        return {"ok": True, "text": getattr(res, "text", "") or "", "model": getattr(res, "model", "")}
    except Exception as exc:  # narration is optional — never break the analysis
        return {"ok": False, "reason": "LLM_UNAVAILABLE", "detail": str(exc)[:200]}


@app.post("/api/v1/agent/chat")
def chat(body: ChatIn, request: Request):
    if not _rate_ok(request):
        return {"reply": "I'm getting a lot of requests right now — give me a minute and try again."}
    reply = _safe_respond(body.text, body.session_id, body.speaker_verified)
    return {"reply": reply}


# ── Research Intelligence surface (READ-ONLY) — projects the existing evidence
# intelligence into Central Command / chat / voice. No trade/broker/portfolio/
# market_data authority; follows the standard session auth (not whitelisted).
@app.get("/api/v1/research/intelligence")
def research_intelligence(request: Request):
    from saathi import research_surface
    return research_surface.intelligence()


@app.get("/api/v1/research/events")
def research_events(request: Request, limit: int = 50):
    from saathi import research_surface
    return research_surface.events(limit=limit)


@app.get("/api/v1/research/events/{event_id}")
def research_event_detail(event_id: str, request: Request):
    from saathi import research_surface
    return research_surface.event_detail(event_id)


@app.get("/api/v1/research/brief")
def research_brief(request: Request):
    from saathi import research_surface
    return research_surface.brief()


@app.get("/api/v1/research/health")
def research_health(request: Request):
    from saathi import research_surface
    return research_surface.health()


@app.post("/api/v1/workspace")
async def workspace_turn(request: Request):
    """Saathi Workspace — one conversation that researches/plans/acts on a Mission.
    Modes: research/planning/implementation/cowork. Auto-analyses pasted GitHub URLs.
    Whitelisted + rate-limited (like chat)."""
    import asyncio
    if not _rate_ok(request):
        return {"reply": "Getting a lot of requests — give me a minute.", "actions": []}
    body = await request.json()
    from saathi.workspace import handle
    return await asyncio.to_thread(handle, body.get("message", ""),
                                   mission_key=body.get("mission", ""), mode=body.get("mode", "cowork"))


@app.post("/api/v1/workspace/plan/save")
async def workspace_save_plan(request: Request):
    """Turn an implementation-mode plan into a real Workflow + Tasks on the Mission. Token-gated."""
    body = await request.json()
    from saathi.workspace import save_plan_as_workflow
    return save_plan_as_workflow(body.get("mission", ""), body.get("name", "Plan"),
                                 body.get("steps") or [])


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
    """Platform connection settings, with credential VALUES redacted.

    This returned `connections.get_all()` verbatim, so an authenticated caller
    received the Facebook page access token — 202 characters of live publishing
    credential — in a 200 body, where it lands in browser devtools, proxy logs
    and any client-side error reporting. The 422 redaction boundary does not
    cover success responses; this one does.

    PRESENCE is preserved. The UI has to show whether a platform is configured,
    and `has_page_access_token: true` says that without disclosing the value.
    Field names come from the repository's existing secret detector rather than
    a second list that would drift from it.
    """
    from saathi.tool_runtime.secrets import REDACTED, is_secret_key

    from . import connections

    safe = {}
    for platform, cfg in (connections.get_all() or {}).items():
        if not isinstance(cfg, dict):
            safe[platform] = cfg
            continue
        out = {}
        for key, value in cfg.items():
            if is_secret_key(key) and value not in (None, "", [], {}):
                out[key] = REDACTED
                out[f"has_{key}"] = True
            elif is_secret_key(key):
                out[key] = value
                out[f"has_{key}"] = False
            else:
                out[key] = value
        safe[platform] = out
    return {"connections": safe}


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
async def voice_command(request: Request, file: UploadFile = File(...),
                        session_id: str = Form("default"),
                        speak_reply: bool = Form(True),
                        require_wake: bool = Form(False)):
    """Full voice turn: audio → verify speaker → transcribe → (wake check) → agent → TTS."""
    global _last_reply_at
    if not _rate_ok(request):
        return {"reply": "One moment — too many requests. Try again shortly.", "transcript": ""}
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

    # Already signed in (password or passkey session, or local machine)? Trust the
    # owner — skip per-utterance voice verification. Only fall back to speaker
    # verification when there is NO session.
    if _is_authed(request) or _is_local(request):
        ver = {"verified": True, "reason": "session_authenticated", "similarity": 1.0}
    else:
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
    output_path = voices_dir / f"voice_{int(time.time())}.mp3"
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

_PROCESS_START = time.time()


@app.get("/api/v1/system/version")
async def system_version():
    """Runtime-build identity (M12 Phase 24, strengthened M13.5 Phase 3) — lets
    the frontend detect a stale/incompatible backend (the bug that broke M11's
    first live smoke). No secrets/paths/env — only counts + a commit hash."""
    from .ops.identity import identity
    return identity(route_count=len(app.routes))


class _VersionCompat(BaseModel):
    api_version: str = ""
    route_manifest_version: str = ""


@app.post("/api/v1/system/version/compat")
async def system_version_compat(body: _VersionCompat):
    """Frontend posts its build's API + route-manifest version; backend replies
    whether they are compatible so the UI can warn on a version mismatch."""
    from .ops.identity import compatible
    return compatible(body.api_version, body.route_manifest_version)


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
    # import the curated agency-agents prompts as Directors (Director Library)
    try:
        from .production.agency_importer import import_directors
        import_directors()
    except Exception:
        pass
    # seed the five businesses as Missions (root object of SaathiOS)
    try:
        from .missions.store import seed_missions
        seed_missions()
    except Exception:
        pass
    # seed the Knowledge Library with foundational sources + the reading backlog
    try:
        from .knowledge_library.importer import seed_defaults as seed_library
        seed_library()
        from .knowledge_library.queue import seed_queue
        seed_queue()
        from .skills_library.seed import seed_skills
        seed_skills()
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


def _install_outermost_cors() -> None:
    """Register CORSMiddleware as the outermost middleware.

    Starlette applies `add_middleware` by prepending, so the last registration
    wins the outermost position. Every other middleware in this module — the
    security headers layer and the `_auth` gate — is registered above, which
    makes this call the one that puts CORS on the outside.

    Ordering matters beyond preflight. With CORS innermost, an authentication
    rejection short-circuits before CORS can label the response, so the browser
    reports a CORS failure for what is really a 401 and the real cause is
    invisible in the console. With CORS outermost:

      * an allowed-origin preflight is answered by CORS and never reaches
        `_auth`, so no `OPTIONS` bypass is needed in the auth gate;
      * an allowed-origin unauthenticated request still returns 401, and that
        401 carries the correct `Access-Control-Allow-Origin`;
      * a disallowed origin gets no `Access-Control-Allow-Origin` on anything,
        and authentication is not consulted to decide that.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )


_install_outermost_cors()


def main():
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)


# NOTE: the `if __name__ == "__main__": main()` entrypoint is intentionally at the
# VERY END of this file. Route definitions continue for ~800 lines below; running
# main() here would call the blocking uvicorn.run() before those routes (finance
# providers, finance/browser/*, observation bridge, …) are registered, so a
# `python -m saathi.server` launch would 404 them. Keep the entrypoint last.


# ── M57 single-host heartbeat (localhost-only; advisory; no authority) ───────
@app.on_event("startup")
def _saathi_start_local_heartbeat():
    """Keep node-local health accurate while the BFF runs. Cancelled on shutdown
    so health goes stale after a bounded timeout once the process stops."""
    try:
        from saathi.platform.cluster import start_local_heartbeat
        start_local_heartbeat()
    except Exception:
        pass


@app.on_event("shutdown")
def _saathi_stop_local_heartbeat():
    try:
        from saathi.platform.cluster import stop_local_heartbeat
        stop_local_heartbeat()
    except Exception:
        pass


@app.on_event("startup")
async def _saathi_start_public_market_data():
    """Start the public crypto feed ONLY when explicitly configured.

    Off unless `SAATHI_PUBLIC_MARKET_DATA=1`. Booting the server must not open a
    socket by default: a feed nobody asked for is an unannounced outbound
    connection, and in test or offline contexts it would be a failure looking for
    somewhere to happen. Public Binance spot market data only — no credentials
    exist on this path and no account, order or user-data surface is reachable.
    """
    import os

    if os.getenv("SAATHI_PUBLIC_MARKET_DATA", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    try:
        from saathi.platform.crypto.runtime import (
            PublicMarketDataConfig, reset_public_market_data_for_tests,
        )

        symbols = tuple(
            s.strip().upper()
            for s in os.getenv("SAATHI_PUBLIC_MARKET_DATA_SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
            if s.strip()
        )
        rt = reset_public_market_data_for_tests(
            PublicMarketDataConfig(enabled=True, symbols=symbols))
        # Async lifecycle: connect, subscribe, then start the single ingestion
        # task. Without the reader the socket would be open and unread.
        await rt.start_async()
    except Exception:
        # A feed that cannot start must not take the server down with it; the
        # health surface reports the real state either way.
        pass


@app.on_event("shutdown")
async def _saathi_stop_public_market_data():
    """Close the public stream cleanly: reader cancelled, socket closed, queue released.

    Order is load-bearing — the transport close is what frees a thread parked in
    a blocking recv, so cancelling the reader alone would leave it waiting.
    """
    try:
        from saathi.platform.crypto import runtime as _rt_mod

        if _rt_mod._RUNTIME is not None:
            await _rt_mod._RUNTIME.stop_async()
    except Exception:
        pass


# ── M — LIVE_NEPSE_BROWSER_MARKET_DATA: read-only live market surface ──────────
# Governed-browser observation of the OFFICIAL public NEPSE site (rendered DOM only;
# no downloads, no XHR/token replay). LIVE_BROWSER_OBSERVED — never canonical history,
# never a trade control. Handlers are sync `def` so FastAPI runs them in a threadpool
# (sync Playwright cannot run on the asyncio loop).
def _nepse_live_snapshot(force: bool = False):
    from saathi.platform.market_data.nepse_live_service import get_default_service
    svc = get_default_service()
    snap = svc.snapshot()
    if snap is None or force:
        snap = svc.refresh(force=True)
    return svc, snap


@app.get("/api/v1/market/nepse/live")
def nepse_live_tile(refresh: int = 0):
    """Central-Command tile: index, breadth, turnover, top movers, freshness. No trade controls."""
    try:
        from saathi.platform.market_data.nepse_live_service import central_command_live_projection
        _, snap = _nepse_live_snapshot(force=bool(refresh))
        return central_command_live_projection(snap)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/nepse/live/full")
def nepse_live_full(refresh: int = 0):
    try:
        _, snap = _nepse_live_snapshot(force=bool(refresh))
        return snap.to_public()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/nepse/live/health")
def nepse_live_health():
    try:
        from saathi.platform.market_data.nepse_live_service import get_default_service
        return get_default_service().health()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/nepse/live/chat")
def nepse_live_chat(q: str = ""):
    try:
        from saathi.platform.market_data.nepse_live_service import chat_answer_live
        _, snap = _nepse_live_snapshot(force=False)
        return chat_answer_live(snap, q)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/market/nepse", response_class=HTMLResponse, include_in_schema=False)
def nepse_live_panel():
    """Phase 19/20 — internal read-only NEPSE market panel. No trade controls; a source
    link to the official public site only."""
    return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8>
<title>SaathiOS — NEPSE Live (observed)</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font:14px system-ui;margin:0;background:#0d1117;color:#e6edf3}
.wrap{max-width:960px;margin:0 auto;padding:16px}
.hdr{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.badge{padding:2px 8px;border-radius:10px;font-weight:600;font-size:12px}
.LIVE{background:#1f6f3f}.CLOSED,.MARKET_CLOSED{background:#5a3a12}.STALE,.RECENT{background:#6b5900}
.PAGE_ERROR,.UNAVAILABLE,.SCHEMA_CHANGED{background:#7d2222}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px}
.card b{display:block;font-size:20px}.muted{color:#8b949e;font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:10px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #21262d;font-size:13px}
th{color:#8b949e}a{color:#58a6ff}button{background:#238636;color:#fff;border:0;padding:6px 12px;border-radius:6px;cursor:pointer}
</style></head><body><div class=wrap>
<div class=hdr><h2 style="margin:0">NEPSE <span class=muted>live observed</span></h2>
<span id=status class=badge>…</span><span id=fresh class=badge>…</span>
<button onclick="load(1)">Refresh</button>
<a href="https://www.nepalstock.com" target=_blank rel=noopener>Open official source ↗</a></div>
<div class=muted id=obs></div>
<div class=grid id=stats></div>
<h3>Top by turnover <span class=muted>(observed)</span></h3>
<table><thead><tr><th>Symbol</th><th>LTP</th><th>Change</th><th>%</th><th>Volume</th></tr></thead><tbody id=rows></tbody></table>
<p class=muted>Source: Official NEPSE (nepalstock.com). Data class: LIVE_BROWSER_OBSERVED — current
awareness only, not canonical historical data. Read-only; no trading controls.</p>
</div><script>
let _ver=-1;
function render(d){
 if(!d||d.error)return;
 if(typeof d.version==='number'){ if(d.version<_ver)return; _ver=d.version; }
 const s=document.getElementById('status');s.textContent=d.market_status;s.className='badge '+d.market_status;
 const f=document.getElementById('fresh');f.textContent=d.freshness;f.className='badge '+d.freshness;
 document.getElementById('obs').textContent='Observed: '+(d.source_as_of||new Date((d.observed_at||0)*1000).toLocaleString())+(d.version!=null?'  (v'+d.version+')':'');
 document.getElementById('stats').innerHTML=[
  ['Index',d.nepse_index],['Change',(d.index_change??'—')+' ('+(d.index_change_percent??'—')+'%)'],
  ['Turnover Rs',d.total_turnover],['Traded shares',d.total_volume],
  ['Advancers',d.advancers],['Decliners',d.decliners],['Unchanged',d.unchanged]]
  .map(([k,v])=>'<div class=card><span class=muted>'+k+'</span><b>'+(v??'—')+'</b></div>').join('');
 document.getElementById('rows').innerHTML=(d.watchlist||[]).map(o=>'<tr><td>'+o.symbol+'</td><td>'+
  (o.ltp??'—')+'</td><td>'+(o.point_change??'—')+'</td><td>'+(o.percent_change??'—')+'</td><td>'+
  (o.volume??'—')+'</td></tr>').join('');
}
async function load(refresh){
 const s=document.getElementById('status');s.textContent='loading…';
 try{const r=await fetch('/api/v1/market/nepse/live'+(refresh?'?refresh=1':''));render(await r.json());}
 catch(e){s.textContent='error';}
}
// consume the shared snapshot over the EXISTING SSE stream — never triggers acquisition
try{const es=new EventSource('/api/events/stream?demo=0');
 es.onmessage=function(e){try{const ev=JSON.parse(e.data);
  if(ev&&ev.name==='market.nepse.snapshot'&&ev.payload)render(ev.payload);}catch(_){}}; }catch(_){}
load(0);</script></body></html>""")


# ── M — TRACKER_MARKET_HISTORY_READMODEL: read-only THIRD-PARTY analytics ──────
# Public REST (no creds/MCP/browser). THIRD_PARTY_STRUCTURED_MARKET_DATA; official
# NEPSE remains current-market authority; never writes md_bars/md_quotes; no signals.
# Sync `def` handlers → FastAPI threadpool (requests is blocking).
@app.get("/api/v1/market/tracker/history")
def tracker_history(symbol: str, range: str = "1Y"):
    try:
        from saathi.platform.market_data.tracker.provider import get_provider
        series, st = get_provider().market_history(symbol, range)
        if series is None:
            return JSONResponse({"available": False, "status": st.value, "symbol": symbol.upper()},
                                status_code=200)
        return series.to_public()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/tracker/chart")
def tracker_chart(symbol: str, range: str = "1Y", indicators: str = ""):
    try:
        from saathi.platform.market_data.tracker.chart import build_chart_model
        which = [w.strip() for w in indicators.split(",") if w.strip()] or None
        return build_chart_model(symbol, range, which_indicators=which)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/tracker/fundamentals")
def tracker_fundamentals(symbol: str):
    try:
        from saathi.platform.market_data.tracker.provider import get_provider
        f, st = get_provider().fundamentals(symbol)
        return f.to_public() if f else JSONResponse({"available": False, "status": st.value}, status_code=200)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/tracker/dividends")
def tracker_dividends(symbol: str = ""):
    try:
        from saathi.platform.market_data.tracker.provider import get_provider
        d, st = get_provider().dividends(symbol or None)
        return {"status": st.value, "count": len(d), "dividends": [x.to_public() for x in d]}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/tracker/reconcile")
def tracker_reconcile(symbol: str):
    try:
        from saathi.platform.market_data.tracker.chart import reconcile_current
        return reconcile_current(symbol).to_public()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/market/analysis/technical")
def market_technical_analysis(body: dict = Body(...)):
    """Agent-assisted technical analysis for NEPSE / crypto. Research-only: deterministic
    indicators from real OHLC, then a governed-agent synthesis. Never advice, never execution."""
    try:
        from saathi.platform.market_data.technical_analysis import analyze
        market = str(body.get("market", "NEPSE"))
        symbol = str(body.get("symbol", ""))
        return analyze(market, symbol)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/market/analysis/smc")
def market_smc_analysis(body: dict = Body(...)):
    """ICT / Smart Money Concepts structure (order blocks, FVG, BOS/CHoCH, liquidity,
    premium/discount, inducement/IDM) from real OHLC. Descriptive research only."""
    try:
        from saathi.platform.market_data import smc
        return smc.analyze(str(body.get("market", "NEPSE")), str(body.get("symbol", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/market/analysis/strategy")
def market_strategy(body: dict = Body(...)):
    """ICT/SMC trading PLAYBOOK: structure mapping (15m for crypto) + potential IDM +
    entry/invalidation/target ideas. Education/research only — never advice/execution."""
    try:
        from saathi.platform.market_data.technical_analysis import strategy
        return strategy(str(body.get("market", "CRYPTO")), str(body.get("symbol", "")),
                        str(body.get("timeframe", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/strategies")
def market_strategies_catalog():
    """The owner's pro-trader strategy playbook (ported from crypto-signal-bot):
    catalog of named rule sets. Research/education only, never advice."""
    try:
        from saathi.platform.market_data import strategy_playbook
        return strategy_playbook.catalog()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/market/strategies/scan")
def market_strategies_scan(body: dict = Body(...)):
    """Scan one symbol (NEPSE or crypto) against every machine-scannable playbook
    strategy; return matches with score, reasons and structural entry/stop/target.
    Deterministic over real OHLC — research only, never advice or an order."""
    try:
        from saathi.platform.market_data import strategy_playbook
        return strategy_playbook.scan(str(body.get("market", "NEPSE")),
                                      str(body.get("symbol", "")),
                                      str(body.get("timeframe", "1d")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/market/analysis/desk")
def market_trade_desk(body: dict = Body(...)):
    """Trade Desk bundle: trade setup (entry/SL/target/RR + loss%/profit%), volume strength
    (buyer vs seller by period), and S/R zones. Deterministic, observation-only — not advice."""
    try:
        from saathi.platform.market_data import trade_desk
        return trade_desk.desk(str(body.get("market", "NEPSE")), str(body.get("symbol", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/free/nepse")
def market_free_nepse(force: int = 0):
    """Full NEPSE market from a free public web source (no API key). Observation-only."""
    try:
        from saathi.platform.market_data import free_sources
        return free_sources.nepse_market(force=bool(force))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/free/movers")
def market_free_movers(top: int = 5):
    try:
        from saathi.platform.market_data import free_sources
        return free_sources.movers(top=min(int(top), 15))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/free/quote")
def market_free_quote(symbol: str):
    try:
        from saathi.platform.market_data import free_sources
        return free_sources.nepse_quote(symbol)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/free/company")
def market_free_company(symbol: str):
    try:
        from saathi.platform.market_data import free_sources
        return free_sources.nepse_company(symbol)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/free/fundamentals")
def market_free_fundamentals(symbol: str):
    """Full fundamentals (EPS/PE/PB/book/market cap) scraped free, any listed symbol."""
    try:
        from saathi.platform.market_data import free_sources
        return free_sources.nepse_fundamentals(symbol)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/free/ranges")
def market_free_ranges(start: int = 0):
    """Bulk 52-week ranges filled by a background job (kick off with ?start=1)."""
    try:
        from saathi.platform.market_data import free_sources
        return free_sources.ranges(start=bool(start))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/portfolio/add")
def portfolio_add(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance import portfolio_desk as pd
        return pd.add_holding(str(body.get("symbol", "")), str(body.get("market", "NEPSE")),
                              float(body.get("qty", 0) or 0), float(body.get("avg_cost", 0) or 0))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/portfolio/remove")
def portfolio_remove(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance import portfolio_desk as pd
        return pd.remove_holding(str(body.get("id", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/portfolio/analysis")
def portfolio_analysis(request: Request):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance import portfolio_desk as pd
        return pd.analysis()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/settings/keys")
def settings_keys_status(request: Request):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.settings import keys
        return keys.status()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/settings/keys")
def settings_keys_set(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.settings import keys
        return keys.set_key(str(body.get("name", "")), str(body.get("value", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/fund/meeting")
def fund_meeting(request: Request, body: dict = Body(...)):
    """Convene the AI hedge-fund committee on a symbol → transcript + CEO decision."""
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance import fund_committee
        return fund_committee.run_meeting(str(body.get("market", "NEPSE")), str(body.get("symbol", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/fund/meetings")
def fund_meetings(request: Request, limit: int = 20):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance import fund_committee
        return fund_committee.list_meetings(min(int(limit), 50))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/fund/meeting/{sid}")
def fund_meeting_get(request: Request, sid: str):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance import fund_committee
        return fund_committee.get_meeting(sid)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/vision/analyze")
def vision_analyze(request: Request, body: dict = Body(...)):
    """Analyse a screenshot with Gemini Vision (owner-only). Image used once, never stored."""
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.vision.screen_vision import analyze_image
        return analyze_image(str(body.get("image_b64", "")), str(body.get("question", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/news")
def market_news(request: Request, symbol: str | None = None, limit: int = 12):
    """Research-event news, optionally filtered to a symbol, with catalyst flags
    (dividend / promoter lock-in / bonus / rights / AGM). Observation-only."""
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        import re as _re
        from saathi import research_surface
        events = (research_surface.events(limit=80) or {}).get("events", [])
        cat = _re.compile(r"dividend|lock[- ]?in|promoter|bonus|right\s*share|book\s*close|agm|auction|delist", _re.I)
        def tag(e):
            s = (e.get("headline") or "") + " " + str(e.get("event_type") or "")
            return bool(cat.search(s))
        if symbol:
            sym = symbol.strip().upper()
            rows = [e for e in events if str(e.get("symbol") or "").upper() == sym]
            rows.sort(key=lambda e: 0 if tag(e) else 1)
        else:
            rows = events
        out = [{"symbol": e.get("symbol"), "headline": e.get("headline") or e.get("title"),
                "event_type": e.get("event_type"), "date": e.get("event_date_normalized") or e.get("event_date_raw"),
                "catalyst": tag(e)} for e in rows[:min(int(limit), 40)]]
        return {"available": True, "symbol": symbol, "count": len(out), "events": out}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/signals")
def market_signals():
    """Deterministic setup scan across a watchlist (observation-only). Reuses the paper-trade
    setup gate — no orders, no advice; a list of where a clean ATR trend setup currently exists."""
    try:
        from saathi.platform.finance import paper_trading as pt
        watch = [("NEPSE", s) for s in ("NABIL", "HDL", "UPPER", "GBIME", "NRIC")] + \
                [("CRYPTO", s) for s in ("BTC", "ETH", "SOL")]
        out = []
        for mk, sym in watch:
            try:
                p = pt.propose(mk, sym)
            except Exception:
                continue
            if p.get("setup"):
                out.append({"market": mk, "symbol": sym, "side": p["side"], "entry": p["entry"],
                            "stop": p["stop"], "target": p["target"], "rr": p["planned_r"]})
        return {"signals": out, "scanned": len(watch), "count": len(out),
                "note": "Deterministic ATR trend setups · observation-only · not advice."}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


# ── Paper trading agent (SIMULATION ONLY — no real orders / broker / execution) ──
@app.post("/api/v1/trading/paper/propose")
def paper_propose(body: dict = Body(...)):
    try:
        from saathi.platform.finance import paper_trading as pt
        return pt.propose(str(body.get("market", "NEPSE")), str(body.get("symbol", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/trading/paper/open")
def paper_open(body: dict = Body(...)):
    try:
        from saathi.platform.finance import paper_trading as pt
        return pt.open_trade(str(body.get("market", "NEPSE")), str(body.get("symbol", "")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/trading/paper/evaluate")
def paper_evaluate():
    try:
        from saathi.platform.finance import paper_trading as pt
        return pt.evaluate()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/trading/paper/journal")
def paper_journal(limit: int = 30):
    try:
        from saathi.platform.finance import paper_trading as pt
        return pt.journal(min(int(limit), 100))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/market/chart", response_class=HTMLResponse, include_in_schema=False)
def tracker_chart_panel():
    """Native SaathiOS chart from tracker structured history. No TradingView, no iframe."""
    return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8>
<title>SaathiOS — NEPSE Chart</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font:14px system-ui;margin:0;background:#0d1117;color:#e6edf3}
.wrap{max-width:1000px;margin:0 auto;padding:16px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
input,button{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:6px 10px}
button{cursor:pointer}button.on{background:#238636;border-color:#238636}
.badge{padding:2px 8px;border-radius:10px;font-size:12px;background:#1f3a5f}
.muted{color:#8b949e;font-size:12px}svg{width:100%;height:auto;background:#0d1117;border:1px solid #21262d;border-radius:8px}
.pit{color:#d29922;font-size:12px;margin-top:6px}
</style></head><body><div class=wrap>
<div class=row><b>NEPSE Chart</b>
<input id=sym value="NABIL" size=8 onkeydown="if(event.key==='Enter')load()">
<span id=ranges></span><button onclick="load()">Load</button>
<span id=src class=badge>—</span></div>
<div class=muted id=meta></div>
<svg id=price viewBox="0 0 1000 340" preserveAspectRatio="none"></svg>
<svg id=vol viewBox="0 0 1000 90" preserveAspectRatio="none" style="margin-top:6px"></svg>
<div class=pit id=pit></div>
<div class=muted id=funda style="margin-top:8px"></div>
</div><script>
let RANGE="1Y"; const RS=["1D","1W","1M","3M","6M","1Y","5Y"];
document.getElementById('ranges').innerHTML=RS.map(r=>`<button data-r="${r}" onclick="setR('${r}')">${r}</button>`).join('');
function setR(r){RANGE=r;paintRanges();load();}
function paintRanges(){document.querySelectorAll('#ranges button').forEach(b=>b.className=b.dataset.r===RANGE?'on':'');}
function px(v,min,max,w){return (max===min)?w/2:((v-min)/(max-min))*w;}
async function load(){
 paintRanges();
 const sym=document.getElementById('sym').value.trim().toUpperCase();
 document.getElementById('src').textContent='loading…';
 try{
  const r=await fetch(`/api/v1/market/tracker/chart?symbol=${sym}&range=${RANGE}&indicators=sma`);
  const d=await r.json();
  if(!d.available){document.getElementById('src').textContent=d.status||'unavailable';return;}
  document.getElementById('src').textContent='NEPSE Portfolio Tracker · third-party';
  document.getElementById('meta').textContent=`${sym} ${d.range} (${d.timeframe}) · ${d.first_date}→${d.last_date} · ${d.n_points} pts · latest ${d.latest_close}`;
  document.getElementById('pit').textContent='⚠ '+d.point_in_time_capability+' — descriptive only, not canonical/backtest data. Current LTP authority: Official NEPSE.';
  const o=d.ohlc, closes=o.map(p=>+p.close), vols=o.map(p=>+p.volume);
  const W=1000,H=340,pad=6; const mn=Math.min(...o.map(p=>+p.low)),mx=Math.max(...o.map(p=>+p.high));
  const X=i=>pad+ (o.length<2?W/2:(i/(o.length-1))*(W-2*pad));
  const Y=v=>H-pad-((v-mn)/((mx-mn)||1))*(H-2*pad);
  // candlesticks
  let s='';const cw=Math.max(1,(W-2*pad)/o.length*0.6);
  o.forEach((p,i)=>{const up=+p.close>=+p.open;const col=up?'#3fb950':'#f85149';
   s+=`<line x1="${X(i)}" y1="${Y(+p.high)}" x2="${X(i)}" y2="${Y(+p.low)}" stroke="${col}" stroke-width="1"/>`;
   const yo=Y(+p.open),yc=Y(+p.close);s+=`<rect x="${X(i)-cw/2}" y="${Math.min(yo,yc)}" width="${cw}" height="${Math.max(1,Math.abs(yc-yo))}" fill="${col}"/>`;});
  // SMA overlay
  const sma=(d.indicators.sma_20||{}).series; const smv=sma?sma['sma_20']:null;
  if(smv){let path='';smv.forEach((v,i)=>{if(v==null)return;path+=(path?'L':'M')+X(i)+' '+Y(v)+' ';});
   s+=`<path d="${path}" fill="none" stroke="#58a6ff" stroke-width="1.4"/>`;}
  document.getElementById('price').innerHTML=s;
  // volume
  const vmx=Math.max(...vols,1);let vs='';
  o.forEach((p,i)=>{const h=(+p.volume/vmx)*80;vs+=`<rect x="${X(i)-cw/2}" y="${90-h}" width="${cw}" height="${h}" fill="#30475e"/>`;});
  document.getElementById('vol').innerHTML=vs;
  const f=d.fundamentals||{};
  document.getElementById('funda').textContent=f.eps?`EPS ${f.eps} · P/E ${f.pe_ratio} · P/B ${f.pb_ratio} · Div yield ${f.dividend_yield}% · ${f.sector||''} (third-party fundamentals)`:'';
 }catch(e){document.getElementById('src').textContent='error';}
}
load();</script></body></html>""")


# ── M — NATIVE_NEPSE_MARKET_INTELLIGENCE_WORKSPACE (read-only, combines sources) ─
# Official NEPSE = current authority; tracker = third-party history/analytics; research
# + catalyst from frozen surfaces. No portfolio MCP, no signals, zero authority.
@app.get("/api/v1/market/workspace/overview")
def mw_overview():
    try:
        from saathi.platform.market_data.tracker.workspace import overview
        return overview()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/workspace/stocks")
def mw_stocks(sort: str = "turnover", sector: str = "", limit: int = 50):
    try:
        from saathi.platform.market_data.tracker.workspace import stock_table
        return stock_table(sort=sort, sector=sector or None, limit=min(max(limit, 1), 600))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/workspace/sectors")
def mw_sectors(sort: str = "turnover"):
    try:
        from saathi.platform.market_data.tracker.workspace import sectors
        return sectors(sort=sort)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/workspace/compare")
def mw_compare(symbols: str, range: str = "1Y", mode: str = "NORMALIZED_PERCENT"):
    try:
        from saathi.platform.market_data.tracker.workspace import compare
        syms = [s.strip() for s in symbols.split(",") if s.strip()][:4]
        return compare(syms, range, mode=mode)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/workspace/panel")
def mw_panel(symbol: str, range: str = "1Y"):
    try:
        from saathi.platform.market_data.tracker.workspace import symbol_panel
        return symbol_panel(symbol, range)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/market/workspace/chat")
def mw_chat(q: str = ""):
    try:
        from saathi.platform.market_data.tracker.workspace import workspace_chat
        return workspace_chat(q)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/market", response_class=HTMLResponse, include_in_schema=False)
def market_workspace_page():
    """Native NEPSE Market Intelligence workspace. No iframe, no TradingView."""
    return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8>
<title>SaathiOS — NEPSE Market Intelligence</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font:14px system-ui;margin:0;background:#0d1117;color:#e6edf3}
.wrap{max-width:1100px;margin:0 auto;padding:14px}
h2{margin:0 0 4px}.muted{color:#8b949e;font-size:12px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.tabs button{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:6px 12px;cursor:pointer}
.tabs button.on{background:#238636;border-color:#238636}
.badge{padding:2px 8px;border-radius:10px;font-size:11px;background:#1f3a5f}
.official{background:#1f6f3f}.third{background:#5a3a12}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:5px 8px;border-bottom:1px solid #21262d;text-align:right}
th:first-child,td:first-child{text-align:left}th{color:#8b949e;cursor:pointer}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px}.card b{display:block;font-size:18px}
input,select{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:5px 8px}
svg{width:100%;height:auto;background:#0d1117;border:1px solid #21262d;border-radius:8px}
.pit{color:#d29922;font-size:12px;margin:6px 0}.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
section{display:none}section.on{display:block}
</style></head><body><div class=wrap>
<h2>NEPSE Market Intelligence</h2>
<div class=muted>Current: <span class="badge official">Official NEPSE</span> · History/analytics: <span class="badge third">NEPSE Portfolio Tracker · third-party</span></div>
<div class=tabs id=tabs></div>
<section id=overview></section>
<section id=stocks></section>
<section id=compare></section>
<section id=sectors></section>
<section id=chart></section>
<section id=panel></section>
</div><script>
const TABS=[["overview","Overview"],["stocks","Stocks"],["compare","Compare"],["sectors","Sectors"],["chart","Chart"],["panel","Fundamentals/Dividends/Research"]];
let CUR="overview";
document.getElementById('tabs').innerHTML=TABS.map(([id,l])=>`<button data-t="${id}" onclick="go('${id}')">${l}</button>`).join('');
function go(t){CUR=t;document.querySelectorAll('.tabs button').forEach(b=>b.className=b.dataset.t===t?'on':'');
 document.querySelectorAll('section').forEach(s=>s.className=s.id===t?'on':'');R[t]&&R[t]();}
async function j(u){const r=await fetch(u);return r.json();}
const num=v=>v==null?'—':(+v).toLocaleString();
const R={};
R.overview=async()=>{const d=await j('/api/v1/market/workspace/overview');const o=d.official||{};
 document.getElementById('overview').innerHTML=`<div class=row><span class="badge official">Official NEPSE</span>
 <span class=muted>${d.official_state}</span></div>
 <div class=cards>${[['Index',o.nepse_index],['Change',(o.index_change??'—')+' ('+(o.index_change_percent??'—')+'%)'],
 ['Turnover',num(o.total_turnover)],['Volume',num(o.total_volume)],['Advancers',o.advancers],['Decliners',o.decliners],
 ['Unchanged',o.unchanged],['Status',o.market_status]].map(([k,v])=>`<div class=card><span class=muted>${k}</span><b>${v??'—'}</b></div>`).join('')}</div>
 <div class=muted style="margin-top:6px">Observed: ${o.source_as_of||'—'} · freshness ${o.freshness||'—'}</div>`;};
R.stocks=async()=>{const el=document.getElementById('stocks');
 el.innerHTML=`<div class=row>Sort:<select id=ss onchange="R.stocks()">
 ${['turnover','volume','gain','decline','pe','market_cap'].map(s=>`<option ${s==(window._ss||'turnover')?'selected':''}>${s}</option>`).join('')}</select>
 <span class=muted>official LTP where observed; else tracker</span></div><div id=stbody>loading…</div>`;
 window._ss=document.getElementById('ss').value;
 const d=await j('/api/v1/market/workspace/stocks?limit=30&sort='+window._ss);
 document.getElementById('stbody').innerHTML=`<div class=muted>${d.count} securities</div><table>
 <tr><th>Symbol</th><th>LTP</th><th>%Chg</th><th>Volume</th><th>Turnover</th><th>Sector</th><th>P/E</th></tr>
 ${(d.rows||[]).map(r=>`<tr><td>${r.symbol} ${r.ltp_source==='OFFICIAL_PAGE_OBSERVED'?'<span class="badge official">O</span>':''}</td>
 <td>${num(r.ltp)}</td><td>${r.percent_change??'—'}</td><td>${num(r.volume)}</td><td>${num(r.turnover)}</td>
 <td style="text-align:left">${r.sector||'—'}</td><td>${r.pe_ratio??'—'}</td></tr>`).join('')}</table>`;};
R.sectors=async()=>{const d=await j('/api/v1/market/workspace/sectors?sort=change');
 document.getElementById('sectors').innerHTML=`<div class=muted>Derived sector analytics (not an official sector index)</div>
 <table><tr><th>Sector</th><th>%Chg</th><th>Turnover</th><th>Volume</th><th>Up</th><th>Down</th><th>Cos</th></tr>
 ${(d.sectors||[]).map(s=>`<tr><td>${s.sector}</td><td>${s.sector_percentage_change??'—'}</td>
 <td>${num(s.aggregate_turnover)}</td><td>${num(s.aggregate_volume)}</td><td>${s.advancers}</td>
 <td>${s.decliners}</td><td>${s.company_count}</td></tr>`).join('')}</table>`;};
R.compare=async()=>{const el=document.getElementById('compare');
 if(!el.dataset.init){el.dataset.init=1;el.innerHTML=`<div class=row>
 <input id=csyms value="NABIL,API,AKPL,HDL" size=24>
 <select id=crange>${['1M','3M','1Y'].map(r=>`<option ${r==='1Y'?'selected':''}>${r}</option>`).join('')}</select>
 <button onclick="drawCompare()">Compare</button></div><div id=cmeta class=muted></div><svg id=csvg viewBox="0 0 1000 320" preserveAspectRatio="none"></svg><div id=cleg></div>`;}
 drawCompare();};
async function drawCompare(){const s=document.getElementById('csyms').value,r=document.getElementById('crange').value;
 const d=await j(`/api/v1/market/workspace/compare?symbols=${encodeURIComponent(s)}&range=${r}`);
 if(!d.series||!d.series.length){document.getElementById('cmeta').textContent='no overlapping data';document.getElementById('csvg').innerHTML='';return;}
 document.getElementById('cmeta').textContent=`Normalized % change · ${d.common_start}→${d.common_end} · ${d.series[0].points.length} pts`;
 const cols=['#58a6ff','#3fb950','#f0883e','#db61a2'];const W=1000,H=320,pad=8;
 let all=[];d.series.forEach(se=>se.points.forEach(p=>all.push(+p[1])));const mn=Math.min(...all),mx=Math.max(...all);
 const n=d.series[0].points.length;const X=i=>pad+(n<2?W/2:i/(n-1)*(W-2*pad));const Y=v=>H-pad-((v-mn)/((mx-mn)||1))*(H-2*pad);
 let svg=`<line x1=0 y1="${Y(0)}" x2="${W}" y2="${Y(0)}" stroke="#30363d"/>`;
 d.series.forEach((se,k)=>{let path='';se.points.forEach((p,i)=>{path+=(i?'L':'M')+X(i)+' '+Y(+p[1])+' ';});
  svg+=`<path d="${path}" fill=none stroke="${cols[k%4]}" stroke-width="1.5"/>`;});
 document.getElementById('csvg').innerHTML=svg;
 document.getElementById('cleg').innerHTML=d.series.map((se,k)=>`<span style="color:${cols[k%4]}">■ ${se.symbol} ${se.change_pct}%</span>`).join('  ');}
R.chart=async()=>{const el=document.getElementById('chart');
 if(!el.dataset.init){el.dataset.init=1;el.innerHTML=`<div class=row><input id=chsym value=NABIL size=8>
 <select id=chr>${['1M','3M','6M','1Y','5Y'].map(r=>`<option ${r==='1Y'?'selected':''}>${r}</option>`).join('')}</select>
 <button onclick="drawChart()">Load</button><span id=chbadge class="badge third"></span></div>
 <div id=chmeta class=muted></div><svg id=chp viewBox="0 0 1000 300" preserveAspectRatio=none></svg>
 <svg id=chv viewBox="0 0 1000 70" preserveAspectRatio=none style="margin-top:5px"></svg>
 <div class=pit id=chpit></div>`;}drawChart();};
async function drawChart(){const sym=document.getElementById('chsym').value.toUpperCase(),r=document.getElementById('chr').value;
 const d=await j(`/api/v1/market/tracker/chart?symbol=${sym}&range=${r}&indicators=sma`);
 if(!d.available){document.getElementById('chmeta').textContent=d.status||'unavailable';return;}
 document.getElementById('chbadge').textContent='NEPSE Portfolio Tracker · third-party';
 document.getElementById('chmeta').textContent=`${sym} ${d.range} ${d.first_date}→${d.last_date} · latest ${d.latest_close}`;
 document.getElementById('chpit').textContent='⚠ '+d.point_in_time_capability+' — descriptive only; current LTP authority: Official NEPSE.';
 const o=d.ohlc;const W=1000,H=300,pad=6;const mn=Math.min(...o.map(p=>+p.low)),mx=Math.max(...o.map(p=>+p.high));
 const X=i=>pad+(o.length<2?W/2:i/(o.length-1)*(W-2*pad)),Y=v=>H-pad-((v-mn)/((mx-mn)||1))*(H-2*pad);
 let s='';const cw=Math.max(1,(W-2*pad)/o.length*0.6);
 o.forEach((p,i)=>{const up=+p.close>=+p.open,c=up?'#3fb950':'#f85149';
  s+=`<line x1="${X(i)}" y1="${Y(+p.high)}" x2="${X(i)}" y2="${Y(+p.low)}" stroke="${c}"/>`;
  const yo=Y(+p.open),yc=Y(+p.close);s+=`<rect x="${X(i)-cw/2}" y="${Math.min(yo,yc)}" width="${cw}" height="${Math.max(1,Math.abs(yc-yo))}" fill="${c}"/>`;});
 const sm=(d.indicators.sma_20||{}).series;if(sm){let pa='';sm['sma_20'].forEach((v,i)=>{if(v==null)return;pa+=(pa?'L':'M')+X(i)+' '+Y(v)+' ';});s+=`<path d="${pa}" fill=none stroke="#58a6ff" stroke-width=1.3/>`;}
 document.getElementById('chp').innerHTML=s;
 const vmx=Math.max(...o.map(p=>+p.volume),1);let vs='';o.forEach((p,i)=>{const h=+p.volume/vmx*60;vs+=`<rect x="${X(i)-cw/2}" y="${70-h}" width="${cw}" height="${h}" fill="#30475e"/>`;});
 document.getElementById('chv').innerHTML=vs;}
R.panel=async()=>{const el=document.getElementById('panel');
 if(!el.dataset.init){el.dataset.init=1;el.innerHTML=`<div class=row><input id=psym value=NABIL size=8><button onclick="loadPanel()">Load</button></div><div id=pbody></div>`;}loadPanel();};
async function loadPanel(){const sym=document.getElementById('psym').value.toUpperCase();
 const d=await j(`/api/v1/market/workspace/panel?symbol=${sym}&range=1Y`);const f=(d.chart||{}).fundamentals||{};const rec=d.reconciliation||{};
 const divs=((d.chart||{}).dividends||[]);
 document.getElementById('pbody').innerHTML=`
 <h3>Reconciliation</h3><div class=card>Official ${rec.official_ltp??'—'} · Tracker ${rec.tracker_ltp??'—'} · <b>${rec.verdict||'—'}</b> <span class=muted>(official authority)</span></div>
 <h3>Fundamentals <span class="badge third">third-party</span></h3><div class=cards>
 ${[['EPS',f.eps],['P/E',f.pe_ratio],['P/B',f.pb_ratio],['Div yield',f.dividend_yield],['Mkt cap',num(f.market_cap)],['52w H',f.week52_high],['52w L',f.week52_low],['Sector',f.sector]].map(([k,v])=>`<div class=card><span class=muted>${k}</span><b>${v??'—'}</b></div>`).join('')}</div>
 <h3>Dividends</h3><table><tr><th>FY</th><th>Cash</th><th>Bonus</th><th>Total</th></tr>
 ${divs.slice(0,8).map(x=>`<tr><td>${x.fiscal_year||'—'}</td><td>${x.cash_dividend??'—'}</td><td>${x.bonus_share??'—'}</td><td>${x.total_dividend??'—'}</td></tr>`).join('')||'<tr><td colspan=4 class=muted>none</td></tr>'}</table>
 <h3>Research</h3><div class=muted>${(d.research||{}).state} · ${((d.research||{}).events||[]).length} events (frozen Research Surface)</div>
 <h3>Catalysts</h3><div class=muted>${(d.catalysts||{}).state} · ${((d.catalysts||{}).catalysts||[]).length} (Fusion; historical reaction = canonical/MD-1 only)</div>
 <h3>Portfolio</h3><div class=card>${(d.portfolio||{}).message}</div>`;}
go('overview');
</script></body></html>""")


# ── routing fix: keep the SPA catch-all StaticFiles mount at "/" LAST ──────────
# Starlette matches routes in list order; a Mount at "/" matches every path, so any
# route registered after it (the market/nepse/tracker/workspace HTML + API routes
# above) would be shadowed and 404. Move root mounts to the end so explicit routes
# resolve first and the SPA remains the final fallback. Idempotent.
try:
    from starlette.routing import Mount as _Mount
    _rr = app.router.routes
    _roots = [r for r in _rr if isinstance(r, _Mount) and getattr(r, "path", "") in ("", "/")]
    for _m in _roots:
        _rr.remove(_m)
        _rr.append(_m)
except Exception:
    pass


# ── M — SAATHIOS_FINANCIAL_BROWSER (security/capability shell; read-only) ───────
# Owner interacts with financial sites; the agent gets only explicit READ capability.
# Never an execution path. Auth-gated. Sync def → threadpool. No credentials handled here.
@app.get("/api/v1/finance/providers")
def fin_providers():
    try:
        from saathi.platform.finance.capability_matrix import matrix
        from saathi.platform.finance.policy import POLICIES
        m = matrix()
        m["policies"] = {p.value: {"allowed_domains": list(pol.allowed_domains),
                                   "default_mode": pol.default_interaction_mode.value,
                                   "owner_only_regions": list(pol.owner_only_regions),
                                   "readable_regions": list(pol.readable_regions),
                                   "downloads": pol.allowed_downloads, "uploads": pol.allowed_uploads,
                                   "navigation": pol.navigation_policy}
                         for p, pol in POLICIES.items()}
        return m
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/sessions")
def fin_sessions():
    try:
        from saathi.platform.finance.session import get_manager
        return {"sessions": get_manager().list()}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/sessions/open")
def fin_open(body: dict = Body(...)):
    try:
        from saathi.platform.finance.session import get_manager
        from saathi.platform.finance.policy import Provider
        prov = str(body.get("provider", "")).upper()
        if prov not in Provider.__members__:
            return JSONResponse({"error": "unknown provider"}, status_code=400)
        s = get_manager().open(Provider[prov])
        # NOTE: opening a session does NOT authenticate; owner must authenticate in-browser.
        return {"session": s.to_public(), "owner_action": "OWNER_AUTHENTICATION_REQUIRED"}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/sessions/kill")
def fin_kill(body: dict = Body(...)):
    try:
        from saathi.platform.finance.session import get_manager
        m = get_manager()
        if body.get("all"):
            return {"killed": m.kill_all()}
        return {"killed": bool(m.kill(str(body.get("session_id", ""))))}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/audit")
def fin_audit(n: int = 50):
    try:
        from saathi.platform.finance.audit import tail
        return {"audit": tail(min(max(n, 1), 500))}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/finance/browser", response_class=HTMLResponse, include_in_schema=False)
def finance_browser_page():
    """Native Financial Browser shell — provider cards + policy. No trade controls, no
    embedded financial account site, no credential handling in the page."""
    return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8>
<title>SaathiOS — Financial Browser</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font:14px system-ui;margin:0;background:#0d1117;color:#e6edf3}
.wrap{max-width:1000px;margin:0 auto;padding:16px}h2{margin:0}.muted{color:#8b949e;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:14px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px}
.card h3{margin:0 0 6px}.k{color:#8b949e}.v{font-weight:600}
.row{display:flex;justify-content:space-between;padding:2px 0;font-size:13px}
.b{padding:1px 7px;border-radius:9px;font-size:11px}
.ok{background:#1f6f3f}.warn{background:#5a3a12}.no{background:#7d2222}.un{background:#3a3f47}
button{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:5px 10px;cursor:pointer;margin-top:8px}
.kill{background:#7d2222;border-color:#7d2222}
.note{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px;margin-top:14px;font-size:12px;color:#8b949e}
</style></head><body><div class=wrap>
<h2>Financial Browser</h2>
<div class=muted>Specialized read-only financial surface. You control the browser and enter all
credentials yourself; SaathiOS receives only explicit read capabilities. No trading, no
withdrawals, no order forms.</div>
<div class=grid id=cards>loading…</div>
<button class=kill onclick="killAll()">Kill switch — revoke all agent reads</button>
<div class=note id=note></div>
</div><script>
const CAPBADGE={PUBLIC_MARKET_DATA:'ok',READ_ONLY_API:'ok',READ_ONLY_MCP:'warn',AGENT_READ_ALLOWED:'ok',
 OWNER_BROWSER_SESSION:'warn',OWNER_ONLY_INTERACTION:'warn',PROHIBITED_AGENT_ACTION:'no',UNSUPPORTED:'no',UNKNOWN:'un'};
function badge(v){return `<span class="b ${CAPBADGE[v]||'un'}">${v}</span>`;}
async function load(){
 const r=await fetch('/api/v1/finance/providers');const d=await r.json();
 if(d.error){document.getElementById('cards').textContent=d.error;return;}
 const P=d.providers;
 document.getElementById('cards').innerHTML=Object.keys(P).map(name=>{const c=P[name];
  return `<div class=card><h3>${name}</h3>
  <div class=row><span class=k>Public market data</span>${badge(c.public_market_data)}</div>
  <div class=row><span class=k>Read-only API</span>${badge(c.read_only_api)}</div>
  <div class=row><span class=k>Read-only MCP</span>${badge(c.read_only_mcp)}</div>
  <div class=row><span class=k>Account data</span>${badge(c.account_data)}</div>
  <div class=row><span class=k>Agent read</span>${badge(c.agent_read)}</div>
  <div class=row><span class=k>Agent actions</span>${badge(c.agent_actions)}</div>
  <div class=row><span class=k>Embed</span><span class="b ${c.embed&&c.embed.includes('BLOCKED')?'no':'un'}">${c.embed}</span></div>
  <div class=muted style="margin-top:6px">${c.note||''}</div>
  <button onclick="openS('${name}')">Open (owner authenticates)</button></div>`;}).join('');
 document.getElementById('note').innerHTML='Trading, withdrawals, transfers, leverage, API-key '+
 'management and order forms are structurally blocked for the agent (PROHIBITED_AGENT_ACTION). '+
 'Credentials/OTP/2FA are OWNER_PRIVATE_INPUT — never observed, logged, or sent to any model. '+
 'Portfolio MCP is deferred pending an owner-supplied key. Any future execution stays: proposal → '+
 'Trading Guardian → approval → ExecutionGateway.';
}
async function openS(p){const r=await fetch('/api/v1/finance/sessions/open',{method:'POST',
 headers:{'content-type':'application/json'},body:JSON.stringify({provider:p})});const d=await r.json();
 alert(p+': '+(d.owner_action||d.error||'opened')+' — enter your own credentials in the provider site; SaathiOS will not.');}
async function killAll(){const r=await fetch('/api/v1/finance/sessions/kill',{method:'POST',
 headers:{'content-type':'application/json'},body:JSON.stringify({all:true})});const d=await r.json();
 alert('Killed '+(d.killed||0)+' session(s); agent read capability revoked.');}
load();
</script></body></html>""")


# Re-assert SPA catch-all mount stays LAST (finance routes were added after the prior
# reorder). Idempotent; keeps all explicit routes reachable.
try:
    from starlette.routing import Mount as _Mount2
    _rr2 = app.router.routes
    for _m2 in [r for r in _rr2 if isinstance(r, _Mount2) and getattr(r, "path", "") in ("", "/")]:
        _rr2.remove(_m2)
        _rr2.append(_m2)
except Exception:
    pass


# ── M — BINANCE_READONLY_ACCOUNT_ADAPTER (read-only; no trading/withdraw path) ──
@app.get("/api/v1/finance/binance/status")
def binance_status():
    try:
        from saathi.platform.finance.crypto_portfolio import get_connection
        c = get_connection()
        return {"provider": "BINANCE", "state": c.state.value, "read_only": True,
                "note": "connect a read-only API key via the SaathiOS secret store (never in chat)"}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/binance/portfolio")
def binance_portfolio(refresh: int = 0):
    try:
        from saathi.platform.finance.crypto_portfolio import get_connection, crypto_view
        c = get_connection()
        snap, st = c.snapshot(force=bool(refresh))
        if snap is None:
            return JSONResponse({"state": st.value, "available": False,
                                 "owner_action": "OWNER_BINANCE_READONLY_CREDENTIAL_REQUIRED"
                                 if st.value == "OWNER_ACTION_REQUIRED" else None}, status_code=200)
        return {"state": st.value, "available": True, "view": crypto_view(snap)}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/binance/disconnect")
def binance_disconnect():
    try:
        from saathi.platform.finance.crypto_portfolio import get_connection
        get_connection().disconnect()
        return {"state": "NOT_CONNECTED"}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/binance/kill")
def binance_kill():
    try:
        from saathi.platform.finance.crypto_portfolio import get_connection
        get_connection().kill()
        return {"state": "NOT_CONNECTED", "killed": True}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/binance/chat")
def binance_chat(q: str = ""):
    try:
        from saathi.platform.finance.crypto_portfolio import get_connection, crypto_view, chat_answer
        c = get_connection()
        snap, st = c.snapshot()
        view = crypto_view(snap) if snap is not None else None
        return chat_answer(q, view=view)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/finance/crypto", response_class=HTMLResponse, include_in_schema=False)
def finance_crypto_page():
    """Native crypto portfolio view. Read-only. No Buy/Sell/Swap/Withdraw/Transfer controls."""
    return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8>
<title>SaathiOS — Crypto Portfolio</title><meta name=viewport content="width=device-width,initial-scale=1">
<style>body{font:14px system-ui;margin:0;background:#0d1117;color:#e6edf3}.wrap{max-width:900px;margin:0 auto;padding:16px}
.muted{color:#8b949e;font-size:12px}.b{padding:2px 8px;border-radius:10px;font-size:11px;background:#1f3a5f}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px}.card b{display:block;font-size:18px}
table{width:100%;border-collapse:collapse}th,td{padding:5px 8px;border-bottom:1px solid #21262d;text-align:right;font-size:13px}
th:first-child,td:first-child{text-align:left}th{color:#8b949e}</style></head><body><div class=wrap>
<h2>Crypto Portfolio <span class=b>Binance · read-only</span></h2>
<div class=muted id=meta>loading…</div><div class=cards id=cards></div>
<table><thead><tr><th>Asset</th><th>Qty</th><th>Available</th><th>Locked</th><th>Price</th><th>Value</th><th>Alloc</th></tr></thead><tbody id=rows></tbody></table>
<p class=muted id=lims></p></div><script>
async function load(){const r=await fetch('/api/v1/finance/binance/portfolio');const d=await r.json();
 if(!d.available){document.getElementById('meta').textContent=(d.owner_action||d.state)+
  ' — connect a read-only API key via the SaathiOS secret store (never in chat).';return;}
 const v=d.view;document.getElementById('meta').textContent='State '+d.state+' · '+v.asset_count+' assets · '+v.freshness+
  ' · cost basis '+v.cost_basis+' · P/L '+v.pnl;
 document.getElementById('cards').innerHTML=[['Total ('+v.valuation_currency+')',v.total_value],
  ['Stablecoin %',v.stablecoin_allocation_pct],['Crypto %',v.crypto_allocation_pct],['Locked %',v.locked_allocation_pct]]
  .map(([k,x])=>'<div class=card><span class=muted>'+k+'</span><b>'+(x??'—')+'</b></div>').join('');
 document.getElementById('rows').innerHTML=v.positions.map(p=>'<tr><td>'+p.asset+' <span class=muted>'+p.asset_type+'</span></td><td>'+
  p.quantity+'</td><td>'+p.available+'</td><td>'+p.locked+'</td><td>'+(p.price??'—')+'</td><td>'+(p.market_value??'PRICE_UNAVAILABLE')+
  '</td><td>'+(p.allocation_pct??'—')+'%</td></tr>').join('');
 document.getElementById('lims').textContent='Limitations: '+(v.limitations||[]).join(' · ');}
load();</script></body></html>""")


# keep SPA catch-all mount LAST (binance routes added after prior reorder)
try:
    from starlette.routing import Mount as _Mount3
    _rr3 = app.router.routes
    for _m3 in [r for r in _rr3 if isinstance(r, _Mount3) and getattr(r, "path", "") in ("", "/")]:
        _rr3.remove(_m3); _rr3.append(_m3)
except Exception:
    pass


# ── M — BROWSER_AUTHENTICATED_FINANCIAL_PORTFOLIO_RUNTIME (owner login; read-only) ─
# Owner drives a real provider browser + enters all credentials; agent only reads (after
# owner enables Saathi Read) via a deterministic observer. No credential/DOM/screenshot to
# any model. No agent click/type/navigate/submit. No execution. Auth-gated.
def _fbr_authed(request) -> bool:
    """Financial-browser routes are owner-only, authenticated loopback (Phase 3)."""
    return _is_authed(request) or _is_local(request)


@app.get("/api/v1/finance/browser/runtimes")
def fbr_runtimes(request: Request):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        return {"runtimes": get_runtime_manager().list()}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/open")
def fbr_open(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        from saathi.platform.finance.policy import Provider
        prov = str(body.get("provider", "")).upper()
        if prov not in Provider.__members__:
            return JSONResponse({"error": "unknown provider"}, status_code=400)
        rt = get_runtime_manager().open(Provider[prov])
        return {"runtime": rt.to_public(),
                "owner_action": "OWNER_FINANCIAL_LOGIN_REQUIRED",
                "note": "log in yourself in the opened browser; SaathiOS never enters credentials"}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/mark-authenticated")
def fbr_mark_auth(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    # OWNER action: confirm they finished logging in (SaathiOS never reads credentials).
    try:
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        rt = get_runtime_manager().mark_owner_authenticated(str(body.get("runtime_id", "")))
        return rt.to_public() if rt else JSONResponse({"error": "no runtime"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/saathi-read")
def fbr_saathi_read(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        m = get_runtime_manager()
        rid = str(body.get("runtime_id", "")); on = bool(body.get("on"))
        rt = (m.set_saathi_read(rid, True) if on else m.set_saathi_read(rid, False))
        return rt.to_public() if rt else JSONResponse({"error": "no runtime"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/close")
def fbr_close(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        rid = str(body.get("runtime_id", ""))
        closed = bool(get_runtime_manager().close(rid))
        if closed:                                          # invalidate bridge cache on close
            from saathi.platform.finance.observation_bridge import get_observation_service
            rt = get_runtime_manager().get(rid)
            get_observation_service().invalidate(rt.provider if rt else None)
        return {"closed": closed}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/browser/portfolio")
def fbr_portfolio(request: Request, runtime_id: str):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        m = get_runtime_manager()
        rt = m.get(runtime_id)
        if rt is None:
            return JSONResponse({"error": "no runtime"}, status_code=404)
        # Deterministic read-only observation of the owner-authenticated live page.
        from saathi.platform.finance.browser_portfolio import read_portfolio
        out = read_portfolio(runtime_id, manager=m)
        out["runtime"] = rt.to_public()
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


# ── Observation Bridge (Phase 24): normalized observations, never browser control ──
@app.get("/api/v1/finance/browser/{provider}/status")
def fbr_obs_status(request: Request, provider: str, runtime_id: str | None = None):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.observation_bridge import get_observation_service
        return get_observation_service().status(provider, runtime_id)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


def _record_portfolio_memory(provider: str, env: dict) -> None:
    """Record structured Financial Memory from a successful observation (never secrets/raw).
    Best-effort: memory failures never break the read."""
    try:
        if not (env or {}).get("available") or not env.get("view"):
            return
        from saathi.platform.finance import financial_memory as fm
        store = fm.get_memory_store()
        view = env["view"]; rid = env.get("runtime_id", "")
        store.record(fm.portfolio_evidence(view, provider=provider.upper(), runtime_id=rid,
                                           session_id=rid))
        for ev in fm.position_evidences(view, provider=provider.upper(), runtime_id=rid,
                                        session_id=rid):
            store.record(ev)
        # market facts (current-price authority) for reconciled positions
        for p in view.get("positions", []):
            if p.get("current_price") and p.get("current_price_source"):
                store.record(fm.market_evidence(
                    provider=provider.upper(),
                    instrument_id=p.get("instrument_id") or p.get("symbol", ""),
                    ltp=p.get("current_price"), source_type=p.get("current_price_source")))
    except Exception:
        pass


@app.post("/api/v1/finance/browser/{provider}/observe-portfolio")
def fbr_obs_portfolio(request: Request, provider: str, body: dict = Body(default={})):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.observation_bridge import get_observation_service
        env = get_observation_service().observe_portfolio(provider, (body or {}).get("runtime_id"))
        _record_portfolio_memory(provider, env)     # structured memory (Milestone B)
        return env
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/{provider}/observe-structure")
def fbr_obs_structure(request: Request, provider: str, body: dict = Body(default={})):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.observation_bridge import get_observation_service
        b = body or {}
        return get_observation_service().observe_structure(
            provider, b.get("runtime_id"),
            authorize_structure_inspection=bool(b.get("authorize_structure_inspection")))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/browser/{provider}/evidence")
def fbr_obs_evidence(request: Request, provider: str, runtime_id: str | None = None):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.observation_bridge import get_observation_service
        return get_observation_service().evidence(provider, runtime_id)
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


# ── OWNER-ONLY embedded viewport (Plane 1 OWNER_VISUAL + Plane 2 OWNER_INPUT) ──────
# These endpoints stream the owner's live provider page and forward the owner's own
# mouse/keyboard/navigation. They are OWNER_INPUT, gated by owner session + loopback +
# an existing REAL provider runtime. They are deliberately NOT agent tools: they appear
# in no agent/LLM tool registry, no MCP surface, and grant no agent browser authority.
def _viewport_gate(request, provider: str):
    """Return (Provider, runtime, err_response). err_response set → stop.
    Owner-authenticated only. The backend binds loopback (127.0.0.1) so it is already
    local-only; requests arrive via the same-origin Next proxy (which stamps
    x-forwarded-*), so we authenticate the owner session/token rather than requiring a
    bare-loopback peer. OWNER_INPUT — never an agent path."""
    if not _fbr_authed(request):
        return None, None, JSONResponse({"error": "unauthorized"}, status_code=401)
    from saathi.platform.finance.browser_runtime import get_runtime_manager
    from saathi.platform.finance.policy import Provider
    prov = str(provider).upper()
    if prov not in Provider.__members__:
        return None, None, JSONResponse({"error": "unknown provider"}, status_code=400)
    p = Provider[prov]
    m = get_runtime_manager()
    rt = m.runtime_for_provider(p)
    if rt is None:
        return None, None, JSONResponse({"state": "BROWSER_NOT_OPEN"}, status_code=409)
    if not m.is_real_runtime(p):
        return None, None, JSONResponse({"state": "DISPLAY_UNAVAILABLE"}, status_code=409)
    return p, rt, None


# ── Financial Memory (structured, provenance-first; read + owner controls) ────────
@app.get("/api/v1/finance/memory/latest")
def fin_memory_latest(request: Request, provider: str | None = None,
                      evidence_type: str | None = None, instrument_id: str | None = None,
                      limit: int = 20):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.financial_memory import get_memory_store
        rows = get_memory_store().latest(provider=provider, evidence_type=evidence_type,
                                         instrument_id=instrument_id, limit=min(int(limit), 100))
        return {"evidence": rows, "count": len(rows)}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/memory/history")
def fin_memory_history(request: Request, instrument_id: str, limit: int = 50):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.financial_memory import get_memory_store
        return {"instrument_id": instrument_id,
                "history": get_memory_store().history(instrument_id, limit=min(int(limit), 200))}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/memory/status")
def fin_memory_status(request: Request, provider: str | None = None):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.financial_memory import get_memory_store, EvidenceType
        st = get_memory_store()
        latest = st.latest(provider=provider, evidence_type=EvidenceType.PORTFOLIO_SNAPSHOT.value, limit=1)
        top = latest[0] if latest else None
        return {"total": st.count(provider=provider),
                "latest_portfolio": ({"observed_at": top["observed_at"], "provider": top["provider"],
                                      "source_type": top["source_type"], "freshness": top["freshness"],
                                      "canonical_ref": top["canonical_ref"]} if top else None)}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/memory/clear-session")
def fin_memory_clear_session(request: Request, body: dict = Body(...)):
    if not _fbr_authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        from saathi.platform.finance.financial_memory import get_memory_store
        sid = str((body or {}).get("session_id", ""))
        if not sid:
            return JSONResponse({"error": "session_id required"}, status_code=400)
        return {"cleared": get_memory_store().clear_session(sid)}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/{provider}/viewport/start")
def fbr_vp_start(request: Request, provider: str, body: dict = Body(default={})):
    p, rt, err = _viewport_gate(request, provider)
    if err:
        return err
    try:
        from saathi.platform.finance import viewport as vp
        from saathi.platform.finance.browser_runtime import get_runtime_manager
        s = vp.get_or_create(p, rt.runtime_id, get_runtime_manager())
        return s.start()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.get("/api/v1/finance/browser/{provider}/viewport/frame")
def fbr_vp_frame(request: Request, provider: str):
    p, rt, err = _viewport_gate(request, provider)
    if err:
        return err
    try:
        from saathi.platform.finance import viewport as vp
        s = vp.get(p)
        if s is None:
            return JSONResponse({"ok": False, "state": "BROWSER_NOT_OPEN"}, status_code=409)
        return s.frame()
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/{provider}/viewport/input")
def fbr_vp_input(request: Request, provider: str, body: dict = Body(...)):
    p, rt, err = _viewport_gate(request, provider)
    if err:
        return err
    try:
        from saathi.platform.finance import viewport as vp
        s = vp.get(p)
        if s is None:
            return JSONResponse({"ok": False, "state": "BROWSER_NOT_OPEN"}, status_code=409)
        return s.owner_input(dict(body or {}))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/{provider}/viewport/navigate")
def fbr_vp_navigate(request: Request, provider: str, body: dict = Body(...)):
    p, rt, err = _viewport_gate(request, provider)
    if err:
        return err
    try:
        from saathi.platform.finance import viewport as vp
        s = vp.get(p)
        if s is None:
            return JSONResponse({"ok": False, "state": "BROWSER_NOT_OPEN"}, status_code=409)
        b = body or {}
        return s.navigate(str(b.get("action", "")), b.get("url"))
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


@app.post("/api/v1/finance/browser/{provider}/viewport/stop")
def fbr_vp_stop(request: Request, provider: str, body: dict = Body(default={})):
    p, rt, err = _viewport_gate(request, provider)
    if err:
        return err
    try:
        from saathi.platform.finance import viewport as vp
        vp.drop(p)
        return {"ok": True, "state": "CLOSED"}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=503)


# keep SPA catch-all mount LAST
try:
    from starlette.routing import Mount as _Mount4
    _rr4 = app.router.routes
    for _m4 in [r for r in _rr4 if isinstance(r, _Mount4) and getattr(r, "path", "") in ("", "/")]:
        _rr4.remove(_m4); _rr4.append(_m4)
except Exception:
    pass


# Entrypoint MUST stay at the very end: all routes above are now registered before
# main() calls the blocking uvicorn.run(). (Importing `saathi.server:app` never runs
# this block; `python -m saathi.server` runs it after full module execution.)
if __name__ == "__main__":
    main()
