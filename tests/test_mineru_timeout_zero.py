"""MinerU timeout normalization treats numeric and string zero consistently."""
from __future__ import annotations


def test_explicit_zero_timeout_is_clamped_to_one_second(monkeypatch):
    from core.mineru_engine import MinerUConfig

    monkeypatch.delenv("DRILLMASTER_MINERU_TIMEOUT", raising=False)
    monkeypatch.delenv("MINERU_TIMEOUT", raising=False)
    monkeypatch.setattr("core.mineru_engine.read_mineru_settings", lambda: {"timeout": 0})
    assert MinerUConfig.from_environment().timeout_seconds == 1


def test_string_zero_timeout_matches_persisted_numeric_zero(monkeypatch):
    from core.mineru_engine import MinerUConfig

    monkeypatch.setattr("core.mineru_engine.read_mineru_settings", lambda: {})
    monkeypatch.setenv("DRILLMASTER_MINERU_TIMEOUT", "0")
    assert MinerUConfig.from_environment().timeout_seconds == 1
