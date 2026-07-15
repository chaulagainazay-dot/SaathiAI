"""InsForge (and similar) provider metadata — read-only, no migration/writes."""
from __future__ import annotations

from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import (
    EvidenceClass,
    KnowledgeQuery,
    KnowledgeResult,
    RetrievalIntent,
    content_fingerprint,
)


class ProviderMetaAdapter:
    name = "provider_meta"

    def supports(self, query: KnowledgeQuery, source: KnowledgeSource) -> bool:
        return source.adapter == self.name and source.source_type == "provider_metadata"

    def describe_capabilities(self) -> dict:
        return {"name": self.name, "modes": ["metadata"], "mutates": False, "writes": False}

    def health(self, source: KnowledgeSource) -> dict:
        try:
            from saathi.providers.insforge import load_config
            from saathi.providers.insforge.provider import InsForgeProvider
            cfg = load_config()
            if not cfg.enabled:
                return {"ok": True, "status": "disabled"}
            r = InsForgeProvider(config=cfg, audit=False).health()
            return {"ok": r.ok, "status": r.data.get("status") if r.ok else r.error_category}
        except Exception as e:
            return {"ok": False, "status": type(e).__name__}

    def retrieve(
        self,
        query: KnowledgeQuery,
        source: KnowledgeSource,
        *,
        limit: int = 8,
    ) -> list[KnowledgeResult]:
        q = query.query.lower()
        # Only respond when query is about providers / insforge / capabilities
        if not any(x in q for x in ("insforge", "provider", "baas", "migration pilot", "capability")):
            if query.intent != RetrievalIntent.INSPECT_PROVIDER:
                return []
        try:
            from saathi.providers.insforge import load_config
            from saathi.providers.insforge.provider import InsForgeProvider, PILOT_STATUS
            cfg = load_config()
            pub = cfg.public_dict()
            text = (
                f"InsForge provider pilot status={PILOT_STATUS} "
                f"enabled={pub.get('enabled')} writes_enabled={pub.get('writes_enabled')} "
                f"allowed_paths={pub.get('allowed_paths')} "
                f"note=data_plane_only_no_trading_no_control_plane"
            )
            return [KnowledgeResult(
                result_id=f"{source.source_id}:config",
                source_id=source.source_id,
                source_type=source.source_type,
                repository_id=source.repository_id,
                object_id="insforge.config",
                path="saathi/providers/insforge",
                title="InsForge provider metadata",
                excerpt=text[:500],
                normalized_content=text[:500],
                native_score=10.0,
                normalized_score=0.8,
                trust_score=0.7,
                freshness_score=1.0,
                final_score=0.0,
                evidence_class=EvidenceClass.PROVIDER_METADATA,
                is_generated=False,
                provenance={"adapter": self.name, "pilot": PILOT_STATUS},
                content_fingerprint=content_fingerprint(text),
            )]
        except Exception:
            return []
