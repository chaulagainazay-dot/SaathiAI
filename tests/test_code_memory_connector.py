"""Code Memory connector — codebase-memory-mcp wired as a Saathi driver."""
import saathi.infrastructure.connectors.drivers.code_memory as cm
from saathi.infrastructure.connectors.drivers.code_memory import CodeMemoryConnector
from saathi.infrastructure.connectors.base import Status, CapabilityUnsupported


def test_manifest_exposes_14_tools():
    m = CodeMemoryConnector().manifest()
    assert len(m.capabilities) == 14
    assert m.category == "engineering" and m.requires_auth
    assert "search_code" in m.capabilities and "index_repository" in m.capabilities


def test_health_reflects_binary_presence(monkeypatch, tmp_path):
    c = CodeMemoryConnector()
    # binary absent → AUTH_REQUIRED (inert, connector-not-center)
    monkeypatch.setattr(cm, "_binary", lambda: None)
    assert c.authenticate() is False
    assert c.health().status == Status.AUTH_REQUIRED
    # binary present → OK
    fake = tmp_path / "codebase-memory-mcp"; fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(cm, "_binary", lambda: str(fake))
    assert c.authenticate() is True
    assert c.health().status == Status.OK


def test_unsupported_capability_rejected(monkeypatch, tmp_path):
    c = CodeMemoryConnector()
    fake = tmp_path / "bin"; fake.write_text("x")
    monkeypatch.setattr(cm, "_binary", lambda: str(fake))
    try:
        c.execute("not_a_tool")
        assert False, "should reject unknown capability"
    except CapabilityUnsupported:
        pass


def test_registered_in_default_registry():
    from saathi.infrastructure.connectors import default_registry
    reg = default_registry()
    assert any(x.id == "code_memory" for x in reg.all())
