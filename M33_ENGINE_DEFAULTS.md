# M33 — Engine-default forensics (Part E)

Mission 33 · branch `arena/01a0c945-drill-master` · base commit `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`

Method for every candidate: **claim → source (file:line + sha256) → in-repo contract →
reproduction → classification → action → verification**. No default was replaced by a
different magic number; where a bound was needed it was taken from an existing in-repo
domain statement, and where no domain statement exists the behaviour is to refuse to
truncate rather than to invent a ceiling.

Allowed classes (Part E): `VALID DOMAIN LIMIT` · `NO LIMIT REQUIRED` ·
`SEPARATE VALIDATION CONTRACT` · `BUG` · `UI-ONLY-PRESENTATION-LIMIT`.

| # | Site | Class | Action |
|---|------|-------|--------|
| E-1 | `core/engineering/engines/casing.py` `fax`/`pi or 0.0` | **BUG** (fabricated input echo) | fixed — M33-FIX-02 |
| E-2 | `core/engineering/engines/torque_drag.py:373` `wob = (wob_klbf_value or 0.0) * 1000` | **VALID DOMAIN LIMIT** | none required |
| E-3 | `core/engineering/torque_drag_persistence.py:123` / `:168` `wob_klbf … or 0.0` | **VALID DOMAIN LIMIT** | none required |
| E-4 | `core/data_quality.py` 24 h coverage `float(log.duration or 0)` | **BUG** (missing treated as measured zero) | fixed — M33-FIX-01 |
| E-5 | W3 derived spin boxes inheriting Qt's 99.99 maximum | **BUG** (silent clamp reaching persistence) | fixed — M33-FIX-03 |

---

## E-1 · Casing combined collapse — absent optional loads echoed as measured zeros

**Source (before):** `core/engineering/engines/casing.py` sha256
`caec140b33dc648890cd79719afc19ebebb4f7817dccac110e0e6767807873b6` (clean at M33 Part A, i.e.
this file equalled HEAD `c28bbef`), lines 209–210 and 225–232:

```python
fax = optional_number(axial_tension_lbf, "axial_tension_lbf") or 0.0
pi = optional_number(internal_pressure_psi, "internal_pressure_psi") or 0.0
...
"fyax_psi": round(yp_ax, 1),
"axial_stress_psi": round(sa, 1),
"internal_pressure_psi": pi,
```

**In-repo contract (three independent statements, all pre-existing):**

1. `core/engineering/result.py:104` — `require_number` docstring: *“Reject None/blank.
   Never invent 0 for a missing engineering input.”* The sibling `optional_number`
   (`:119`) exists precisely to return `None` for absent input.
2. `core/engineering/casing_persistence.py:70` — `build_snapshot` docstring: *“`None`
   optional loads are preserved as `None` so reconstruction reproduces the identical call.”*
   The snapshot therefore already records "not supplied" for exactly these two loads.
3. `CasingEngine.evaluate` itself treats `None` as "not supplied": the von Mises check runs
   only `if pi is not None and pe is not None and fax is not None`, the burst/collapse/tension
   safety factors are gated on `if pi/pe/fax is not None and … > 0`, and unsupplied
   temperature/connection ratings produce explicit warnings.

**Reproduction (before, `verify-venv`, Qt-free engine):**

```
CasingEngine.evaluate(od_in=9.625, wall_in=0.472, id_in=8.681, yield_psi=80000)   # no loads
  -> governing_collapse=4754.0  axial_stress=0.0  fyax=80000.0  pi_echo=0.0   warnings=4
CasingEngine.evaluate(<same>, axial_tension_lbf=0, internal_pressure_psi=0)       # explicit 0
  -> governing_collapse=4754.0  axial_stress=0.0  fyax=80000.0  pi_echo=0.0   warnings=4
```

The two are indistinguishable in the returned `values`, and `tabs/w13_Engineering_Calculator.py`
rendered the first as `"4754 psi  fyax=80,000 psi"` — an input the engineer never entered —
while `w13._csg_calc_strength` caches `result_values = r.values` and
`core/repositories/casing_repository.py` persists it. The W13 field is labelled
**"Axial tension (opt)"** and `_csg_calc_strength` maps a zero spin box to `None`
(`axial = self.csg_axial.value() or None`), so "not supplied" is the *designed* state for
this input, not an accident of a library caller.

**Verdict:** the rating numbers were never wrong (with both loads absent the API 5C3
baseline is reproduced exactly: `pc_corr = pc_ax + 0·(…)`, and `fyax(Yp, 0) = Yp`). What was
wrong is the *record*: an absent load was reported as a measured `0.0` stress and a computed
`fyax`, contradicting three in-repo contract statements, and that fabricated pair was
displayed and persisted. **Class: BUG (semantic, reporting) — severity MEDIUM** (safety-adjacent:
the biaxial reduction is presented as applied when no axial load was given).

**Action — M33-FIX-02** (`core/engineering/engines/casing.py`, post-fix sha256
`17eb484b1a0957129ea7e45b7101702b9c9d09b99f9263c6cb7a8c097a30e545`; 29 insertions / 4 deletions
vs HEAD, reviewed hunk-by-hunk):

* `fyax_psi`, `axial_stress_psi`, `internal_pressure_psi` are reported as `None` when the
  corresponding load was not supplied; an explicitly supplied `0` still reports `0.0` / `Yp`.
* `axial_tension_supplied` / `internal_pressure_supplied` booleans make the state explicit in
  the record (booleans are compared exactly by `deep_numeric_diff`).
* Two warnings state the reduction was not applied; `evaluate` now merges `comb.warnings`
  into its own warning list.
* `tabs/w13_Engineering_Calculator.py` (`5b200e73…` → `4fd94858…`) renders
  `"… psi  fyax=n/a (no axial load supplied)"` instead of raising `TypeError`
  (a bare `f"{None:,.0f}"`).
* **No physics change:** `collapse_uncorrected_psi`, `collapse_fyax_psi`,
  `collapse_combined_psi`, regime, D/t and every safety factor are numerically identical
  to before (verified against the pre-fix run for tension / compression / Pi cases).

**Verification:** `tests/test_casing_absent_load_semantics.py` (5 tests, Qt-free) +
`tests/test_casing_absent_load_widget_smoke.py` (1 subprocess-isolated widget test) — 6 passed;
casing/persistence/release-gate suite re-run: 81 passed. Mutants `E-CASING-ECHO`,
`E-CASING-WARN`, `E-W13-FORMAT` → killed (3/3).

**Known consequence (honest, not a regression):** a run saved *before* this fix without an
axial/internal-pressure load stored the fabricated `0.0`/`80000.0` values. Re-verifying such a
row now legitimately reports `DIFFERENT` on exactly those three keys — `deep_numeric_diff`
treats `0.0` vs `None` as a divergence. That is the honest report of a semantic change; no
stored row was rewritten and no backfill was performed (unsolicited backfill is forbidden).

---

## E-2 · T&D `wob_klbf` default 0.0 in the engine

**Source:** `core/engineering/engines/torque_drag.py:335/356` `wob_klbf: float = 0.0`,
line 373 `wob = (wob_klbf_value or 0.0) * 1000.0  # lbf`.

**Contract:** the default is *declared in the public engine signature itself* — the engine's
own statement that "no WOB supplied" means "no weight on bit applied". The value is validated
(`if wob_klbf_value is not None and wob_klbf_value < 0: raise EngineeringError`), so negative
is rejected while zero is a legal, physically meaningful operating state (bit off bottom →
pure string drag; the four modes pickup/slack-off/rotating/sliding are computed with zero bit
load). The result does **not** echo any WOB input as a measured value (only
`friction_factor`, `mud_density`, `buoyancy_factor` are echoed), so no fabricated input can
reach the record. The only application caller is
`tabs/w13_Engineering_Calculator.py:2676 wob_klbf=self.wt_wob.value()` — a spin box that
always yields a number, never `None`.

**Reproduction:** `TorqueDragEngine.calculate(...)` with `wob_klbf` omitted and with
`wob_klbf=0.0` produce identical `values` (checked directly; both integrate with
`wob_lbf = 0.0`).

**Class: VALID DOMAIN LIMIT / NO LIMIT REQUIRED.** Zero weight on bit is a real domain state,
the default is declared by the engine's own signature, negative input is rejected and nothing
in the result claims an input that was not supplied. No change made — a change here would be
a speculative redesign of the engine's public signature.

---

## E-3 · T&D historical snapshot `wob_klbf` canonicalisation

**Source:** `core/engineering/torque_drag_persistence.py:123`
`"wob_klbf": _clean_number(wob_klbf) or 0.0` and `:168`
`"wob_klbf": params.get("wob_klbf", 0.0) or 0.0`.

**Contract:** the module docstring and `docs/audits/2026-09-13_CALCULATION_PERSISTENCE.md`
(§G, §"Input-completeness matrix") define the snapshot as the *exact engine arguments* and
name the runtime source of `wob_klbf` as the `wt_wob` spin box — always a number. The value
coerced here is the value the engine itself would use (`wob_klbf: float = 0.0`), and
`snapshot_to_engine_args` hands it straight back to that engine, so reconstruction is
byte-for-byte the call that produced the run. Contrast `wellbore_id_in`, where `None` is
*meaningful* (skip the buckling check) and the same code correctly preserves `None`, and the
component numerics, where `None` is omitted.

**Reproduction:** `build_snapshot(wob_klbf=None, …)` stores `0.0`;
`snapshot_to_engine_args(...)["wob_klbf"] == 0.0`; re-running the stored snapshot reproduces
the stored result exactly (`MATCH`).

**Class: VALID DOMAIN LIMIT.** The T&D engine declares no "unknown WOB" state, so coercing to
its own declared default cannot change a result and cannot misreport an input (the engine
never echoes WOB). Severity if treated as an inconsistency: LOW — recorded in
`M33_ROOT_CAUSES.md` as an accepted design consequence, not as an open defect. No change made.

---

## E-4 · Data-quality 24 h coverage — missing duration counted as zero hours

**Source (before):** `core/data_quality.py` (clean at Part A; HEAD sha256
`9ebc926f31d99e2b161083b1e55405621cca0a9875cebe51bb142a386df8e562`), coverage metric
`hours = sum(float(log.duration or 0) for log in logs)` with
`min(100, hours / 24 * 100) if hours else 0.0`.

**Contract:** the mission's own zero-semantics rule and this module's purpose ("data quality")
require that an *unrecorded* duration is not a measured zero; a single missing duration made
the day look like a real 12 h (or 0 h) coverage figure, and `summary()` averaged that
fabricated number into the score.

**Class: BUG** (a missing measurement presented as a measured value). **Fixed — M33-FIX-01**
(`core/data_quality.py` post-fix `0151a92768ec15d1d26c3e81890c5cd2aad2479b12b97b3c00d2eff92a7ba9cc`):
coverage returns `value=None`, `status="unknown"`, `confidence=0.0` with
`{total_hours: None, unrecorded_entries, recorded_entries, entries}` as soon as one
`TimeLog24H.duration is None` (a recorded `0.0` stays a measured zero); `summary()` excludes
unknown metrics from the score and reports `score=None` + `status="unknown"` when nothing is
known, plus `unknown_metrics` and `confidence` (= known/total); `dashboard_kpis` averages only
known metrics. `QualityMetric.value` is now `Optional[float]`.
**Verification:** 4 S29 tests in `tests/test_m31_scenarios.py` + the
`test_m29_release_closure.py` / `test_m31_scenarios.py` suites, all green; mutants
`R-CODEHOURS` and the coverage-family controls killed.

---

## E-5 · W3 derived-value spin boxes inheriting Qt's 99.99 maximum

**Source:** `tabs/w3_drilling_report.py` (pre-fix M33 Part-A sha256
`fd6eca6ceac069775a800a52b89cd267c91f729f1847d54d96c74c00ac4a40c0`):

```python
def _calc_spin(spin):
    spin.setMinimum(-1); spin.setSpecialValueText("Not computed"); spin.setValue(-1)
def _set_calc(spin, value):
    spin.setValue(spin.minimum() if value is None else value)
```

`self.avg_rop = _calc_spin(QDoubleSpinBox())` never sets a maximum, so the widget keeps Qt's
**default `QDoubleSpinBox` maximum of 99.99**, and `setValue` **silently clamps**.

**Who set 99.99 / why:** nobody — it is Qt's `QDoubleSpinBox` default. It was never a domain
decision; it became effective only because this read-only derived display was built with a bare
`QDoubleSpinBox()`.

**Engineering range / domain contract (found in-repo, not invented):**
`core/validators.py:213` — `DrillingParamsValidator` validates the persisted report with
`("avg_rop", 0, 500)` (and warns "outside range (0-500) - verify unit"); the same bound is used
by the W13 ROP inputs (`self.bit_rop = self._make_dspin(30, 0, 500, 1, " ft/hr")`). So
0–500 m/hr is this repository's stated domain range for `avg_rop`.

**UI vs persistence (why this is not a presentation-only limit):** the widget is read-only but
it *is* the source of the payload — `collect_data()` reads `_calc_value(self.avg_rop)`, and
`load_from_dict` writes a stored value back through `_set_calc`. The clamp therefore reaches
the database in both directions.

**Reproduction (before, verbatim from the reinstated pre-fix source):**

```
tests/test_m31_scenarios.py::test_derived_avg_rop_display_is_not_silently_clamped
E  AssertionError: derived ROP was truncated to 99.99 (engine returned 150.0)
E  assert 99.99 == 150.0 ± 1.5e-04
tests/test_m31_scenarios.py::test_calc_spin_domain_maximum_is_explicit
E  AssertionError: avg_rop's domain bound must reach the widget
E  assert 99.99 == 500
```

(`DrillingManager.calculate_rop(1000.0, 1150.0, 1.0)` = 150.0 m/hr — a legal value per the
validator — displayed and persisted as 99.99; a stored 150 came back as 99.99 on reload and
would be re-saved as 99.99.)

**Class: BUG** (silent truncation of a computed, domain-legal value, propagated to
persistence) — severity HIGH for data integrity, because the number written to the report is
not the number the engine produced.

**Action — M33-FIX-03** (`tabs/w3_drilling_report.py` post-fix
`e2764c18e975670539ef409b5bf931271510191a9581a406a8db8f3dc4e427a0`):

* `_calc_spin(spin, maximum=None)` — the field's documented domain bound is passed explicitly
  at the call site; `avg_rop` now declares **500** (`core/validators.py`, cited in a comment).
  No new constant was introduced: the value is the validator's own range for that field.
* `_set_calc` never truncates silently: if a computed value exceeds the widget's range the
  range is widened to hold the true value, because the widget feeds the persisted payload and
  plausibility belongs to the validator (which still warns for values outside 0–500). This
  applies to TFA/HSI, which have no documented bound in this repository — inventing one would
  have been a magic number.
* The special-value sentinel contract (`minimum = -1` ⇔ "Not computed", `_calc_value` returning
  `None`) is unchanged, and the fields remain read-only.

**Verification:** `test_derived_avg_rop_display_is_not_silently_clamped` (ROP 150 inside the
domain, plus a 900 out-of-domain value that must be shown rather than truncated, with the
validator's warning asserted) and `test_calc_spin_domain_maximum_is_explicit` (the call-site
bound and the Qt default fallback) in `tests/test_m31_scenarios.py` — green;
`tests/test_m31_scenarios.py` + `test_m29_release_closure.py` + `test_m30_semantic_regressions.py`
(219 tests) green; mutants `E-W3-CLAMP-MAX`, `E-W3-CLAMP-GUARD`, `E-W3-CLAMP-BOUND` → killed.

---

## Mutation-control status (Part E additions)

`docs/audits/m33-evidence/m33-mutation-controls.json`: **24/24 killed, 0 survivors**, every
mutated file restored byte-identically (sha256 self-check before/after the whole run). The
Part-E block contains the six mutants above plus the `E-W3-CLAMP-BOUND` re-run that was added
after the first pass left one survivor (a real coverage gap: the call-site domain bound was
unasserted) — the survivor is recorded in the JSON, not hidden.
