"""Code Memory — codebase-memory-mcp as a Saathi connector (Engineering dept).

Wires the code-intelligence engine (DeusData/codebase-memory-mcp) in as a
uniform driver, not the center: Saathi asks the registry for code capabilities;
the binary is a swappable provider behind this driver. Execution shells out to
the binary's single-shot CLI (`codebase-memory-mcp cli <tool> <json>`) — 100%
local, no network, no API keys. Inert (AUTH_REQUIRED) until the binary is present.

Env: CODEBASE_MEMORY_BIN overrides the binary path (default: ~/.local/bin/codebase-memory-mcp).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from ..base import Connector, Health, Status
from ..manifest import Manifest

# the binary's 14 tools, surfaced as connector capabilities
_TOOLS = frozenset({
    "index_repository", "search_graph", "query_graph", "trace_path",
    "get_code_snippet", "get_graph_schema", "get_architecture", "search_code",
    "list_projects", "delete_project", "index_status", "detect_changes",
    "manage_adr", "ingest_traces",
})


def _binary() -> str | None:
    env = os.getenv("CODEBASE_MEMORY_BIN")
    if env and os.path.exists(env):
        return env
    default = os.path.expanduser("~/.local/bin/codebase-memory-mcp")
    if os.path.exists(default):
        return default
    return shutil.which("codebase-memory-mcp")


class CodeMemoryConnector(Connector):
    id = "code_memory"

    def manifest(self) -> Manifest:
        return Manifest(
            id=self.id, display_name="Code Memory (codebase-memory-mcp)",
            category="engineering", version=1, capabilities=_TOOLS,
            permissions=frozenset({"read_fs"}), requires_auth=True,  # "auth" == binary present
            cost=0.0, latency="low", reliability=0.9,
            health_checks=frozenset({"binary"}))

    def authenticate(self) -> bool:
        return _binary() is not None

    def health(self) -> Health:
        b = _binary()
        if not b:
            return Health(Status.AUTH_REQUIRED,
                          "binary not installed (see codebase-memory-mcp)")
        return Health(Status.OK, f"local code-intelligence engine ready", metrics={"binary": b})

    def execute(self, capability: str, **payload):
        """Run one code-intelligence tool. payload becomes the tool's JSON args."""
        self._require(capability)
        b = _binary()
        args = json.dumps(payload) if payload else "{}"
        proc = subprocess.run([b, "cli", capability, args],
                              capture_output=True, text=True, timeout=payload.pop("_timeout", 120))
        out = proc.stdout.strip()
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            return {"ok": proc.returncode == 0, "output": out, "error": proc.stderr.strip()[:500]}
