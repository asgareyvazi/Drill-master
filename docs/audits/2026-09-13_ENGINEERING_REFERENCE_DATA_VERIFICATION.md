# Engineering Reference-Data Architecture — Independent Verification + Repair

**Date:** 2026-09-13
**Branch:** `arena/01a085e0-drill-master`
**Nature:** forensic continuation. The prior agent's report was treated as
untrusted claims and independently verified against the repository.

---

## A. Repository identity

| Item | Value |
|---|---|
| Path | `/home/user/Drill-master` |
| Remote | `github.com/asgareyvazi/Drill-master.git` |
| Branch | `arena/01a085e0-drill-master` |
| HEAD at start of this session | `b05ea76` (grafted base — **session reset**) |
| Recovered HEAD | `7a662c2` (verified as the true remote tip via `git ls-remote`) |
| Parent of `7a662c2` | `b210cad` |
| Final HEAD | *(this commit)* |
| Working tree | clean except untracked `.github/workflows/` (pre-existing) |

> **Session-reset note:** the local checkout had been reset to the grafted base
> `b05ea76` and `.venv`/`qt-libs` were absent. Recovery: `git fetch` →
> `git reset --hard 7a662c2` (SHA confirmed against `git ls-remote` first) →
> rebuild venv + headless-Qt stubs. No committed work was lost.

## B. Previous-report verification

| Claim | Verdict | Evidence |
|---|---|---|
| No shipped engineering reference/master datasets | **VERIFIED** | Repo-wide search for `*.xlsx/xls/csv/json/db/sqlite/parquet` + domain terms: only DDR templates, test fixtures, one real DDR workbook. No pipe/casing/bit/mud catalog. |
| Optional, absent vendor `DrillPipe.xlsx` | **VERIFIED** | `find / -iname 'DrillPipe*.xlsx'` → none. `core/runtime_config.drill_pipe_reference_paths()` only lists candidate paths; W13 shows "reference unavailable". |
| Created `core/engineering/drill_pipe.py` | **VERIFIED** | File present, committed in `7a662c2`, 322 lines. |
| Created `tests/test_drill_pipe_spec.py` | **VERIFIED** | Present, committed, 21 tests. |
| Canonical `DrillPipeSpec`, vendor normalization, provenance, duplicate classification | **VERIFIED (present) but PARTIALLY CORRECT** | Classes/functions exist and are coherent; however the normalizer had real safety defects (below). |
| `to_component()` connects to the Torque/Drag engine | **PARTIALLY VERIFIED — TEST-ONLY** | `to_component` produces the correct engine contract and the GT test passes, but **no production code constructs `DrillPipeSpec`**. `grep` shows the only non-test importer is the test itself. It is a *foundation*, not a production integration. |
| `999 passed / 4 skipped` | **VERIFIED** | Independent full run before changes: `999 passed, 4 skipped`. |
| `ruff debt = 5489`, E722=0, F821=0, compileall clean | **VERIFIED** | Reproduced exactly. |
| Remote tip `7a662c2` | **VERIFIED** | `git ls-remote origin` matches. |

**Overall:** the previous report was largely honest (it explicitly called the
handoff test-only and the slice a "foundation"), but the foundation shipped with
production-safety defects that this pass repairs.

## C. Defects found by independent inspection (and repaired)

All three are violations of the mission's explicit safety rules (§7, §8, §33).

1. **Silent conflicting-column resolution (CRITICAL, §7).**
   `from_vendor_row` used a *first-wins* alias lookup. Given a row with
   `OD=5.000` and `OD (in)=5.125` (both mapped aliases of `nominal_od_in`), it
   silently returned `5.0` and **discarded** the conflicting `5.125` — the losing
   column was not even preserved in `extra` (its header matched an alias). The
   mission states such conflicts "must not silently resolve".

2. **Invalid numeric values accepted as engineering facts (§8).**
   `OD=0`, `OD=-1`, `OD=inf`, and the overflow string `"1e400"` (→ `inf`) all
   passed through to become identity-forming values. A drill pipe cannot have a
   non-positive or non-finite diameter/weight. The engine's own validation does
   not guard per-component OD, so the spec is the correct boundary.

3. **Collapsed data states (§8).** Unknown, invalid, and conflicting were not
   distinguished — everything silently became `None` or a wrong number.

### Repair
- Replaced first-wins lookup with `_present_matches` (collects **all** matching
  columns). Materially different values → field left `None` + a
  `CONFLICTING_SOURCE` issue that **preserves both raw values**; agreeing
  duplicate columns are not a conflict.
- Added domain validation: non-positive / non-finite (NaN, inf, overflow) and
  booleans are rejected to `None` with a distinct `INVALID_VALUE` issue.
- Unknown sentinels (`""`, `nan`, `n/a`, `unknown`, `null`, `-`, …) stay `None`
  with **no** issue — unknown is explicitly not invalid.
- Added an immutable `SpecIssue` record and a `DrillPipeSpec.issues` tuple
  (serialized in `as_dict`), so problems are surfaced for audit/manual
  resolution, never silently resolved. A conflict in one field does not corrupt
  other fields.

These states are now distinct: **unknown ≠ invalid ≠ conflicting ≠ zero**.

## D. Engineering data inventory (independently reconstructed)

| Domain | Existing source | Existing model | Calculator | UI | Persistence | Canonical spec justified now? |
|---|---|---|---|---|---|---|
| Drill Pipe | absent optional vendor Excel (viewer) | `DrillPipeSpec` (master, this module) | T&D/weight (`weight,od,id,length`) | W13 read-only viewer; **w5 operational inventory editor** | w5 → `equipment_logs` (well/report-scoped) | Foundation yes; persistence blocked (no dataset) |
| Casing | none | `CasingReport` (operational) | `CasingEngine` (manual `yield_psi`) | W13 manual | `casing_reports` | No — no dataset, manual inputs suffice |
| Bit | none | `BitReport` JSON blob | `BitPerformanceEngine` | W13/W3 | `bit_reports` | No |
| Mud | none | `MudReport` | `MudVolumeEngine` | W13/W3 | `mud_reports` | No |
| BHA | none | `BHAReport` JSON blob | T&D/hydraulics | schematic | `bha_reports` | No — future normalization path only |

**New finding the prior audit missed:** `tabs/w5_Equipment_Widget.py`
(`EquipmentWidget`, mounted in `main_window.py`) has a **DrillPipeTab** with
columns *Size & Weight / Connection / ID / Grade / TJ OD-ID / Length / Quantity
/ Condition / Last Inspection / Remarks*, persisted via `save_drill_pipe` →
`save_all_data` → `equipment_logs` keyed by `well_id`+`report_id`. This is
**operational inventory** (has Quantity / Condition / Last Inspection), correctly
*separate* from the reference `DrillPipeSpec`. It reinforces the
reference-vs-operational boundary (§19) rather than contradicting it.

## E. Persistence architecture (for §18)

Every table in `core/database.py` is project/well/report-scoped operational data
(`Well`, `Section`, `DailyReport`, `*Report`, `EquipmentLog`, …). There is **no
global/reference-scoped table**. A reference catalog would therefore require a
new global scope — a real architectural decision that must not be forced without
an actual source-of-truth dataset. **Deferred, not omitted.**

## F. Unit integrity (independently recomputed)

- `UnitManager.convert(19.5, "weight", "ppf", "klbf")` → **0.0195** — confirms
  `ppf` (a linear weight, lb/ft) is treated numerically only, NOT as a physical
  linear density. The spec correctly isolates this by keeping nominal weight in
  ppf and never converting it. **Correct and now covered by tests.**
- `convert(127, "diameter", "mm", "in")` → **5.0**; `25.4 mm` → **1.0**. Diameter
  conversion is physically correct and used by the spec.
- Buoyed weight, hand-recomputed: BF = 1 − 10/65.5 = 0.847328;
  10000 × 19.5 × BF / 1000 = **165.229 klbf** — matches the engine and the GT
  test.

## G. Maturity classification (§27) — evidence-based

| Level | Status |
|---|---|
| FOUNDATION (canonical representation exists) | ✅ present, now safety-hardened |
| INTEGRATION (production code consumes it) | ❌ none — test-only |
| PERSISTENCE (store/retrieve canonical data) | ❌ no global scope, no dataset |
| SELECTION (users pick canonical records) | ❌ |
| IMPORT (real vendor data enters safely) | ❌ blocked on a real dataset |
| GOVERNANCE (revision/approval lifecycle) | 🟡 provenance + issues only |

## H. Decision (§28) and why

**Outcome A — the foundation was not production-ready; repair it.** Chosen over
"add integration" or "add persistence/UI/import" because:
- No source-of-truth dataset exists → persistence/import/UI would be an empty
  shell and would risk fabricating data (forbidden).
- The foundation had genuine correctness defects (silent conflict resolution,
  invalid-value acceptance) that must be fixed *before* anything consumes it.
- The repair is minimal, reuses `UnitManager`, adds no new infrastructure, and
  changes no engine, DB, or UI.

## I. Files changed

| File | Why | What |
|---|---|---|
| `core/engineering/drill_pipe.py` | Close §7/§8/§33 safety defects | `_present_matches` (all-candidates, conflict-aware); `_to_number` with finite+domain guards; `SpecIssue` + `issues`; conflict/invalid/unknown made distinct states; `as_dict` serializes issues |
| `tests/test_drill_pipe_spec.py` | Prove the repair | +10 adversarial tests (conflict, agreeing-dup, text conflict, zero/negative/inf/overflow invalid, unknown-not-invalid, bool, isolation, serialization) |
| `docs/audits/2026-09-13_ENGINEERING_REFERENCE_DATA_VERIFICATION.md` | This report | verification + repair record |

No engine formula, `core/database.py`, `UnitManager`, or UI code was modified.

## J. Verification

- Baseline (before changes): `999 passed, 4 skipped`; E722=0; F821=0; debt 5489;
  compileall clean.
- `tests/test_drill_pipe_spec.py`: 21 → **31 passed**.
- Final gates: E722=0; F821=0; ruff debt **5489** (no increase); new files clean;
  compileall clean.
- Full regression: **1009 passed, 4 skipped** (999 baseline + 10 new tests; no
  regression, no removed/skipped/xfailed tests).

## K. Recommended next step (one)

Obtain a **real, licensed drill-pipe source-of-truth dataset** (committed
reference table or an explicit company standard). Only then: add a
global-scoped reference persistence path keyed by `DrillPipeSpec.identity_key`
that consumes `from_vendor_row` output, surfaces `issues` in an import summary
(rows read/accepted/rejected-invalid/conflicting/duplicate/inserted/updated),
and never overwrites silently. Do **not** build persistence, import UI, or a
Database Center until that dataset exists — the current evidence does not justify
them.
