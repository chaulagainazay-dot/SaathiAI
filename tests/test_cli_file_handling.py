"""CLI file-argument handling must fail closed on missing/malformed files.

Regression for a defect where --record-file / --approval-file / etc. pointing at a
nonexistent file raised an unhandled FileNotFoundError traceback instead of a clean
fail-closed result.
"""
from __future__ import annotations

import json

import pytest

from saathi.credentials import cli as credcli

MISSING = "/tmp/definitely-nonexistent-saathi-file-xyz.json"


@pytest.mark.parametrize("argv", [
    ["m39-3-validate-approval", "--record-file", MISSING],
    ["m39-4-validate-config", "--config-file", MISSING],
    ["m39-5-validate-event", "--event-file", MISSING],
    ["m39-5-detect-alerts", "--signals-file", MISSING],
    ["m41-run-canary", "--approval-file", MISSING],
    ["m43-run-validation", "--approval-file", MISSING, "--source-kind",
     "OS_KEYCHAIN_REFERENCE", "--locator", "x:y"],
    ["m43-run-revocation", "--approval-file", MISSING, "--source-kind",
     "OS_KEYCHAIN_REFERENCE", "--locator", "x:y"],
])
def test_missing_file_fails_closed_no_traceback(argv):
    # must return a handled int (never raise), and never GRADUATION/CANARY success
    rc = credcli.main(argv)
    assert isinstance(rc, int)
    assert rc in (2, 5)  # fail-closed, not 0


def test_malformed_json_fails_closed(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not json")
    rc = credcli.main(["m39-3-validate-approval", "--record-file", str(bad)])
    assert rc == 5


def test_read_json_helper_never_raises(tmp_path):
    data, err = credcli._read_json_file(MISSING)
    assert data is None and err == "file_not_found"
    bad = tmp_path / "b.json"; bad.write_text("nope{")
    data, err = credcli._read_json_file(str(bad))
    assert data is None and err.startswith("unreadable")
    good = tmp_path / "g.json"; good.write_text(json.dumps({"a": 1}))
    data, err = credcli._read_json_file(str(good))
    assert data == {"a": 1} and err is None
