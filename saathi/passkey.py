"""Passkey (WebAuthn) — fingerprint / Face ID unlock for the owner.

Register a platform authenticator (Mac Touch ID, iPad Face ID) once, then unlock
with biometrics instead of the password. On success the caller issues the normal
session cookie, so the rest of SaathiOS (and voice) treats you as the owner without
re-verifying your voice.

Single-owner: credentials + the in-flight challenge are stored locally. RP id/origin
are derived from the request host so it works on both localhost and the VM domain
(register once per host).
"""
from __future__ import annotations

import json
from pathlib import Path

_STORE = Path.home() / ".saathi" / "passkeys.json"
_pending: dict[str, bytes] = {}   # host → last challenge (single owner)


def _load() -> list[dict]:
    try:
        return json.loads(_STORE.read_text())
    except Exception:
        return []


def _save(creds: list[dict]) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    _STORE.write_text(json.dumps(creds))


def has_passkey(rp_id: str = "") -> bool:
    creds = _load()
    return any((not rp_id) or c.get("rp_id") == rp_id for c in creds)


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
    return json.loads(options_to_json(opts))


def verify_registration(credential: dict, rp_id: str, origin: str) -> bool:
    from webauthn import verify_registration_response
    from webauthn.helpers import bytes_to_base64url
    ch = _pending.get(rp_id)
    if not ch:
        return False
    v = verify_registration_response(credential=json.dumps(credential),
                                     expected_challenge=ch, expected_rp_id=rp_id,
                                     expected_origin=origin)
    creds = _load()
    creds.append({"id": bytes_to_base64url(v.credential_id),
                  "public_key": bytes_to_base64url(v.credential_public_key),
                  "sign_count": v.sign_count, "rp_id": rp_id})
    _save(creds)
    _pending.pop(rp_id, None)
    return True


def authentication_options(rp_id: str) -> dict:
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers import base64url_to_bytes
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor
    allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["id"]))
             for c in _load() if c.get("rp_id") == rp_id]
    opts = generate_authentication_options(rp_id=rp_id, allow_credentials=allow or None)
    _pending[rp_id] = opts.challenge
    return json.loads(options_to_json(opts))


def verify_authentication(credential: dict, rp_id: str, origin: str) -> bool:
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes
    ch = _pending.get(rp_id)
    if not ch:
        return False
    cid = credential.get("id") or credential.get("rawId")
    creds = _load()
    match = next((c for c in creds if c["id"] == cid and c.get("rp_id") == rp_id), None)
    if not match:
        return False
    try:
        v = verify_authentication_response(
            credential=json.dumps(credential), expected_challenge=ch, expected_rp_id=rp_id,
            expected_origin=origin, credential_public_key=base64url_to_bytes(match["public_key"]),
            credential_current_sign_count=match.get("sign_count", 0))
    except Exception:
        return False
    match["sign_count"] = v.new_sign_count
    _save(creds)
    _pending.pop(rp_id, None)
    return True
