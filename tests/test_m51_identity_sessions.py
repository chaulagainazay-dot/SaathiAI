"""M51 identity, password, session hardening, abuse controls."""
from __future__ import annotations

import pytest

from saathi.platform.context import PlatformContextError
from saathi.platform.identity import password_policy_check
from saathi.platform.service import reset_platform_for_tests
import saathi.platform.alpha  # ensure mixin  # noqa: F401


@pytest.fixture()
def plat(tmp_path):
    return reset_platform_for_tests(tmp_path / "m51.db")


def test_password_policy():
    assert password_policy_check("short")[0] is False
    assert password_policy_check("password1234")[0] is False
    assert password_policy_check("GoodPassw0rd!")[0] is True


def test_secure_bootstrap_and_password_login(plat):
    out = plat.bootstrap_owner_secure(
        email="owner@alpha.local",
        name="Owner",
        password="GoodPassw0rd!",
    )
    assert out["token"]
    assert out["session"]["auth_method"] == "LOCAL_PASSWORD"
    assert out["private_alpha"]["private_alpha"] is True

    # wrong password
    with pytest.raises(PlatformContextError) as ei:
        plat.authenticate_login(
            email="owner@alpha.local", password="WrongPassw0rd!"
        )
    assert ei.value.code == "AUTH_FAILED"

    # correct
    again = plat.authenticate_login(
        email="owner@alpha.local", password="GoodPassw0rd!"
    )
    assert again["token"]


def test_session_rotation_invalidates_old(plat):
    boot = plat.bootstrap_owner_secure(
        email="o@a.local", name="O", password="GoodPassw0rd!"
    )
    old = boot["token"]
    rot = plat.rotate_session(old)
    assert rot["token"] != old
    with pytest.raises(PlatformContextError):
        plat.require_context(old)
    ctx = plat.require_context(rot["token"])
    assert ctx.user_id


def test_password_change_revokes_other_sessions(plat):
    boot = plat.bootstrap_owner_secure(
        email="o2@a.local", name="O", password="GoodPassw0rd!"
    )
    t1 = boot["token"]
    t2 = plat.authenticate_login(email="o2@a.local", password="GoodPassw0rd!")["token"]
    ctx = plat.require_context(t1)
    plat.change_password(ctx, current="GoodPassw0rd!", new_password="BetterPassw0rd!")
    with pytest.raises(PlatformContextError):
        plat.require_context(t2)
    # current session may still be valid (except_session)
    assert plat.require_context(t1).user_id


def test_login_lockout(plat):
    plat.bootstrap_owner_secure(
        email="lock@a.local", name="L", password="GoodPassw0rd!"
    )
    for _ in range(8):
        with pytest.raises(PlatformContextError):
            plat.authenticate_login(
                email="lock@a.local",
                password="bad",
                client_key="lock-client",
            )
    with pytest.raises(PlatformContextError) as ei:
        plat.authenticate_login(
            email="lock@a.local",
            password="GoodPassw0rd!",
            client_key="lock-client",
        )
    assert ei.value.code == "AUTH_FAILED"
