"""M29 — Automatic registry documentation generation."""
from __future__ import annotations

from typing import Any, Optional

from saathi.connectors.registry.trust import trust_summary


def generate_registry_docs(
    registry: Any = None,
    *,
    include_trust_matrix: bool = True,
) -> dict[str, Any]:
    """Produce connector catalog + trust/capability/rollout summaries."""
    if registry is None:
        from saathi.connectors.gov.registry import get_registry
        registry = get_registry()

    catalog: list[dict[str, Any]] = []
    trust_counts: dict[str, int] = {}
    cap_counts: dict[str, int] = {}
    rollout_union: set[str] = set()

    for rec in registry.all_records():
        m = rec.manifest
        trust = getattr(m, "trust_level", "INTERNAL")
        trust_s = trust if isinstance(trust, str) else getattr(trust, "value", str(trust))
        caps = list(getattr(m, "capability_classes", ()) or ())
        if not caps:
            # fall back to kind-derived labels for catalog
            kind = getattr(m, "kind", None)
            kind_s = kind.value if hasattr(kind, "value") else str(kind or "http")
            caps = [kind_s.upper()]
        rollout = list(getattr(m, "rollout_compatible", ()) or ())
        for r in rollout:
            rollout_union.add(str(r).upper())
        trust_counts[trust_s] = trust_counts.get(trust_s, 0) + 1
        for c in caps:
            cs = c if isinstance(c, str) else getattr(c, "value", str(c))
            cap_counts[cs] = cap_counts.get(cs, 0) + 1

        catalog.append({
            "connector_id": m.connector_id,
            "version": m.version,
            "display_name": getattr(m, "display_name", "") or m.connector_id,
            "description": m.description or "",
            "owner": getattr(m, "owner", "") or "",
            "adapter_type": getattr(m, "adapter_type", None)
                or (m.kind.value if hasattr(m.kind, "value") else str(m.kind)),
            "trust_level": trust_s,
            "lifecycle": rec.lifecycle.value if hasattr(rec.lifecycle, "value") else str(rec.lifecycle),
            "capability_classes": [c if isinstance(c, str) else getattr(c, "value", str(c)) for c in caps],
            "supported_operations": list(m.supported_operations or m.capabilities or ()),
            "rollout_compatible": [str(r).upper() for r in rollout],
            "dependencies": list(getattr(m, "dependencies", ()) or ()),
            "deprecated": bool(getattr(m, "deprecated", False)),
            "replacement_connector": getattr(m, "replacement_connector", "") or "",
            "health_policy": getattr(m, "health_policy", None) or {},
            "readiness_policy": getattr(m, "readiness_policy", None) or {},
            "supported_environments": list(getattr(m, "supported_environments", ()) or ()),
        })

    catalog.sort(key=lambda x: x["connector_id"])

    out: dict[str, Any] = {
        "schema": "m29.registry_docs.v1",
        "connector_catalog": catalog,
        "trust_summary": {
            "counts": trust_counts,
            "matrix": trust_summary() if include_trust_matrix else {},
        },
        "capability_summary": {
            "counts": cap_counts,
            "unique": sorted(cap_counts.keys()),
        },
        "rollout_summary": {
            "union_modes": sorted(rollout_union),
            "connector_count": len(catalog),
        },
        "privacy_safe": True,
        "m29": True,
    }
    return out


def render_registry_docs_markdown(docs: Optional[dict[str, Any]] = None, registry: Any = None) -> str:
    docs = docs or generate_registry_docs(registry)
    lines = [
        "# Connector Registry Catalog (M29)",
        "",
        f"Connectors: **{docs['rollout_summary']['connector_count']}**",
        "",
        "## Catalog",
        "",
        "| ID | Version | Trust | Adapter | Ops | Deprecated |",
        "|----|---------|-------|---------|-----|------------|",
    ]
    for c in docs["connector_catalog"]:
        lines.append(
            f"| `{c['connector_id']}` | {c['version']} | {c['trust_level']} | "
            f"{c['adapter_type']} | {len(c['supported_operations'])} | "
            f"{'yes' if c['deprecated'] else 'no'} |"
        )
    lines.extend(["", "## Trust counts", ""])
    for k, v in sorted(docs["trust_summary"]["counts"].items()):
        lines.append(f"- **{k}**: {v}")
    lines.extend(["", "## Capability counts", ""])
    for k, v in sorted(docs["capability_summary"]["counts"].items()):
        lines.append(f"- **{k}**: {v}")
    lines.extend(["", "## Rollout modes (union)", ""])
    lines.append(", ".join(docs["rollout_summary"]["union_modes"]) or "(none)")
    lines.append("")
    return "\n".join(lines)
