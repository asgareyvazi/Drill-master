# M324 — CI evaluation of the PySide6 candidates (isolated overlay runs)

Workflow `.github/workflows/pyside-candidate-evaluation.yml`. Every leg installs the **locked** runtime and then overlays the candidate with `--no-deps`, in a throw-away runner. The repository pin stays **6.8.1.1**. **Status of D63/D74: BLOCKED BY OWNER DECISION.** This file is evidence for that decision; it is not the decision.

Job logs cannot be read from this environment. Every result below comes from the jobs API (step conclusions) and from check-run annotations, which the probe, the JUnit reporter and the PyInstaller step emit since `55b7340` / `b18706d`.

## 1. Runs

| Run | SHA | What changed in the workflow |
|---|---|---|
| `45018951634` | `e70ae78` | first run. Linux legs 5/6 green; Windows legs failed in "UI regression subset" (no detail); cancelled by the next push |
| `45019907032` | `55b7340` | + 6.8.1.1 **baseline** leg on Windows, failures annotated per test, PyInstaller step always attempted |
| `45024680781` | `b18706d` | + D91 fix (m115 tool stdout), per-run probe annotations, PyInstaller / smoke log tails annotated |
| next | after `3293c3d` | + probe HANG detection (timeout per run, annotated); the candidate leg rehearses the M325 lock edit in the runner checkout so the frozen smoke validates against the candidate |

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

## 4. Effect on the recommendation (`m324_pyside_upgrade_decision.md` §7)

- Both candidates are now supported by Windows evidence (probe and UI subset).
- **6.8.3 on Python 3.13 is not yet supported** (finding 3). Until the next run shows the HANG annotation or a pass, the safer candidate is **6.8.2.1**: it passed every completed leg on `b18706d`, including 3.13.
- Neither candidate has had its frozen exe launched yet (finding 2).
- The owner decision remains open. M325 is not executed.
