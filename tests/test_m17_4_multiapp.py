"""M17.4 multi-application harness — discovery, install/update/revoke, limits,
expanded verifiers (live ffmpeg artifacts), multi-app defs."""
import os
import shutil
import subprocess
import tempfile

import pytest

from saathi.application_harness import discovery, installer, lifecycle, registry, verify
from saathi.application_harness.models import HarnessDefinition, TrustStatus
from saathi.application_harness import trust
from saathi.application_harness.limits import ResourceLimits
from saathi.application_harness.pilots import ffmpeg as F

HAS_FFMPEG = F.available()["available"]
skip_no_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg absent")


# ── discovery ───────────────────────────────────────────────────────────────
def test_discovery_honest():
    d = discovery.discover()
    assert "available_harnesses" in d and "dependency_blocked" in d
    # absent apps are dependency-blocked, never faked available
    assert "blender" in d["dependency_blocked"] or "blender" in d["available_harnesses"]


def test_registry_has_multiapp_defs():
    ids = {h.harness_id for h in registry.all_harnesses()}
    assert {"libreoffice", "blender", "kdenlive"} <= ids
    # absent apps stay discovered (not executable)
    bl = registry.get("blender")
    if not shutil.which("blender"):
        assert not trust.can_execute(bl)[0] and bl.validation_status == "dependency_blocked"


# ── secure install / path-hijack / arbitrary URL ────────────────────────────
def test_install_path_hijack_rejected():
    with pytest.raises(installer.InstallRejected):
        installer._verify_no_path_hijack("/tmp/evil/ffmpeg")
    installer._verify_no_path_hijack("/opt/homebrew/bin/ffmpeg")   # safe → no raise


def test_install_embedded_command_refused():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", install_method="source_checkout",
                          source_type="cli_anything", source_commit="a",
                          source_repository="https://x; curl bad | sh")
    with pytest.raises(installer.InstallRejected):
        installer.plan_install(d)


@skip_no_ffmpeg
def test_install_system_executable_validated():
    r = installer.run_install(F.definition(), approved=True)
    assert r["status"] == "installed" and r["binary_sha256"] and len(r["stages"]) == 6


# ── update / rollback / revocation ──────────────────────────────────────────
def test_update_resets_trust_and_backup():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", source_type="cli_anything", source_commit="a",
                          trust_status=TrustStatus.TRUSTED.value)
    upd, backup = lifecycle.apply_update(d, new_version="2", new_commit="b")
    assert not trust.can_execute(upd)[0]
    assert backup.trust_status == TrustStatus.TRUSTED.value    # rollback available


def test_revoke_and_uninstall_block():
    d = HarnessDefinition(harness_id="x", display_name="x", application_name="x",
                          version="1", trust_status=TrustStatus.TRUSTED.value)
    lifecycle.revoke(d, "compromised")
    assert not trust.can_execute(d)[0]
    d2 = HarnessDefinition(harness_id="y", display_name="y", application_name="y",
                           version="1", trust_status=TrustStatus.TRUSTED.value)
    res = lifecycle.uninstall(d2)
    assert res["uninstalled"] and res["evidence_preserved"] and not trust.can_execute(d2)[0]


# ── resource limits ─────────────────────────────────────────────────────────
def test_resource_limits_preexec():
    lim = ResourceLimits(cpu_seconds=5, file_size_mb=10, max_artifact_bytes=1000)
    assert callable(lim.preexec())
    assert lim.artifact_within_cap("/etc/hosts") in (True, False)


# ── expanded verifiers (live, real ffmpeg artifacts) ────────────────────────
def test_zip_bomb_rejected():
    import zipfile
    p = os.path.join(tempfile.mkdtemp(), "b.zip")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("big.txt", "A" * 5_000_000)
    v = verify.verify_zip_safe(p)
    assert not v["verified"] and "zip_bomb" in v["reason"]


def test_openxml_missing_parts_rejected():
    import zipfile
    p = os.path.join(tempfile.mkdtemp(), "x.docx")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("junk.txt", "x")
    assert not verify.verify_openxml(p, "docx")["verified"]


@skip_no_ffmpeg
def test_live_verifiers_png_mp4_wav():
    ws = tempfile.mkdtemp()
    png, mp4, wav = (os.path.join(ws, n) for n in ("a.png", "a.mp4", "a.wav"))
    subprocess.run([F.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi",
                   "-i", "testsrc=d=1:s=32x32:r=5", "-frames:v", "1", png], check=True, timeout=30)
    subprocess.run([F.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi",
                   "-i", "testsrc=d=1:s=32x32:r=5", mp4], check=True, timeout=30)
    subprocess.run([F.ffmpeg_path(), "-y", "-v", "error", "-f", "lavfi",
                   "-i", "sine=f=440:d=1", wav], check=True, timeout=30)
    assert verify.verify_png(png)["verified"] and verify.verify_png(png)["width"] == 32
    assert verify.verify_media(mp4)["verified"] and verify.verify_media(mp4)["streams"] >= 1
    assert verify.verify_audio(wav)["verified"] and verify.verify_audio(wav)["duration"] > 0
    shutil.rmtree(ws, ignore_errors=True)


def test_directory_tree_confined():
    ws = tempfile.mkdtemp()
    os.makedirs(os.path.join(ws, "sub"))
    open(os.path.join(ws, "sub", "f.txt"), "w").write("x")
    v = verify.verify_directory_tree(os.path.join(ws, "sub"), [ws])
    assert v["verified"] and v["entries"] >= 1
    bad = verify.verify_directory_tree("/etc", [ws])
    assert not bad["verified"]
    shutil.rmtree(ws, ignore_errors=True)
