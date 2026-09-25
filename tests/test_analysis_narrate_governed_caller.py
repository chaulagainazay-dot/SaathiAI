"""The narration endpoint must reach the model through a REGISTERED caller.

Written because this endpoint shipped broken and silent. It called the deprecated
`llm.generate` facade with `caller_id="analysis_narrate"`, which is not a
registered caller, so `preflight_inference` denied every request and the route
always answered `LLM_UNAVAILABLE`. Nothing failed loudly; there was no test.

Two things are pinned here: the governance rule (server routes do not open new
`llm.generate` call sites) and the behaviour that rule was protecting (the caller
actually resolves to a policy).
"""
from __future__ import annotations

import ast
from pathlib import Path

from saathi.inference.caller_policy import get_caller_policy
from saathi.inference.legacy_facade import preflight_inference
from saathi.tools._llm_helper import CALLER_ID, PATH_ID, ask_llm, ask_llm_result

SERVER_SRC = Path("saathi/server.py")

# What the narrate route actually asks for.
NARRATE_MAX_TOKENS = 900
NARRATE_TIMEOUT = 60.0


def test_the_helper_caller_is_registered_and_passes_preflight():
    """The defect itself: an unregistered caller is denied before any provider."""
    assert get_caller_policy(CALLER_ID) is not None
    pf = preflight_inference(
        caller_id=CALLER_ID, path_id=PATH_ID,
        prompt="facts", system="system", max_tokens=NARRATE_MAX_TOKENS,
        timeout=NARRATE_TIMEOUT,
    )
    assert pf.ok, (pf.reason_code, pf.error_message)
    # The route's own budget must survive the policy cap, or narration truncates.
    assert pf.max_output_tokens >= NARRATE_MAX_TOKENS


def test_the_previous_caller_id_was_never_registered():
    """Proves the old path could not have worked, so this is a fix not a rename."""
    assert get_caller_policy("analysis_narrate") is None
    pf = preflight_inference(
        caller_id="analysis_narrate", path_id="legacy_llm_generate",
        prompt="facts", system="system", max_tokens=NARRATE_MAX_TOKENS,
        timeout=NARRATE_TIMEOUT,
    )
    assert pf.ok is False
    assert pf.reason_code == "unknown_caller"


def test_the_server_opens_no_llm_generate_call_site():
    """The M21.3/M22 rule, checked structurally rather than via the release gate.

    The release gate already enforces this repo-wide; asserting it here means a
    regression in THIS file fails a fast, local test instead of only surfacing in
    an eleven-suite gate run.
    """
    tree = ast.parse(SERVER_SRC.read_text())
    src = SERVER_SRC.read_text()
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "generate" and \
                isinstance(f.value, ast.Name) and f.value.id in {"llm", "llm_mod"}:
            offenders.append(node.lineno)
        if isinstance(f, ast.Name) and f.id == "generate" and \
                "from saathi.llm import generate" in src:
            offenders.append(node.lineno)
    assert not offenders, offenders


def test_narrate_routes_through_the_sanctioned_helper():
    src = SERVER_SRC.read_text()
    assert "ask_llm_result" in src
    # The route must not reach the deprecated facade by another name either.
    assert "caller_id=\"analysis_narrate\"" not in src


def test_the_helper_public_api_is_unchanged_and_the_result_form_adds_the_model():
    """`ask_llm` has many callers; widening it must not have moved its contract."""
    import inspect

    assert inspect.signature(ask_llm).return_annotation in ("str", str)
    text_params = list(inspect.signature(ask_llm).parameters)
    result_params = list(inspect.signature(ask_llm_result).parameters)
    assert text_params == result_params == ["prompt", "system", "timeout", "max_tokens"]

    # The reason the result form exists: the model identity the UI displays, which
    # the text-only form cannot carry.
    from saathi.llm import LLMResult

    assert {"text", "provider", "model"} <= set(LLMResult.__dataclass_fields__)
