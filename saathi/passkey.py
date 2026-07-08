"""Passkey (WebAuthn) — v1.2 adapter over Security Store.

The public API is unchanged from v1.1 for backward compatibility.
The backend now uses SQLite via Security Store instead of JSON files.
"""
from __future__ import annotations

import time

from saathi.security.store import get_store


def _store():
    return get_store()


def _owner_id() -> str:
    return _store().get_or_create_owner()


_pending: dict[str, bytes] = {}   # host → last challenge (single owner)


def has_passkey(rp_id: str = "") -> bool:
    rows = _store().passkey_list(_owner_id(), rp_id=rp_id)
    return len(rows) > 0


def registration_options(rp_id: str) -> dict:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                          ResidentKeyRequirement, UserVerificationRequirement)
    opts = generate_registration_options(
        rp_id=rp_id, rp_name="SaathiOS", user_name="ajay", user_id=b"ajay-owner",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED))
    _pending[rp_id] = opts.challenge
    return __import__("json").loads(options_to_json(opts))


def verify_registration(credential: dict, rp_id: str, origin: str, ua: str = "") -> bool:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url
    import re
    ch = _pending.get(rp_id)
    if not ch:
        return False
    v = verify_registration_response(credential=__import__("json").dumps(credential),
                                     expected_challenge=ch, expected_rp_id=rp_id,
                                     expected_origin=origin)
    # Parse UA for device metadata
    device_name = ""
    browser = ""
    platform = "desktop"
    if ua:
        browser = ("Edge" if re.search(r"Edg/|EdgA/", ua) else
                   "Chrome" if re.search(r"Chrome|CriOS", ua) else
                   "Firefox" if re.search(r"Firefox|FxiOS", ua) else
                   "Safari" if "Safari" in ua else "Unknown")
        device_name = ("iPhone" if "iPhone" in ua else
                       "iPad" if "iPad" in ua else
                       "Mac" if "Mac OS X" in ua or "Macintosh" in ua else
                       "Android" if "Android" in ua else
                       "Windows" if "Windows" in ua else
                       "Linux" if "Linux" in ua else "Unknown")
        platform = ("mobile" if re.search(r"iPhone|Android.*Mobile", ua) else
                    "tablet" if re.search(r"iPad|Android(?!.*Mobile)", ua) else
                    "desktop")
    _store().passkey_save(
        user_id=_owner_id(),
        credential_id=bytes_to_base64url(v.credential_id),
        public_key=bytes_to_base64url(v.credential_public_key),
        rp_id=rp_id,
        sign_count=v.sign_count,
        device_name=device_name,
        browser=browser,
        platform=platform,
        created_at=time.time(),
    )
    _pending.pop(rp_id, None)
    return True


def authentication_options(rp_id: str) -> dict:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    creds = _store().passkey_list(_owner_id(), rp_id=rp_id)
    allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
             for c in creds]
    opts = generate_authentication_options(rp_id=rp_id, allow_credentials=allow or None)
    _pending[rp_id] = opts.challenge
    return __import__("json").loads(options_to_json(opts))


def verify_authentication(credential: dict, rp_id: str, origin: str) -> bool:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    ch = _pending.get(rp_id)
    if not ch:
        return False
    cid = credential.get("id") or credential.get("rawId")
    match = _store().passkey_get(cid)
    if not match or match.get("rp_id") != rp_id:
        return False
    try:
        v = verify_authentication_response(
            credential=__import__("json").dumps(credential), expected_challenge=ch,
            expected_rp_id=rp_id, expected_origin=origin,
            credential_public_key=base64url_to_bytes(match["public_key"]),
            credential_current_sign_count=match.get("sign_count", 0))
    except Exception:
        return False
    _store().passkey_update_sign_count(cid, v.new_sign_count)
    _pending.pop(rp_id, None)
    return True


def list_passkeys(rp_id: str = "") -> list[dict]:
    """Return all registered passkeys with metadata (no secrets)."""
    out = []
    for c in _store().passkey_list(_owner_id(), rp_id=rp_id):
        out.append({
            "id": c.get("id", ""),
            "rp_id": c.get("rp_id", ""),
            "label": c.get("label", ""),
            "sign_count": c.get("sign_count", 0),
            "created": c.get("created_at", 0),
            "last_used": c.get("last_used_at", 0),
            "device_name": c.get("device_name", ""),
            "browser": c.get("browser", ""),
            "platform": c.get("platform", ""),
        })
    return out


def delete_passkey(credential_id: str) -> bool:
    """Remove a passkey by credential ID."""
    return _store().passkey_delete(credential_id)


def rename_passkey(credential_id: str, label: str) -> bool:
    """Rename a passkey."""
    return _store().passkey_rename(credential_id, label)
