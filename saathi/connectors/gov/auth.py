"""M27 — Auth references only (env names / local secure path). No secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from saathi.connectors.gov.models import AuthMode, ConnectorManifest


@dataclass
class AuthResolution:
    """Result of auth resolution — never includes secret values in evidence."""

    ok: bool
    mode: str
    env_names_present: tuple[str, ...] = ()
    env_names_missing: tuple[str, ...] = ()
    detail: str = ""
    # Internal only: not serialized to evidence
    _secret_present: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "env_names_present": list(self.env_names_present),
            "env_names_missing": list(self.env_names_missing),
            "detail": self.detail,
            "secrets_in_response": False,
        }


def resolve_auth(manifest: ConnectorManifest, *, environ: Optional[dict[str, str]] = None) -> AuthResolution:
    """Check whether configured auth material exists without returning values."""
    env = environ if environ is not None else dict(os.environ)
    mode = manifest.auth_mode

    if mode is AuthMode.NONE:
        return AuthResolution(ok=True, mode=mode.value, detail="no_auth_required")

    if mode is AuthMode.ENV_VAR:
        names = tuple(manifest.auth_env_names or ())
        if not names:
            return AuthResolution(ok=False, mode=mode.value, detail="auth_env_names_empty")
        present = tuple(n for n in names if (env.get(n) or "").strip())
        missing = tuple(n for n in names if n not in present)
        return AuthResolution(
            ok=len(missing) == 0,
            mode=mode.value,
            env_names_present=present,
            env_names_missing=missing,
            detail="env_auth_ok" if not missing else "env_auth_missing",
            _secret_present=len(present) > 0,
        )

    if mode is AuthMode.LOCAL_SECURE:
        # Presence probe only — path from env name SAATHI_CONNECTOR_SECRET_DIR optional
        base = (env.get("SAATHI_CONNECTOR_SECRET_DIR") or "").strip()
        if not base:
            return AuthResolution(
                ok=False,
                mode=mode.value,
                detail="local_secure_dir_not_configured",
            )
        # Do not read secret files into memory for evidence; existence of dir is enough for M27
        from pathlib import Path
        ok = Path(base).is_dir()
        return AuthResolution(
            ok=ok,
            mode=mode.value,
            detail="local_secure_dir_ok" if ok else "local_secure_dir_missing",
            _secret_present=ok,
        )

    if mode is AuthMode.FUTURE_SECRET_MANAGER:
        return AuthResolution(
            ok=False,
            mode=mode.value,
            detail="secret_manager_not_enabled_m27",
        )

    return AuthResolution(ok=False, mode=str(mode), detail="unknown_auth_mode")
