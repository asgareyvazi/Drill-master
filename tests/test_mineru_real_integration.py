"""Opt-in real MinerU integration test.

Run on the developer machine only after pointing at a real input file:

    MINERU_INTEGRATION_INPUT=C:\\path\\to\\report.pdf \\
      python -m pytest -q tests/test_mineru_real_integration.py

The test deliberately skips when no input is supplied; CI must not pretend a
MinerU installation or real document exists.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.mineru_engine import DocumentNormalizer, MinerUAdapter


@pytest.mark.integration
def test_real_mineru_parse_and_normalize():
    value = os.getenv("MINERU_INTEGRATION_INPUT")
    if not value:
        pytest.skip("Set MINERU_INTEGRATION_INPUT to run against a real MinerU installation")
    source = Path(value).expanduser()
    if not source.is_file():
        pytest.fail(f"MINERU_INTEGRATION_INPUT is not a file: {source}")

    adapter = MinerUAdapter()
    health = adapter.health_check()
    assert health.available, health.to_dict()
    result = adapter.parse_file(source)
    assert result.success, result.error
    assert result.document is not None
    assert result.document.raw_files, "MinerU generated no inspectable output files"
    normalized = DocumentNormalizer().normalize(result.document)
    assert normalized.validation.valid, normalized.validation.errors
    assert normalized.pages >= 1
    assert normalized.tables_extracted >= 0
