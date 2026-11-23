# M324 — CI evaluation of the PySide6 candidates (isolated overlay runs)

Workflow `.github/workflows/pyside-candidate-evaluation.yml`. Every leg installs the **locked** runtime and then overlays the candidate with `--no-deps`, in a throw-away runner. The repository pin stays **6.8.1.1**. **Status of D63/D74: BLOCKED BY OWNER DECISION.** This file is evidence for that decision; it is not the decision.

Job logs cannot be read from this environment. Every result below comes from the jobs API (step conclusions) and from check-run annotations, which the probe, the JUnit reporter and the PyInstaller step emit since `55b7340` / `b18706d`.

## 1. Runs

| Run | SHA | What changed in the workflow |
|---|---|---|
| `45018951634` | `e70ae78` | first run. Linux legs 5/6 green; Windows legs failed in "UI regression subset" (no detail); cancelled by the next push |
| `45019907032` | `55b7340` | + 6.8.1.1 **baseline** leg on Windows, failures annotated per test, PyInstaller step always attempted |
| `45024680781` | `b18706d` | + D91 fix (m115 tool stdout), per-run probe annotations, PyInstaller / smoke log tails annotated |
| `45115378469` | `67ea1e2` | + probe HANG detection (timeout per run, annotated); the candidate leg rehearses the M325 lock edit in the runner checkout so the frozen smoke validates against the candidate |
| next | after `2646543` | + the probe prints its stage and dumps every thread's stack (`faulthandler`) 30 s before the timeout; 5 runs per mode on 3.13; a Linux 3.13 × 6.8.1.1 baseline leg (product mode) |

## 2. Results on `b18706d` (run `45024680781`)

| Leg | D63 probe (3 windows, 3 runs per mode) | UI subset | PyInstaller build | Frozen smoke |
|---|---|---|---|---|
| windows 6.8.1.1 (baseline, product mode only) | 3/3 rc 0, **retains** 3 windows (28,863 live widgets) | ✅ | ✅ | ✅ |
| windows 6.8.2.1 | auto 3/3 + product 3/3 rc 0, **releases** (0 alive, 0 live widgets) | ✅ | ✅ | ❌ licence metadata (see §3) |
| windows 6.8.3 | auto 3/3 + product 3/3 rc 0, **releases** | ✅ | ✅ | ❌ licence metadata (see §3) |
| linux 3.11 × 6.8.2.1 / 6.8.3 | 6/6 rc 0, releases | ✅ | ✅ | — |
| linux 3.12 × 6.8.2.1 / 6.8.3 | 6/6 rc 0, releases | ✅ | ✅ | — |
| linux 3.13 × 6.8.2.1 | 6/6 rc 0, releases | ✅ | ✅ | — |
| linux 3.13 × 6.8.3 | **step failed without any per-run annotation** | skipped | skipped | — |

## 3. Findings

1. **D91 (fixed in `b18706d`).** On `55b7340` all three Windows legs, **including the 6.8.1.1 baseline**, failed the same three `test_m115_ux_startup` tests. The cause was `tools/quality/ux_startup_m115.py` printing non-ASCII JSON to a piped Windows stdout (ANSI code page), which raised `UnicodeEncodeError` after the JSON file had been written. The defect was pre-existing, Windows-only and in a test tool; it was not caused by a candidate. The tool now writes UTF-8 bytes. On `b18706d` the UI subset passes on all three Windows legs.
2. **Frozen smoke on the candidates fails only on the licence-metadata check.** It reports "missing licence metadata of the bundled distribution PySide6==6.8.1.1" (and the same for Addons, Essentials and shiboken6). `package_smoke.validate_bundle` compares the bundled `*.dist-info` against the **lock pins**; the overlay bundles 6.8.2.1 / 6.8.3 dist-info. Every other bundle check passed (exe, Qt DLLs, `qwindows.dll`, package data, forbidden modules). This is the lock / notices edit that M325 performs, not a candidate defect. Because validation stops the smoke before the exe is launched, the frozen app has **not yet been run** on a candidate. The workflow now rehearses the M325 lock edit in the runner checkout, so the next run launches the frozen exe.
3. **Linux 3.13 × 6.8.3: open.** The probe step failed on `55b7340` (both 3.13 legs) and on `b18706d` (6.8.3 only), with no per-run annotation. The probe printed nothing for any run, which is consistent with a run that never returned: `subprocess.TimeoutExpired` was uncaught. A hang is now reported as `rc=HANG` with the stderr tail. This needs the next run before 6.8.3 can be recommended on Python 3.13. 6.8.2.1 × 3.13 passed 6/6 on `b18706d`.
4. **The fix is confirmed on Windows.** On 6.8.1.1, auto mode is the known crash and is excluded from the baseline. On both candidates, auto mode freed three real MainWindows 3/3 with rc 0 on Windows and Linux. Product mode released them on the candidates and retained them on 6.8.1.1, as designed (D74).

## 3a. Results on `67ea1e2` (run `45115378469`)

| Leg | D63 probe | UI subset | PyInstaller build | Frozen smoke |
|---|---|---|---|---|
| windows 6.8.1.1 (baseline) | ✅ (retains, as designed) | ✅ | ✅ | ✅ |
| **windows 6.8.2.1** | ✅ releases | ✅ | ✅ | **✅ (frozen exe launched)** |
| **windows 6.8.3** | ✅ releases | ✅ | ✅ | **✅ (frozen exe launched)** |
| linux 3.11 / 3.12 × both candidates | ✅ | ✅ | ✅ | — |
| linux 3.13 × 6.8.3 | ✅ 6/6 | ✅ | ✅ | — |
| linux 3.13 × 6.8.2.1 | ❌ **3/6 runs HANG** (auto runs 1 and 3, product run 2); 3/6 rc 0 in 15 s | skipped | skipped | — |

5. **Finding 2 is closed.** With the lock pins naming the candidate (the rehearsed M325 edit, applied only in the runner), the frozen package passes every bundle check and the frozen exe runs on both candidates on Windows.
6. **Finding 3 is now a HANG, not a crash, and it affects Python 3.13 with either candidate.**
   - Every hung run printed "window 2: alive after its last reference was dropped: False" and nothing more. The process stopped while building, showing or closing the third MainWindow, after two windows had been released.
   - 6.8.3 hung on `b18706d` (the step failed without per-run output) and passed 6/6 here. 6.8.2.1 passed 6/6 on `b18706d` and hung 3/6 here. The hang is intermittent and not tied to one candidate.
   - It has never occurred on Python 3.11 or 3.12: 0 in 36 runs per candidate across the three runs, plus all Windows py3.12 legs.
   - **The product does not ship on Python 3.13**; the Windows build uses 3.12. The hung frame is not yet identified. The next run dumps every thread's stack and prints the stage. A 6.8.1.1 baseline on 3.13 (windows retained) shows whether the hang needs a released window.

## 4. Effect on the recommendation (`m324_pyside_upgrade_decision.md` §7)

- **On the shipped runtime (Windows, Python 3.12) both candidates pass everything**: probe, UI subset, PyInstaller build and the launched frozen exe (run `45115378469`). Linux 3.11 / 3.12 is also clean.
- **Python 3.13: both candidates hang intermittently** (finding 6). This does not block a 3.12 product. It does block any move to Python 3.13 until the hung frame is known.
- Neither candidate is safer on 3.13. The earlier preference for 6.8.2.1 came from a single run and is withdrawn. **The recommendation returns to 6.8.3**, the newer patch release of the same 6.8 line, with 6.8.2.1 as the alternative. This remains an OWNER DECISION, and M325 is not executed.
