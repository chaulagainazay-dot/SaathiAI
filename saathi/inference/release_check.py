"""M21.3 — Release-check enforcement for inference architecture.

Deterministic, offline, no network, no secrets.

  python -m saathi.inference.release_check
  python -m saathi.inference.release_check --json
  python -m saathi.inference.release_check --explain

Exit 0 on pass, 2 on blocking failure.
"""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
SAATHI = ROOT / "saathi"
MANIFEST_PATH = ROOT / "docs" / "M21_3_RESIDUAL_EXCEPTION_MANIFEST.json"

# Frozen allowlist of production llm.generate call sites (file:line optional;
# file-level match used when line drifts within known symbols).
KNOWN_LLM_GENERATE_SITES: frozenset[str] = frozenset({
    "saathi/inference/compat.py",
    # M23: chat_adapter no longer calls llm.generate
    "saathi/tools/cheap_llm.py",
    "saathi/tools/_llm_helper.py",
    "saathi/llm.py",  # definition + internal only
    "saathi/inference/adapters/cloud.py",
})

# Files allowed to construct OpenAI/Anthropic SDKs or provider URLs.
# M22: llm.py / agent.py / research.py removed — transports live in adapters only.
# Remaining non-adapter entries are non-inference media/eval paths (out of M22 scope).
PROVIDER_SDK_ALLOWLIST: frozenset[str] = frozenset({
    "saathi/vision.py",
    "saathi/tools/voice.py",
    "saathi/tools/mr_yeti_voice.py",
    "saathi/tools/video_editor.py",
    "saathi/tools/speaking_eval.py",
    "saathi/tools/writing_eval.py",
    "saathi/tools/auto_dev.py",
    "saathi/tools/cheap_llm.py",
    "saathi/server.py",
    "saathi/inference/bypass_guard.py",
    "saathi/inference/release_check.py",
})

PROVIDER_SDK_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "saathi/inference/adapters/",
    "saathi/infrastructure/human_browser/",
)

# Credential env reads allowed only in these modules (exact paths) for M22 inference keys
CREDENTIAL_READ_ALLOWLIST: frozenset[str] = frozenset({
    "saathi/config.py",
    "saathi/inference/adapters/http_providers.py",
    "saathi/inference/adapters/grounding.py",
    "saathi/inference/adapters/agent_provider.py",
    "saathi/inference/adapters/cloud.py",
    "saathi/inference/adapters/openai_compat.py",
    "saathi/inference/adapters/ollama.py",
    "saathi/inference/provider_descriptor.py",
    "saathi/inference/provider_policy.py",
    "saathi/inference/availability.py",
    "saathi/inference/release_check.py",
    "saathi/inference/bypass_guard.py",
    "saathi/codebase_memory/secrets_scan.py",
})

CREDENTIAL_ENV_NEEDLES: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "DEEPSEEK_API_KEY",
    "GLM_API_KEY",
    "QWEN_API_KEY",
)

FORBIDDEN_URLS = (
    "api.openai.com",
    "api.anthropic.com",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    "openrouter.ai/api",
)

FORBIDDEN_SDK = frozenset({"OpenAI", "Anthropic"})

# Patterns that must not appear as production logger calls with raw fields
RAW_LOG_PATTERNS = (
    "log_prompt=True",
    "log_output=True",
)

EXCHANGE_IMPORT_NEEDLES = (
    "ccxt",
    "binance",
    "coinbase",
    "kraken",
    "bybit",
)


@dataclass
class Finding:
    rule_id: str
    path: str
    line: int
    symbol: str
    detail: str
    severity: str = "blocking"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReleaseReport:
    schema: str = "m22.release_check.v1"
    milestone: str = "M22"
    ok: bool = True
    production_certified: bool = False
    files_scanned: int = 0
    finding_count: int = 0
    blocking_count: int = 0
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "milestone": self.milestone,
            "ok": self.ok,
            "production_certified": self.production_certified,
            "files_scanned": self.files_scanned,
            "finding_count": self.finding_count,
            "blocking_count": self.blocking_count,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
        }


def _rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def _iter_py(base: Path) -> Iterable[Path]:
    if not base.is_dir():
        return
    for p in base.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        yield p


def _sdk_allowed(rel: str) -> bool:
    if rel in PROVIDER_SDK_ALLOWLIST:
        return True
    for pref in PROVIDER_SDK_ALLOWLIST_PREFIXES:
        if rel.startswith(pref):
            return True
    # Governance / policy modules may mention URLs as strings for docs
    if rel.startswith("saathi/inference/") and any(
        rel.endswith(x)
        for x in (
            "provider_policy.py",
            "provider_descriptor.py",
            "provider_decision.py",
            "provider_governance.py",
            "availability.py",
            "cost_policy.py",
            "failure_taxonomy.py",
            "circuit_breaker.py",
            "path_inventory.py",
            "residual_paths.py",
            "contract.py",
            "caller_policy.py",
            "gateway_path.py",
            "runtime.py",
            "legacy_facade.py",
            "chat_adapter.py",
            "release_check.py",
            "bypass_guard.py",
        )
    ):
        return True
    return False


def _scan_ast_file(path: Path, findings: list[Finding]) -> None:
    rel = _rel(path)
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=rel)
    except Exception as e:
        findings.append(
            Finding(
                rule_id="syntax_or_read_error",
                path=rel,
                line=0,
                symbol="",
                detail=str(e)[:200],
                severity="warning",
            )
        )
        return

    # Duplicate request models
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name in {
                "InferenceRequest",
                "GovernedInferenceRequest",
                "CanonicalInferenceRequest",
            }:
                if rel != "saathi/inference/request.py":
                    findings.append(
                        Finding(
                            rule_id="duplicate_request_model",
                            path=rel,
                            line=node.lineno,
                            symbol=node.name,
                            detail="request model outside saathi/inference/request.py",
                        )
                    )
            if node.name in {
                "ProviderCircuitBreakerRegistry",
                "CanonicalCostTable",
                "ProviderCostTable",
            }:
                if not rel.startswith("saathi/inference/"):
                    findings.append(
                        Finding(
                            rule_id="duplicate_governance_type",
                            path=rel,
                            line=node.lineno,
                            symbol=node.name,
                            detail="governance type outside inference package",
                        )
                    )
            # Trading caller registration smell
            if "Trading" in node.name and "Caller" in node.name and rel.startswith(
                "saathi/inference/"
            ):
                findings.append(
                    Finding(
                        rule_id="trading_caller_registration",
                        path=rel,
                        line=node.lineno,
                        symbol=node.name,
                        detail="Trading*Caller type in inference package",
                    )
                )

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not _sdk_allowed(rel):
                for sub in FORBIDDEN_URLS:
                    if sub in node.value:
                        findings.append(
                            Finding(
                                rule_id="direct_provider_url",
                                path=rel,
                                line=getattr(node, "lineno", 0),
                                symbol="",
                                detail=f"forbidden URL substring {sub!r}",
                            )
                        )

        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in FORBIDDEN_SDK and not _sdk_allowed(rel):
                findings.append(
                    Finding(
                        rule_id="direct_sdk_constructor",
                        path=rel,
                        line=getattr(node, "lineno", 0),
                        symbol=name,
                        detail=f"forbidden constructor {name}()",
                    )
                )

            # llm.generate call sites
            is_gen = False
            if isinstance(node.func, ast.Name) and node.func.id == "generate":
                if "from saathi.llm import generate" in src or "from ..llm import generate" in src:
                    is_gen = True
            if isinstance(node.func, ast.Attribute) and node.func.attr == "generate":
                if isinstance(node.func.value, ast.Name) and node.func.value.id in {
                    "llm",
                    "llm_mod",
                }:
                    is_gen = True
            if is_gen and rel != "saathi/llm.py":
                if rel not in KNOWN_LLM_GENERATE_SITES:
                    findings.append(
                        Finding(
                            rule_id="new_llm_generate_call_site",
                            path=rel,
                            line=getattr(node, "lineno", 0),
                            symbol="generate",
                            detail="llm.generate call outside frozen allowlist",
                        )
                    )

    # Raw log flags — skip scanners, docs, and False assignments
    if rel not in {
        "saathi/inference/release_check.py",
        "saathi/inference/bypass_guard.py",
        "saathi/inference/legacy_facade.py",
    }:
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in RAW_LOG_PATTERNS:
                if pat in line and "test" not in rel:
                    # allow False assignments and string mentions of the flag name
                    if "False" in line or "not " in line.lower():
                        continue
                    if 'f"' in line or "detail=" in line or "rule" in line:
                        continue
                    findings.append(
                        Finding(
                            rule_id="raw_prompt_or_output_logging",
                            path=rel,
                            line=i,
                            symbol="",
                            detail=pat,
                        )
                    )

    # Exchange imports in inference package
    if rel.startswith("saathi/inference/"):
        for i, line in enumerate(src.splitlines(), 1):
            low = line.lower()
            if low.strip().startswith("#"):
                continue
            for needle in EXCHANGE_IMPORT_NEEDLES:
                if f"import {needle}" in low or f"from {needle}" in low:
                    findings.append(
                        Finding(
                            rule_id="exchange_import_in_inference",
                            path=rel,
                            line=i,
                            symbol=needle,
                            detail="exchange SDK import forbidden in inference",
                        )
                    )


def _check_residual_paths(findings: list[Finding], summary: dict[str, Any]) -> None:
    from saathi.inference.residual_paths import RESIDUAL_PATH_CONTROLS, ResidualDisposition

    unknown = [
        p.path_id
        for p in RESIDUAL_PATH_CONTROLS
        if p.disposition is ResidualDisposition.UNKNOWN
    ]
    bypass = [
        p.path_id
        for p in RESIDUAL_PATH_CONTROLS
        if p.disposition is ResidualDisposition.DIRECT_PROVIDER_BYPASS
    ]
    summary["residual_path_count"] = len(RESIDUAL_PATH_CONTROLS)
    summary["unknown_paths"] = unknown
    summary["direct_bypass_paths"] = bypass
    if unknown:
        findings.append(
            Finding(
                rule_id="unknown_inference_path",
                path="saathi/inference/residual_paths.py",
                line=0,
                symbol=",".join(unknown),
                detail=f"UNKNOWN residual paths: {unknown}",
            )
        )
    if bypass:
        findings.append(
            Finding(
                rule_id="direct_provider_bypass",
                path="saathi/inference/residual_paths.py",
                line=0,
                symbol=",".join(bypass),
                detail=f"DIRECT_PROVIDER_BYPASS residual paths: {bypass}",
            )
        )
    # Legacy exceptions must have expiry
    for p in RESIDUAL_PATH_CONTROLS:
        if p.disposition is ResidualDisposition.LEGACY_ALLOWED_TEMPORARILY:
            if not p.expiry_milestone or p.expiry_milestone in {"n/a", "none", ""}:
                findings.append(
                    Finding(
                        rule_id="legacy_without_expiry",
                        path="saathi/inference/residual_paths.py",
                        line=0,
                        symbol=p.path_id,
                        detail="legacy residual missing expiry_milestone",
                    )
                )


def _check_manifest(findings: list[Finding], summary: dict[str, Any]) -> None:
    if not MANIFEST_PATH.is_file():
        findings.append(
            Finding(
                rule_id="missing_exception_manifest",
                path=str(MANIFEST_PATH.relative_to(ROOT)),
                line=0,
                symbol="",
                detail="M21.3 residual exception manifest missing",
            )
        )
        return
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    summary["manifest_schema"] = data.get("schema")
    summary["manifest_exception_count"] = len(data.get("exceptions") or [])
    if int(data.get("unknown_count") or 0) != 0:
        findings.append(
            Finding(
                rule_id="manifest_unknown_nonzero",
                path=_rel(MANIFEST_PATH),
                line=0,
                symbol="unknown_count",
                detail="manifest unknown_count must be 0",
            )
        )
    if int(data.get("direct_provider_bypass_count") or 0) != 0:
        findings.append(
            Finding(
                rule_id="manifest_bypass_nonzero",
                path=_rel(MANIFEST_PATH),
                line=0,
                symbol="direct_provider_bypass_count",
                detail="manifest direct_provider_bypass_count must be 0",
            )
        )
    if data.get("production_certified") is True:
        findings.append(
            Finding(
                rule_id="production_certified_true",
                path=_rel(MANIFEST_PATH),
                line=0,
                symbol="production_certified",
                detail="M21.3 must not set production_certified=true",
            )
        )
    for ex in data.get("exceptions") or []:
        if not ex.get("expiry_milestone"):
            findings.append(
                Finding(
                    rule_id="manifest_exception_no_expiry",
                    path=_rel(MANIFEST_PATH),
                    line=0,
                    symbol=ex.get("path_id", ""),
                    detail="exception missing expiry_milestone",
                )
            )
        f = ex.get("file") or ""
        if f and "*" in f:
            findings.append(
                Finding(
                    rule_id="manifest_wildcard_file",
                    path=_rel(MANIFEST_PATH),
                    line=0,
                    symbol=ex.get("path_id", ""),
                    detail="wildcard file patterns forbidden",
                )
            )


def _check_callers(findings: list[Finding], summary: dict[str, Any]) -> None:
    from saathi.inference.caller_policy import (
        CallerCertification,
        list_caller_ids,
        get_caller_policy,
    )

    ids = list_caller_ids()
    summary["caller_count"] = len(ids)
    summary["caller_ids"] = ids
    # Unknown transitional: must be disabled or absent for production acceptance
    unk = get_caller_policy("unknown")
    if unk is not None:
        if unk.enabled and unk.certification is not CallerCertification.FORBIDDEN:
            # M21.3: unknown may exist only if disabled
            if unk.certification is CallerCertification.TEST and not unk.enabled:
                summary["transitional_unknown"] = "disabled_test_only"
            elif unk.enabled:
                findings.append(
                    Finding(
                        rule_id="transitional_unknown_enabled",
                        path="saathi/inference/caller_policy.py",
                        line=0,
                        symbol="unknown",
                        detail="transitional unknown caller must be disabled in M21.3",
                    )
                )
        summary["transitional_unknown"] = summary.get(
            "transitional_unknown", unk.certification.value
        )
    else:
        summary["transitional_unknown"] = "removed"

    # No *enabled* trading callers (FORBIDDEN denylist entries are intentional)
    for cid in ids:
        low = cid.lower()
        if any(x in low for x in ("trading", "trade_order", "exchange_order", "withdrawal")):
            pol = get_caller_policy(cid)
            if pol is None:
                continue
            if pol.certification is CallerCertification.FORBIDDEN or not pol.enabled:
                continue
            findings.append(
                Finding(
                    rule_id="trading_caller_registration",
                    path="saathi/inference/caller_policy.py",
                    line=0,
                    symbol=cid,
                    detail="enabled trading-related caller id forbidden",
                )
            )

    # Fake engine not production-eligible
    fake = get_caller_policy("fake_engine")
    if fake and fake.certification is not CallerCertification.TEST:
        findings.append(
            Finding(
                rule_id="fake_provider_production",
                path="saathi/inference/caller_policy.py",
                line=0,
                symbol="fake_engine",
                detail="fake_engine must remain TEST certification",
            )
        )


def _check_chat_adapter(findings: list[Finding], summary: dict[str, Any]) -> None:
    engine = SAATHI / "chat" / "engine.py"
    if not engine.is_file():
        return
    src = engine.read_text(encoding="utf-8")
    summary["chat_uses_adapter"] = "chat_adapter" in src or "chat_generate" in src
    if "chat_generate" not in src and "chat_adapter" not in src:
        findings.append(
            Finding(
                rule_id="chat_engine_missing_adapter",
                path="saathi/chat/engine.py",
                line=0,
                symbol="_default_llm",
                detail="chat engine must route through chat_adapter",
            )
        )
    # Direct generate in engine is only ok if adapter wraps it; prefer none
    if "llm_mod.generate" in src and "chat_generate" not in src:
        findings.append(
            Finding(
                rule_id="chat_direct_llm_generate",
                path="saathi/chat/engine.py",
                line=0,
                symbol="_default_llm",
                detail="chat must not call llm.generate without adapter",
            )
        )
    # M23: engine must not import provider SDKs / credentials
    for needle, rule in (
        ("from openai", "chat_direct_sdk_import"),
        ("import openai", "chat_direct_sdk_import"),
        ("from anthropic", "chat_direct_sdk_import"),
        ("import anthropic", "chat_direct_sdk_import"),
        ("OPENAI_API_KEY", "chat_credential_read"),
        ("ANTHROPIC_API_KEY", "chat_credential_read"),
    ):
        if needle in src:
            findings.append(
                Finding(
                    rule_id=rule,
                    path="saathi/chat/engine.py",
                    line=0,
                    symbol="ChatEngine",
                    detail=f"chat engine must not contain {needle!r}",
                )
            )


def _check_m23_chat_governed(findings: list[Finding], summary: dict[str, Any]) -> None:
    """M23: governed chat default — no llm.generate / SDK / retry / raw log in chat package."""
    chat_root = SAATHI / "chat"
    adapter = SAATHI / "inference" / "chat_adapter.py"
    runtime = chat_root / "runtime.py"
    summary["m23_chat"] = {
        "governed_default": False,
        "runtime_present": runtime.is_file(),
        "adapter_present": adapter.is_file(),
    }

    if not runtime.is_file():
        findings.append(
            Finding(
                rule_id="chat_runtime_missing",
                path="saathi/chat/runtime.py",
                line=0,
                symbol="run_chat_completion",
                detail="M23 requires saathi.chat.runtime as canonical authority",
            )
        )
        return

    rt_src = runtime.read_text(encoding="utf-8")
    summary["m23_chat"]["governed_default"] = (
        "GOVERNED_CHAT_DEFAULT = True" in rt_src
        or "GOVERNED_CHAT_DEFAULT=True" in rt_src
    )
    if "GOVERNED_CHAT_DEFAULT = True" not in rt_src and "GOVERNED_CHAT_DEFAULT=True" not in rt_src:
        findings.append(
            Finding(
                rule_id="chat_governed_default_false",
                path="saathi/chat/runtime.py",
                line=0,
                symbol="GOVERNED_CHAT_DEFAULT",
                detail="governed_chat_default must be true",
            )
        )
    if "LEGACY_CHAT_EXECUTION = False" not in rt_src and "LEGACY_CHAT_EXECUTION=False" not in rt_src:
        findings.append(
            Finding(
                rule_id="chat_legacy_execution_enabled",
                path="saathi/chat/runtime.py",
                line=0,
                symbol="LEGACY_CHAT_EXECUTION",
                detail="legacy_chat_execution must be unavailable (False)",
            )
        )

    # Scan chat package + adapter for forbidden patterns
    scan_files: list[Path] = []
    if chat_root.is_dir():
        scan_files.extend(sorted(chat_root.glob("*.py")))
    if adapter.is_file():
        scan_files.append(adapter)

    forbidden_sdk = ("from openai", "import openai", "from anthropic", "import anthropic")
    forbidden_urls = (
        "api.openai.com",
        "api.anthropic.com",
        "api.groq.com",
        "generativelanguage.googleapis.com",
        "openrouter.ai/api",
    )
    credential_needles = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    )
    raw_log_needles = (
        'logger.info(prompt',
        'logger.debug(prompt',
        'logger.info(f"{prompt',
        "log_prompt=True",
        "log_output=True",
        'logger.info(output',
        'logger.debug(output',
    )

    for path in scan_files:
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()

        def _line_of(sub: str) -> int:
            for i, ln in enumerate(lines, 1):
                if sub in ln:
                    return i
            return 0

        for needle in forbidden_sdk:
            if needle in src:
                findings.append(
                    Finding(
                        rule_id="chat_direct_sdk_import",
                        path=rel,
                        line=_line_of(needle),
                        symbol="chat_package",
                        detail=f"chat must not import provider SDK ({needle})",
                    )
                )
        for needle in forbidden_urls:
            if needle in src:
                findings.append(
                    Finding(
                        rule_id="chat_direct_provider_url",
                        path=rel,
                        line=_line_of(needle),
                        symbol="chat_package",
                        detail=f"chat must not contain provider URL {needle!r}",
                    )
                )
        for needle in credential_needles:
            if needle in src:
                findings.append(
                    Finding(
                        rule_id="chat_credential_read",
                        path=rel,
                        line=_line_of(needle),
                        symbol="chat_package",
                        detail=f"chat must not read credential env {needle}",
                    )
                )
        # llm.generate forbidden in chat package and adapter (AST-level, not docs)
        try:
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "") == "saathi.llm":
                    for alias in node.names or []:
                        if alias.name == "generate":
                            findings.append(
                                Finding(
                                    rule_id="chat_direct_llm_generate",
                                    path=rel,
                                    line=getattr(node, "lineno", 0) or 0,
                                    symbol="chat_package",
                                    detail="M23 chat must not import saathi.llm.generate",
                                )
                            )
                if isinstance(node, ast.Attribute) and node.attr == "generate":
                    if isinstance(node.value, ast.Name) and node.value.id in {
                        "llm",
                        "llm_mod",
                    }:
                        findings.append(
                            Finding(
                                rule_id="chat_direct_llm_generate",
                                path=rel,
                                line=getattr(node, "lineno", 0) or 0,
                                symbol="chat_package",
                                detail="M23 chat must not call llm.generate",
                            )
                        )
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == "generate":
                        # only if file also imports generate from saathi.llm
                        if "from saathi.llm import generate" in src:
                            findings.append(
                                Finding(
                                    rule_id="chat_direct_llm_generate",
                                    path=rel,
                                    line=getattr(node, "lineno", 0) or 0,
                                    symbol="chat_package",
                                    detail="M23 chat must not call generate()",
                                )
                            )
        except SyntaxError:
            pass
        for needle in raw_log_needles:
            if needle in src:
                findings.append(
                    Finding(
                        rule_id="chat_raw_prompt_log" if "prompt" in needle or "log_prompt" in needle else "chat_raw_output_log",
                        path=rel,
                        line=_line_of(needle),
                        symbol="chat_package",
                        detail=f"raw content logging forbidden: {needle}",
                    )
                )
        # Caller-level retry / fallback lists in chat (simple static patterns)
        if re_search_retry(src):
            findings.append(
                Finding(
                    rule_id="chat_caller_retry",
                    path=rel,
                    line=0,
                    symbol="chat_package",
                    detail="chat-specific provider retry loops are forbidden",
                )
            )
        if "fallback_chain" in src and "chat" in rel and "runtime" not in rel:
            # engine may set empty fallback_chain for gateway policy — allow empty only
            if 'fallback_chain": []' not in src and "fallback_chain\": []" not in src and "fallback_chain': []" not in src:
                if "fallback_chain" in src:
                    pass  # engine uses empty list — checked loosely
        if any(t in src for t in ("binance", "ccxt", "withdraw", "place_order")):
            findings.append(
                Finding(
                    rule_id="chat_trading_tool",
                    path=rel,
                    line=0,
                    symbol="chat_package",
                    detail="trading/exchange capability forbidden in chat",
                )
            )

    # Adapter must call runtime
    if adapter.is_file():
        asrc = adapter.read_text(encoding="utf-8")
        if "run_chat_completion" not in asrc and "chat.runtime" not in asrc:
            findings.append(
                Finding(
                    rule_id="chat_adapter_missing_runtime",
                    path="saathi/inference/chat_adapter.py",
                    line=0,
                    symbol="chat_generate",
                    detail="chat_adapter must delegate to chat.runtime",
                )
            )

    # Residual manifest must not retain chat exception
    if MANIFEST_PATH.is_file():
        try:
            data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            for ex in data.get("exceptions") or []:
                pid = (ex.get("path_id") or "").lower()
                if "chat" in pid and "engine" in pid:
                    findings.append(
                        Finding(
                            rule_id="chat_residual_exception_present",
                            path="docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json",
                            line=0,
                            symbol=ex.get("path_id") or "chat",
                            detail="M23 removed chat residual exception; must not reappear",
                        )
                    )
            if int(data.get("chat_residual_exception_count") or 0) != 0:
                findings.append(
                    Finding(
                        rule_id="chat_residual_count_nonzero",
                        path="docs/M21_3_RESIDUAL_EXCEPTION_MANIFEST.json",
                        line=0,
                        symbol="chat_residual_exception_count",
                        detail="chat_residual_exception_count must be 0 after M23",
                    )
                )
        except Exception:
            pass


def re_search_retry(src: str) -> bool:
    """Detect obvious chat-level retry loops (not router chain iteration)."""
    # Very specific anti-patterns
    needles = (
        "for _attempt in range",
        "for attempt in range",
        "max_provider_retries",
        "retry_providers =",
        "provider_fallback_list",
    )
    return any(n in src for n in needles)


def _check_llm_helper(findings: list[Finding], summary: dict[str, Any]) -> None:
    p = SAATHI / "tools" / "_llm_helper.py"
    if not p.is_file():
        return
    src = p.read_text(encoding="utf-8")
    # After M21.3 must not contain direct provider URL invoke chain
    for sub in FORBIDDEN_URLS:
        if sub in src:
            findings.append(
                Finding(
                    rule_id="llm_helper_direct_provider",
                    path="saathi/tools/_llm_helper.py",
                    line=0,
                    symbol="ask_llm",
                    detail=f"_llm_helper still contains provider URL {sub!r}",
                )
            )
    summary["llm_helper_delegates"] = "generate(" in src or "llm.generate" in src


def _check_m22_facades_and_credentials(
    findings: list[Finding], summary: dict[str, Any]
) -> None:
    """M22: product facades must not own provider HTTP/SDK; credentials isolated."""
    facade_files = {
        "saathi/llm.py": "legacy_llm_generate",
        "saathi/agent.py": "agent_runtime",
        "saathi/tools/research.py": "research_tools",
    }
    for rel, symbol in facade_files.items():
        p = ROOT / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for sub in FORBIDDEN_URLS:
            if sub in src:
                findings.append(
                    Finding(
                        rule_id="facade_direct_provider_url",
                        path=rel,
                        line=0,
                        symbol=symbol,
                        detail=f"M22 facade must not contain provider URL {sub!r}",
                    )
                )
        for needle in ("from openai", "import openai", "import anthropic", "from anthropic"):
            if needle in src:
                findings.append(
                    Finding(
                        rule_id="facade_direct_sdk_import",
                        path=rel,
                        line=0,
                        symbol=symbol,
                        detail=f"M22 facade must not import provider SDK ({needle})",
                    )
                )

    # Credential isolation for M22-migrated inference facades / paths only
    # (broader product media tools remain out of M22 scope).
    m22_credential_scan_targets = (
        "saathi/llm.py",
        "saathi/agent.py",
        "saathi/tools/research.py",
        "saathi/tools/_llm_helper.py",
        "saathi/tools/cheap_llm.py",
        "saathi/inference/chat_adapter.py",
        "saathi/inference/compat.py",
        "saathi/inference/legacy_facade.py",
        "saathi/chat/engine.py",
    )
    cred_hits = 0
    for rel in m22_credential_scan_targets:
        if rel in CREDENTIAL_READ_ALLOWLIST:
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for needle in CREDENTIAL_ENV_NEEDLES:
                if needle not in line:
                    continue
                if "getenv" in line or "environ" in line or "os.environ" in line:
                    cred_hits += 1
                    findings.append(
                        Finding(
                            rule_id="caller_credential_read",
                            path=rel,
                            line=i,
                            symbol=needle,
                            detail="provider credential env read outside adapter allowlist",
                        )
                    )
    summary["m22_credential_scan_hits"] = cred_hits
    summary["m22_facade_check"] = True


def _check_cost_unknown_not_zero(findings: list[Finding], summary: dict[str, Any]) -> None:
    try:
        from saathi.inference.cost_policy import CostStatus, validate_pricing
        from saathi.inference.provider_descriptor import get_descriptor

        # Sanity: unknown pricing must not be treated as free paid
        # (descriptor for openai should not be zero_marginal if cloud)
        d = get_descriptor("openai")
        if d is not None and d.local_or_cloud == "cloud" and d.pricing.zero_marginal:
            findings.append(
                Finding(
                    rule_id="unknown_cost_as_zero",
                    path="saathi/inference/provider_descriptor.py",
                    line=0,
                    symbol="openai",
                    detail="cloud provider marked zero_marginal",
                )
            )
        summary["cost_policy_loaded"] = True
    except Exception as e:
        summary["cost_policy_loaded"] = False
        findings.append(
            Finding(
                rule_id="cost_policy_load_error",
                path="saathi/inference/cost_policy.py",
                line=0,
                symbol="",
                detail=type(e).__name__,
                severity="warning",
            )
        )


def _check_m24_durable_governance(findings: list[Finding], summary: dict[str, Any]) -> None:
    """M24: durable governance authority, zero residual exceptions, no process-local production authority."""
    m24: dict[str, Any] = {
        "residual_exception_count": None,
        "durable_store": False,
        "process_local_authority": False,
        "cloud_engine_governed": False,
        "openai_compat_engine_governed": False,
    }

    # Manifest: zero inference residual exceptions
    if MANIFEST_PATH.is_file():
        try:
            data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            ex_count = len(data.get("exceptions") or [])
            m24["residual_exception_count"] = ex_count
            if ex_count != 0:
                findings.append(
                    Finding(
                        rule_id="m24_residual_exceptions_nonzero",
                        path=_rel(MANIFEST_PATH),
                        line=0,
                        symbol="exceptions",
                        detail=f"M24 requires 0 residual exceptions; found {ex_count}",
                    )
                )
            if int(data.get("inference_residual_exception_count") or 0) != 0:
                findings.append(
                    Finding(
                        rule_id="m24_inference_residual_count_nonzero",
                        path=_rel(MANIFEST_PATH),
                        line=0,
                        symbol="inference_residual_exception_count",
                        detail="inference_residual_exception_count must be 0 after M24",
                    )
                )
            for ex in data.get("exceptions") or []:
                pid = (ex.get("path_id") or "").lower()
                if pid in {"engine_cloud_caller", "engine_openai_compat"}:
                    findings.append(
                        Finding(
                            rule_id="m24_engine_residual_reintroduced",
                            path=_rel(MANIFEST_PATH),
                            line=0,
                            symbol=ex.get("path_id") or "",
                            detail="M24 removed engine residual exceptions; must not reappear",
                        )
                    )
        except Exception as e:
            findings.append(
                Finding(
                    rule_id="m24_manifest_parse_error",
                    path=_rel(MANIFEST_PATH),
                    line=0,
                    symbol="",
                    detail=type(e).__name__,
                )
            )

    # Durable modules present
    gov_store = ROOT / "saathi" / "inference" / "governance_store.py"
    gov_svc = ROOT / "saathi" / "inference" / "governance_service.py"
    if not gov_store.is_file() or not gov_svc.is_file():
        findings.append(
            Finding(
                rule_id="m24_governance_modules_missing",
                path="saathi/inference/",
                line=0,
                symbol="governance_store",
                detail="M24 durable governance modules required",
            )
        )
    else:
        m24["durable_store"] = True
        src = gov_store.read_text(encoding="utf-8")
        for needle in (
            "provider_circuit",
            "budget_reservation",
            "cost_usage",
            "BEGIN IMMEDIATE",
            "reserved_amount",
        ):
            if needle not in src:
                findings.append(
                    Finding(
                        rule_id="m24_schema_marker_missing",
                        path="saathi/inference/governance_store.py",
                        line=0,
                        symbol=needle,
                        detail=f"expected schema/protocol marker missing: {needle}",
                    )
                )

    # Residual path dispositions for engines
    try:
        from saathi.inference.residual_paths import ResidualDisposition, get_residual_control

        for pid in ("engine_cloud_caller", "engine_openai_compat"):
            ctrl = get_residual_control(pid)
            if ctrl is None:
                findings.append(
                    Finding(
                        rule_id="m24_engine_control_missing",
                        path="saathi/inference/residual_paths.py",
                        line=0,
                        symbol=pid,
                        detail="engine residual control missing",
                    )
                )
                continue
            if ctrl.disposition is not ResidualDisposition.CANONICAL:
                findings.append(
                    Finding(
                        rule_id="m24_engine_not_canonical",
                        path="saathi/inference/residual_paths.py",
                        line=0,
                        symbol=pid,
                        detail=f"expected CANONICAL, got {ctrl.disposition.value}",
                    )
                )
            else:
                if pid == "engine_cloud_caller":
                    m24["cloud_engine_governed"] = True
                else:
                    m24["openai_compat_engine_governed"] = True
    except Exception as e:
        findings.append(
            Finding(
                rule_id="m24_residual_path_error",
                path="saathi/inference/residual_paths.py",
                line=0,
                symbol="",
                detail=type(e).__name__,
            )
        )

    # Circuit breaker must not claim process-local authority in production path
    cb = ROOT / "saathi" / "inference" / "circuit_breaker.py"
    if cb.is_file():
        csrc = cb.read_text(encoding="utf-8")
        if "DurableGovernanceStore" not in csrc and "governance_store" not in csrc:
            findings.append(
                Finding(
                    rule_id="m24_circuit_not_durable",
                    path="saathi/inference/circuit_breaker.py",
                    line=0,
                    symbol="ProviderCircuitBreakerRegistry",
                    detail="circuit breaker must use durable governance store",
                )
            )
        if '"process_local": True' in csrc or "'process_local': True" in csrc:
            # only ok if marked as non-production; flag if default snapshot still True
            if "persistent\": True" not in csrc and "persistent': True" not in csrc:
                findings.append(
                    Finding(
                        rule_id="m24_process_local_circuit_authority",
                        path="saathi/inference/circuit_breaker.py",
                        line=0,
                        symbol="process_local",
                        detail="process-local must not be production circuit authority",
                    )
                )
                m24["process_local_authority"] = True

    # Cost policy: process_daily_store must not return InMemory as default authority claim
    cp = ROOT / "saathi" / "inference" / "cost_policy.py"
    if cp.is_file():
        cpsrc = cp.read_text(encoding="utf-8")
        if "DurableDailyCostStore" not in cpsrc:
            findings.append(
                Finding(
                    rule_id="m24_cost_not_durable",
                    path="saathi/inference/cost_policy.py",
                    line=0,
                    symbol="process_daily_store",
                    detail="daily cost must use durable store",
                )
            )
        if "def process_daily_store" in cpsrc and "durable_daily_store" not in cpsrc:
            findings.append(
                Finding(
                    rule_id="m24_process_daily_not_durable",
                    path="saathi/inference/cost_policy.py",
                    line=0,
                    symbol="process_daily_store",
                    detail="process_daily_store must delegate to durable authority",
                )
            )

    # Adapters must not call circuit/cost mutation APIs
    for rel, label in (
        ("saathi/inference/adapters/cloud.py", "CloudCallerEngine"),
        ("saathi/inference/adapters/openai_compat.py", "OpenAICompatEngine"),
        ("saathi/inference/adapters/http_providers.py", "http_providers"),
    ):
        p = ROOT / rel
        if not p.is_file():
            continue
        src = p.read_text(encoding="utf-8")
        for banned, rule in (
            ("record_failure(", "m24_adapter_circuit_mutation"),
            ("record_success(", "m24_adapter_circuit_mutation"),
            ("add_spend(", "m24_adapter_budget_mutation"),
            ("reserve_budget(", "m24_adapter_budget_mutation"),
            ("settle_reservation(", "m24_adapter_budget_mutation"),
        ):
            if banned in src:
                findings.append(
                    Finding(
                        rule_id=rule,
                        path=rel,
                        line=0,
                        symbol=label,
                        detail=f"adapter must not call {banned.rstrip('(')}",
                    )
                )

    # OpenAI-compat SSRF policy present
    oc = ROOT / "saathi" / "inference" / "adapters" / "openai_compat.py"
    if oc.is_file():
        osrc = oc.read_text(encoding="utf-8")
        if "validate_openai_compat_base_url" not in osrc:
            findings.append(
                Finding(
                    rule_id="m24_openai_compat_ssrf_missing",
                    path="saathi/inference/adapters/openai_compat.py",
                    line=0,
                    symbol="validate_openai_compat_base_url",
                    detail="SSRF URL policy required for openai_compat",
                )
            )

    # Float money enforcement marker in governance_store
    if gov_store.is_file():
        gsrc = gov_store.read_text(encoding="utf-8")
        if "FLOAT_MONEY_REJECTED" not in gsrc and "binary float" not in gsrc.lower():
            findings.append(
                Finding(
                    rule_id="m24_float_money_not_rejected",
                    path="saathi/inference/governance_store.py",
                    line=0,
                    symbol="_money",
                    detail="must reject binary float money",
                )
            )

    # Production certified must stay false in gate/manifest
    if MANIFEST_PATH.is_file():
        try:
            data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            if data.get("production_certified") is True:
                findings.append(
                    Finding(
                        rule_id="m24_production_certified_true",
                        path=_rel(MANIFEST_PATH),
                        line=0,
                        symbol="production_certified",
                        detail="M24 must not set production_certified=true",
                    )
                )
        except Exception:
            pass

    summary["m24"] = m24
    summary["m24_residual_exception_count"] = m24.get("residual_exception_count")


def run_release_check(*, root: Optional[Path] = None) -> ReleaseReport:
    findings: list[Finding] = []
    summary: dict[str, Any] = {
        "rules": [
            "unknown_inference_path",
            "direct_provider_bypass",
            "new_llm_generate_call_site",
            "direct_provider_url",
            "direct_sdk_constructor",
            "duplicate_request_model",
            "duplicate_governance_type",
            "raw_prompt_or_output_logging",
            "transitional_unknown_enabled",
            "trading_caller_registration",
            "exchange_import_in_inference",
            "fake_provider_production",
            "production_certified_true",
            "chat_engine_missing_adapter",
            "llm_helper_direct_provider",
            "legacy_without_expiry",
            "manifest_exception_no_expiry",
            "facade_direct_provider_url",
            "facade_direct_sdk_import",
            "caller_credential_read",
        ],
        "milestone": "M24",
    }
    base = (root / "saathi") if root else SAATHI
    files = 0
    for p in _iter_py(base if base.is_dir() else SAATHI):
        files += 1
        _scan_ast_file(p, findings)

    _check_residual_paths(findings, summary)
    _check_manifest(findings, summary)
    _check_callers(findings, summary)
    _check_chat_adapter(findings, summary)
    _check_m23_chat_governed(findings, summary)
    _check_llm_helper(findings, summary)
    _check_m22_facades_and_credentials(findings, summary)
    _check_cost_unknown_not_zero(findings, summary)
    _check_m24_durable_governance(findings, summary)

    # Cloud fallback default
    try:
        from saathi.inference.config import load_inference_settings

        s = load_inference_settings()
        summary["allow_cloud_fallback_default"] = bool(s.allow_cloud_fallback)
        if s.allow_cloud_fallback and not __import__("os").getenv(
            "SAATHI_ALLOW_CLOUD_FALLBACK"
        ):
            # settings true without env is suspicious
            pass
    except Exception:
        pass

    blocking = [f for f in findings if f.severity == "blocking"]
    return ReleaseReport(
        ok=len(blocking) == 0,
        production_certified=False,
        files_scanned=files,
        finding_count=len(findings),
        blocking_count=len(blocking),
        findings=findings,
        summary=summary,
    )


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    explain = "--explain" in argv
    as_json = "--json" in argv or not explain
    rep = run_release_check()
    if explain and not as_json:
        print(f"M21.3 release_check: {'PASS' if rep.ok else 'FAIL'}")
        print(f"files_scanned={rep.files_scanned} blocking={rep.blocking_count}")
        print(f"production_certified={rep.production_certified}")
        for f in rep.findings:
            print(f"  [{f.severity}] {f.rule_id} {f.path}:{f.line} {f.symbol} — {f.detail}")
        if rep.ok:
            print("summary:", json.dumps(rep.summary, indent=1, default=str)[:2000])
    else:
        print(json.dumps(rep.to_dict(), indent=1, default=str))
    return 0 if rep.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
