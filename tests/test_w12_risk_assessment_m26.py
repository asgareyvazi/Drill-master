"""M26 §14 — W12 risk assessment must not fabricate risk from missing data.

The old analyze_risk() collapsed a missing safety report into days_without_lti=0
and then scored that as the MAXIMUM-risk case (8/10 HIGH), i.e. "no data" was
silently rendered as "worst case". It also asserted flat Equipment=5 / Weather=4
constants as if they were assessments.

The rule-based scorer is now pure and unit-testable: every category whose input
is UNKNOWN resolves to None (NOT ASSESSED), never a fabricated score. Only real
recorded values produce a score. The risk formula thresholds themselves are
unchanged for the cases that DO have data.
"""
from tabs.w12_Analysis import AnalysisWidget

_score = AnalysisWidget._risk_scores


def test_missing_safety_report_is_not_assessed_not_max_risk():
    scores = _score(npt_pct=10.0, days_without_lti=None, has_safety_report=False)
    assert scores["Safety"] is None, "no safety report -> UNKNOWN, not 8/10 HIGH"


def test_null_days_without_lti_is_not_assessed():
    # A safety report exists but the days field is NULL -> still UNKNOWN.
    scores = _score(npt_pct=10.0, days_without_lti=None, has_safety_report=True)
    assert scores["Safety"] is None


def test_equipment_and_weather_have_no_data_source_so_unknown():
    scores = _score(npt_pct=10.0, days_without_lti=100, has_safety_report=True)
    assert scores["Equipment"] is None
    assert scores["Weather"] is None


def test_unknown_npt_leaves_npt_and_well_control_unknown():
    scores = _score(npt_pct=None, days_without_lti=100, has_safety_report=True)
    assert scores["NPT Risk"] is None
    assert scores["Well Control"] is None


def test_real_recorded_values_still_score_by_rule():
    # Long LTI-free record = low safety risk; low NPT = low NPT risk.
    good = _score(npt_pct=5.0, days_without_lti=120, has_safety_report=True)
    assert good["Safety"] == 2
    assert good["NPT Risk"] == 3
    assert good["Well Control"] == 3
    # Recent LTI + high NPT = high risk (formula thresholds preserved).
    bad = _score(npt_pct=35.0, days_without_lti=10, has_safety_report=True)
    assert bad["Safety"] == 8
    assert bad["NPT Risk"] == 9
    assert bad["Well Control"] == 6
