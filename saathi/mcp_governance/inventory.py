"""Authoritative MCP inventory for SaathiOS (machine-readable).

Markdown companion: ``docs/MCP_INVENTORY.md``.
Cross-ref: ``docs/EXTERNAL_CAPABILITY_STATUS.md``.

Home-level MCPs are inventoried as *session* tools — not product-integrated
merely because they appear in ``~/.grok/config.toml``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

CANONICAL_CODEBASE_MEMORY_ID = "saathi-codebase-memory"
CODEBASE_MEMORY_ALIASES = (
    "codebase-memory",
    "codebase-memory-mcp",
    "code_memory",
)

INVENTORY_VERSION = "m17.25.1"
LAST_VERIFIED = "2026-07-15"


@dataclass(frozen=True)
class McpEntry:
    canonical_name: str
    purpose: str
    provider_or_repository: str
    command_or_url: str
    transport: str
    configuration_file: str
    project_scope: str
    filesystem_scope: str
    network_scope: str
    read_write: str
    credentials: str
    timeout: str
    retry_policy: str
    health_check: str
    enabled_by_default: bool
    classification: str  # authoritative | experimental | broken | blocked
    last_verified: str
    disable_method: str
    security_risks: str
    data_retention: str
    aliases: tuple[str, ...] = ()
    product_integrated: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["aliases"] = list(self.aliases)
        return d


def _entries() -> list[McpEntry]:
    """Built-in inventory of currently detected MCPs (home + project samples)."""
    return [
        McpEntry(
            canonical_name=CANONICAL_CODEBASE_MEMORY_ID,
            purpose="Local code-graph intelligence / semantic codebase recall",
            provider_or_repository="DeusData/codebase-memory-mcp (local binary)",
            command_or_url="~/.local/bin/codebase-memory-mcp",
            transport="stdio (agent); CLI single-shot via CodeMemoryConnector",
            configuration_file="~/.grok/config.toml [mcp_servers.codebase-memory]; "
                               "Saathi driver saathi/infrastructure/connectors/drivers/code_memory.py; "
                               "governance saathi/mcp_governance/",
            project_scope="Session agent + SaathiOS adapter (not automatic product path)",
            filesystem_scope="Indexed project trees only (tool-defined)",
            network_scope="None (local binary)",
            read_write="Read graph/search; index writes to MCP-owned store; "
                       "verified lessons via mcp_governance only",
            credentials="None (local)",
            timeout="connect 5s / request 30s (mcp_governance defaults; CLI up to 120s)",
            retry_policy="Idempotent reads: max 2 retries; writes: no blind retry",
            health_check="saathi.mcp_governance.health_snapshot(); CodeMemoryConnector.health()",
            enabled_by_default=True,
            classification="authoritative",
            last_verified=LAST_VERIFIED,
            disable_method="SAATHI_MCP_CODEBASE_MEMORY_DISABLED=1 or set_enabled(False) "
                           "or enabled=false in user MCP config",
            security_risks="Memory poisoning; path escape if namespace not enforced; "
                           "secret leakage into index",
            data_retention="MCP-local index; Saathi lessons produce Evidence only (no secret bodies)",
            aliases=CODEBASE_MEMORY_ALIASES,
            product_integrated=True,
            notes="Canonical product name saathi-codebase-memory; home aliases are duplicates "
                  "of the same binary — not conflicting backends.",
        ),
        McpEntry(
            canonical_name="context7",
            purpose="Library documentation lookup for coding agents",
            provider_or_repository="Upstash @upstash/context7-mcp",
            command_or_url="npx -y @upstash/context7-mcp",
            transport="stdio",
            configuration_file="~/.grok/config.toml [mcp_servers.context7]",
            project_scope="User agent session only",
            filesystem_scope="N/A",
            network_scope="Context7 / Upstash network",
            read_write="Read docs",
            credentials="None in repo",
            timeout="npx cold-start dependent",
            retry_policy="Agent host default",
            health_check="stderr 'running on stdio' / session only",
            enabled_by_default=True,
            classification="experimental",
            last_verified=LAST_VERIFIED,
            disable_method="enabled = false in ~/.grok/config.toml",
            security_risks="Remote content injection into agent context (untrusted)",
            data_retention="None in SaathiOS",
            product_integrated=False,
        ),
        McpEntry(
            canonical_name="headroom",
            purpose="Intended headroom MCP (broken — binary missing)",
            provider_or_repository="headroom CLI",
            command_or_url="headroom mcp serve",
            transport="stdio",
            configuration_file="~/.grok/config.toml [mcp_servers.headroom]",
            project_scope="User agent",
            filesystem_scope="Unknown",
            network_scope="Unknown",
            read_write="Unknown",
            credentials="—",
            timeout="—",
            retry_policy="—",
            health_check="FAILED — binary missing",
            enabled_by_default=True,
            classification="broken",
            last_verified=LAST_VERIFIED,
            disable_method="enabled = false until installed",
            security_risks="Broken enabled entry causes agent noise",
            data_retention="N/A",
            product_integrated=False,
            notes="Documented debt; do not treat as product MCP.",
        ),
        McpEntry(
            canonical_name="agent-browser",
            purpose="Browser automation MCP (Claude settings)",
            provider_or_repository="agent-browser CLI",
            command_or_url="/opt/homebrew/bin/agent-browser mcp --tools all",
            transport="stdio",
            configuration_file="Claude Code settings (session)",
            project_scope="Claude session only",
            filesystem_scope="Browser profile",
            network_scope="Network",
            read_write="High (browser side effects)",
            credentials="Browser session",
            timeout="Unknown",
            retry_policy="Unknown",
            health_check="Binary path presence only",
            enabled_by_default=False,
            classification="experimental",
            last_verified=LAST_VERIFIED,
            disable_method="Remove from Claude MCP settings",
            security_risks="Ungoverned browser path — SaathiOS browser goes via ExecutionGateway",
            data_retention="Browser profile",
            product_integrated=False,
            notes="Not the governed browser path (M17.23–M17.26).",
        ),
        McpEntry(
            canonical_name="exa",
            purpose="Web search MCP sample (mcporter)",
            provider_or_repository="Exa",
            command_or_url="https://mcp.exa.ai/mcp",
            transport="HTTP",
            configuration_file="config/mcporter.json",
            project_scope="Sample file only",
            filesystem_scope="N/A",
            network_scope="Remote Exa API",
            read_write="Read",
            credentials="Remote API (not in SaathiOS secrets store)",
            timeout="—",
            retry_policy="—",
            health_check="None in SaathiOS",
            enabled_by_default=False,
            classification="experimental",
            last_verified=LAST_VERIFIED,
            disable_method="Delete or ignore config/mcporter.json entry",
            security_risks="Remote untrusted results",
            data_retention="None",
            product_integrated=False,
        ),
        McpEntry(
            canonical_name="hosted-agent-connectors",
            purpose="Hosted GitHub / Gmail / Drive / tasks (agent host OAuth)",
            provider_or_repository="Agent host (Cursor/Claude/Grok host)",
            command_or_url="Hosted OAuth",
            transport="Host",
            configuration_file="Host session settings",
            project_scope="Session",
            filesystem_scope="Cloud",
            network_scope="Cloud",
            read_write="Varies",
            credentials="Host OAuth",
            timeout="Host",
            retry_policy="Host",
            health_check="Session-dependent",
            enabled_by_default=False,
            classification="experimental",
            last_verified=LAST_VERIFIED,
            disable_method="Disconnect host MCP",
            security_risks="Cloud data exposure; not ExecutionGateway-routed",
            data_retention="Host",
            product_integrated=False,
        ),
        McpEntry(
            canonical_name="continuum",
            purpose="Shared engineering knowledge memory (external candidate)",
            provider_or_repository="pouyahasanamreji/continuum",
            command_or_url="NOT INSTALLED",
            transport="MCP (planned)",
            configuration_file="Not configured — BLOCKED_LICENSE",
            project_scope="Deferred",
            filesystem_scope="Would be project-path only",
            network_scope="TBD",
            read_write="Deferred",
            credentials="TBD",
            timeout="N/A",
            retry_policy="N/A",
            health_check="N/A — not installed",
            enabled_by_default=False,
            classification="blocked",
            last_verified=LAST_VERIFIED,
            disable_method="Do not enable; keep out of project MCP config",
            security_risks="License unclear; memory poisoning if installed prematurely",
            data_retention="N/A",
            product_integrated=False,
            notes="Status BLOCKED_LICENSE. Public repo exists; no clear root licence. "
                  "No clone, package, embed, or redistribute authorized.",
        ),
    ]


def load_inventory() -> list[McpEntry]:
    return list(_entries())


def inventory_entries() -> list[dict[str, Any]]:
    return [e.to_dict() for e in load_inventory()]


def inventory_by_name() -> dict[str, McpEntry]:
    out: dict[str, McpEntry] = {}
    for e in load_inventory():
        out[e.canonical_name] = e
        for a in e.aliases:
            out[a] = e
    return out


def detect_duplicates(
    configured_names: Iterable[str] | None = None,
    *,
    backends: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Detect duplicate MCP names and conflicting backends.

    If two active names map to *different* backends and ownership is unclear,
    returns ``requires_human_decision=True`` (caller should stop with
    REQUIRES_HUMAN_DECISION).
    """
    names = list(configured_names) if configured_names is not None else list(
        CODEBASE_MEMORY_ALIASES
    ) + [CANONICAL_CODEBASE_MEMORY_ID]
    inv = inventory_by_name()
    # Group aliases that resolve to same canonical
    groups: dict[str, list[str]] = {}
    unknown: list[str] = []
    for n in names:
        e = inv.get(n)
        if e is None:
            unknown.append(n)
            continue
        groups.setdefault(e.canonical_name, []).append(n)

    duplicate_names = {k: v for k, v in groups.items() if len(set(v)) > 1}
    conflicts: list[dict[str, str]] = []
    requires_human = False
    if backends:
        # backends: configured_name -> command/url identity
        by_backend: dict[str, list[str]] = {}
        for n, b in backends.items():
            key = hashlib.sha256(str(b).strip().encode()).hexdigest()[:16]
            by_backend.setdefault(key, []).append(n)
        # Same alias family, different backend hashes → conflict
        canon_backends: dict[str, set[str]] = {}
        for n, b in backends.items():
            e = inv.get(n)
            canon = e.canonical_name if e else n
            canon_backends.setdefault(canon, set()).add(str(b).strip())
        for canon, backs in canon_backends.items():
            if len(backs) > 1:
                conflicts.append({
                    "canonical": canon,
                    "backends": " | ".join(sorted(backs)),
                })
                requires_human = True

    return {
        "duplicate_name_groups": duplicate_names,
        "unknown_names": unknown,
        "conflicts": conflicts,
        "requires_human_decision": requires_human,
        "canonical_codebase_memory": CANONICAL_CODEBASE_MEMORY_ID,
        "aliases": list(CODEBASE_MEMORY_ALIASES),
        "same_backend_aliases_ok": not requires_human,
    }


def inventory_complete(detected_names: Iterable[str]) -> dict[str, Any]:
    """Every detected name must appear as canonical or alias in inventory."""
    inv = inventory_by_name()
    missing = [n for n in detected_names if n not in inv]
    return {
        "complete": len(missing) == 0,
        "missing": missing,
        "inventory_size": len(load_inventory()),
        "version": INVENTORY_VERSION,
    }


def resolve_canonical(name: str) -> str | None:
    e = inventory_by_name().get(name)
    return e.canonical_name if e else None


def continuum_status() -> dict[str, Any]:
    e = inventory_by_name()["continuum"]
    return {
        "repository": "pouyahasanamreji/continuum",
        "status": "BLOCKED_LICENSE",
        "classification": e.classification,
        "installed": False,
        "product_integrated": False,
        "reason": (
            "Public repository exists; operational documentation may exist; "
            "no clear root licence found; no direct clone, packaging, embedding, "
            "or redistribution authorized."
        ),
        "future_pilot_requires": "Published licence or written permission",
    }


def inventory_json() -> str:
    return json.dumps({
        "version": INVENTORY_VERSION,
        "last_verified": LAST_VERIFIED,
        "entries": inventory_entries(),
        "continuum": continuum_status(),
    }, indent=2)
