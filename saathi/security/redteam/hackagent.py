"""M15.2 optional HackAgent wrapper — isolated, pinned, advisory-only.

HackAgent (Apache-2.0) is an OPTIONAL dev-security dependency used to generate
adversarial prompts and run attack strategies. It is:
  * NOT a production dependency and never on the production request path
  * local-mode only; cloud sync disabled by default
  * pinned to a reviewed version; an unpinned/absent install is env-blocked
  * ADVISORY — its judgments never confirm or clear a finding on their own
When absent (as in this environment) the harness runs deterministic-only and
reports HackAgent as environment_blocked. Nothing here calls out to a network.
"""
from __future__ import annotations

from saathi.security.redteam.config import HACKAGENT_PINNED_VERSION


def availability() -> dict:
    """Honest availability probe — never raises, never installs, never network."""
    try:
        import hackagent  # type: ignore
        version = getattr(hackagent, "__version__", "unknown")
        pinned_ok = version == HACKAGENT_PINNED_VERSION
        return {
            "installed": True, "version": version,
            "pinned_version": HACKAGENT_PINNED_VERSION,
            "pinned_ok": pinned_ok,
            "status": "available" if pinned_ok else "version_mismatch_blocked",
            "cloud_sync": False, "mode": "local",
        }
    except Exception:
        return {
            "installed": False, "version": None,
            "pinned_version": HACKAGENT_PINNED_VERSION,
            "status": "environment_blocked",
            "reason": "HackAgent not installed (optional dev-security extra); "
                      "deterministic probes are authoritative",
            "cloud_sync": False, "mode": "local",
        }


def guard_enabled(enabled: bool) -> None:
    """Refuse to 'enable' HackAgent unless genuinely installed + pinned + local."""
    if not enabled:
        return
    a = availability()
    if a["status"] != "available":
        raise RuntimeError(f"HackAgent cannot be enabled: {a['status']}")
