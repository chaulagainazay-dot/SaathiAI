"""Daily Scorecard tests — the success rule, measured from real Episodes."""
from saathi.daily_scorecard import score, Scorecard


def _eps(*intents):
    return [{"intent": i, "outcome": "success"} for i in intents]


def test_complete_day_all_five():
    sc = score(_eps("decision_pipeline", "content_publish", "investment_learning_pass",
                    "reflection"), revenue_usd=235)
    assert sc.met == {"decision": True, "automation": True, "learning": True,
                      "revenue": True, "reflect": True}
    assert sc.complete and sc.score == 5
    assert sc.missing == []
    assert "5/5" in sc.render()


def test_reflect_is_required_for_a_perfect_day():
    # decide + automate + learn + earn but no reflection → 4/5
    sc = score(_eps("decision_pipeline", "content_publish", "investment_learning_pass"), revenue_usd=235)
    assert sc.score == 4 and not sc.complete
    assert sc.missing == ["reflect"]
    assert "⬜ reflect" in sc.render()


def test_missing_learning_and_revenue():
    sc = score(_eps("ceo_approve", "daily_discovery"), revenue_usd=0)
    assert sc.met["decision"] and sc.met["automation"]
    assert not sc.met["learning"] and not sc.met["revenue"]
    assert set(sc.missing) == {"learning", "revenue", "reflect"}
    assert sc.score == 2


def test_revenue_alone_counts():
    sc = score([], revenue_usd=50)
    assert sc.met["revenue"] and sc.score == 1


def test_reflection_episode_counts():
    sc = score(_eps("reflection"), revenue_usd=0)
    assert sc.met["reflect"] and sc.score == 1


def test_empty_day():
    sc = score([], 0)
    assert sc.score == 0
    assert sc.missing == ["decision", "automation", "learning", "revenue", "reflect"]
    assert "0/5" in sc.render()


def test_content_analytics_counts_as_learning_and_automation():
    sc = score(_eps("content_analytics"), revenue_usd=0)
    assert sc.met["automation"] and sc.met["learning"]     # analytics is both automate + learn
