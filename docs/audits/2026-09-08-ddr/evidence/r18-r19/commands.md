# R18/R19 verification, 2026-09-09

Working branch: `arena/01a0801f-drill-master`.
Verified starting commit: `7d21679ee64012ba425302b9fbc7445dee334142`.
No branch switch, reset, force push or broad inventory rerun.

```bash
source .venv/bin/activate
export PYTEST_ADDOPTS='-p no:pytest-qt'
export QT_QPA_PLATFORM=offscreen
export DRILLMASTER_TEST_DDR_XLSX='/home/user/Drill-master/08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx'

python -m pytest -ra tests/test_r18_r19_save_preservation.py
python -m pytest -ra tests/test_r18_r19_save_preservation.py -k legacy
python -m pytest -ra tests/test_r18_r19_save_preservation.py -k 'not legacy'
python -m pytest -ra tests/test_autosave_manager_regression.py tests/test_ddr_followup_lifecycle.py tests/test_ddr_forensic_regressions.py tests/test_ddr_regression.py tests/test_engineering_ground_truth.py tests/test_p0_time_log_validation.py tests/test_r18_r19_save_preservation.py tests/test_real_oeoc_golden.py tests/test_real_user_acceptance_regressions.py
python -m pytest -ra
python -m compileall -q core dialogs tabs tests
git diff --check
git status --short
```

Ruff also passed for `core/editor_state.py`, `core/editor_bindings.py`,
`core/legacy_bha.py`, `core/save_outcome.py`, and the new test module.

`pytest-qt` is disabled because the native Qt Widgets library dependency
`libGL.so.1` is unavailable. This does not remove or weaken test assertions.
The existing QCoreApplication timer regression runs in the subsystem; the new
widget tests execute production method bodies with widget protocols, not a
native QMainWindow. New persistence fixtures explicitly use a generated-credential
Production SQLite database and a created hierarchy. No fixture credentials or
DB/workbook artifacts are committed.

Golden A was enabled, unchanged. Golden B remains NOT AVAILABLE / NOT VERIFIED.
The last full run followed the final source edits; subsequent edits are audit/evidence only.
Final commit/push SHA and clean working-tree verification are supplied in the
handoff, rather than embedding a self-referential commit hash in this commit.
