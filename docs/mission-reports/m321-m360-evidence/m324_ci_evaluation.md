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
| `45117305817` | `56d3542` | + the probe prints its stage and dumps every thread's stack (`faulthandler`) 30 s before the timeout; 5 runs per mode on 3.13; a Linux 3.13 × 6.8.1.1 baseline leg (product mode) |
| `45122895952` | `6ace038` | + the stacks are dumped twice (at 135 s and 270 s), so it shows whether each stuck thread still moves |
| `45138911996` | `82d1fff` | + GIL heartbeat (`--heartbeat`) and a compact report so both dumps fit one annotation |
| `45140757485` | `29620f4` | Python 3.13: native gdb stacks of a hung probe (`--native-dump`), 150 s timeout, and `mode=retain` on the candidates |
| `45142542401` | `90192f5` | full native stacks of the two blocked threads; `mode=collect` instead of `retain` on the 3.13 candidates |
| `45144294084` | `246e7bf` | Python 3.13: the probe runs with `core.qt_gc` installed (`--qt-gc`), as `app.py` does; a control step without it is diagnostic only. **All 10 jobs ✅** |

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

## 3b. Results on `56d3542` (run `45117305817`): the hung frame

**Unchanged:**
- All three Windows legs are green: probe, UI subset, PyInstaller and frozen exe.
- Linux 3.11 / 3.12 are green.

**New baseline:** Linux 3.13 × **6.8.1.1** (product mode, windows retained) passed **5/5**, and its UI subset and PyInstaller build passed.

**Linux 3.13 hangs:**

| Candidate | Hung runs | Where it stopped |
|---|---|---|
| 6.8.2.1 | 1 of 10 (auto run 3) | after "window 3: constructed" |
| 6.8.3 | 2 of 10 (auto runs 1 and 3) | after "window 3: constructed" |

So the process stops in the `show()` / `pump()` phase of the third window. The thread dumps (`faulthandler`, 270 s) were the same in all three hangs:

| Thread | Frames |
|---|---|
| main | `pump` → `QApplication.processEvents()` → **pyqtgraph geometry code**: `AxisItem.boundingRect`, `LabelItem.resizeEvent` and `enum.__call__` in the three dumps. `processEvents()` never returned. |
| worker (`ReadOnlyQueryWorker`) | `HomeTab._snapshot_job` → `operations_dashboard.build_snapshot` (line 368) → SQLAlchemy statement compilation. It was in the same query in all three dumps. |
| db maintenance | idle in `Event.wait` |

**Reading.** This is a livelock, not a crash and not a lock wait:
- The main thread keeps executing pyqtgraph layout code inside one `processEvents()` call.
- The dashboard worker has not finished one snapshot query after minutes.

The main-thread frames are the D51 signature: an `AxisItem` layout frame in a ~10-minute block, seen once in 300 CI runs and never reproduced since. That makes this the first reproducible trigger of the D51 class. **The data does not yet show** whether the worker is starved or re-started in a loop, or whether a released window's objects take part. 6.8.1.1 never releases windows and did not hang in 5 runs, but 5 runs cannot exclude a 10–20 % rate. The next run dumps twice to answer this.

**What it means for the decision:**
- The shipped runtime is Windows on Python 3.12, where no hang has been seen in any run (Windows and Linux 3.11 / 3.12 together: 0 hangs in 108 candidate probe runs across the last three evaluation runs).
- **D51 is re-opened as REPRODUCED ON PYTHON 3.13 (Linux CI, candidates, auto and product policy).** Root cause: OPEN.

## 3c. Results on `6ace038` (run `45122895952`): two dumps per hang

**Unchanged:**
- Windows (all three legs) and Linux 3.11 / 3.12 are green.
- The Linux 3.13 × 6.8.1.1 baseline (product mode) passed 5/5 again.

**Linux 3.13 hangs:**

| Candidate | Hung runs |
|---|---|
| 6.8.3 | 6 of 10 (3 of 5 auto, 3 of 5 product) |
| 6.8.2.1 | 1 of 10 (product) |

**Correction (made after `534e4f3`).** The first version of this section said the dashboard worker "moved" from line 368 back to line 365, and it called the hang a reload cycle. That was a **misreading**: GitHub cuts every annotation at 4,096 characters, and the two dumps compared there came from **two different runs**. Read run by run, the evidence is as follows.

| Run (6.8.3) | Dumps visible | Dashboard worker, dump 1 → dump 2 (135 s apart) |
|---|---|---|
| product 4, product 2 | 1 (second cut off) | `build_snapshot:368` (SQLAlchemy-generated `<lambda>`) |
| product 1 | 2 | `result.py:271 __init__` → **same line** |
| auto 5 | 2 | `loading.py:956 _instance_processor` → **same line** |
| auto 4 | 2 | `loading.py:956 _instance_processor` → **same line** |
| auto 2 | 2 | `result.py:442 _row_getter` (memoised property entry) → **same line** |

- **Main thread:** only the first dump of each run is complete. It is always inside pyqtgraph geometry code under one `processEvents()`: `AxisItem._updateLabel` (the recorded D51 frame), `AxisItem.boundingRect`, `LabelItem.resizeEvent` or `enum.__call__`.
- **Dashboard worker:** in all four complete pairs it is on **exactly the same line 135 s apart**. Those lines take no lock. They are a function entry and a `for` loop head, which are the points where CPython's evaluation loop gives up the GIL when another thread asks for it. On a small synthetic database these queries normally finish in milliseconds.

**Reading (corrected):** the worker is **parked waiting for the GIL**, and the main thread keeps it the whole time while it runs pyqtgraph layout code inside one `processEvents()`. So it is **GIL starvation** of the worker, combined with a main thread that does not leave the layout code. It is not a reload cycle.
- What keeps the main thread in layout code is **not identified**. It could be a pyqtgraph axis/label resize loop, or a native Qt call made from a Python override that keeps the GIL (ordinary Qt calls from Python slots do not release it; see [n1mm-scope-bridge #236](https://github.com/Reid-n0rc/n1mm-scope-bridge/issues/236)).
- It is seen on Python 3.13 only, with either candidate. The 6.8.1.1 baseline did not hang in 10 runs across the two evaluations.
- Under 6.8.1.1, windows 1 and 2 stay alive (`alive_at_end=3`); under both candidates they are released. Every hang is at window 3, after earlier windows were freed. This is an observation, not a proven cause.

**Instrumentation added after `534e4f3`** (`d63_window_release_probe.py --heartbeat`, `probe_loop.compact_hang_report`, test `tests/test_m324_hang_report.py`):
- **Heartbeat:** a pure-Python thread prints an `HB` line every `timeout/10` s with the top frames of every thread. It needs the GIL to print. If the `HB` lines **stop** when the hang starts, one thread held the GIL continuously, which confirms starvation. If they continue, the frames in them show whether the main thread still moves.
- **Compact report:** each dump is reduced to role-labelled threads (main / dash-worker / maint / worker / hb) with their innermost frames, so both dumps and the heartbeats fit one annotation.

## 3d. Results on `82d1fff` (run `45138911996`): GIL heartbeat — starvation confirmed, main thread blocked in native code

**Unchanged:**
- Windows ×3 and Linux 3.11 / 3.12 ×4 are green.
- The Linux 3.13 × 6.8.1.1 baseline passed 5/5. Across the three evaluations that is 15 runs and 0 hangs; windows are retained there.

**Linux 3.13 hangs:** 6.8.3: 1 of 10 (auto run 4). 6.8.2.1: 1 of 10 (auto run 3). Both are at window 3, after windows 1 and 2 were freed.

| Signal | 6.8.3 auto 4 | 6.8.2.1 auto 3 |
|---|---|---|
| Heartbeat lines in 300 s (one due every 30 s) | **0** | **0** |
| Heartbeat thread | `d63_window_release_probe.py:167` (`time.sleep`) in both dumps: it woke up and is waiting for the GIL | same |
| Main thread, dump 1 → dump 2 (135 s apart) | `AxisItem.py:350 _updateLabel < updateAutoSIPrefix < setRange < linkedViewChanged`, **identical** | `GraphicsWidget.py:40 _resetCachedProperties` called straight from `processEvents()`, **identical** |
| Dashboard worker | `<string>:1 <lambda> < selectable.py:2407 _generate_columns_plus_names` (SQLAlchemy), identical | same frame, identical |

**What this proves:**
1. **One thread held the GIL for the whole hang.** A pure-Python thread that only sleeps could not print once in 290 s.
2. **That thread is the main thread, and it is not executing Python.** A thread running bytecode hands the GIL over within 5 ms (the switch interval) and moves on between dumps. Here the main thread is on the same line for 135 s while holding the GIL, so it is **blocked inside a native call** made from that line:
   - `AxisItem.py:350` is `self.label.setHtml(self.labelString())`, a Qt call through Shiboken.
   - `GraphicsWidget.py:40` sets cached attributes to `None`, which deallocates the previous Qt value wrappers through Shiboken.
3. **It is a deadlock, not a livelock.** The worker and heartbeat threads wait for the GIL; the main thread waits inside native code, presumably for a lock, and keeps the GIL.

**Not proven:** which native lock, and which thread holds it. Faulthandler shows only Python threads. Qt's native threads and threads blocked in `PyGILState_Ensure` are invisible to it.

**Version vs. window release:**
- Shiboken's `BindingManager` (the wrapper map and its `std::recursive_mutex`) is the same in 6.8.1.1 and 6.8.3 (source compared at the `v6.8.1.1` and `v6.8.3` tags).
- The one difference the probe exercises is that **only the candidate legs free windows 1 and 2**. The 6.8.1.1 product policy keeps them.
- So the hang may be triggered by freeing windows under Python 3.13, not by the candidate itself. The next run separates the two: `mode=retain` on the candidates keeps windows as 6.8.1.1 does. It also takes native gdb stacks (`thread apply all bt`) of every hung probe before killing it, to name the lock and its holder.

## 3e. Root cause (runs `45140757485` and `45142542401`): the M50 deadlock, reproduced because the probe lacked `core.qt_gc`

**Native stacks** (gdb `thread apply all bt`, taken from every hung probe before it was killed; 6 hangs in run `45140757485`, 3 in `45142542401`; the two blocked threads were identical in all of them):

| Thread | Native stack (innermost first, abridged) | Holds | Waits for |
|---|---|---|---|
| T1 main | `QBasicMutex::lockInternal < QObject::~QObject < QAction::~QAction < QObjectPrivate::deleteChildren < QWidget::~QWidget < QMenu::~QMenu < … < Shiboken::BindingManager::runDeletionInMainThread < _make_pending_calls < _Py_HandlePending < _PyEval_EvalFrameDefault < … QGraphicsLayoutItem::effectiveSizeHint / QGraphicsScene::itemsBoundingRect < … QCoreApplicationPrivate::sendPostedEvents < QEventDispatcherGlib::processEvents` | the GIL | Qt's signal-slot (connection) mutex |
| T2 `ReadOnlyQueryWorker` | `take_gil < PyEval_RestoreThread < PyGILState_Ensure < Shiboken::GilState < Sbk_GetPyOverride < QObject::~QObject (< QMenu::~QMenu < QWidget::~QWidget) < subtype_dealloc < dict_dealloc < … < delete_garbage < gc_collect_main < _Py_RunGC < _Py_HandlePending < _PyEval_EvalFrameDefault` | Qt's connection mutex (inside `~QObject`) | the GIL |

**Mechanism:** a lock-order inversion between the GIL and Qt's connection mutex.
1. Python's cyclic collector ran **on the dashboard worker thread** (`_Py_RunGC` from the evaluation loop's pending-work check). The garbage was the cycles of a **freed window**.
2. On that thread Shiboken destroyed Qt objects of the window (`subtype_dealloc → ~QObject`). It also queued the plain widgets for deletion on the main thread (`delete_in_main_thread` → `Py_AddPendingCall`, source `basewrapper.cpp` at `v6.8.3`).
3. `~QObject` on the worker took Qt's connection mutex, then called into Python (`Sbk_GetPyOverride`), so it waits for the GIL.
4. The main thread holds the GIL, runs the queued deletion (`runDeletionInMainThread`), and its `~QObject` waits for the same mutex.

The earlier observations fit this:
- The main thread "stuck in pyqtgraph geometry" is the Python frame active when the pending call ran.
- The worker "parked on a function entry or loop head" is exactly where the evaluation loop runs pending GC.
- 0 heartbeats: the GIL is never released.
- Hangs only where windows are freed: on 6.8.2.1 / 6.8.3 windows are freed even in `mode=retain` (`alive_at_end=0`); 6.8.1.1 keeps them.
- `mode=collect` (garbage collected on the main thread right after each free): **0 of 8** hangs, against **3 of 16** for auto / product in the same run.

**This is the deadlock M50 already found and fixed.**
- `core/qt_gc.py` (M50) describes the same two native stacks. `app.py` installs it before any worker starts: automatic collection is off, and a GUI-thread `QTimer` collects. The test session follows the same rule (D53, `tests/conftest.py`).
- **The D63 probe builds `MainWindow` directly and never installed `core.qt_gc`.** Every probe run was therefore made without the application's GC policy, and the 3.13 hangs reproduce a defect class the product already guards against.
- The same failure, with the same two stacks, is reported in other PySide applications. Their fix is the same: collect only on the GUI thread ([longhorn-baja-racing/dashboard #152](https://github.com/longhorn-baja-racing/dashboard/pull/152), [LoRAIro #1492](https://github.com/NEXTAltair/LoRAIro/issues/1492)).

**Why it was seen on Python 3.13 only** is not established. It may come from collection timing or thresholds; it is not needed for the conclusion.

**Confirmation step:** run `45144294084` (§3f).

## 3f. Confirmation on `246e7bf` (run `45144294084`): no hang with the application's GC policy

All 10 jobs ✅: Windows ×3, Linux 3.11 / 3.12 ×4, and Linux 3.13 ×3.

| Linux, Python 3.13 | Probe as the application runs (`--qt-gc`) | Control: same job, same probe, without `core.qt_gc` (diagnostic) |
|---|---|---|
| 6.8.3 | **0 / 16 HANG** (8 auto, 8 product); worker-thread collections 0 in every run | 1 / 8 HANG |
| 6.8.2.1 | **0 / 16 HANG** (8 auto, 8 product); worker-thread collections 0 in every run | 4 / 8 HANG |
| 6.8.1.1 baseline | 0 / 8 (product) | not run |

- 0 of 32 against 5 of 16 on the same runners. If the GC policy made no difference, the chance that all 5 hangs fall in the 16 control runs is C(16,5) / C(48,5) ≈ 0.003 (Fisher's exact test, one-sided).
- `worker_collections=0` is the `core.qt_gc` watchdog: no cyclic collection started off the GUI thread in any product-faithful run.
- Product entry points: `run.py` starts `DrillMasterApp` (`app.py`), which installs `core.qt_gc` before any worker starts. The other `MainWindow(...)` callers are developer tools (screenshots, measurements, this probe).

**Conclusion:**
- The Python 3.13 hangs in this evaluation are the **M50 deadlock**, reproduced by a probe that lacked the application's GC policy.
- They are **not a defect of PySide6 6.8.2.1 / 6.8.3 as the product runs them**, and they give no reason to stay off Python 3.13.
- The single historical D51 event (M266, once in 300 CI runs, with an `AxisItem` frame) happened while the test session already followed the D53 rule. It is **not proven** to be the same event, so it stays under the M309 monitor.

**New fact for M325:**
- On 6.8.2.1 / 6.8.3, closed windows are freed **even in `mode=retain`** (`alive_at_end=0`, runs `45140757485` and `45142542401`), not only under the product release policy.
- After an upgrade, every closed window therefore becomes cyclic garbage. **`core.qt_gc` is then a hard precondition.** Any code path that builds windows and starts workers must install it, as `app.py` does.

## 4. Effect on the recommendation (`m324_pyside_upgrade_decision.md` §7)

- **On the shipped runtime (Windows, Python 3.12) both candidates pass everything**: probe, UI subset, PyInstaller build and the launched frozen exe (run `45115378469`). Linux 3.11 / 3.12 is also clean.
- **Python 3.13: no hang when the probe runs as the application does** (§3f: 0 / 32 with `core.qt_gc`). The earlier 3.13 hangs (finding 6, §3a–§3e) are the M50 GIL / Qt-mutex deadlock, reproduced because the probe lacked the application's GC policy. They no longer block Python 3.13.
- **Precondition added for M325:** on the candidates closed windows are always freed, so `core.qt_gc` (installed by `app.py`) must stay installed on every path that builds windows and starts workers.
- Neither candidate differs in these results. The earlier preference for 6.8.2.1 came from a single run and is withdrawn. **The recommendation is 6.8.3**, the newer patch release of the same 6.8 line, with 6.8.2.1 as the alternative. This remains an OWNER DECISION, and M325 is not executed.
