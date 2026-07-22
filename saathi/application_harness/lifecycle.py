"""M17.4 harness update + revocation lifecycle.

Update: compare source/version/hash, RESET trust (a new version is never
automatically trusted), support rollback. Revocation: disable / quarantine /
revoke / uninstall — all block execution and preserve evidence.
"""
from __future__ import annotations

import copy
import time

from saathi.application_harness.models import HarnessDefinition, TrustStatus
from saathi.application_harness import trust as T


def check_update(current: HarnessDefinition, *, new_version: str,
                 new_commit: str, new_hash: str = "",
                 old_hash: str = "") -> dict:
    changed = (new_version != current.version) or (new_commit != current.source_commit) \
        or (bool(new_hash) and new_hash != old_hash)
    return {"update_available": changed,
            "version_changed": new_version != current.version,
            "source_changed": new_commit != current.source_commit,
            "hash_changed": bool(new_hash) and new_hash != old_hash,
            "trust_reset_required": changed}


def apply_update(current: HarnessDefinition, *, new_version: str,
                 new_commit: str) -> tuple[HarnessDefinition, HarnessDefinition]:
    """Returns (updated, backup). The updated harness is NOT trusted — trust
    resets to source_pinned pending a fresh review. backup enables rollback."""
    backup = copy.deepcopy(current)
    updated = copy.deepcopy(current)
    updated.version = new_version
    T.revalidate_source(updated, new_commit=new_commit)  # resets trust
    updated.version = new_version
    updated.updated_at = time.time()
    return updated, backup


def disable(defn: HarnessDefinition) -> HarnessDefinition:
    # a disabled harness is deprecated (blocks execution) but keeps its record
    defn.trust_status = TrustStatus.DEPRECATED.value
    return defn


def quarantine(defn: HarnessDefinition, reason: str = "") -> HarnessDefinition:
    return T.quarantine(defn, reason)


def revoke(defn: HarnessDefinition, reason: str = "") -> HarnessDefinition:
    defn.trust_status = TrustStatus.REVOKED.value
    defn.validation_status = f"revoked:{reason}"[:120]
    return defn


def uninstall(defn: HarnessDefinition) -> dict:
    prev = defn.trust_status
    defn.trust_status = TrustStatus.REVOKED.value
    return {"uninstalled": True, "harness": defn.harness_id,
            "previous_trust": prev, "evidence_preserved": True}


def blocked_by_lifecycle(defn: HarnessDefinition) -> tuple[bool, str]:
    ok, reason = T.can_execute(defn)
    return (not ok), reason
