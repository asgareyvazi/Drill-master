"""Mission 25 — W12 recent-reports table None-vs-zero presentation truth.

The recent-reports table used ``r.rig_day or 0`` / ``r.depth_2400 or 0`` which
collapsed an UNKNOWN value into a fabricated 0. Presentation must keep the
distinction: None -> "—", an explicit reported 0 -> "0" / "0.0", a positive
value -> the value. This is presentation-only; no formula changes.
"""
from tabs.w12_Analysis import _fmt_rig_day, _fmt_recent_depth


class TestRigDayCell:
    def test_none_is_em_dash(self):
        assert _fmt_rig_day(None) == "—"

    def test_explicit_zero_is_zero(self):
        assert _fmt_rig_day(0) == "0"

    def test_positive_value(self):
        assert _fmt_rig_day(12) == "12"


class TestRecentDepthCell:
    def test_none_is_em_dash(self):
        assert _fmt_recent_depth(None) == "—"

    def test_explicit_zero_is_zero(self):
        assert _fmt_recent_depth(0.0) == "0.0"

    def test_positive_value(self):
        assert _fmt_recent_depth(1234.5) == "1234.5"
