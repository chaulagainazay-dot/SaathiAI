import os, json, pytest
os.environ.setdefault("BAADAR_DB", "/tmp/test_baadar.db")

from saathi.tools.intelligence import init_db


def test_generate_referral_code_is_unique():
    from saathi.tools.referral import generate_referral_code
    code1 = generate_referral_code("uid_001")
    code2 = generate_referral_code("uid_002")
    assert code1 != code2
    assert len(code1) == 8


def test_check_triggers_only_on_half_band_improvement():
    init_db()
    from saathi.tools.referral import check_and_trigger_referral
    # Improvement of 0.4 — should NOT trigger
    result = check_and_trigger_referral("uid_no", 6.0, 6.4)
    assert result["triggered"] is False
    # Improvement of 0.5 — should trigger
    result = check_and_trigger_referral("uid_yes", 6.0, 6.5)
    assert result["triggered"] is True
    assert "referral_code" in result
