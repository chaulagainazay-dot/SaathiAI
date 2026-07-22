"""M17.7 fourth live application harness — zip archive (packaging via gateway).

Archive/packaging is a distinct category from FFmpeg (media), SQLite (database)
and jq (JSON): the produced container is itself an attack surface. This is the
first LIVE exercise of the harness's ZIP-slip / zip-bomb verifier — a hostile
archive routed through the same service path verifies as NOT success even though
the packaging tool exited 0.
"""
import os
import shutil
import tempfile
import zipfile

import pytest

from saathi.application_harness.pilots import zip_archive as Z
from saathi.application_harness import service as SVC, registry
from saathi.application_harness.models import HarnessActionIntent

HAS_ZIP = Z.available()["available"]
skip_no = pytest.mark.skipif(not HAS_ZIP, reason="zip/unzip absent")


def _payload(ws):
    p = os.path.join(ws, "payload.txt")
    open(p, "w").write("saathi-harness-pilot\n")
    return p


# ── four distinct live applications (media + database + transform + archive) ─
@skip_no
def test_four_live_applications():
    execs = {h.harness_id for h in registry.all_harnesses() if h.executable()}
    assert {"ffmpeg", "sqlite", "jq", "zip"} <= execs


# ── untrusted member-name validation (path traversal rejected) ──────────────
@pytest.mark.parametrize("bad", [
    "/etc/passwd", "../escape", "a/../../b", "../../x", "dir/../../../y", "\x00null",
])
def test_traversal_members_rejected(bad):
    assert not Z.validate_member(bad)[0]


def test_good_members_allowed():
    assert Z.validate_member("payload.txt")[0]
    assert Z.validate_member("dir/file.txt")[0]
    assert Z.validate_members(["a.txt", "b/c.txt"])[0]
    assert not Z.validate_members(["ok.txt", "../evil"])[0]


# ── live pack + independent (ZIP-slip/bomb-safe) verification ────────────────
@skip_no
def test_live_pack_verified():
    ws = tempfile.mkdtemp(); src = _payload(ws)
    out = os.path.join(ws, "out.zip")
    defn = Z.definition(); ops = {o.operation_id: o for o in Z.operations()}
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="zip",
                            operation_id="pack")
    r = SVC.run_harness_action(defn=defn, op=ops["pack"], intent=i,
                               argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=out, verify_kind="zip")
    assert r["status"] == "success"
    assert r["verification"]["verified"] is True
    assert os.path.exists(out)
    shutil.rmtree(ws, ignore_errors=True)


# ── the key evidence: a REAL hostile archive is rejected by the live verifier ─
@skip_no
def test_zip_slip_archive_not_success():
    ws = tempfile.mkdtemp()
    evil = os.path.join(ws, "evil.zip")
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escape.txt", "pwned")
    defn = Z.definition(); ops = {o.operation_id: o for o in Z.operations()}
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="zip",
                            operation_id="list_entries")
    r = SVC.run_harness_action(defn=defn, op=ops["list_entries"], intent=i,
                               argv=Z.build_list_argv(archive_path=evil),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=evil, verify_kind="zip")
    assert r["status"] != "success"
    assert r["verification"]["verified"] is False
    shutil.rmtree(ws, ignore_errors=True)


@skip_no
def test_zip_bomb_archive_not_success():
    ws = tempfile.mkdtemp()
    bomb = os.path.join(ws, "bomb.zip")
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("big.txt", "0" * 400_000)   # ~400 KB -> tiny compressed -> huge ratio
    defn = Z.definition(); ops = {o.operation_id: o for o in Z.operations()}
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="zip",
                            operation_id="list_entries")
    r = SVC.run_harness_action(defn=defn, op=ops["list_entries"], intent=i,
                               argv=Z.build_list_argv(archive_path=bomb),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=bomb, verify_kind="zip")
    assert r["status"] != "success"
    shutil.rmtree(ws, ignore_errors=True)


# ── list a clean archive (read-only op) ─────────────────────────────────────
@skip_no
def test_live_list_clean_archive():
    ws = tempfile.mkdtemp(); src = _payload(ws)
    out = os.path.join(ws, "out.zip")
    defn = Z.definition(); ops = {o.operation_id: o for o in Z.operations()}
    pack = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="zip",
                               operation_id="pack")
    SVC.run_harness_action(defn=defn, op=ops["pack"], intent=pack,
                           argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                           work_dir=ws, file_roots=[ws], owner="ajay",
                           verify_target=out, verify_kind="zip")
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="zip",
                            operation_id="list_entries")
    r = SVC.run_harness_action(defn=defn, op=ops["list_entries"], intent=i,
                               argv=Z.build_list_argv(archive_path=out),
                               work_dir=ws, file_roots=[ws], owner="ajay",
                               verify_target=out, verify_kind="zip")
    assert r["status"] == "success" and r["verification"]["verified"] is True
    shutil.rmtree(ws, ignore_errors=True)


# ── cross-user isolation ────────────────────────────────────────────────────
@skip_no
def test_cross_user_blocked():
    ws = tempfile.mkdtemp(); src = _payload(ws)
    out = os.path.join(ws, "out.zip")
    defn = Z.definition(); ops = {o.operation_id: o for o in Z.operations()}
    i = HarnessActionIntent(user_id="victim", session_id="s", harness_id="zip",
                            operation_id="pack")
    r = SVC.run_harness_action(defn=defn, op=ops["pack"], intent=i,
                               argv=Z.build_pack_argv(output_path=out, input_paths=[src]),
                               work_dir=ws, file_roots=[ws], owner="attacker",
                               verify_target=out, verify_kind="zip")
    assert r["status"] == "blocked" and "ownership" in r["error_code"]
    shutil.rmtree(ws, ignore_errors=True)


# ── verifier helper directly ────────────────────────────────────────────────
@skip_no
def test_verify_archive_helper():
    ws = tempfile.mkdtemp()
    clean = os.path.join(ws, "clean.zip")
    with zipfile.ZipFile(clean, "w") as z:
        z.writestr("a.txt", "hello")
    assert Z.verify_archive(clean)["verified"] is True
    slip = os.path.join(ws, "slip.zip")
    with zipfile.ZipFile(slip, "w") as z:
        z.writestr("../x", "bad")
    assert Z.verify_archive(slip)["verified"] is False
    shutil.rmtree(ws, ignore_errors=True)
