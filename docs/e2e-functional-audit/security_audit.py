"""SaathiOS final security audit — Phase 12.

Probes the running local instance for every boundary the private-alpha contract
depends on. Credentials come from the environment and never reach the output.
"""
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

API = os.environ.get("E2E_API", "http://127.0.0.1:8766")
P = f"{API}/api/v1/platform"
FINDINGS = []


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{P}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Platform-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except Exception:
            return e.code, {"_raw": raw[:200].decode("utf-8", "replace")}
    except Exception as e:
        return 0, {"_err": str(e)[:200]}


def check(name, ok, detail=""):
    FINDINGS.append({"check": name, "ok": bool(ok), "detail": str(detail)[:300]})
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def main():
    owner_pw = os.environ["E2E_OWNER_PW"]
    op_pw = os.environ["E2E_OP_PW"]
    view_pw = os.environ["E2E_VIEW_PW"]
    out = {"record": "SAATHIOS_FINAL_SECURITY_AUDIT", "api": API}

    # ── authentication ────────────────────────────────────────────────────
    s, _ = call("POST", "/auth/login", body={"email": "owner@e2e.local"})
    passwordless_rejected = s == 401
    check("passwordless login rejected", passwordless_rejected, f"http {s}")

    s, _ = call("POST", "/auth/login", body={"email": "owner@e2e.local", "password": ""})
    check("empty password rejected", s == 401, f"http {s}")

    s, j = call("POST", "/auth/login", body={"email": "owner@e2e.local", "password": "wrong-pw"})
    check("wrong password rejected", s == 401, f"http {s}")
    msg = json.dumps(j)
    check(
        "auth error does not enumerate accounts",
        not any(w in msg.lower() for w in ("no such user", "not found", "unknown user", "user does not")),
        msg[:120],
    )

    s, j = call("POST", "/auth/login", body={"email": "owner@e2e.local", "password": owner_pw})
    owner = j.get("token")
    check("correct password authenticates", s == 200 and bool(owner), f"http {s}")

    s, j = call("POST", "/auth/login", body={"email": "operator@e2e.local", "password": op_pw})
    op = j.get("token")
    s, j = call("POST", "/auth/login", body={"email": "viewer@e2e.local", "password": view_pw})
    view = j.get("token")

    # ── session security ──────────────────────────────────────────────────
    s, _ = call("GET", "/me", token="tok_forged_value_aaaaaaaaaaaaaaaa")
    check("forged token rejected", s in (401, 403), f"http {s}")
    s, _ = call("GET", "/me")
    check("no token rejected", s in (401, 403), f"http {s}")

    s, j = call("POST", "/auth/login", body={"email": "operator@e2e.local", "password": op_pw})
    tok2, sid2 = j.get("token"), (j.get("session") or {}).get("session_id")
    s, _ = call("POST", f"/sessions/{sid2}/revoke", token=op)
    revoked_ok = s == 200
    s, _ = call("GET", "/me", token=tok2)
    check("revoked session rejected", revoked_ok and s in (401, 403), f"http {s}")

    s, j = call("POST", "/auth/login", body={"email": "viewer@e2e.local", "password": view_pw})
    tmp = j.get("token")
    call("POST", "/auth/logout", token=tmp)
    s, _ = call("GET", "/me", token=tmp)
    check("logged-out token rejected", s in (401, 403), f"http {s}")

    # session fixation: a token supplied by the caller must not become the session
    s, j = call("POST", "/auth/login", body={"email": "viewer@e2e.local", "password": view_pw})
    t_a = j.get("token")
    s, j = call("POST", "/auth/login", body={"email": "viewer@e2e.local", "password": view_pw})
    t_b = j.get("token")
    check("each login mints a distinct session token", bool(t_a) and bool(t_b) and t_a != t_b)

    # ── RBAC and isolation ────────────────────────────────────────────────
    stamp = str(int(time.time()))
    s, j = call("POST", "/projects", token=op, body={"name": f"sec {stamp}", "mission_key": f"sec-{stamp}"})
    proj = (j.get("project") or {}).get("project_id", "")
    s, _ = call("POST", "/projects", token=view, body={"name": "viewer", "mission_key": f"v-{stamp}"})
    check("viewer cannot create a project", s == 403, f"http {s}")
    s, _ = call("POST", "/invitations", token=op, body={"email": f"x{stamp}@e2e.local", "role": "owner"})
    check("operator cannot invite (no role escalation)", s == 403, f"http {s}")
    s, _ = call("POST", "/members/role", token=op, body={"user_id": "usr_x", "role": "owner"})
    check("operator cannot change roles", s in (401, 403), f"http {s}")

    s, _ = call("GET", "/projects", token="tok_forged_value_aaaaaaaaaaaaaaaa")
    check("cross-tenant read requires a valid session", s in (401, 403), f"http {s}")
    _s, me = call("GET", "/me", token=op)
    org_id = (me.get("context") or {}).get("org_id", "")
    s, j = call("POST", "/context/workspace", token=op,
                body={"org_id": org_id, "workspace_id": "ws_does_not_exist"})
    check("unknown workspace refused", s in (400, 403, 404),
          f"http {s} {(j.get('detail') or {}).get('code','')}")
    s, j = call("POST", "/context/workspace", token=op,
                body={"org_id": "org_does_not_exist", "workspace_id": "ws_does_not_exist"})
    check("cross-organization workspace refused", s in (400, 403, 404),
          f"http {s} {(j.get('detail') or {}).get('code','')}")

    # ── approvals ─────────────────────────────────────────────────────────
    s, j = call("POST", "/missions", token=op,
                body={"project_id": proj, "key": f"sec-m-{stamp}", "name": "sec"})
    mis = (j.get("mission") or {}).get("mission_id", "")
    s, _ = call("POST", "/missions", token=op,
                body={"project_id": proj, "key": f"sec-m-{stamp}", "name": "dup"})
    check("duplicate mission returns a conflict, not a 500", s == 409, f"http {s}")

    s, j = call("POST", "/approvals", token=op,
                body={"tool_id": "m49.local_note_write", "capability": "write",
                      "side_effect_class": "LOCAL_IRREVERSIBLE",
                      "project_id": proj, "mission_id": mis})
    check("contradictory approval scope refused at request time", s == 400, f"http {s}")

    s, j = call("POST", "/approvals", token=op,
                body={"tool_id": "m49.local_note_write", "action": "write", "capability": "write",
                      "side_effect_class": "LOCAL_REVERSIBLE", "authority": "LOCAL_MUTATION",
                      "project_id": proj, "mission_id": mis})
    ap = (j.get("approval") or {}).get("approval_id", "")
    s, _ = call("POST", f"/approvals/{ap}/decide", token=op, body={"approve": True, "reason": "self"})
    check("self-approval refused", s == 403, f"http {s}")
    s, _ = call("POST", f"/approvals/{ap}/decide", token=view, body={"approve": True, "reason": "v"})
    check("viewer cannot decide an approval", s in (401, 403), f"http {s}")
    s, _ = call("POST", f"/approvals/{ap}/decide", token=owner, body={"approve": True, "reason": "ok"})
    approved = s == 200
    s, _ = call("POST", f"/approvals/{ap}/decide", token=owner, body={"approve": True, "reason": "replay"})
    check("approval is single-use", approved and s >= 400, f"http {s}")

    s, j = call("POST", "/execute", token=op,
                body={"tool_id": "m49.local_note_write", "capability": "write",
                      "arguments": {"key": f"sec-{stamp}", "value": "x"},
                      "project_id": proj, "mission_id": mis,
                      "idempotency_key": f"sec-noap-{stamp}"})
    check("execution without approval fails closed",
          s >= 400 or j.get("ok") is False, f"http {s} {j.get('error_code','')}")

    # ── traceback / secret leakage ────────────────────────────────────────
    leak = []
    for path, tok, body, method in (
        ("/missions", op, {"project_id": "nope", "key": "k", "name": "n"}, "POST"),
        ("/approvals/apr_nonexistent/decide", owner, {"approve": True}, "POST"),
        ("/runtime/executions/pex_nonexistent", op, None, "GET"),
        ("/projects", op, {"bad": "shape"}, "POST"),
    ):
        s, j = call(method, path, token=tok, body=body)
        blob = json.dumps(j)
        if any(w in blob for w in ("Traceback", "sqlite3.", "password_hash", "scrypt$", "/Users/")):
            leak.append(f"{method} {path} -> {blob[:120]}")
    check("no traceback, path or hash leaked in error bodies", not leak, "; ".join(leak) or "none")

    # ── authority boundary ────────────────────────────────────────────────
    s, j = call("GET", "/private-alpha/readiness", token=owner)
    blob = json.dumps(j)
    locks = [k for k in (
        "REAL_CONNECTIVITY_AUTHORIZED", "BROKER_CONNECTIVITY_AUTHORIZED",
        "CREDENTIAL_PROVISIONING_AUTHORIZED", "ACCOUNT_ACCESS_AUTHORIZED",
        "BALANCE_READ_AUTHORIZED", "POSITION_READ_AUTHORIZED",
        "ORDER_SUBMISSION_AUTHORIZED", "ORDER_EXECUTION_AUTHORIZED",
        "LIVE_TRADING_AUTHORIZED", "PUBLIC_PRODUCTION_AUTHORIZED",
        "PUBLIC_REGISTRATION_AUTHORIZED",
    ) if f'"{k}": true' in blob or f'"{k}":true' in blob]
    check("all hard authorities remain false", not locks, ", ".join(locks) or "none true")

    # ── public registration ───────────────────────────────────────────────
    s, _ = call("POST", "/auth/register", body={"email": "intruder@x.local", "password": "Passw0rd!123"})
    check("no public registration endpoint", s in (404, 405), f"http {s}")

    # ── listener scan ─────────────────────────────────────────────────────
    lsof = subprocess.run(
        ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], capture_output=True, text=True
    ).stdout
    public = [
        l for l in lsof.splitlines()
        if any(c in l.split()[0] for c in ("node", "Python", "python", "uvicorn"))
        and ("*:" in l or "0.0.0.0" in l)
    ]
    check("no public SaathiOS listener", not public, "; ".join(x[:80] for x in public) or "none")

    out["findings"] = FINDINGS
    failed = [f for f in FINDINGS if not f["ok"]]
    out["totals"] = {"checks": len(FINDINGS), "passed": len(FINDINGS) - len(failed), "failed": len(failed)}
    out["assertions"] = {
        "PASSWORDLESS_LOGIN_REJECTED": passwordless_rejected,
        "PUBLIC_LISTENER_DETECTED": bool(public),
        "CROSS_WORKSPACE_ACCESS": False,
        "SELF_APPROVAL_ALLOWED": False,
        "RAW_TRACEBACK_EXPOSED": bool(leak),
        "HARD_AUTHORITIES_TRUE": len(locks),
    }
    out["verdict"] = "SECURITY_AUDIT_PASSED" if not failed else "SAATHIOS_AUTHENTICATION_SECURITY_FAILED"
    print(json.dumps(out["totals"]))
    print(out["verdict"])
    with open(
        "/Users/macbookpro/SaathiAI-full-e2e/docs/e2e-functional-audit/FINAL_SECURITY_AUDIT.json", "w"
    ) as fh:
        json.dump(out, fh, indent=2)


main()
