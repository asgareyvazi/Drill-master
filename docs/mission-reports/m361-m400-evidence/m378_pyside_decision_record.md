# M378 — PySide6 decision record (replaces the imprecise M324 wording)

Status: **BLOCKED BY OWNER DECISION.** The pin stays `PySide6 == 6.8.1.1` (with `PySide6_Addons`,
`PySide6_Essentials`, `shiboken6` at the same version) in `requirements-lock.txt`. No pin was changed in M361–M400.

Evidence gathered 2026-11-23 from the PyPI JSON API (`pypi.org/pypi/PySide6/json`) and the GitHub API for
`pyside/pyside-setup` (tags, compare). Nothing in this record was taken from memory.

## 1. Correction of the M324 wording

M324 said 6.8.4 / 6.8.5 were "commercial-only / not public". **That is wrong as written.**

| Fact | Evidence |
|---|---|
| An LGPL **source** release of 6.8.4 exists | tag `v6.8.4-lts-lgpl`, tag object `696890e1`, commit `fc6d063e`, 2026-08-03, message "Qt For Python Release 6.8.4" |
| An LGPL **source** release of 6.8.5 exists | tag `v6.8.5-lts-lgpl`, tag object `c3115a21`, commit `b37cb18a`, 2026-10-17, message "Qt For Python Release 6.8.5" (source tarball `pyside-setup-opensource-src-6.8.5`) |
| **No PyPI wheels** for 6.8.4 or 6.8.5 | PyPI 6.8 line: 6.8.0, 6.8.0.1, 6.8.0.2, 6.8.1, 6.8.1.1, 6.8.2, 6.8.2.1, 6.8.3 — nothing later |

Correct statement: *6.8.4 and 6.8.5 are published as open-source LGPL source releases; the Qt Company does not
publish binary wheels for them on PyPI. Using them would mean building PySide6 + shiboken6 + Qt 6.8.x from source
for Windows and Linux, which this project has never done and has no CI for.*

## 2. Candidates that can be installed from PyPI

| | 6.8.1.1 (current) | 6.8.2.1 | 6.8.3 |
|---|---|---|---|
| PyPI upload | (pinned since before M321) | 2025-02-06 | 2025-03-27 |
| Wheels | cp39-abi3, Python < 3.14 | cp39-abi3, Python < 3.14 | cp39-abi3, Python < 3.14 |
| PYSIDE-2201 fix (`bfb7fd1c68`, 6.8-branch cherry-pick of dev `e226b582` "PySideSignal: Reduce number of weakref handlers for sender tracking") | **no** | yes (in 6.8.1.1..6.8.3 range) | yes |
| D51 relevance | the M309 monitor + `core.qt_gc` workaround are in place; 0/32 hangs with `--qt-gc` vs 5/16 without (M324 probe) | fix present; not measured in this repo's CI | fix present; M324 evaluation workflow ran 10/10 on 6.8.3 |
| PyInstaller 6.11.1 hooks | generic | generic | generic |
| `bindingmanager.cpp` vs 6.8.1.1 | — | — | identical |
| `SbkDeallocWrapperCommon` off-main-thread path | — | — | `Py_AddPendingCall` → `runDeletionInMainThread` |

`v6.8.3` → `v6.8.5-lts-lgpl`: diverged, 99 ahead / 3 behind, 239 files. The 3 commits only on 6.8.3 are the version
string, the trace-set regression fix `99cdacf4e7` (equivalent `d02f57c67f` is in 6.8.5) and "Pin qt5#6.8.3".
`bfb7fd1c68` is an ancestor of `v6.8.5-lts-lgpl` (205 ahead / 0 behind), so 6.8.5 also contains the fix.

## 3. Recommendation (not a decision)

Recommendation unchanged from M324: **6.8.3**, alternative **6.8.2.1**. 6.8.4 / 6.8.5 are not recommended while
there are no wheels (a from-source Qt build is a new supply-chain and CI burden; that is an owner decision of its
own, not a technical default).

## 4. Checklist the owner approval would trigger (none executed)

1. Change all four pins together (`PySide6`, `PySide6_Addons`, `PySide6_Essentials`, `shiboken6`) in
   `requirements-lock.txt`; regenerate `docs/engineering/dependency_audit.json` (`--write`, then `--check`).
2. Source CI on 3.11 / 3.12 / 3.13 and Windows CI on the exact SHA; the PySide evaluation workflow 10/10.
3. Re-run the D51 probe **with** `--qt-gc` (product-faithful) and without, same counts as M324.
4. Windows package smoke (`packaging/package_smoke.py`) and the release-evidence gate.
5. Keep `core.qt_gc` until the probe shows 0 hangs without it on all three Python versions.
6. Record the result as a new addendum; never rewrite M324.

## 5. Status

| Item | Status |
|---|---|
| Wording correction | PASS (this record + M364 addenda in `m324_pyside_upgrade_decision.md` and the M321–M360 report) |
| Pin change | BLOCKED (owner decision) |
| 6.8.4 / 6.8.5 wheels | NOT AVAILABLE on PyPI (source only) |
