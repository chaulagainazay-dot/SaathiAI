"""M20.7 — Shared flag inventory for Engineering Orchestrator + Inference.

Does not introduce a second feature-flag system. Documents and reads existing
SAATHI_ENG_* and SAATHI_INF_* / SAATHI_INFERENCE_* environment variables.

Domains remain separate; this is observability + disable discovery only.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FlagSpec:
    key: str
    domain: str  # engineering | inference | shared
    default: str
    description: str
    security_sensitive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Canonical inventory (read-only catalogue)
FLAG_CATALOG: tuple[FlagSpec, ...] = (
    # Engineering M20.0+
    FlagSpec("SAATHI_ENG_ORCH_ENABLED", "engineering", "0", "Engineering orchestrator master switch"),
    FlagSpec("SAATHI_ENG_ORCH_LAUNCH", "engineering", "0", "Allow agent launch"),
    FlagSpec("SAATHI_ENG_ORCH_WRITES", "engineering", "0", "Allow write-enabled sessions", True),
    FlagSpec("SAATHI_ENG_ORCH_COMMITS", "engineering", "0", "Allow commit acceptance", True),
    FlagSpec("SAATHI_ENG_ORCH_PUSHES", "engineering", "0", "Allow push", True),
    FlagSpec("SAATHI_ENG_ORCH_MAX_SESSIONS", "engineering", "1", "Max concurrent engineering sessions"),
    FlagSpec("SAATHI_ENG_ORCH_MAX_RETRIES", "engineering", "3", "Max retries per issue"),
    FlagSpec("SAATHI_ENG_ORCH_SESSION_TIMEOUT_SEC", "engineering", "3600", "Session timeout"),
    FlagSpec("SAATHI_ENG_ORCH_STALL_TIMEOUT_SEC", "engineering", "600", "Stall threshold"),
    FlagSpec("SAATHI_ENG_ORCH_STORE", "engineering", "", "Override engineering store directory"),
    FlagSpec("SAATHI_ENG_ORCH_ALLOWED_ADAPTERS", "engineering", "mock,claude_code", "Agent adapters"),
    FlagSpec("SAATHI_ENG_ORCH_ALLOWED_BRANCHES", "engineering", "milestone/*,feat/*,fix/*", "Branch allowlist"),
    # Inference M20.1–M20.6
    FlagSpec("SAATHI_INFERENCE_ENABLED", "inference", "0", "Inference runtime master switch"),
    FlagSpec("SAATHI_INFERENCE_GATEWAY_ENABLED", "inference", "0", "M20.2 governed gateway path"),
    FlagSpec("SAATHI_ALLOW_CLOUD_FALLBACK", "inference", "0", "Cloud fallback (must stay off for local pilots)", True),
    FlagSpec("SAATHI_DEFAULT_ENGINE", "inference", "ollama", "Default local engine id"),
    FlagSpec("SAATHI_OLLAMA_BASE_URL", "inference", "http://127.0.0.1:11434", "Ollama endpoint"),
    FlagSpec("SAATHI_OLLAMA_ALLOWED_HOSTS", "inference", "127.0.0.1,localhost,::1", "Host allowlist"),
    FlagSpec("SAATHI_INFERENCE_MAX_PROMPT_CHARS", "inference", "16000", "Prompt bound"),
    FlagSpec("SAATHI_INFERENCE_MAX_OUTPUT_TOKENS", "inference", "1024", "Output token bound"),
    FlagSpec("SAATHI_INFERENCE_TIMEOUT", "inference", "60", "Request timeout seconds"),
    FlagSpec("SAATHI_INFERENCE_MAX_CONCURRENT", "inference", "1", "Local concurrency"),
    FlagSpec("SAATHI_INFERENCE_MIN_AVAILABLE_MEMORY_GB", "inference", "1.5", "Memory gate"),
    FlagSpec("SAATHI_INF_ROLLOUT", "inference", "legacy", "Global caller rollout mode"),
    FlagSpec("SAATHI_INF_ROLLOUT_CHEAP_ASK", "inference", "legacy", "cheap_ask mode"),
    FlagSpec("SAATHI_INF_ROLLOUT_PROSE_CLEAN", "inference", "legacy", "prose_clean mode"),
    FlagSpec("SAATHI_OPENJARVIS_COMPAT", "inference", "0", "OJ concepts flag (no OJ process)"),
    # M21.0 provider kill switches (1 = killed / disabled)
    FlagSpec("SAATHI_INFERENCE_KILL_ALL", "inference", "0", "Hard-kill all providers via policy", True),
    FlagSpec("SAATHI_PROVIDER_KILL_OLLAMA", "inference", "0", "Kill local ollama provider", True),
    FlagSpec("SAATHI_PROVIDER_KILL_FAKE", "inference", "0", "Kill fake test engine"),
    FlagSpec("SAATHI_PROVIDER_KILL_OPENAI_COMPAT", "inference", "0", "Kill openai-compat engine"),
    FlagSpec("SAATHI_PROVIDER_KILL_ANTHROPIC", "inference", "0", "Kill anthropic cloud family", True),
    FlagSpec("SAATHI_PROVIDER_KILL_OPENAI", "inference", "0", "Kill openai cloud family", True),
    FlagSpec("SAATHI_PROVIDER_KILL_GROQ", "inference", "0", "Kill groq cloud family", True),
    FlagSpec("SAATHI_PROVIDER_KILL_GEMINI", "inference", "0", "Kill gemini cloud family", True),
    FlagSpec("SAATHI_PROVIDER_KILL_OPENROUTER", "inference", "0", "Kill openrouter multiproxy", True),
    FlagSpec("SAATHI_PROVIDER_KILL_DEEPSEEK", "inference", "0", "Kill deepseek family", True),
    FlagSpec("SAATHI_PROVIDER_KILL_GLM", "inference", "0", "Kill glm family", True),
    FlagSpec("SAATHI_PROVIDER_KILL_QWEN", "inference", "0", "Kill qwen family", True),
)


def _present(key: str) -> bool:
    return key in os.environ


def _raw(key: str) -> str | None:
    return os.environ.get(key)


def flag_snapshot() -> dict[str, Any]:
    """Current effective flags (values only; never secrets)."""
    rows = []
    enabled_sensitive = []
    for spec in FLAG_CATALOG:
        raw = _raw(spec.key)
        effective = raw if raw is not None and str(raw).strip() != "" else spec.default
        # treat empty as default
        is_on = str(effective).strip().lower() in ("1", "true", "yes", "on")
        if spec.default in ("0", "legacy") and raw is not None:
            # non-boolean modes
            if spec.key.startswith("SAATHI_INF_ROLLOUT"):
                is_on = str(effective).strip().lower() not in ("", "legacy")
        row = {
            "key": spec.key,
            "domain": spec.domain,
            "default": spec.default,
            "set_in_env": _present(spec.key),
            "effective": effective if not spec.security_sensitive or not is_on else effective,
            "description": spec.description,
            "security_sensitive": spec.security_sensitive,
            "non_default": (raw is not None and str(raw).strip() != "" and str(raw).strip() != str(spec.default)),
        }
        rows.append(row)
        if spec.security_sensitive and is_on:
            enabled_sensitive.append(spec.key)
    return {
        "schema": "m20_flag_snapshot.v1",
        "flags": rows,
        "security_sensitive_enabled": enabled_sensitive,
        "disable_all_hint": disable_procedure()["unset_commands"],
    }


def disable_procedure() -> dict[str, Any]:
    eng = [
        "SAATHI_ENG_ORCH_ENABLED",
        "SAATHI_ENG_ORCH_LAUNCH",
        "SAATHI_ENG_ORCH_WRITES",
        "SAATHI_ENG_ORCH_COMMITS",
        "SAATHI_ENG_ORCH_PUSHES",
    ]
    inf = [
        "SAATHI_INFERENCE_ENABLED",
        "SAATHI_INFERENCE_GATEWAY_ENABLED",
        "SAATHI_ALLOW_CLOUD_FALLBACK",
        "SAATHI_INF_ROLLOUT",
        "SAATHI_INF_ROLLOUT_CHEAP_ASK",
        "SAATHI_INF_ROLLOUT_PROSE_CLEAN",
    ]
    provider_kills = [
        "SAATHI_INFERENCE_KILL_ALL",
        "SAATHI_PROVIDER_KILL_OLLAMA",
        "SAATHI_PROVIDER_KILL_ANTHROPIC",
        "SAATHI_PROVIDER_KILL_OPENAI",
        "SAATHI_PROVIDER_KILL_GROQ",
        "SAATHI_PROVIDER_KILL_GEMINI",
        "SAATHI_PROVIDER_KILL_OPENROUTER",
        "SAATHI_PROVIDER_KILL_DEEPSEEK",
        "SAATHI_PROVIDER_KILL_GLM",
        "SAATHI_PROVIDER_KILL_QWEN",
        "SAATHI_PROVIDER_KILL_OPENAI_COMPAT",
        "SAATHI_PROVIDER_KILL_FAKE",
    ]
    return {
        "engineering_keys": eng,
        "inference_keys": inf,
        "provider_kill_keys": provider_kills,
        "unset_commands": [
            "unset " + " ".join(eng),
            "unset " + " ".join(inf),
            "unset " + " ".join(provider_kills),
            "# or set masters to 0 / legacy; set kills to 0 to re-enable after deliberate kill",
            "# emergency: export SAATHI_INFERENCE_KILL_ALL=1",
        ],
        "hard_denials_always_false": [
            "merge_allowed",
            "deploy_allowed",
            "force_push_allowed",
            "trading_allowed",
            "unrestricted_shell",
            "unrestricted_mcp",
        ],
        "note": "Defaults are already off/legacy; unsetting is sufficient. M21.0 kill switches default off (not killed).",
    }


def domains_isolated() -> dict[str, Any]:
    """Static guarantees: domains not merged."""
    return {
        "engineering_package": "saathi.engineering",
        "inference_package": "saathi.inference",
        "shared_console": "saathi.m20_console",
        "second_mission_engine": False,
        "second_model_router": False,
        "second_execution_gateway": False,
        "second_run_ledger": False,
        "merged_store": False,
        "trading_guardian_coupled": False,
    }
