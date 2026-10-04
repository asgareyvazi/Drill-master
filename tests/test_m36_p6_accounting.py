"""Regression tests for M36/P6 register conservation semantics."""
from __future__ import annotations

import json
from pathlib import Path

from tools.m36.p6_apply import _fix_commit_for_record, calculate_accounting
from tools.m36.p6_validate import reconcile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/audits/m36-evidence"


def _record(ident, classification, *, batch=None, priority="MEDIUM", file=None, line=None):
    return {
        "id": ident,
        "classification": classification,
        "p6_batch": batch,
        "priority": priority,
        "p6_class": "A",
        "file": file or f"core/{ident}.py",
        "line": line or 1,
    }


def test_start_open_excludes_pre_p6_fixed_records():
    register = {
        "records": [
            _record("FIX-1", "DEFECT-FIXED", priority="HIGH"),
            _record("FIX-2", "DEFECT-FIXED", priority="HIGH"),
            _record("A-1", "VERIFIED-CORRECT", batch="p6-batch-002", priority="HIGH"),
            _record("A-2", "INTENTIONAL", batch="p6-batch-002", priority="MEDIUM"),
            _record("A-3", "OPEN", batch="p6-batch-003", priority="MEDIUM"),
            _record("A-4", "DOMAIN_DECISION_REQUIRED", batch="p6-batch-003", priority="MEDIUM"),
        ],
        "totals": {
            "records": 6,
            "open": 1,
            "open_by_priority": {"MEDIUM": 1},
            "open_by_class": {"A": 1},
            "defect_fixed": 2,
        },
    }
    batches = [
        {"batch": "p6-batch-002", "records": 2, "sites": 2,
         "by_classification": {"VERIFIED-CORRECT": 1, "INTENTIONAL": 1}},
        {"batch": "p6-batch-003", "records": 1, "sites": 1,
         "by_classification": {"DOMAIN_DECISION_REQUIRED": 1}},
    ]

    result = calculate_accounting(register, batches)

    assert result["check"] is True
    assert result["register_records_at_p6_start"] == 6
    assert result["pre_p6_defect_fixed_records"] == 2
    assert result["open_records_at_p6_start"] == 4
    assert result["open_by_priority_at_p6_start"] == {"HIGH": 1, "MEDIUM": 3}
    assert result["adjudicated_by_p6_batches"] == 3
    assert result["current_open"] == 1


def test_rejects_miscounted_batch_or_open_register_totals():
    register = {
        "records": [
            _record("FIX-1", "DEFECT-FIXED", priority="HIGH"),
            _record("A-1", "VERIFIED-CORRECT", batch="p6-batch-002"),
        ],
        "totals": {
            "records": 2,
            "open": 0,
            "open_by_priority": {},
            "open_by_class": {},
            "defect_fixed": 1,
        },
    }
    batch = {"batch": "p6-batch-002", "records": 9, "sites": 1,
             "by_classification": {"VERIFIED-CORRECT": 1}}

    result = calculate_accounting(register, [batch])

    assert result["check"] is False
    assert any("batch record counts" in error for error in result["errors"])


def test_rejects_batch_classification_or_site_drift():
    register = {
        "records": [
            _record("FIX-1", "DEFECT-FIXED", priority="HIGH"),
            _record("A-1", "VERIFIED-CORRECT", batch="p6-batch-002", file="core/a.py", line=1),
            _record("A-2", "VERIFIED-CORRECT", batch="p6-batch-002", file="core/a.py", line=1),
        ],
        "totals": {
            "records": 3,
            "open": 0,
            "open_by_priority": {},
            "open_by_class": {},
            "defect_fixed": 1,
        },
    }
    batch = {"batch": "p6-batch-002", "records": 2, "sites": 2,
             "by_classification": {"INTENTIONAL": 2}}

    result = calculate_accounting(register, [batch])

    assert result["check"] is False
    assert any("class counts" in error for error in result["errors"])
    assert any("site count" in error for error in result["errors"])


def test_read_only_p6_reconciliation_passes_structural_audit():
    result = reconcile(verify_git_history=False)

    assert result["structural_checks"] == "PASS", result["errors"]
    assert result["register"]["records"] == 1224
    assert result["batches"]["item_records"] == 1222
    assert result["batches"]["unique_item_ids"] == 1222
    assert result["secondary_new_findings"]["count"] == 20


def test_direct_fix_commit_can_be_recovered_from_batch_fix_metadata():
    payload = {
        "defects_fixed": [
            {"records": ["INV34-1", "INV34-2"], "fix_commit": "abc123"},
            {"id": "INV34-3", "records": None, "commit": "def456"},
        ]
    }
    assert _fix_commit_for_record(payload, "INV34-1") == "abc123"
    assert _fix_commit_for_record(payload, "INV34-2") == "abc123"
    assert _fix_commit_for_record(payload, "INV34-3") == "def456"
    assert _fix_commit_for_record(payload, "INV34-missing") is None


def test_current_master_register_and_ledger_use_correct_partition():
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text())
    ledger = json.loads((EVIDENCE / "m36-master-ledger.json").read_text())

    result = calculate_accounting(register, ledger["batches"])

    assert result["check"] is True, result["errors"]
    assert result["register_records_at_p6_start"] == 1224
    assert result["pre_p6_defect_fixed_records"] == 2
    assert result["open_records_at_p6_start"] == 1222
    assert result["adjudicated_by_p6_batches"] == 1222
    assert result["current_open"] == 0
    assert ledger["start_open"] == 1222
    assert ledger["start_high"] == 369
    assert ledger["start_medium"] == 853
    assert "register_open_at_p6_start" not in ledger.get("arithmetic", {})
    assert "defect_fixed_by_p6" not in ledger.get("arithmetic", {})
