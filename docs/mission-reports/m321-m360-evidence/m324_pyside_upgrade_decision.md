# M324 — PySide6 upgrade decision package (D63 / D74)

**Decision owner:** product owner. **Status: BLOCKED BY OWNER DECISION.** This package does not change the pin. `requirements-lock.txt` keeps PySide6 / Essentials / Addons / shiboken6 at **6.8.1.1**. `requirements.txt` and `pyproject.toml` keep `>=6.6,<7`. The mission brief does not count as licence or dependency approval. M325 (the pin change) runs only with explicit owner approval.

Dates: sources were read on 2026-10-13 (session date). The sandbox system clock runs ahead (2026-11-22), so timestamps inside generated artifacts (database `created_at`, file mtimes) show that date; they are not the reading date.

Every candidate below was evaluated in an **isolated environment**: `pip install --no-deps --target /tmp/ps<version>` locally, and a throw-away CI runner overlay (`.github/workflows/pyside-candidate-evaluation.yml`). The product environment was never modified.

## 1. Candidate set: the requested 6.8.5 target does not exist publicly

PyPI JSON API, read 2026-10-13. The open-source 6.8.x releases on PyPI are 6.8.0, 6.8.0.1, 6.8.0.2, 6.8.1, 6.8.1.1, 6.8.2, 6.8.2.1 and **6.8.3**. **There is no public 6.8.4 or 6.8.5 wheel.** Later 6.8 LTS patch releases are distributed only to commercial Qt licensees. A "6.8.5 target" therefore cannot be met under the LGPL distribution the product uses. The newest public 6.8 LTS release, **6.8.3**, replaces it in this comparison.

Newer public lines exist (6.9.0–6.9.3, 6.10.0–6.10.3). They are outside this decision because they are a minor-version jump with a new Qt base, and they are noted only for the record. 6.10 raises the Linux floor to manylinux_2_34 (glibc ≥ 2.34).

| | 6.8.1.1 (current pin) | 6.8.2.1 | 6.8.3 (newest public 6.8) |
|---|---|---|---|
| PyPI upload | 2024-12-20 | 2025-02-06 | 2025-03-27 |
| Wheels (all four distributions) | cp39-abi3: win_amd64, manylinux_2_28_x86_64, manylinux_2_39_aarch64, macosx_12_0_universal2 | same | same |
| `Requires-Python` | `<3.14,>=3.9` | `<3.14,>=3.9` | `<3.14,>=3.9` |
| Essentials wheel size win_amd64 / linux x86_64 | 69.2 / 90.9 MiB | 69.1 / 90.9 MiB | 68.8 / 90.7 MiB |
| Addons wheel size win_amd64 / linux x86_64 | 122.0 / 152.9 MiB | 122.0 / 153.2 MiB | 121.9 / 153.1 MiB |
| Essentials sha256 win_amd64 | (in lock) | `18de224f…649e` | `3c0fae55…4b07` |
| Essentials sha256 manylinux_2_28_x86_64 | (in lock) | `5ab31e53…195a` | `fd57fa0c…53c1` |
| D63 fix (`PySideSignalInstanceShared`) in source | **absent** | present (v6.8.2 tag) | present (v6.8.3 tag) |
| `License:` metadata | `LGPL` | `LGPL` | `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` |
| Linux glibc floor (x86_64) | 2.28 | 2.28 | 2.28 |

The four distributions (PySide6 meta, PySide6-Essentials, PySide6-Addons, shiboken6) must move **together**. Each release pins the others exactly.

## 2. Is the fix present? (source evidence, not changelog)

- Upstream fix: pyside-setup commit `e226b5827c110d16c9d3b3f1b8d62b1c3a6e8605`, "libpyside/PySideSignal: Reduce number of weakref handlers for sender tracking". Task numbers PYSIDE-2201 and PYSIDE-79; committed 2024-12-16; marked `Pick-to: 6.8`.
- Source check at each release tag, using `sources/pyside6/libpyside/pysidesignal_p.h` (code.qt.io, read 2026-10-13):
  - **v6.8.1.1:** `PySideSignalInstancePrivate` holds a raw `PyObject *source`. There is no shared/deleted tracking struct.
  - **v6.8.2** and **v6.8.3:** these add `struct PySideSignalInstanceShared { PyObject *source; bool deleted; }` behind a `std::shared_ptr`. This is the structure the fix introduces.
- The 6.8.2 changelog does **not** list PYSIDE-2201. The evidence is the source tree at the tags, not the release notes.
- **Limitation:** there is no commit-level bisect, because PySide cannot be built in the sandbox. The behavioural evidence in §3 is consistent with the fix but does not prove which commit removes the crash.

## 3. Behavioural evidence: D63 window-release probe (local, isolated)

Command: `tools/quality/d63_window_release_probe.py --windows 3`, 5 runs per cell. Environment: Python 3.11.2, offscreen, Debian 12 (glibc 2.36), HEAD `b7d16db` content. Raw log: `m324_probe_matrix_local.txt`.

| PySide6 | `--mode auto` (windows freed by refcount) | `--mode product` (the D74 policy decides) |
|---|---|---|
| 6.8.1.1 | **SIGSEGV in 4 / 5 runs** (rc 139) | 0 / 5 crashes; policy **retains** windows: 3 alive, 28,797 live widgets at end |
| 6.8.2.1 | 0 / 5 crashes; 0 alive, 0 live widgets | 0 / 5 crashes; policy **releases**: 0 alive, 0 live widgets |
| 6.8.3 | 0 / 5 crashes; 0 alive, 0 live widgets | 0 / 5 crashes; policy **releases**: 0 alive, 0 live widgets |

This matches M307 (6.8.2.1: 0/5) and now adds 6.8.3. `core/qt_lifetime.window_release_policy()` switches to release automatically for any PySide6 ≥ 6.8.2. **No product code change is needed after approval; only the pins move.**

## 4. Regression subset per candidate (local, isolated)

Command: 23 UI-heavy test files, listed in `tools/quality/pyside_eval/ui_tests.txt`. They cover:
- M49 knowledge UI (the Windows width regression);
- M102 context probes, M115 UX/startup and chart axes, M117 widget journeys;
- the M308 window-release policy and the W3c well switch;
- M109, M311, M314, M317, M318 (W2 / W13 / architecture panel UIs) and M320 E;
- the M323 / M328 tests and the explicit-import contract.

Raw log: `m324_ui_matrix_local.txt`.

| PySide6 | tests | failures | errors | skipped | wall |
|---|---|---|---|---|---|
| 6.8.1.1 | 322 | 0 | 0 | 0 | 233 s |
| 6.8.2.1 | 322 | 0 | 0 | 0 | 224 s |
| 6.8.3 | 322 | 0 | 0 | 0 | 227 s |

Both candidates import every Qt module the product uses: QtWidgets, QtCore, QtGui, QtPrintSupport, QtSvg, QtNetwork, QtTest and QtCharts. QtCharts is in **Addons** and is used optionally by W10 Planning.

## 5. Matrix: what was run where

| Check | 6.8.2.1 | 6.8.3 | Where |
|---|---|---|---|
| Linux x86_64, Python 3.11: probe + 322 tests | PASS | PASS | local, isolated |
| Linux, Python 3.11 / 3.12 / 3.13: probe + UI subset + PyInstaller freeze smoke | see §8 | see §8 | CI `pyside-candidate-evaluation.yml` (`linux` job) |
| Windows 2022, Python 3.12: probe + UI subset + PyInstaller build of `packaging/DrillMaster.spec` + `package_smoke.py --run` | see §8 | see §8 | CI (`windows` job) |
| Local PyInstaller freeze | **NOT RUN** | **NOT RUN** | The sandbox Python has no shared `libpython3.11.so`, and GitHub release assets (standalone CPython) are blocked. |
| Local Python 3.12 / 3.13 | **NOT RUN** | **NOT RUN** | No interpreter is available in the sandbox. The wheels are `cp39-abi3`, so the same binary serves 3.9–3.13. |
| macOS / aarch64 | **NOT RUN** | **NOT RUN** | Not a product target. |
| Full suite (≈5,900 tests) on the candidate | **NOT RUN** | **NOT RUN** | To be run in M325 on the pinned candidate, by CI on the exact SHA. |

**PyInstaller:** the build pin is `pyinstaller==6.11.1` with `pyinstaller-hooks-contrib==2025.1`. The 6.11.0 / 6.11.1 changelog lists PySide6 6.8 support (QtGraphsWidgets hook for 6.8.0) and no 6.8.2- or 6.8.3-specific change. The same hooks apply to all 6.8.x releases. Empirical confirmation comes from the CI Windows job (§8).

## 6. LGPL obligations (unchanged in kind)

The classification is unchanged: `tools/quality/dependency_audit.py` classifies all three releases as **weak copyleft (LGPL)**, because the metadata contains "LGPL". 6.8.3 only spells out the SPDX expression `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. The product would **elect LGPL-3.0-only**, as it does today.

The obligations for the one-folder PyInstaller distribution are the same for every candidate:
- dynamic linking (Qt and PySide shared libraries kept as separate, replaceable files in the bundle, never statically merged);
- the LGPL-3.0 and GPL-3.0 licence texts and the Qt / PySide notices in `THIRD_PARTY_NOTICES.md`;
- the source offer or URL for the exact Qt / PySide version;
- no technical measure that prevents the user from replacing the libraries;
- the installer's licence text names the version.

**Owner action on approval:** update the version strings in `THIRD_PARTY_NOTICES.md` and in the release metadata to the chosen release. Shipping a licence text does not by itself meet LGPL; the dependency-audit gate keeps copyleft entries as owner gates.

## 7. Recommendation (for the owner, not a decision)

- **Recommended:** PySide6 / Essentials / Addons / shiboken6 **6.8.3**, the newest public 6.8 LTS release.
  - It contains the D63 fix (source evidence) and gave 0 crashes in 10 probe runs and 322 / 322 tests locally.
  - Same wheels, same Python range and same glibc floor as the current pin.
  - The only metadata change is the SPDX licence spelling.
- **Acceptable alternative:** 6.8.2.1. It has the same fix evidence (M307 plus this package) but omits the later 6.8.3 bug-fix content.
- **Not available:** 6.8.5 is commercial-only.
- **Not recommended now:** 6.9 / 6.10. That would be a minor jump with a new Qt base and needs a separate qualification; 6.10 also needs glibc ≥ 2.34.

**If approved (M325):**
1. Change `requirements-lock.txt` lines 22–27 to the chosen version, with its hashes if the lock carries them.
2. Leave `requirements.txt` / `pyproject.toml` (`>=6.6,<7`) unchanged, or tighten them to `>=6.8.2,<6.9` (owner's choice).
3. Run `tools/quality/dependency_audit.py --write`.
4. Update the notices.
5. Get full-suite CI on the exact SHA (Linux 3.11 / 3.12 / 3.13 + Windows release gate including PyInstaller and package smoke).
6. Re-run the probe in product mode.
7. Then close D63 / D74 in the register. **Until then, D74 remains the retain policy** (M326 keeps testing it).

## 8. CI evaluation runs

Filled in after the evaluation workflow ran on the pushed SHA: see `m324_ci_evaluation.md`.
