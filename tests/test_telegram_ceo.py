"""Telegram CEO Companion tests — run the business from chat, everything an Episode."""
from saathi.telegram_ceo import handle_command, briefing_text, DREAM_TARGET

HOME = {
    "greeting": "Good morning, Ajay.", "dreamPct": 0.28, "revenueToday": 423,
    "priorityScore": 73, "dreamCurrent": 22000,
    "priorityReasons": [{"label": "Execution up 4%", "tone": "up"}],
    "actions": [
        {"title": "Publish Video #53", "dept": "AI STUDIO", "meta": "queued", "tag": "RUN"},
        {"title": "Review Opportunity #218", "dept": "OPPORTUNITY", "meta": "DD passed", "tag": "REVIEW"},
    ],
    "approvals": {"count": 2, "items": ["1 investment", "1 allocation"]},
}


def _home():
    return HOME


def _cmd(text, episodes=None, rev=None):
    return handle_command(
        text, ceo_home_fn=_home,
        record_episode=lambda **kw: (episodes if episodes is not None else []).append(kw) or 1,
        record_revenue_fn=(rev if rev is not None else (lambda **kw: 1)))


# ── non-commands defer to the general agent (return None) ──────────────────
def test_non_command_returns_none():
    assert _cmd("how are you?") is None
    assert _cmd("") is None


# ── morning briefing matches the CEO format ────────────────────────────────
def test_briefing_contains_the_essentials():
    b = briefing_text(HOME)
    assert "Good morning" in b
    assert "0.28%" in b and "$423" in b and "73" in b
    assert "Publish Video #53" in b
    assert "2 approvals" in b
    assert "/approve" in b and "/revenue" in b


def test_brief_command():
    assert "Publish Video #53" in _cmd("/brief")


# ── /details lists priorities ──────────────────────────────────────────────
def test_details():
    d = _cmd("/details")
    assert "Publish Video #53" in d and "Review Opportunity #218" in d


# ── /approve records an Episode ────────────────────────────────────────────
def test_approve_records_episode():
    eps = []
    reply = _cmd("/approve", episodes=eps)
    assert "Approved: Publish Video #53" in reply
    assert eps[-1]["intent"] == "ceo_approve"


def test_approve_index():
    eps = []
    reply = _cmd("/approve 2", episodes=eps)
    assert "Review Opportunity #218" in reply


# ── /run triggers + records ────────────────────────────────────────────────
def test_run_records_episode():
    eps = []
    reply = _cmd("/run", episodes=eps)
    assert "Running: Publish Video #53" in reply
    assert eps[-1]["intent"] == "ceo_run"


# ── /revenue records via the unified interface + shows dream contribution ──
def test_revenue_command_records_and_reports_dream():
    calls = []
    def rev(**kw):
        calls.append(kw); return 1
    reply = _cmd("/revenue 18400 cafeteria NPR", rev=rev)
    assert calls and calls[0]["amount"] == 18400 and calls[0]["currency"] == "NPR"
    assert calls[0]["source"] == "POS"                 # cafeteria → POS
    assert "Dream +" in reply and "$138" in reply       # 18400 NPR ≈ $138

def test_revenue_usage_hint():
    assert "Usage" in _cmd("/revenue")


# ── /opps surfaces opportunity actions ─────────────────────────────────────
def test_opportunities():
    assert "Review Opportunity #218" in _cmd("/opps")


# ── /dream ─────────────────────────────────────────────────────────────────
def test_dream():
    assert "0.28" in _cmd("/dream") or "0.2800" in _cmd("/dream")


# ── /reflect captures the daily surprise as an Episode ─────────────────────
def test_reflect_records_reflection_episode():
    eps = []
    reply = _cmd("/reflect Dal Bhat demand spikes when it rains", episodes=eps)
    assert "Captured" in reply
    assert eps[-1]["intent"] == "reflection"
    assert "rains" in eps[-1]["result"]


def test_reflect_prompts_when_empty():
    assert "What surprised you today" in _cmd("/reflect")
