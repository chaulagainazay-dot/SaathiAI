"""M15.1 connector UI contract — the page uses the real platform API and shows
honest states (no mock connection data, no fake success)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "saathi-os" / "app" / "connectors" / "page.jsx"
API = ROOT / "saathi-os" / "lib" / "api.js"


def test_ui_uses_real_platform_api():
    src = PAGE.read_text()
    for helper in ["platformConnectors", "platformHealth", "platformExecutions",
                   "platformPendingApprovals", "platformDecideApproval"]:
        assert helper in src, f"UI must call {helper}"


def test_ui_has_honest_states_not_mocks():
    src = PAGE.read_text().lower()
    # honest states present
    assert "environment-blocked" in src
    assert "no mock success" in src or "honest" in src
    # no fabricated success strings baked into the page
    assert "mockconnected" not in src and "fakesuccess" not in src


def test_api_helpers_point_at_platform_routes():
    src = API.read_text()
    assert "/api/v1/connectors/health/platform" in src
    assert "/api/v1/connectors/executions" in src
    assert "/api/v1/connectors/approvals/pending" in src
