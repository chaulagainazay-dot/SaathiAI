"""M17.6 third live application harness — jq (JSON transformation via gateway)."""
import json
import os
import shutil
import tempfile

import pytest

from saathi.application_harness.pilots import jq_harness as JQ
from saathi.application_harness import service as SVC, registry
from saathi.application_harness.models import HarnessActionIntent

HAS_JQ = JQ.available()["available"]
skip_no = pytest.mark.skipif(not HAS_JQ, reason="jq absent")


def _input(ws):
    p = os.path.join(ws, "in.json")
    open(p, "w").write(json.dumps({"items": [{"n": 1}, {"n": 2}, {"n": 3}], "name": "x"}))
    return p


# ── three distinct live applications ────────────────────────────────────────
def test_three_live_applications():
    execs = {h.harness_id for h in registry.all_harnesses() if h.executable()}
    assert {"ffmpeg", "sqlite", "jq"} <= execs   # media + database + data-transform


# ── filter validation (env leak / file read / shell rejection) ──────────────
@pytest.mark.parametrize("bad", [
    "env", "$ENV.HOME", "input", "inputs", 'include "x"', 'import "x"',
    'getpath(["a"])', "@sh", "$__loc__", ".a | debug", "input_filename",
])
def test_forbidden_filters_rejected(bad):
    assert not JQ.validate_filter(bad)[0]


def test_good_filter_allowed():
    assert JQ.validate_filter(".items | length")[0]
    assert JQ.validate_filter("{count:(.items|length), name}")[0]


# ── live transform + independent JSON verification ──────────────────────────
@skip_no
def test_live_transform_verified():
    ws = tempfile.mkdtemp(); inp = _input(ws)
    defn = JQ.definition(); op = JQ.operations()[0]
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="jq",
                            operation_id="transform")
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=JQ.build_argv(filter_expr="{count:(.items|length), name}",
                                                  input_path=inp),
                               work_dir=ws, file_roots=[ws], owner="ajay")
    assert r["status"] == "success"
    assert r["verification"]["verified"] is True and r["verification"]["records"] == 1
    shutil.rmtree(ws, ignore_errors=True)


@skip_no
def test_invalid_output_not_success():
    """A filter producing no output → verification fails → NOT success."""
    ws = tempfile.mkdtemp(); inp = _input(ws)
    defn = JQ.definition(); op = JQ.operations()[0]
    i = HarnessActionIntent(user_id="ajay", session_id="s", harness_id="jq",
                            operation_id="transform")
    # select nothing (empty) → jq -e exits 1 → adapter reports failed/uncertain
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=JQ.build_argv(filter_expr=".items[] | select(.n>99)",
                                                  input_path=inp),
                               work_dir=ws, file_roots=[ws], owner="ajay")
    assert r["status"] != "success"
    shutil.rmtree(ws, ignore_errors=True)


@skip_no
def test_cross_user_blocked():
    ws = tempfile.mkdtemp(); inp = _input(ws)
    defn = JQ.definition(); op = JQ.operations()[0]
    i = HarnessActionIntent(user_id="victim", session_id="s", harness_id="jq",
                            operation_id="transform")
    r = SVC.run_harness_action(defn=defn, op=op, intent=i,
                               argv=JQ.build_argv(filter_expr=".name", input_path=inp),
                               work_dir=ws, file_roots=[ws], owner="attacker")
    assert r["status"] == "blocked" and "ownership" in r["error_code"]
    shutil.rmtree(ws, ignore_errors=True)


def test_verify_json_stdout_helper():
    assert JQ.verify_json_stdout('{"a":1}\n{"b":2}')["records"] == 2
    assert not JQ.verify_json_stdout("not json")["verified"]
    assert not JQ.verify_json_stdout("")["verified"]
