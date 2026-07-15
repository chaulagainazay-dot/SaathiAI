"""Permission and sensitive-path filtering for knowledge retrieval."""
from __future__ import annotations

import re
from pathlib import Path

from saathi.knowledge.registry import KnowledgeSource
from saathi.knowledge.types import KnowledgeQuery, TrustLevel

_SENSITIVE_NAME = re.compile(
    r"(^\.env$|\.env\.|credentials|secret|private[_-]?key|\.pem$|id_rsa|"
    r"wallet|seed\.json|exchange|broker_token)",
    re.I,
)

_TRUST_RANK = {
    TrustLevel.HIGH: 3,
    TrustLevel.MEDIUM: 2,
    TrustLevel.LOW: 1,
    TrustLevel.UNTRUSTED: 0,
}


def path_is_sensitive(path: str) -> bool:
    p = (path or "").replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    if _SENSITIVE_NAME.search(name) or _SENSITIVE_NAME.search(p):
        return True
    parts = p.lower().split("/")
    if any(x in parts for x in ("secrets", "private_keys", ".ssh", "wallets")):
        return True
    return False


def source_permitted(query: KnowledgeQuery, source: KnowledgeSource) -> tuple[bool, str]:
    if not source.enabled:
        return False, "source_disabled"
    if _TRUST_RANK[source.trust] < _TRUST_RANK[query.min_trust]:
        return False, "trust_below_minimum"
    if query.source_type_denylist and source.source_type in query.source_type_denylist:
        return False, "source_type_denied"
    if query.source_type_allowlist and source.source_type not in query.source_type_allowlist:
        return False, "source_type_not_allowlisted"
    if query.repository_ids and source.repository_id not in query.repository_ids:
        # empty list means default set — handled by router
        pass
    # Trading / exchange secrets never via knowledge
    if "exchange" in source.source_id.lower() or "trading_guardian_secrets" in source.source_id:
        return False, "trading_secrets_denied"
    return True, "ok"


def filter_sensitive_results(path: str, excerpt: str) -> tuple[bool, str]:
    """Return (ok, reason). Fail closed on sensitive paths."""
    if path_is_sensitive(path):
        return False, "sensitive_path"
    return True, "ok"
