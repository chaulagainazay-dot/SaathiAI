"""Put a test security store into a properly bootstrapped ACTIVE state.

D14 made authentication conditional on the installation being ACTIVE: a store
with no bootstrap marker authenticates nobody, because a credential that exists
before an owner legitimately does is evidence of planting, not of ownership.

Tests that predate D14 built a store, logged in, and expected a session. That is
no longer a complete setup -- it is the uninitialised state. This helper
performs the same transition the real bootstrap performs, without needing an
operator token file, so those tests can describe what they were always about
(sessions, passkeys, revocation) rather than re-testing bootstrap.

Do not use this to skip bootstrap in a test *of* bootstrap.
"""
from __future__ import annotations

import secrets
import time

DEFAULT_TEST_PASSWORD = "T3st!Active#Pw"


def make_active(store, *, password: str = DEFAULT_TEST_PASSWORD,
                email: str = "owner@test.local", name: str = "Test Owner") -> str:
    """Create the owner, its scrypt credential and the bootstrap marker.

    Returns the owner id. Idempotent: a store that is already ACTIVE is left
    alone and its existing owner returned.
    """
    from saathi.platform.identity import hash_password_scrypt

    existing = store.bootstrap_completed()
    if existing:
        return existing["owner_id"]

    owner_id = store.owner_id() or secrets.token_hex(16)
    now = time.time()
    db = store.db
    db.execute(
        "INSERT OR IGNORE INTO users (id, email, name, created_at, updated_at) "
        "VALUES (?,?,?,?,?)",
        (owner_id, email, name, now, now),
    )
    db.execute(
        "INSERT OR IGNORE INTO user_roles (user_id, role_id, assigned_at) VALUES (?,?,?)",
        (owner_id, "role-owner", now),
    )
    if not store.latest_password(owner_id):
        db.execute(
            "INSERT INTO passwords (user_id, hash, strength_score, created_at) "
            "VALUES (?,?,?,?)",
            (owner_id, hash_password_scrypt(password), 4, now),
        )
    db.execute(
        "INSERT OR REPLACE INTO bootstrap_marker (id, completed_at, owner_id, method) "
        "VALUES (1,?,?,?)",
        (now, owner_id, "test_fixture"),
    )
    db.commit()
    return owner_id
