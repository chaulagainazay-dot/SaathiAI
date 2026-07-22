"""Failure classifier — maps an incident's evidence to a FailureCategory.

Pattern-based, deterministic, explainable. Produces primary category,
confidence, suspected files, subsystem, and a recommended repair level. It
deliberately distinguishes connector-auth failures from code failures so the
loop never "fixes" a missing credential by rewriting working code.
"""
from __future__ import annotations

import re

from saathi.repair.incident import (
    RepairIncident, FailureCategory, RepairLevel,
)

# subsystem hints from file paths / test names
_SUBSYSTEM_HINTS = [
    ("execution", "execution_gateway"),
    ("events", "event_bus"),
    ("bff", "bff"),
    ("connector", "connectors"),
    ("intent", "intent_router"),
    ("planner", "planner"),
    ("capabilit", "capability_registry"),
    ("cowork", "cowork"),
    ("chat", "chat"),
    ("router", "routing"),
]


def _subsystem_for(text: str) -> str:
    t = (text or "").lower()
    for needle, name in _SUBSYSTEM_HINTS:
        if needle in t:
            return name
    return ""


def classify(inc: RepairIncident) -> RepairIncident:
    blob = " \n ".join(filter(None, [
        inc.exception_type or "",
        inc.stack_trace or "",
        inc.actual_behavior or "",
        inc.evidence.test_output_tail,
        inc.evidence.logs_tail,
        " ".join(inc.failed_tests),
    ]))
    low = blob.lower()

    cat = FailureCategory.UNKNOWN
    conf = 0.3
    files: list[str] = []

    # --- import / collision ------------------------------------------------
    if re.search(r"cannot import name|no module named|importerror", low):
        cat = FailureCategory.IMPORT_ERROR
        conf = 0.9
        m = re.search(r"from ([\w\.]+) import|module '([\w\.]+)'", blob)
        if m:
            mod = (m.group(1) or m.group(2) or "").replace(".", "/")
            if mod:
                files.append(f"{mod}.py")
    elif re.search(r"error during collection|errors during collection|interrupted: \d+ error", low):
        cat = FailureCategory.COLLECTION_ERROR
        conf = 0.85
    # --- async -------------------------------------------------------------
    elif re.search(r"coroutine .* was never awaited|was never awaited|got future .* attached", low):
        cat = FailureCategory.ASYNC_ERROR
        conf = 0.9
    # --- event bus ---------------------------------------------------------
    elif "events.bus" in low or ("attributeerror" in low and "subscribe" in low) or "event bus" in low:
        cat = FailureCategory.EVENT_BUS_ERROR
        conf = 0.8
    # --- server startup ----------------------------------------------------
    elif inc.evidence.server_import_ok is False:
        cat = FailureCategory.SERVER_STARTUP_ERROR
        conf = 0.85
    # --- connector auth vs runtime (never conflate) ------------------------
    elif re.search(r"401|unauthorized|invalid_grant|token expired|not authenticated|credentials? (missing|not found)|reauth", low):
        cat = FailureCategory.CONNECTOR_AUTH_ERROR
        conf = 0.8
    elif re.search(r"connector|connection refused|timeout|503|502|upstream", low) and "connector" in low:
        cat = FailureCategory.CONNECTOR_RUNTIME_ERROR
        conf = 0.65
    # --- execution bypass / grounding / hallucination ----------------------
    elif re.search(r"execution.?bypass|bypass.*gateway|never (called|executed).*(gateway|connector)", low):
        cat = FailureCategory.EXECUTION_BYPASS
        conf = 0.75
    elif re.search(r"not grounded|no tool.?call|tool.*never (called|invoked)|no execution (record|evidence)", low):
        cat = FailureCategory.TOOL_RESULT_NOT_GROUNDED
        conf = 0.7
    elif re.search(r"hallucinat|claimed .* (sent|retrieved|created) but|generic (director|response) instead", low):
        cat = FailureCategory.AGENT_HALLUCINATION
        conf = 0.7
    # --- capability / intent / routing -------------------------------------
    elif re.search(r"capability .* not registered|no capability|unregistered capability", low):
        cat = FailureCategory.CAPABILITY_NOT_REGISTERED
        conf = 0.75
    elif re.search(r"intent", low) and re.search(r"mismatch|not routed|no intent|misroute", low):
        cat = FailureCategory.INTENT_ERROR
        conf = 0.65
    elif re.search(r"404|route not found|no route|method not allowed|405", low):
        cat = FailureCategory.ROUTING_ERROR
        conf = 0.7
    # --- api contract ------------------------------------------------------
    elif re.search(r"assert \d+ == \d+|contract|schema|missing (key|field)|keyerror", low):
        cat = FailureCategory.API_CONTRACT_MISMATCH
        conf = 0.6
    # --- db / config / deps ------------------------------------------------
    elif re.search(r"sqlite|operationalerror|no such table|migration|database", low):
        cat = FailureCategory.DATABASE_ERROR
        conf = 0.7
    elif re.search(r"missing .* env|environment variable|not configured|config(uration)? error", low):
        cat = FailureCategory.CONFIGURATION_ERROR
        conf = 0.65
    elif re.search(r"versionconflict|incompatible|dependency|pip install|distributionnotfound", low):
        cat = FailureCategory.DEPENDENCY_ERROR
        conf = 0.6
    elif inc.failed_tests:
        cat = FailureCategory.TEST_FAILURE
        conf = 0.5

    inc.category = cat
    inc.confidence = conf
    if files:
        inc.suspected_files = list(dict.fromkeys(files + inc.suspected_files))
    inc.subsystem = (_subsystem_for(blob) or _subsystem_for(" ".join(inc.failed_tests))
                     or inc.subsystem)

    # recommended repair level (policy engine refines this)
    inc.repair_level = _recommend_level(cat)
    return inc


# Categories the loop may attempt to auto-repair with vetted strategies.
_AUTO_OK = {
    FailureCategory.IMPORT_ERROR,
    FailureCategory.COLLECTION_ERROR,
    FailureCategory.ASYNC_ERROR,
    FailureCategory.EVENT_BUS_ERROR,
}
# Categories that need a human (external systems / credentials / policy).
_MANUAL = {
    FailureCategory.CONNECTOR_AUTH_ERROR,
    FailureCategory.DEPENDENCY_ERROR,
}


def _recommend_level(cat: FailureCategory) -> RepairLevel:
    if cat in _AUTO_OK:
        return RepairLevel.SAFE_LOCAL
    if cat in _MANUAL:
        return RepairLevel.DIAGNOSE_ONLY
    return RepairLevel.DIAGNOSE_ONLY
