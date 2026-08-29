# DrillMaster — Testing Documentation

> **Version:** 1.0 — Audit Baseline (2026-08-24)

---

## 1. Test Suite Overview

**Location:** `tests/`
**Framework:** pytest
**Total Tests:** 64 (all passing)
**Run Time:** ~6 seconds

### Run Command
```bash
cd /home/user/Drill-master
source .venv/bin/activate
python -m pytest tests/ -v
```

---

## 2. Test Inventory

### 2.1 P0 Critical Tests

| File | Tests | Focus |
|------|-------|-------|
| test_p0_atomic_import.py | 3 | Atomic import transactions, rollback, no orphan data |
| test_p0_engineering_core.py | 20 | All engineering calculations (trajectory, bit, BHA, hydraulics, well control, operations, mud ledger) |
| test_p0_permissions.py | 5 | RBAC enforcement, viewer restrictions, permission checks |
| test_p0_time_log_validation.py | 10 | Time log overlap detection, duration calculation, 24h coverage |
| test_p0_unit_preservation.py | 8 | Unit conversion preservation, original value retention, canonical normalization |
| test_p0_well_identity.py | 3 | Well identity management, code uniqueness |

### 2.2 Integration Tests

| File | Tests | Focus |
|------|-------|-------|
| test_core_import.py | 4 | Core import pipeline, table detection, sheet classification |
| test_import_quality_extra.py | 3 | Import quality validation, data quality checks |
| test_operations.py | 3 | Operations intelligence, ROP/NPT trend analysis |

### 2.3 Unit Tests

| File | Tests | Focus |
|------|-------|-------|
| test_canonical_schema.py | 1 | Canonical schema integrity |
| test_config_and_mapping.py | 2 | Configuration and mapping store |
| test_health_check.py | 1 | System health checks |
| test_table_mapper.py | 1 | Table-to-record mapping |

---

## 3. Test Categories

### 3.1 Atomic Import Tests
- Verify that multi-table imports are atomic (all or nothing)
- Verify rollback restores exact pre-import state
- Verify no orphan child data after failed import

### 3.2 Engineering Core Tests
- **Trajectory:** Single point, multi-point, validation (monotonic MD, inc range), projection
- **Bit:** TFA from nozzles, HSI calculation
- **BHA:** Cumulative length/weight, component validation
- **Hydraulics:** Annular velocity, ECD, PV/YP from viscometer
- **Well Control:** Kill MW, MAASP
- **Operations:** ROP degradation detection, NPT threshold alerts
- **Mud Ledger:** Closing stock calculation, alert generation

### 3.3 Permission Tests
- Viewer role cannot delete
- Engineer role cannot manage users
- Permission enforcement on critical operations

### 3.4 Unit Preservation Tests
- Original value is preserved after conversion
- Canonical unit is correctly applied
- Conversion rule is recorded
- Failed conversions are flagged

### 3.5 Time Log Validation Tests
- Overlapping time entries are detected
- Duration calculation is correct
- 24-hour coverage is verified

---

## 4. Missing Tests (Recommended Additions)

### 4.1 Integration Tests
- Full Excel → Import → Validate → Save → Display pipeline
- Real-world Excel fixtures (merged cells, multi-row headers)
- Import → Export → Compare roundtrip

### 4.2 Database Tests
- Session management under concurrent access
- Backup and restore verification
- Migration compatibility

### 4.3 UI Tests
- Tab switching with data preservation
- SelectionManager signal propagation
- Auto-save functionality

---

## 5. Test Fixtures

Currently, tests use in-memory SQLite databases and synthetic data. Future improvements should include:

1. **Real Excel fixtures:** Representative drilling spreadsheets
2. **Edge case fixtures:** Merged cells, hidden rows, formulas
3. **Large dataset fixtures:** Performance testing with 1000+ rows
