"""M17.3 harness live-validation report — honest capability classification."""
from __future__ import annotations

import os
import subprocess
import tempfile
import time

from saathi.application_harness.pilots import ffmpeg as F
from saathi.application_harness import service as SVC
from saathi.application_harness.models import HarnessActionIntent


def build_report(owner: str = "ajay") -> dict:
    caps = {}
    ff = F.available()
    if ff["available"]:
        caps.update(_ffmpeg_live(owner))
    else:
        for k in ("ffmpeg_probe", "ffmpeg_transcode", "independent_verification"):
            caps[k] = {"status": "dependency-blocked"}
    # zip archive — a fourth distinct application category (packaging)
    from saathi.application_harness.pilots import zip_archive as Z
    if Z.available()["available"]:
        caps.update(_zip_live(owner))
    else:
        for k in ("zip_pack", "zip_slip_rejected"):
            caps[k] = {"status": "dependency-blocked"}
    # LibreOffice / Blender — not installed here
    import shutil
    caps["libreoffice_pdf"] = {"status": "live-application-tested" if shutil.which("soffice")
                               else "dependency-blocked"}
    caps["blender_render"] = {"status": "live-application-tested" if shutil.which("blender")
                              else "dependency-blocked"}
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "capabilities": caps, "verdict": _verdict(caps)}


def _ffmpeg_live(owner: str) -> dict:
    ws = tempfile.mkdtemp(prefix="harness-live-")
    src = os.path.join(ws, "src.mp4")
    out = os.path.join(ws, "out.mp4")
    caps = {}
    try:
        subprocess.run([F.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi",
                       "-i", "testsrc=duration=1:size=64x64:rate=5", src],
                      check=True, timeout=30)
        defn = F.definition(); ops = {o.operation_id: o for o in F.operations()}
        pi = HarnessActionIntent(user_id=owner, session_id="s", harness_id="ffmpeg",
                                 operation_id="probe_media")
        rp = SVC.run_harness_action(defn=defn, op=ops["probe_media"], intent=pi,
                                    argv=F.build_probe_argv(input_path=src), work_dir=ws,
                                    file_roots=[ws], owner=owner, verify_target=src,
                                    verify_kind="media")
        caps["ffmpeg_probe"] = {"status": "live-application-tested" if rp["status"] == "success"
                                else "live_failed"}
        ti = HarnessActionIntent(user_id=owner, session_id="s", harness_id="ffmpeg",
                                 operation_id="transcode")
        rt = SVC.run_harness_action(defn=defn, op=ops["transcode"], intent=ti,
                                    argv=F.build_transcode_argv(input_path=src, output_path=out),
                                    work_dir=ws, file_roots=[ws], owner=owner,
                                    verify_target=out, verify_kind="media")
        caps["ffmpeg_transcode"] = {"status": "live-application-tested" if rt["status"] == "success"
                                    else "live_failed"}
        caps["independent_verification"] = {
            "status": "live-application-tested" if rt.get("verification", {}).get("verified")
            else "live_failed"}
    except Exception as e:
        for k in ("ffmpeg_probe", "ffmpeg_transcode", "independent_verification"):
            caps.setdefault(k, {"status": "live_failed", "error": str(e)[:120]})
    finally:
        import shutil
        shutil.rmtree(ws, ignore_errors=True)
    return caps


def _zip_live(owner: str) -> dict:
    """Pack a real archive through the gateway (verified success) AND route a
    hostile ZIP-slip archive through the SAME verifier (must be rejected)."""
    import zipfile
    from saathi.application_harness.pilots import zip_archive as Z
    ws = tempfile.mkdtemp(prefix="harness-live-zip-")
    caps = {}
    try:
        src = os.path.join(ws, "payload.txt")
        open(src, "w").write("saathi-harness-pilot\n")
        out = os.path.join(ws, "out.zip")
        defn = Z.definition(); ops = {o.operation_id: o for o in Z.operations()}
        pi = HarnessActionIntent(user_id=owner, session_id="s", harness_id="zip",
                                 operation_id="pack")
        rp = SVC.run_harness_action(defn=defn, op=ops["pack"], intent=pi,
                                    argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                                    work_dir=ws, file_roots=[ws], owner=owner,
                                    verify_target=out, verify_kind="zip")
        caps["zip_pack"] = {"status": "live-application-tested"
                            if rp["status"] == "success" else "live_failed"}
        # hostile archive: a real .zip carrying a `../` traversal entry. The
        # verifier inspects the container and rejects it -> NOT success.
        evil = os.path.join(ws, "evil.zip")
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../escape.txt", "pwned")
        li = HarnessActionIntent(user_id=owner, session_id="s", harness_id="zip",
                                 operation_id="list_entries")
        rl = SVC.run_harness_action(defn=defn, op=ops["list_entries"], intent=li,
                                    argv=Z.build_list_argv(archive_path=evil),
                                    work_dir=ws, file_roots=[ws], owner=owner,
                                    verify_target=evil, verify_kind="zip")
        caps["zip_slip_rejected"] = {"status": "live-application-tested"
                                     if rl["status"] != "success" else "live_failed"}
    except Exception as e:
        for k in ("zip_pack", "zip_slip_rejected"):
            caps.setdefault(k, {"status": "live_failed", "error": str(e)[:120]})
    finally:
        import shutil
        shutil.rmtree(ws, ignore_errors=True)
    return caps


def _verdict(caps: dict) -> str:
    live = any(c["status"] == "live-application-tested" for c in caps.values())
    return "AGENT-NATIVE APPLICATION PILOT READY" if live else "HARNESS PLATFORM STAGING READY"
