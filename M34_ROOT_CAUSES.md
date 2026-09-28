# M34 — Root Causes

Every entry below answers the same four questions: **what is the mechanism, where is it in the source, what did
we execute to prove it, and what is the verdict.** Verdicts are drawn from
`{VALID DOMAIN LIMIT, NO LIMIT REQUIRED, SEPARATE VALIDATION CONTRACT, BUG, UI-ONLY PRESENTATION LIMIT,
FAILURE-AS-ZERO, MISSING-VS-ZERO, PACKAGING DEFECT, BY-DESIGN}` — and each one is attached to a record in
`m34-ledger.json`, not to a narrative.

---

## 1. Engine defaults: is a plausible number standing in for an absent input?

The pattern family is `default-zero-param` (350 records) and `numeric-coalesce` (65). The audit question is
never "does the signature say `= 0`" but "does a plausible number enter the result stream when the engineer
supplied nothing".

| Site | Mechanism | Evidence | Verdict |
|---|---|---|---|
| `core/engineering/engines/casing.py` `CasingEngine.evaluate` | An absent `axial_tension_lbf` / `internal_pressure_psi` used to be folded to `0.0` and then *reported* (`fyax_psi`, `axial_stress_psi`, `internal_pressure_psi`), i.e. a biaxial/Pi correction that was never supplied appeared as a computed value | M33-FIX-CASING (verified this mission): `fax_supplied`/`pi_supplied` are computed separately, the reported values are `None` for an absent load, `axial_tension_supplied`/`internal_pressure_supplied` are part of `values`, and both absences emit explicit warnings. Reproduced by `tests/test_casing_absent_load_semantics.py` (5 tests) + offscreen widget smoke; mutants `M34-M-CASING-FABRICATE` and `M34-M-CASING-ZERONONE` killed | **FAILURE-AS-ZERO → FIXED** (the fix is byte-identical to M33's recorded post-state) |
| `core/engineering/engines/torque_drag.py` | Defaults feed a deterministic torque/drag model; the sweep's `default-zero-param` records there are INTENTIONAL with the declared default named on each record | ledger records for that file (all terminal); no open record names this file's defaults | **VALID DOMAIN LIMIT** — the defaults are physical inputs (a zero load is a real operating point), and the engine reports its inputs back |
| `core/engineering/torque_drag_persistence.py` (`:123`, `:168` in M33's numbering) | Persistence of torque/drag runs: absent inputs are stored as `NULL`, which is what the schema allows | `snapshot-serialize` / `get-default` records for this file are terminal; the sweep found no fabricated value written for an absent input | **NO LIMIT REQUIRED / BY-DESIGN** |
| `core/data_quality.py` `24h time coverage` | An unrecorded duration used to be summed as 0 h, understating coverage as a *measurement* | M33-FIX-DATAQUALITY (verified this mission): `unrecorded` is counted first, and when it is non-zero the metric is `value=None, status="unknown"` with the reason in `detail`. Two tests pin both branches; mutant `M34-M-NONETOZERO` killed | **FAILURE-AS-ZERO → FIXED** |
| `core/validators.py` domain ranges | `("avg_rop", 0, 500)` etc. are the *documented* engineering ranges — this is the contract the UI must respect | read directly from the validator table; used as the bound passed to the widget (below) | **SEPARATE VALIDATION CONTRACT** |

---

## 2. The Qt 99.99 clamp

**Mechanism (independently reproduced this mission, not quoted):** a bare `QDoubleSpinBox()` has a default
maximum of **99.99**; `setValue(150)` leaves the widget reading **99.99** — Qt truncates silently. Any derived
engineering value above 99.99 that is written into such a widget is therefore displayed *and persisted* as a
smaller number than the engine produced.

**Where it lived:** the W3 drilling tab's read-only derived fields (`avg_rop`, `tfa_value`, `hsi`) and the
dialogs' measurement spin boxes.

**What the repository now does** (`tabs/w3_drilling_report.py`):

* `_calc_spin(spin, maximum=None)` — minimum `-1` with `setSpecialValueText("Not computed")`; the **documented
  domain maximum is passed explicitly at each call site** (`_calc_spin(QDoubleSpinBox(), 500)` for `avg_rop`,
  taken from `core/validators.py`'s `("avg_rop", 0, 500)`).
* `_calc_value(spin)` — reads `None` when the widget still shows the sentinel, so `collect_data` persists
  *unknown* for an uncomputed value.
* `_set_calc(spin, value)` — `None` → sentinel; a real value above the current maximum **raises the maximum**
  instead of being truncated.

**Executed proof:** `tests/test_m31_scenarios.py::test_derived_avg_rop_display_is_not_silently_clamped` passes;
`M34-M-CLAMPRESTORE` (delete the raise-the-maximum guard) and `M34-M-QT99CLAMP` (delete the explicit domain
maximum, leaving Qt's 99.99) are both **killed**. The dialogs' measurement fields keep the same separation
(`setMinimum(-1)`, `"Not recorded"`, empty-string persistence, and `M34-M-DIALOG` killed).

**Verdict: UI-ONLY PRESENTATION LIMIT → resolved by contract.** The bound is the *engineering* domain range, not
a magic number: the UI never invents a number and never silently truncates one; plausibility warning remains the
validator's job. The forbidden move — "99.99 → 999999" — was not made anywhere.

---

## 3. Missing vs zero, across the boundaries

| Boundary | Mechanism found | Verdict |
|---|---|---|
| Engine → result | absent load reported as `None` plus a `*_supplied` flag and a warning (`casing`) | **FIXED** |
| Result → UI | sentinel minimum + "Not computed" text; `None` never rendered as `0` | **FIXED / BY-DESIGN** |
| UI → payload → DB | `_calc_value` returns `None` for an untouched field; persistence keeps `NULL` | **FIXED** |
| Time logs | `duration is None` stays missing: NPT derivation skips it and warns, activity-code usage carries `unrecorded_hours`, the legacy validator reports an incomplete 24 h | **FIXED** (M32-FIX-004/005/006, re-verified) |
| Metrics | `24h time coverage` reports `unknown`, not a subtotal | **FIXED** (M33-FIX-DATAQUALITY) |
| Exports | an unrecorded duration exports as an **empty cell**, never `0 h` | **FIXED** (M32-FIX-002, re-verified) |
| Ordering | an unknown section depth sorts **last**, not as 0 | **FIXED** (M32-FIX-003, re-verified) |
| Where it remains open | 88 `R-TRUTH-NUMERIC` records test a *numeric* value for falsiness with no `None` guard, and 26 `R-SPIN-ZERO` records write `0` into a widget outside construction/load paths | **OPEN — named fact on each record** |

---

## 4. Failure as zero (the M32 fix set, re-verified in M34)

| Fix | Contract | M34 verification |
|---|---|---|
| M32-FIX-004 | derived NPT skips logs with no recorded duration and logs the skip | probe present; test passes; mutant `M34-M-NPT` killed |
| M32-FIX-005 | activity-code usage hours are unknown when a duration is missing | probe present; test passes; mutant `M34-M-CODEHOURS` killed; `M34-M-DURATIONORZERO` is the documented equivalent survivor |
| M32-FIX-006 | the legacy validator reports an unrecorded duration instead of 0 h | probe present; test passes; mutant `M34-M-VALIDATOR` killed |
| M32-FIX-007 | a failed engine calculation returns `None`, not `0` | probe present; test passes; mutant `M34-M-ROP` killed |
| M32-FIX-008 | the tab persists `unknown` for uncomputed derived values | probe present; test passes; mutant `M34-M-TABPERSIST` killed |
| M32-FIX-001/002/003 | dialogs keep unrecorded measurements blank; exports leave a blank cell; unknown depth sorts last | probes present; tests pass; mutants `M34-M-DIALOG`, `M34-M-EXPORT`, `M34-M-HIERARCHY` killed |

All ten M32 fixes plus the three M33 fixes: **13/13 VERIFIED** (`m34-fix-reverification.json`), with two files
whose hashes legitimately differ from the M32 record because M33 changed them — stated on the record rather than
explained away.

---

## 5. Ownership, scope and sessions

* The ownership guards are present and active: `_check_report_scoped_well_ownership` raises
  `OwnershipIntegrityError` when a report-scoped snapshot claims a foreign well, and the M26 ownership suite
  passes. Removing the guard in a mutant fails the suite (`M34-M-OWNERSHIP` killed) — the guard is load-bearing,
  not decorative.
* `NULL` ownership is deliberately treated as *unknown* and left untouched (no fabricated foreign key), which is
  the behaviour the ownership tests assert.
* Session lifecycle: 1 256 of 1 282 `session-lifecycle` records are terminal with the ownership/close named on
  each record; **26 remain open** (`R-SESSION-OTHER`, 15 of them HIGH `R-SESSION-LEAK`) because the close cannot
  be proven from the enclosing function alone.
* `raw-sql-text` 40/40 VERIFIED: every raw SQL string is parameterised — no interpolation of user data was found.

---

## 6. Packaging (new in M34, and blocking)

**Mechanism.** The repository's own release gate builds a wheel from `git ls-files`. Two production modules —
`core/operational_time.py`, `core/safety_semantics.py` — are **untracked**, while tracked modules import them
(`core/actual_vs_plan.py:155`, `core/database.py:4420`, `core/ddr_pdf_export.py:8`, `core/report_engine.py:16`,
`core/operations_intelligence.py:13/128`, `tabs/w10_Planning_Widget.py:19`, …).

**Executed proof** (`m34-wheel-and-clean-env.json`): the tracked-only wheel builds
(`drillmaster-1.0.0-py3-none-any.whl`, 1 036 029 B, sha256 `5d5211600372ced4…`), contains every entry the gate
requires and no `tests/`, installs cleanly with `--no-index --target` — and then, started from `/tmp` with the
checkout absent from `sys.path`:

```
File ".../tabs/w10_Planning_Widget.py", line 19, in <module>
  from core.operational_time import summarize_time_logs
ModuleNotFoundError: No module named 'core.operational_time'
```

**Verdict: PACKAGING DEFECT — blocking.** A release artefact built from the repository as it stands cannot start.
M33 reported this stage as passing against a staging state whose cited commit `a9d7dede…` does not resolve in
this repository (see `M34_M33_RECOVERY.md` §5). The remedy is one action — add the two modules (and their tests)
to the Commit-1 population — and the Commit-1 simulation shows the population behaves correctly when they are
present (see `M34_RELEASE_CERTIFICATION.md`).

---

## 7. Root causes that were *rejected*

* **"One root cause explains hundreds."** Not used: the largest single rule closes 1 483 *prose* occurrences,
  each individually verified to sit inside a comment or docstring — a precision fix, not a semantic umbrella.
* **"The line moved, so it is fixed."** Not used: carried records require the file hash to still match, and a
  record whose file changed is re-adjudicated (that is how the 2 837 inherited open items came to change state).
* **"The suite is green, so it is correct."** Not used: the suite is green *and* 371 HIGH items are open by our
  own criteria; both facts are in the same documents.
* **"A magic number fixes a clamp."** Not used: the widget bound is the validator's documented domain range, and
  the sentinel is explicit.
