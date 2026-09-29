"""Bulk ledger validation must not treat explicit zero closing stock as missing."""
from __future__ import annotations


def test_explicit_zero_closing_stock_is_checked_against_known_ledger():
    from core.validators import BulkValidator

    result = BulkValidator.validate([{
        "material_name": "Barite",
        "unit": "sacks",
        "initial_stock": 10.0,
        "received": 2.0,
        "used": 1.0,
        "current_stock": 0.0,
    }])
    assert any("Stock mismatch" in warning["message"] for warning in result.warnings)


def test_zero_closing_stock_matches_known_zero_ledger_and_null_stays_unknown():
    from core.validators import BulkValidator

    clean = BulkValidator.validate([{
        "material_name": "Barite", "unit": "sacks", "initial_stock": 0.0,
        "received": 0.0, "used": 0.0, "current_stock": 0.0,
    }])
    assert not any("Stock mismatch" in warning["message"] for warning in clean.warnings)

    unknown = BulkValidator.validate([{
        "material_name": "Barite", "unit": "sacks", "initial_stock": None,
        "received": 2.0, "used": 1.0, "current_stock": None,
    }])
    assert not any("Stock mismatch" in warning["message"] for warning in unknown.warnings)
