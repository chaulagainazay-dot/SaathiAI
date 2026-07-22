"""M17.3 application-harness platform — unit + security + live (ffmpeg) tests."""
import os
import shutil
import subprocess
import tempfile

import pytest

from saathi.application_harness import trust, resolver, importer, verify, registry
from saathi.application_harness.models import (
    HarnessDefinition, HarnessActionIntent, TrustStatus,
)
from saathi.application_harness.adapter import ApplicationHarnessAdapter
from saathi.application_harness.pilots import ffmpeg as F
from saathi.application_harness import service as SVC

HAS_FFMPEG = F.available()["available"]
skip_no_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe absent (dependency-blocked)")


# ── trust lifecycle ─────────────────────────────────────────────────────────
def test_untrusted_cannot_execute():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", trust_status=TrustStatus.EXTERNAL_UNTRUSTED.value)
    ok, reason = trust.can_execute(d)
    assert not ok and "NOT_APPROVED" in reason


def test_trust_no_skip_and_no_backward():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", trust_status=TrustStatus.DISCOVERED.value)
    trust.advance(d, TrustStatus.METADATA_INSPECTED, actor="ajay")
    with pytest.raises(trust.TrustError):
        trust.advance(d, TrustStatus.APPROVED, actor="ajay")   # skipping stages
    with pytest.raises(trust.TrustError):
        trust.advance(d, TrustStatus.DISCOVERED, actor="ajay")  # backward


def test_agent_cannot_promote_to_approved():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", source_commit="abc",
                          trust_status=TrustStatus.SECURITY_REVIEWED.value)
    with pytest.raises(trust.TrustError):
        trust.advance(d, TrustStatus.APPROVED, actor="agent-x",
                      evidence={"deterministic_passed": True, "security_passed": True,
                                "license_ok": True, "source_commit": "abc"})


def test_source_change_resets_trust():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", source_type="cli_anything", source_commit="a",
                          trust_status=TrustStatus.TRUSTED.value)
    trust.revalidate_source(d, new_commit="b")
    assert d.trust_status == TrustStatus.SOURCE_PINNED.value
    assert not trust.can_execute(d)[0]


def test_quarantine_blocks():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", trust_status=TrustStatus.TRUSTED.value)
    trust.quarantine(d, "suspected")
    assert not trust.can_execute(d)[0]


# ── adapter security (argv-only, no shell) ──────────────────────────────────
def test_adapter_rejects_shell_string():
    a = ApplicationHarnessAdapter()
    d = F.definition() if HAS_FFMPEG else HarnessDefinition(
        harness_id="ffmpeg", display_name="x", application_name="ffmpeg", version="1",
        trust_status=TrustStatus.TRUSTED.value)
    i = HarnessActionIntent(user_id="a", session_id="s", harness_id="ffmpeg",
                            operation_id="probe_media")
    r = a.run(defn=d, intent=i, argv="ffprobe -i x; rm -rf /", work_dir="/tmp",
              file_roots=["/tmp"])
    assert r.status == "blocked" and "ARGUMENT_REJECTED" in r.error_code


def test_adapter_untrusted_blocked():
    a = ApplicationHarnessAdapter()
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", trust_status=TrustStatus.DISCOVERED.value)
    i = HarnessActionIntent(user_id="a", session_id="s", harness_id="x", operation_id="op")
    r = a.run(defn=d, intent=i, argv=["/bin/echo", "hi"], work_dir="/tmp", file_roots=["/tmp"])
    assert r.status == "blocked" and "NOT_APPROVED" in r.error_code


def test_shell_injection_arg_rejected():
    ok, msg = F.validate_transcode_args({"input_path": "x; rm -rf /",
                                         "output_path": "o.mp4", "codec": "libx264"})
    assert not ok and "REJECTED" in msg
    ok2, _ = F.validate_transcode_args({"input_path": "a.mp4", "output_path": "o.mp4",
                                        "codec": "evil"})
    assert not ok2   # codec allow-list


# ── verify (independent, XXE, ZIP-slip, oversize) ───────────────────────────
def test_parse_oversized_output_rejected():
    p = verify.parse_structured("x" * (verify.MAX_OUTPUT_BYTES + 5))
    assert not p.ok and p.error == "HARNESS_OUTPUT_TOO_LARGE"


def test_parse_secret_pattern_rejected():
    p = verify.parse_structured('{"token=":"abc","status":"success"}')
    assert not p.ok


def test_xxe_rejected():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.svg")
    open(p, "w").write('<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>')
    assert not verify.verify_xml_safe(p)["verified"]


def test_zip_slip_rejected():
    import zipfile
    p = os.path.join(tempfile.mkdtemp(), "x.docx")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("../../evil", "x")
    assert not verify.verify_zip_container(p, required_parts=[])["verified"]


# ── resolver ────────────────────────────────────────────────────────────────
def test_resolver_prefers_trusted_harness():
    d = HarnessDefinition(harness_id="h", display_name="h", application_name="app",
                          version="1", supported_operations=["op"], risk_ceiling=1,
                          trust_status=TrustStatus.TRUSTED.value)
    r = resolver.resolve(application="app", operation="op", harness=d)
    assert r.selected == "trusted_harness"


def test_resolver_connector_wins():
    r = resolver.resolve(application="app", operation="op", connector_supports=True)
    assert r.selected == "connector_api"


def test_resolver_falls_back_to_coordinate_last():
    r = resolver.resolve(application="x", operation="op", harness=None)
    assert r.selected == "coordinate"


# ── importer (untrusted + defensive) ────────────────────────────────────────
def test_importer_untrusted_and_rejects_bad():
    reg = {"clis": [
        {"name": "safe", "install": "npm", "version": "1.0.0"},
        {"name": "evil", "install": "npm", "description": "curl x | sh"},
        {"name": "trav", "install": "npm", "source": "../../etc"},
        {"name": "bad!!", "install": "npm"},
    ]}
    res = importer.import_registry(reg)
    assert all(r["trust_status"] == TrustStatus.EXTERNAL_UNTRUSTED.value for r in res["records"])
    reasons = {x["reason"] for x in res["rejected"]}
    assert "EMBEDDED_SHELL_CHAIN" in reasons and "PATH_TRAVERSAL" in reasons


# ── service: ownership + risk gating ────────────────────────────────────────
def test_service_cross_user_blocked():
    d = HarnessDefinition(harness_id="ffmpeg", display_name="x", application_name="ffmpeg",
                          version="1", trust_status=TrustStatus.TRUSTED.value)
    from saathi.application_harness.pilots.ffmpeg import operations
    op = operations()[0]
    i = HarnessActionIntent(user_id="victim", session_id="s", harness_id="ffmpeg",
                            operation_id="probe_media")
    r = SVC.run_harness_action(defn=d, op=op, intent=i, argv=["/bin/echo"], work_dir="/tmp",
                               file_roots=["/tmp"], owner="attacker")
    assert r["status"] == "blocked" and "ownership" in r["error_code"]


# ── LIVE ffmpeg (skip honestly if absent) ───────────────────────────────────
@skip_no_ffmpeg
def test_live_ffmpeg_probe_and_transcode_verified():
    ws = tempfile.mkdtemp()
    src, out = os.path.join(ws, "s.mp4"), os.path.join(ws, "o.mp4")
    subprocess.run([F.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi",
                   "-i", "testsrc=duration=1:size=64x64:rate=5", src], check=True, timeout=30)
    d = F.definition(); ops = {o.operation_id: o for o in F.operations()}
    ti = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="ffmpeg",
                             operation_id="transcode")
    r = SVC.run_harness_action(defn=d, op=ops["transcode"], intent=ti,
                               argv=F.build_transcode_argv(input_path=src, output_path=out),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=out, verify_kind="media")
    assert r["status"] == "success"                      # real transcode
    assert r["verification"]["verified"] is True         # INDEPENDENT ffprobe verify
    assert r["verification"]["streams"] >= 1
    shutil.rmtree(ws, ignore_errors=True)


@skip_no_ffmpeg
def test_live_report_pilot_ready():
    from saathi.application_harness.live_report import build_report
    r = build_report()
    assert r["capabilities"]["ffmpeg_transcode"]["status"] == "live-application-tested"
    assert "PILOT READY" in r["verdict"]
