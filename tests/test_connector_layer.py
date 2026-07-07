"""Universal Account & Connector LAYER — catalog, encrypted accounts, capability dispatch, events."""
import tempfile, os
from saathi.connectors.catalog import catalog, provider_info, capabilities_for
from saathi.connectors.accounts import AccountStore
from saathi.connectors import manager


def _s():
    fd, p = tempfile.mkstemp(suffix=".db"); os.close(fd)
    return AccountStore(p)


def test_catalog_covers_key_providers_with_capabilities():
    provs = {p["provider"] for p in catalog()}
    assert {"gmail", "youtube", "instagram", "stripe", "telegram", "github", "google_drive"} <= provs
    assert "send" in provider_info("gmail")["capabilities"]
    assert provider_info("gmail")["auth_type"] == "oauth"
    assert "upload" in capabilities_for("youtube")


def test_account_secret_is_encrypted_and_not_returned_by_default():
    s = _s()
    a = s.add(provider="gmail", display_name="Ajay Gmail", email="a@x.com",
              secret={"refresh_token": "SUPER_SECRET"})
    got = s.get(a["id"])
    assert "secret" not in got and got["has_secret"] is True
    withs = s.get(a["id"], with_secret=True)
    assert withs["secret"]["refresh_token"] == "SUPER_SECRET"
    import sqlite3
    raw = sqlite3.connect(s.db_path).execute("SELECT secret_enc FROM account").fetchone()[0]
    assert b"SUPER_SECRET" not in (raw or b"")


def test_one_account_many_missions_and_list_filter():
    s = _s()
    a = s.add(provider="youtube", display_name="Mr Yeti channel")
    s.link_mission(a["id"], "mr_yeti"); s.link_mission(a["id"], "pielts")
    assert set(s.get(a["id"])["missions"]) == {"mr_yeti", "pielts"}
    assert len(s.list(mission="mr_yeti")) == 1
    assert len(s.list(mission="surmount_travels")) == 0
    s.link_mission(a["id"], "pielts", on=False)
    assert s.get(a["id"])["missions"] == ["mr_yeti"]


def test_execute_validates_capability_and_runs_simulated():
    s = _s()
    a = s.add(provider="gmail", display_name="g")
    bad = manager.execute(a["id"], "email.launch_rockets", store=s)
    assert bad["ok"] is False and "no capability" in bad["error"]
    ok = manager.execute(a["id"], "email.send", {"to": "x"}, store=s)
    assert ok["ok"] and ok["mode"] == "simulated" and ok["event"] == "email.sent"


def test_execute_missing_account():
    assert manager.execute("nope", "email.send")["ok"] is False


def test_provider_health_reports_simulated():
    assert manager.provider_health()["gmail"] == "simulated"
