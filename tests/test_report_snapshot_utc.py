"""Residual R1: ``captured_at`` without the deprecated ``datetime.utcnow()``.

``core/report_snapshot.py`` produced 63 of the 67 repository warnings on
Python 3.12/3.13. The replacement must keep the stored format: *naive* UTC ISO
text (no ``+00:00`` suffix, not local time), so new snapshots stay comparable
with the ones already persisted.
"""
import warnings
from datetime import datetime, timezone

import core.report_snapshot as rs
from core.database import DailyReport

_UTC_INSTANT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _GuardedDatetime(datetime):
    """``utcnow`` is forbidden; local ``now()`` is deliberately not UTC."""

    @classmethod
    def utcnow(cls):
        raise AssertionError("datetime.utcnow() is deprecated and must not be called")

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            # A local wall clock 3 h 30 min ahead of UTC: a naive local
            # timestamp would be detected as a wrong captured_at.
            return datetime(2026, 1, 1, 15, 30, 0)
        return _UTC_INSTANT.astimezone(tz)


def _transient_report():
    return DailyReport(well_id=7, section_id=3, report_number=1, summary="synthetic")


def test_captured_at_is_naive_utc_without_utcnow(monkeypatch):
    monkeypatch.setattr(rs, "datetime", _GuardedDatetime)
    snap = rs.build_report_snapshot(None, _transient_report(), models={})
    assert snap["captured_at"] == "2026-01-01T12:00:00"


def test_helper_returns_naive_utc(monkeypatch):
    monkeypatch.setattr(rs, "datetime", _GuardedDatetime)
    value = rs._utc_now_naive()
    assert value.tzinfo is None
    assert value == datetime(2026, 1, 1, 12, 0, 0)


def test_real_clock_format_and_no_deprecation_warning():
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        snap = rs.build_report_snapshot(None, _transient_report(), models={})
    after = datetime.now(timezone.utc).replace(tzinfo=None)
    text = snap["captured_at"]
    assert "+" not in text and not text.endswith("Z")
    parsed = datetime.fromisoformat(text)
    assert parsed.tzinfo is None
    assert before <= parsed <= after
    assert not [w for w in caught if issubclass(w.category, DeprecationWarning)
                and "utcnow" in str(w.message)]
    # Ownership context is still carried unchanged.
    assert (snap["well_id"], snap["section_id"]) == (7, 3)
