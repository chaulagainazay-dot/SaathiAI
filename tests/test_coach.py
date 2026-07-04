"""Saathi Coach tests — conversational IELTS as the Learn box, deterministic scoring."""
from saathi.coach import (
    daily_challenge, score_speaking, BandPredictor, SaathiCoach, pick_topic, TOPICS,
)


# ── today's challenge prefers the longest-neglected skill ──────────────────
def test_daily_challenge_targets_neglected_skill():
    ch = daily_challenge(last_practiced_days={"Speaking": 2, "Reading": 0, "Writing": 0, "Listening": 0}, now=0)
    assert ch.skill == "Speaking"
    assert "2 days" in ch.reason
    assert ch.topic in TOPICS and ch.minutes == 8


def test_topics_are_ajays_projects():
    assert any("SaathiAI" in t for t in TOPICS)
    assert any("cafeteria" in t for t in TOPICS)
    assert any("Canada" in t for t in TOPICS)


# ── scoring: a fluent, varied answer bands well ────────────────────────────
def test_good_answer_scores_high():
    text = ("SaathiAI is an operating system I built to run my businesses. It coordinates "
            "content production, financial decisions and my hospital cafeteria through a shared "
            "learning runtime, so every outcome becomes evidence that improves tomorrow's decisions. "
            "I designed it because I genuinely enjoy building systems rather than studying, and this "
            "lets me practise English while explaining work I care deeply about.")
    s = score_speaking(text)
    assert s.band >= 6.5
    assert s.vocabulary >= 6.5


# ── the classic weakness: repeated fillers is detected by name ─────────────
def test_repeated_filler_is_the_weakness():
    text = ("Actually the cafeteria actually sells dal bhat and actually we actually try to "
            "actually reduce waste actually every day actually because actually it actually matters "
            "actually to me and the team.")
    s = score_speaking(text)
    assert "actually" in s.weakness and "times" in s.weakness
    assert s.fillers.get("actually", 0) >= 4


def test_too_short_is_flagged():
    s = score_speaking("Yes I think so.")
    assert s.band == 4.0 and "short" in s.weakness.lower()


# ── Band Predictor: baseline, updates, prediction with confidence ──────────
def test_band_predictor_updates_and_predicts(tmp_path):
    bp = BandPredictor(tmp_path / "bp.db", now=lambda: 1.0)
    assert bp.current_bands()["Speaking"] == 6.5      # baseline
    bp.record("Speaking", 7.0)
    assert bp.current_bands()["Speaking"] == 7.0
    p = bp.predict(days_left=11)
    assert p["predicted_overall"] >= p["overall"]     # improving toward the exam
    assert 0.5 <= p["confidence"] <= 0.95
    assert set(p["current"]) == {"Listening", "Reading", "Writing", "Speaking"}


# ── a practice session records a Learning Episode (lights the Learn box) ───
def test_practice_records_learning_episode(tmp_path):
    eps, events = [], []
    bp = BandPredictor(tmp_path / "bp.db", now=lambda: 1.0)
    coach = SaathiCoach(bp, record_episode=lambda **kw: eps.append(kw) or 1,
                        publish=lambda n, p: events.append((n, p)))
    out = coach.practice_speaking(
        "I run a hospital cafeteria and I reduce food waste by forecasting demand carefully "
        "each morning, which has cut our dal bhat waste noticeably over the last few weeks.",
        topic="cafeteria waste")
    assert "band" in out and out["band"] > 0
    assert eps[-1]["intent"] == "ielts_speaking_practice"     # counts as Learn
    assert eps[-1]["product"] == "pielts"
    assert events[-1][0] == "coach.session"


# ── the Learn box lights up from a coach episode ───────────────────────────
def test_coach_episode_counts_as_learn():
    from saathi.daily_scorecard import score
    sc = score([{"intent": "ielts_speaking_practice", "outcome": "success"}], revenue_usd=0)
    assert sc.met["learning"]
