# M43 continuation — baseline (before any product-code change)

Measured 2026-10-20 on Linux, Python 3.12, `QT_QPA_PLATFORM=offscreen`,
**without** libGL and **without** the Qt stub. Only the privacy package
(`bd47fa6`: policy, privacy test, containment script, privacy docs) has been
committed since; it does not touch product code. Official CI on Ubuntu with the
real Qt system libraries remains the authoritative test result.

## Git state

| Item | Value |
|---|---|
| Working branch | `arena/72010272-drill-master` |
| Baseline commit | `aee2cc866fdbee0f80943f465169efd8006c2db6` (docs-only on top of code SHA `ad67602`) |
| `drill-Master` (default) | `e3fa42a`, 4 commits not on the working branch (merge base `51c0b85`), working branch 135 ahead |
| Exact-SHA CI for `aee2cc8` | Source gate `39407466768` success, Windows gate `39407466748` success (attempt 1) |

## Test suite (`/tmp` worktree at `aee2cc8`)

```
QT_QPA_PLATFORM=offscreen python -m pytest -p no:cacheprovider --tb=no -rfE \
  --continue-on-collection-errors --cov=. --cov-branch --cov-report=json
64 failed, 2573 passed, 45 skipped, 19 errors in 617.51s
```

The 83 failing/erroring IDs are **identical** to the Phase 1 fail set of the
previous mission (`28d7920`), which was classified there as libGL-only
(`ImportError: libGL.so.1` in subprocess smoke tests and widget imports). No
new failure. These tests pass in official CI (exact-SHA runs listed in
`M43_RELEASE_HARDENING_REPORT.md`, section D), where the real libraries are
installed.

## Coverage — the denominator problem

| Population | Files | Statements | Branches | Branch+line |
|---|---|---|---|---|
| Product files *measured* (excl. `tests/`, `tools/`, `packaging/`) — the figure reported so far | 149 | 42,417 | 12,762 | **44.40 %** (44.24 % at `9060b08`) |
| Product files tracked but **never imported** by the local run | 44 | 14,843 | 3,118 | 0 % |
| **All 193 tracked product files** | 193 | 57,260 | 15,880 | **33.50 %** |

`--cov=.` reports only files that were imported. The 44 missing files are
mostly `tabs/` widgets (for example `w3c_section_data.py`, `w7_logistics_Widget.py`,
`w2_Daily_Report.py`) that the libGL failures prevent from loading locally,
plus genuinely unimported modules such as `core/witsml_import.py` and
`core/document_import.py`. The earlier 44.24 % is therefore **not** a
whole-product figure. The CI value will be higher than the local 33.50 %
because the libGL tests run there; it has not been measured in CI yet.
Statement and branch counts for the unimported files come from
`coverage.parser.PythonParser`, i.e. coverage's own rules.

## Static metrics

| Metric | Value | Gate |
|---|---|---|
| Ruff debt (`core dialogs tabs tests`, ruff 0.16.6) | 5,342 | ceiling 5,375 |
| — of which F405 / E702 / E701 / F403 | 4,499 / 531 / 115 / 92 | |
| F403 wildcard imports, whole repository | 94 (tabs 56, dialogs 30, core 6, `main_window.py` 2) — all are `PySide6.QtWidgets/QtGui/QtCore/QtCharts/QtPrintSupport` | |
| Exception handlers / broad / silent / silent-broad | 1,035 / 628 / 192 / 68 | silent ceiling 192 (core 112) |
| Silent by area | core 112, tabs 50, dialogs 18, `main_window.py` 10, `app.py` 2 | |
| `setStyleSheet` calls (product + tests) | 502 | |
| `processEvents` calls in product code | 22 (`w11_Export` 11, `app.py` 3, `excel_import_dialog` 3, `main_window` 2, three files 1 each) | |
| Privacy check (tracked tree) | 979 files, 0 findings | test |

Largest non-test source files (lines): `core/database.py` 10,713;
`tabs/w13_Engineering_Calculator.py` 5,918; `dialogs/smart_template_dialog.py`
3,568; `main_window.py` 3,236; `tabs/w12_Analysis.py` 3,216;
`tabs/w10_Planning_Widget.py` 2,879; `tabs/w2_Daily_Report.py` 2,404;
`core/excel_intelligence.py` 2,304; `core/report_engine.py` 2,276.

Raw outputs (not committed; local forensics): `base_full.txt`, `cov_base.json`,
`base_failset.txt`.
