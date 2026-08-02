"""SaathiOS private-alpha API journey driver.

Drives the platform API the way the rendered UI does, recording a pass/fail
verdict per assertion. Credentials come from the environment and are never
written to the evidence output.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("E2E_API", "http://127.0.0.1:8766")
RESULTS = []


def call(method, path, token=None, body=None, expect=None, note=""):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Platform-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except Exception as e:  # connection-level failure
        code, raw = 0, str(e).encode()
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"_raw": raw[:400].decode("utf-8", "replace")}
    ok = True if expect is None else (code in (expect if isinstance(expect, (list, tuple)) else [expect]))
    RESULTS.append({
        "step": note or f"{method} {path}",
        "method": method,
        "path": path,
        "status": code,
        "expected": expect,
        "ok": ok,
    })
    return code, payload


def redact(d):
    if isinstance(d, dict):
        return {k: ("<redacted>" if "token" in k.lower() or "password" in k.lower() else redact(v))
                for k, v in d.items()}
    if isinstance(d, list):
        return [redact(x) for x in d]
    return d


def main():
    owner_pw = os.environ["E2E_OWNER_PW"]
    op_pw = os.environ["E2E_OP_PW"]
    view_pw = os.environ["E2E_VIEW_PW"]
    out = {"base": BASE, "steps": [], "artifacts": {}}

    # ---- 1. owner login -----------------------------------------------------
    code, j = call("POST", "/api/v1/platform/auth/login",
                   body={"email": "owner@e2e.local", "password": owner_pw},
                   expect=200, note="owner valid login")
    owner_tok = j.get("token")
    assert owner_tok, f"owner login returned no token: {redact(j)}"
    org_id = j["session"]["org_id"]
    ws_id = j["session"]["workspace_id"]
    out["artifacts"]["org_id"] = org_id
    out["artifacts"]["workspace_id"] = ws_id

    # ---- 2. invalid login fails closed -------------------------------------
    code, j = call("POST", "/api/v1/platform/auth/login",
                   body={"email": "owner@e2e.local", "password": "definitely-wrong-password"},
                   expect=[401, 403], note="invalid password rejected")
    out["artifacts"]["invalid_login_body"] = redact(j)

    code, j = call("POST", "/api/v1/platform/auth/login",
                   body={"email": "nosuchuser@e2e.local", "password": "definitely-wrong-password"},
                   expect=[401, 403], note="unknown account rejected")
    out["artifacts"]["unknown_account_body"] = redact(j)

    # ---- 3. identity + context ---------------------------------------------
    call("GET", "/api/v1/platform/me", token=owner_tok, expect=200, note="owner /me")
    call("GET", "/api/v1/platform/organizations", token=owner_tok, expect=200, note="list organizations")
    call("GET", "/api/v1/platform/workspaces", token=owner_tok, expect=200, note="list workspaces")
    call("GET", "/api/v1/platform/navigation", token=owner_tok, expect=200, note="navigation")
    call("GET", "/api/v1/platform/modules", token=owner_tok, expect=200, note="module discovery")
    call("GET", "/api/v1/platform/private-alpha", token=owner_tok, expect=200, note="private-alpha banner")

    # ---- 4. unauthenticated access fails closed -----------------------------
    call("GET", "/api/v1/platform/missions", expect=[401, 403], note="missions without token denied")
    call("GET", "/api/v1/platform/audit", token="tok_bogus_value",
         expect=[401, 403], note="missions with bogus token denied")

    # ---- 5. invite operator + viewer ---------------------------------------
    code, j = call("POST", "/api/v1/platform/invitations", token=owner_tok,
                   body={"email": "operator@e2e.local", "role": "operator", "workspace_id": ws_id},
                   expect=200, note="owner invites operator")
    op_code = (j.get("invitation") or {}).get("invite_code")
    code, j = call("POST", "/api/v1/platform/invitations", token=owner_tok,
                   body={"email": "viewer@e2e.local", "role": "viewer", "workspace_id": ws_id},
                   expect=200, note="owner invites viewer")
    view_code = (j.get("invitation") or {}).get("invite_code")
    out["artifacts"]["invite_codes_issued"] = bool(op_code) and bool(view_code)

    code, j = call("POST", "/api/v1/platform/invitations/accept",
                   body={"invite_code": op_code, "name": "E2E Operator", "password": op_pw},
                   expect=200, note="operator accepts invite")
    op_tok = j.get("token")
    code, j = call("POST", "/api/v1/platform/invitations/accept",
                   body={"invite_code": view_code, "name": "E2E Viewer", "password": view_pw},
                   expect=200, note="viewer accepts invite")
    view_tok = j.get("token")

    # re-login both to prove password auth works, not just the accept token
    code, j = call("POST", "/api/v1/platform/auth/login",
                   body={"email": "operator@e2e.local", "password": op_pw},
                   expect=200, note="operator password login")
    op_tok = j.get("token") or op_tok
    code, j = call("POST", "/api/v1/platform/auth/login",
                   body={"email": "viewer@e2e.local", "password": view_pw},
                   expect=200, note="viewer password login")
    view_tok = j.get("token") or view_tok

    out["artifacts"]["roles_provisioned"] = {
        "owner": bool(owner_tok), "operator": bool(op_tok), "viewer": bool(view_tok)}

    # ---- 6. RBAC matrix ------------------------------------------------------
    rbac = []
    def probe(role, tok, method, path, body=None):
        code, _ = call(method, path, token=tok, body=body, expect=None,
                       note=f"rbac {role} {method} {path}")
        rbac.append({"role": role, "method": method, "path": path, "status": code})
        return code

    for role, tok in (("owner", owner_tok), ("operator", op_tok), ("viewer", view_tok)):
        probe(role, tok, "GET", "/api/v1/platform/missions")
        probe(role, tok, "GET", "/api/v1/platform/audit")
        probe(role, tok, "GET", "/api/v1/platform/approvals")
        probe(role, tok, "POST", "/api/v1/platform/projects",
              {"name": f"rbac probe {role}", "description": "rbac"})
        probe(role, tok, "POST", "/api/v1/platform/invitations",
              {"email": f"probe-{role}@e2e.local", "role": "viewer", "workspace_id": ws_id})
    out["artifacts"]["rbac_matrix"] = rbac

    # ---- 7. project + mission ------------------------------------------------
    stamp = str(int(time.time()))
    code, j = call("POST", "/api/v1/platform/projects", token=op_tok,
                   body={"name": "E2E Project", "mission_key": f"e2e-{stamp}"},
                   expect=200, note="operator creates project")
    proj = j.get("project") or j
    proj_id = proj.get("project_id") or proj.get("id")
    out["artifacts"]["project_id"] = proj_id

    code, j = call("GET", "/api/v1/platform/projects", token=op_tok, expect=200,
                   note="operator lists projects")

    code, j = call("POST", "/api/v1/platform/missions", token=op_tok,
                   body={"project_id": proj_id, "key": f"e2e-mission-{stamp}",
                         "name": "E2E Local Mission"},
                   expect=200, note="operator creates mission")
    mission = j.get("mission") or j
    mission_id = mission.get("mission_id") or mission.get("id")
    out["artifacts"]["mission_id"] = mission_id
    out["artifacts"]["mission_create_response"] = redact(j)

    # duplicate-key submission must not silently create a second mission
    call("POST", "/api/v1/platform/missions", token=op_tok,
         body={"project_id": proj_id, "key": f"e2e-mission-{stamp}", "name": "E2E Local Mission"},
         expect=[400, 409], note="duplicate mission key rejected")

    # viewer must not be able to create a mission
    call("POST", "/api/v1/platform/missions", token=view_tok,
         body={"project_id": proj_id, "key": f"e2e-viewer-{stamp}", "name": "viewer mission"},
         expect=[401, 403], note="viewer mission creation denied")

    code, j = call("GET", f"/api/v1/platform/missions/{mission_id}/runtime", token=op_tok,
                   expect=200, note="mission runtime readable")
    out["artifacts"]["mission_runtime"] = redact(j)

    # ---- 8. agent binding + approval flow ------------------------------------
    code, j = call("POST", "/api/v1/platform/agent-bindings", token=owner_tok,
                   body={"agent_id": f"e2e-agent-{stamp}", "name": "E2E Agent",
                         "allowed_tools": ["m49.local_note_write"],
                         "allowed_capabilities": ["write"],
                         "authority_ceiling": "LOCAL_MUTATION"},
                   expect=200, note="owner creates agent binding")
    binding = j.get("binding") or {}
    out["artifacts"]["binding_id"] = binding.get("binding_id")

    code, j = call("POST", "/api/v1/platform/approvals", token=op_tok,
                   body={"tool_id": "m49.local_note_write", "action": "write",
                         "capability": "write", "side_effect_class": "LOCAL_REVERSIBLE",
                         "authority": "LOCAL_MUTATION",
                         "project_id": proj_id, "mission_id": mission_id},
                   expect=200, note="operator requests approval")
    ap = j.get("approval") or j
    approval_id = ap.get("approval_id") or ap.get("id")
    out["artifacts"]["approval_id"] = approval_id
    out["artifacts"]["approval_create_response"] = redact(j)

    assert approval_id, f"approval request produced no id: {redact(j)}"

    # self-approval must be rejected
    call("POST", f"/api/v1/platform/approvals/{approval_id}/decide", token=op_tok,
         body={"approve": True, "reason": "self approval attempt"},
         expect=[400, 403, 409], note="self-approval rejected")
    # viewer must not be able to decide
    call("POST", f"/api/v1/platform/approvals/{approval_id}/decide", token=view_tok,
         body={"approve": True, "reason": "viewer approval attempt"},
         expect=[401, 403], note="viewer approval denied")
    # owner approves
    code, j = call("POST", f"/api/v1/platform/approvals/{approval_id}/decide", token=owner_tok,
                   body={"approve": True, "reason": "e2e owner approval"},
                   expect=200, note="owner approves")
    out["artifacts"]["approval_decide_response"] = redact(j)
    # single-use: second decide must fail
    call("POST", f"/api/v1/platform/approvals/{approval_id}/decide", token=owner_tok,
         body={"approve": True, "reason": "replay"},
         expect=[400, 403, 409], note="approval single-use enforced")

    # ---- 9. execution --------------------------------------------------------
    code, j = call("POST", "/api/v1/platform/execute", token=op_tok,
                   body={"tool_id": "m49.local_note_write",
                         "capability": "write",
                         "arguments": {"key": f"e2e-{stamp}", "value": "certified"},
                         "approval_id": approval_id, "project_id": proj_id,
                         "mission_id": mission_id,
                         "idempotency_key": f"e2e-exec-{stamp}"},
                   expect=200, note="operator executes approved local tool")
    out["artifacts"]["execute_response"] = redact(j)

    # replaying the same idempotency key must not double-execute
    code, j = call("POST", "/api/v1/platform/execute", token=op_tok,
                   body={"tool_id": "m49.local_note_write",
                         "capability": "write",
                         "arguments": {"key": f"e2e-{stamp}", "value": "certified"},
                         "approval_id": approval_id, "project_id": proj_id,
                         "mission_id": mission_id,
                         "idempotency_key": f"e2e-exec-{stamp}"},
                   expect=[200, 400, 409], note="idempotent replay handled")
    out["artifacts"]["execute_replay"] = redact(j)

    # executing without an approval must fail closed
    call("POST", "/api/v1/platform/execute", token=op_tok,
         body={"tool_id": "m49.local_note_write",
               "capability": "write",
               "arguments": {"key": f"e2e-noapproval-{stamp}", "value": "x"},
               "project_id": proj_id, "mission_id": mission_id,
               "idempotency_key": f"e2e-noapproval-{stamp}"},
         expect=[400, 401, 403, 409], note="unapproved execution denied")

    code, j = call("GET", "/api/v1/platform/runtime/executions", token=op_tok, expect=200,
                   note="list executions")
    execs = j.get("executions") or []
    out["artifacts"]["execution_count"] = len(execs)
    exec_id = execs[0].get("execution_id") if execs else None
    out["artifacts"]["execution_sample"] = redact(execs[0]) if execs else None

    if exec_id:
        call("GET", f"/api/v1/platform/runtime/executions/{exec_id}", token=op_tok,
             expect=200, note="execution detail")
        call("GET", f"/api/v1/platform/runtime/executions/{exec_id}/timeline", token=op_tok,
             expect=200, note="execution timeline")
        call("POST", f"/api/v1/platform/runtime/executions/{exec_id}/cancel", token=op_tok,
             body={}, expect=403, note="operator denied runtime cancel (RUNTIME_OPERATE is owner+)")

    call("GET", "/api/v1/platform/runtime/metrics", token=op_tok, expect=200, note="runtime metrics")
    call("GET", "/api/v1/platform/runtime/diagnostics", token=op_tok, expect=200, note="runtime diagnostics")
    call("GET", "/api/v1/platform/audit", token=owner_tok, expect=200, note="audit trail readable")

    # ---- 10. chat / conversation ---------------------------------------------
    call("GET", "/api/v1/platform/conversation/health", token=op_tok, expect=200,
         note="conversation health")
    code, j = call("GET", "/api/v1/platform/conversation/providers", token=op_tok, expect=200,
                   note="conversation providers")
    out["artifacts"]["conversation_providers"] = redact(j)

    # ---- 11. voice -----------------------------------------------------------
    code, j = call("GET", "/api/v1/platform/voice/health", token=op_tok, expect=200, note="voice health")
    out["artifacts"]["voice_health"] = redact(j)
    code, j = call("GET", "/api/v1/platform/voice/providers", token=op_tok, expect=200, note="voice providers")
    out["artifacts"]["voice_providers"] = redact(j)
    code, j = call("GET", "/api/v1/platform/voice/runtime/health", token=op_tok, expect=200,
                   note="voice runtime health")
    out["artifacts"]["voice_runtime_health"] = redact(j)
    code, j = call("GET", "/api/v1/platform/voice/runtime/stt-providers", token=op_tok, expect=200,
                   note="stt providers")
    out["artifacts"]["stt_providers"] = redact(j)

    # ---- 12. operations ------------------------------------------------------
    for p in ("/api/v1/platform/private-alpha/readiness",
              "/api/v1/platform/private-alpha/checklist",
              "/api/v1/platform/private-alpha/contract",
              "/api/v1/platform/core/health",
              "/api/v1/platform/core/home",
              "/api/v1/platform/core/notifications"):
        call("GET", p, token=owner_tok, expect=200, note=f"ops {p}")

    # ---- 13. sessions / revocation / logout ----------------------------------
    code, j = call("GET", "/api/v1/platform/sessions", token=op_tok, expect=200, note="list sessions")
    sessions = j.get("sessions") or []
    out["artifacts"]["session_count"] = len(sessions)

    # second operator session, then revoke it and prove it is dead
    code, j = call("POST", "/api/v1/platform/auth/login",
                   body={"email": "operator@e2e.local", "password": op_pw},
                   expect=200, note="operator second session")
    op_tok2 = j.get("token")
    sid2 = (j.get("session") or {}).get("session_id")
    call("GET", "/api/v1/platform/me", token=op_tok2, expect=200, note="second session works")
    call("POST", f"/api/v1/platform/sessions/{sid2}/revoke", token=op_tok,
         expect=200, note="revoke second session")
    call("GET", "/api/v1/platform/me", token=op_tok2, expect=[401, 403],
         note="revoked session denied")

    call("POST", "/api/v1/platform/auth/logout", token=view_tok, expect=200, note="viewer logout")
    call("GET", "/api/v1/platform/me", token=view_tok, expect=[401, 403],
         note="logged-out token denied")

    out["steps"] = RESULTS
    out["summary"] = {
        "total": len(RESULTS),
        "passed": sum(1 for r in RESULTS if r["ok"]),
        "failed": sum(1 for r in RESULTS if not r["ok"]),
        "unasserted": sum(1 for r in RESULTS if r["expected"] is None),
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(json.dumps({"fatal": str(e), "steps": RESULTS}, indent=2))
        sys.exit(2)
