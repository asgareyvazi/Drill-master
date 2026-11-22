# M307–M308 — D63 root cause and the D74 window-release policy

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC databases only. The project dependency pin
(`requirements-lock.txt`: PySide6 6.8.1.1) is **unchanged**; PySide6 6.8.2.1 was used only from an isolated
`pip install --target /tmp/pyside682` directory for diagnosis.

## M307 — D63: what was found

**New native evidence** (`tools/quality/native/segv_dictkey.c`, opt-in `LD_PRELOAD`, read-only):

* At the known fault (`0x515ee3`, CPython 3.11.2 `free_keys_object`), the registers identify the dict being
  freed (`r14`) and the entry being cleared (`rbp - 0x10`). Run 1 decoded it: the keys are
  `bottomChanged, topChanged, decimalsChanged, notationChanged, changed, destroyed, objectNameChanged` — exactly
  the signals of a **QDoubleValidator** (+ QValidator, QObject). The freed value is the cached
  **SignalInstance under `notationChanged`**. This dict is PySide's per-object signal-instance cache filled by
  `PySide::Signal::updateSourceObject` (seen in the M264 native stack).
* Runs 2/3 (and both later controls) crashed at a second site, return address `0x557c7d`: CPython's weakref clear
  (`Py_CLEAR(wr->wr_callback)` → `_Py_Dealloc`), i.e. while releasing a **weakref callback** object.
* Disassembly: `m307_d63_disassembly.txt`; raw runs: `m307_d63_probe_runs_d57f5b2.txt`.

**Source reading** (PySide 6.8.1, `sources/pyside6/libpyside/pysidesignal.cpp`, `pysideweakref.cpp`):
`instanceInitialize` calls `PySide::WeakRef::create(source, sourceGone, self)`. This registers a weakref with a
callback on the **signal source** whose user data is a **raw pointer to the SignalInstance** (no reference is
held, and `signalInstanceFree` does not remove the weakref). When the SignalInstance is freed before its source,
for example while the source's instance dict is cleared, the callback later runs `sourceGone(self)` and
writes `self->deleted = true` **into freed memory**. That is a use-after-free write, which matches both crash sites.

**Upstream:** commit `e226b5827c` (2024-12-13, "libpyside/PySideSignal: Reduce number of weakref handlers for
sender tracking", PYSIDE-2201, "Pick-to: 6.8") replaces the raw pointer with a heap-allocated
`shared_ptr<PySideSignalInstanceShared>`, so `sourceGone` writes into shared state that outlives the instance.
GitHub contents API check: `PySideSignalInstanceSharedPtr` is absent in v6.8.1 and v6.8.1.1 and present in
v6.8.2, v6.8.2.1, v6.8.3 and v6.9.0.

**A/B experiment** (same probe, `--mode auto`, same session):

| PySide6 | runs | SIGSEGV | windows freed | live widgets at end |
|---|---|---|---|---|
| 6.8.1.1 (pinned) | 5 | **5/5** | – | – |
| 6.8.2.1 (isolated) | 5 | **0/5** | 3/3 every run | **0** |

**Classification:** root cause identified with strong evidence, but in the third-party library; not fixed in
the product. The register label is **OWNER DECISION REQUIRED**: bumping the PySide6 pin to ≥ 6.8.2 (same
LGPL-3.0 licence family as today) is a dependency change that needs the owner, an exact-version licence audit
and a full-suite qualification on the new pin.

**Limits, stated plainly:** no commit-level bisect (PySide cannot be built in the sandbox); 6.8.2.1 contains
other changes as well. The causal chain rests on four things: the decoded freed object, the crash sites, the
source reading, and the version A/B. The second crash site was not decoded register-by-register.

## M308 — D74 incremental fix, gated on the D63 fix

* `core/qt_lifetime.py`: `window_release_policy()` returns release only on PySide6 ≥ 6.8.2. It retains windows on
  older versions, an unrecognised version, or `DRILLMASTER_RETAIN_CLOSED_WINDOWS=1`, and always gives a reason.
  `apply_window_release_policy()` is idempotent and makes `HomeTab.parent_window`, `WellInfoTab.main_window` and
  `DailyReportWidget.parent_window` weak (`WeakWindowAttribute`; a value set before installation is still
  returned).
* `MainWindow.__init__` applies the policy before `init_ui()` builds any tab and keeps it in
  `window.window_release_policy`.
* Lambdas were **not** changed: with the three attributes weak, the windows are freed (0 alive, 0 widgets), so
  the lambdas are not the remaining holders on 6.8.2.1.
* No `gc.collect()` was added; windows are not destroyed explicitly; the change does nothing on the pinned
  6.8.1.1.

**Measured before / after** (`--mode product`, product code only; `m308_d74_product_policy_runs.txt`):

| PySide6 | policy | closed windows alive at end | live widgets | crash |
|---|---|---|---|---|
| 6.8.1.1 (pinned) | retain | 3 / 3 | 28,680 | 0 / 2 |
| 6.8.2.1 | release | **0 / 3** | **0** | 0 / 2 |

**Status:** D74 stays PARTIALLY RESOLVED on the shipped pin (closed windows are still retained on 6.8.1.1). The
release path exists and is measured, and it switches on automatically once the owner approves PySide6 ≥ 6.8.2.

**Tests:** `tests/test_m308_window_release_policy.py` (16): the version table, operator override, weak release on
plain classes (refcount only, no gc), retention installs nothing, product classes follow the installed PySide6,
and the policy is applied before the tabs are built. The D63/window set (`test_m265_window_routes` first, then
every test that builds a MainWindow or imports `main_window`, 501 tests) passed on 6.8.1.1, apart from the
`test_model_registry` regression described below, which was then fixed.

**Regression found and fixed in the same step:** the M298 function `registry()` tripped the ORM-registry guard
(`test_model_registry::test_only_core_database_creates_a_declarative_base`; it was committed in `d57f5b2`). It
was renamed to `field_registry()`; the guard was not loosened.
