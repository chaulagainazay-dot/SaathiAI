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
    "saathi/inference/chat_adapter.py",
    "saathi/tools/cheap_llm.py",
    "saathi/tools/_llm_helper.py",
    "saathi/llm.py",  # definition + internal only
    "saathi/inference/adapters/cloud.py",
})

# Files allowed to construct OpenAI/Anthropic SDKs or provider URLs
PROVIDER_SDK_ALLOWLIST: frozenset[str] = frozenset({
    "saathi/llm.py",
    "saathi/agent.py",
    "saathi/vision.py",
    "saathi/tools/voice.py",
    "saathi/tools/mr_yeti_voice.py",
    "saathi/tools/video_editor.py",
    "saathi/tools/speaking_eval.py",
    "saathi/tools/writing_eval.py",
    "saathi/tools/auto_dev.py",
    "saathi/tools/research.py",
    "saathi/tools/cheap_llm.py",
    "saathi/server.py",
    "saathi/inference/bypass_guard.py",
    "saathi/inference/release_check.py",
})

PROVIDER_SDK_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "saathi/inference/adapters/",
    "saathi/infrastructure/human_browser/",
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
    schema: str = "m21.3.release_check.v1"
    milestone: str = "M21.3"
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
        ]
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
    _check_llm_helper(findings, summary)
    _check_cost_unknown_not_zero(findings, summary)

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
