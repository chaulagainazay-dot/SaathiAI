"""ECP M17.24 — external capability register + project Grok skills foundation.

No runtime services. Verifies documentation register completeness and that
project skills exist with required frontmatter for Grok discovery.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / ".grok" / "skills"
SES_000E = ROOT / "docs" / "SES" / "v1.0" / "SES-000E_REPOSITORY_INDEX.md"
MCP_INV = ROOT / "docs" / "integrations" / "MCP_PROJECT_INVENTORY.md"
REPO_DECISIONS = ROOT / "docs" / "integrations" / "REPOSITORY_DECISIONS.md"

REQUIRED_SKILLS = (
    "frontend-gsap",
    "saathios-loop-engineering",
    "external-integration-audit",
    "external-service-health",
)

# Priority 1–3 program repositories (owner/name as registered)
ECP_REPOS = (
    "greensock/gsap-skills",
    "pouyahasanamreji/continuum",
    "braedonsaunders/codeflow",
    "cobusgreyling/loop-engineering",
    "tracewayapp/traceway",
    "VersusControl/versus-incident",
    "gtsteffaniak/filebrowser",
    "Leantime/leantime",
    "ATH-MaaS/Pixelle-Video",
    "Moh4696/freecut",
    "walterlow/freecut",
    "mwakidenis/WebCheck-OSINT",
    "SendWithSES/Drag-and-Drop-Email-Designer",
    "Blotato-Inc/blotato-skills",
    "AHS12/thoth-blueprint",
    "HKUDS/Vibe-Trading",
    "Fincept-Corporation/FinceptTerminal",
)


def test_project_grok_skills_exist_with_frontmatter():
    assert SKILLS_ROOT.is_dir(), "project .grok/skills/ missing"
    for name in REQUIRED_SKILLS:
        skill_md = SKILLS_ROOT / name / "SKILL.md"
        assert skill_md.is_file(), f"missing skill {name}"
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---"), f"{name}: SKILL.md needs YAML frontmatter"
        assert f"name: {name}" in text
        assert "description:" in text
        # body must not claim full product integration
        assert "FULLY_INTEGRATED" not in text


def test_ses_000e_registers_all_ecp_repos():
    text = SES_000E.read_text(encoding="utf-8")
    assert "Part 6 — External Capability Program" in text or "Part 6" in text
    for repo in ECP_REPOS:
        assert repo in text, f"SES-000E missing register entry for {repo}"
    # Foundation must not claim FULLY_INTEGRATED for the program set without evidence
    assert "# Part 6" in text
    ecp_section = text.split("# Part 6", 1)[1]
    assert "FULLY_INTEGRATED" not in ecp_section
    # Honest REGISTERED markers in the ECP body (not merely the status ladder list)
    assert "REGISTERED" in ecp_section
    assert "Maximum status after foundation" in ecp_section


def test_ses_000e_has_required_ecp_fields_for_gsap():
    text = SES_000E.read_text(encoding="utf-8")
    assert "greensock/gsap-skills" in text
    for field in (
        "Integration type",
        "Authoritative role",
        "What it must not replace",
        "License",
        "Rollback / disable method",
        "Local Mac suitability",
    ):
        assert field in text


def test_mcp_inventory_documents_codebase_memory():
    text = MCP_INV.read_text(encoding="utf-8")
    assert "codebase-memory" in text
    assert "headroom" in text.lower()
    assert "SaathiAI/.grok/config.toml" in text or ".grok/config.toml" in text
    assert "Continuum" in text
    # no claim that Continuum is already integrated
    assert "Not configured" in text or "not configured" in text.lower() or "M17.25" in text


def test_repository_decisions_no_false_complete_adapters():
    text = REPO_DECISIONS.read_text(encoding="utf-8")
    assert "adapter stub" in text.lower() or "stubs" in text.lower()
    # Old unqualified "✅ Complete" for OpenMontage row should be gone
    assert "WRAP | ✅ Complete" not in text


def test_project_grok_config_exists_and_is_conservative():
    cfg = ROOT / ".grok" / "config.toml"
    assert cfg.is_file()
    text = cfg.read_text(encoding="utf-8")
    assert "mcp" in text.lower()
    # foundation must not enable continuum command yet
    assert "enabled = true" not in text or "continuum" not in text.lower()
