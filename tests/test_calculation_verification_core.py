"""Unit tests for the shared, engine-agnostic verification core.

This core was extracted because TWO real engines (Torque & Drag and Casing)
share an identical verification contract; the subtle deep-diff (the site of a
past false-MATCH bug) must not be duplicated. These tests pin the semantics
independently of either engine.
"""
from __future__ import annotations

from types import SimpleNamespace

from core.engineering.calculation_verification import (
    DEFAULT_ABS_TOL,
    VERIFY_DIFFERENT,
    VERIFY_MATCH,
    VERIFY_NOT_REPRODUCIBLE,
    clean_number,
    classify_verification,
    deep_numeric_diff,
)


def _ok(values):
    return SimpleNamespace(success=True, values=values, error=None)


def _fail(error="boom"):
    return SimpleNamespace(success=False, values={}, error=error)


def test_clean_number_normalizes_nan_and_types():
    assert clean_number(float("nan")) is None
    assert clean_number(float("inf")) is None
    assert clean_number(3) == 3.0
    assert clean_number(True) is None   # bool is not a number here
    assert clean_number("x") is None    # non-numeric string -> None


def test_deep_numeric_diff_within_tolerance_is_match():
    a = {"x": 1.0, "n": {"y": 2.0}}
    b = {"x": 1.0 + DEFAULT_ABS_TOL / 2, "n": {"y": 2.0}}
    assert deep_numeric_diff(a, b) == []


def test_deep_numeric_diff_detects_nested_change():
    diffs = deep_numeric_diff({"n": {"y": 2.0}}, {"n": {"y": 2.5}})
    assert len(diffs) == 1 and diffs[0]["path"] == "n.y"


def test_deep_numeric_diff_detects_missing_key():
    diffs = deep_numeric_diff({"a": 1.0, "b": 2.0}, {"a": 1.0})
    assert any(d["path"] == "b" for d in diffs)


def test_deep_numeric_diff_detects_list_elementwise():
    diffs = deep_numeric_diff({"v": [1.0, 2.0, 3.0]}, {"v": [1.0, 9.0, 3.0]})
    assert any(d["path"] == "v[1]" for d in diffs)


def test_deep_numeric_diff_ignores_non_numeric_keys():
    a = {"note": "first", "x": 1.0}
    b = {"note": "second", "x": 1.0}
    assert deep_numeric_diff(a, b, non_numeric_keys={"note"}) == []


def test_classify_match():
    o = classify_verification({"x": 1.0}, _ok({"x": 1.0}),
                              snapshot_method="M", current_method="M")
    assert o.status == VERIFY_MATCH and o.method_matches is True


def test_classify_different():
    o = classify_verification({"x": 1.0}, _ok({"x": 2.0}),
                              snapshot_method="M", current_method="M")
    assert o.status == VERIFY_DIFFERENT
    assert o.all_differences


def test_classify_not_reproducible_when_engine_fails():
    o = classify_verification({"x": 1.0}, _fail("bad input"),
                              snapshot_method="M", current_method="M")
    assert o.status == VERIFY_NOT_REPRODUCIBLE
    assert "bad input" in (o.detail or "")


def test_classify_method_drift_is_reported_but_still_compares():
    o = classify_verification({"x": 1.0}, _ok({"x": 1.0}),
                              snapshot_method="OLD", current_method="NEW")
    assert o.status == VERIFY_MATCH
    assert o.method_matches is False
