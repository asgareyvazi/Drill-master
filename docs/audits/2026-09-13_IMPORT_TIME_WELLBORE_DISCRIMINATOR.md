# Import-Time Canonical Wellbore/Section Discriminator — Forensic Pass

**Date:** 2026-09-13
**Branch:** `arena/01a085e0-drill-master`
**Baseline commit:** `7db7189` (prior "Scope Identity Attribution" pass)

This pass completes the *import-time* half of the deterministic
Well → Wellbore → Section scope-attribution architecture introduced at
`7db7189`. The prior pass built the read-side authority
(`core/scope_attribution.py`) that classifies existing reports as
ALREADY / RESOLVED / AMBIGUOUS / UNRESOLVED / INVALID. This pass asks the
upstream question: **does the import pipeline ever receive a canonical wellbore
discriminator from the source, and if not, where is the gap?**

The repository, executed code, tests, schema, and real fixtures are the only
sources of truth. No prior report, comment, or audit doc was trusted.

---

## A. Identity model (as enforced by code)

- **Well** identity = `(project_id, name/code)` — `Well` row.
- **Wellbore** identity = `(well_id, name)` via
  `DatabaseManager.get_or_create_wellbore` (`core/database.py`). A **sidetrack**
  is a *distinct* `Wellbore` under the *same* `Well` (never a new Well, never
  merged into its parent). `wellbore_type ∈ {original, sidetrack}`.
- **Section** identity is scoped to its *wellbore*, not just its well: the same
  section name (e.g. `8-1/2"`) can legitimately exist under both an original
  bore and a sidetrack and is a **distinct** Section in each.
- **DailyReport** carries `well_id` (always), `section_id`, and `wellbore_id`
  (NULL when the source did not name a bore). `DrillingParameters` /
  `TimeLog24H` have no scope columns — they inherit scope through
  `report_id → DailyReport`, so attributing the DailyReport is the lever for all
  longitudinal wellbore KPIs.

Canonical wellbore identity is independent of rig, date, report number,
filename, operator, and session.

---

## B. Baseline vs. final gates

| Gate | Baseline (`7db7189`) | Final |
|---|---|---|
| pytest | 960 passed / 4 skipped | **978 passed / 4 skipped** |
| new tests | — | +18 (`tests/test_wellbore_discriminator_import.py`) |
| ruff E722 | 0 | 0 |
| ruff F821 | 0 | 0 |
| ruff total debt | 5489 | **5489** (no increase) |
| `compileall` | clean | clean |

---

## C. Actual root cause (where the discriminator originates / is lost)

**The consumer expected a field the producer could never supply.**

- `core/ddr_import_service.py` (line ~331) reads
  `wi.get("wellbore_name") or wi.get("wellbore")` and, when present, calls
  `get_or_create_wellbore(...)`. The end-to-end wiring
  (`well_info.wellbore_name` → `extracted["well_info"]["wellbore_name"]` →
  `wi["wellbore_name"]` → Wellbore) **already existed**.
- BUT the canonical field registry `core/canonical_schema.py` defined
  `well_info.name`, `well_info.section_name`, `well_info.well_shape`,
  `well_info.well_type`, … and **no `well_info.wellbore_name` field and zero
  wellbore aliases**. `core/profile_import_engine.py` and
  `core/canonical_mapper.py` had **zero** wellbore references.
- Consequence: no extraction/profile/AI path could ever legitimately populate
  `wellbore_name`. The discriminator was structurally impossible to capture,
  so `wellbore_id` was always NULL and every report deferred to
  UNRESOLVED/AMBIGUOUS — regardless of what a source contained.

**Why the previous pass correctly "refused to guess":** it operated only on
already-persisted rows, where the discriminator had already been dropped at
import. Refusing to fabricate a bore from rig/date/well-name was the correct
integrity choice; the missing link was strictly *upstream* — a schema field to
receive a genuine discriminator.

---

## D. Does the real source actually contain a discriminator? (§3)

Inspected the real golden workbook `08-DDR OEOC-208 AZNS-207 2024-Oct-22.xlsx`
and its profile `templates/OEOC_DDR_v3.json` directly (openpyxl, all sheets).

Header fields that exist: `Well Name: AZNS-207`, `Well Type: Development`,
`Well Shape: Vertical`, `Hole Section (inch): 17-1/2"`.

**No wellbore / bore / sidetrack discriminator exists in the header.** The only
"side-track" strings are in the *Activity Codes* reference dictionary (a generic
operation glossary), not a field identifying this report's bore. `Well Shape:
Vertical` is a trajectory attribute, not a bore identity.

**Conclusion:** for this real format the source genuinely provides no wellbore
discriminator. Therefore leaving `wellbore_id` NULL (→ UNRESOLVED) is the
**correct** outcome, and no profile mapping was added for OEOC (there is no
anchor to map). The architecture change makes capture possible *when a future
source does* carry the field, without fabricating one where it does not.

---

## E. Attribution proof (source field → normalized → WellboreID → SectionID → DR)

With the new canonical field in place, a source that names a bore now flows
end-to-end (proven in `TestWellboreDiscriminatorFlow`):

```
well_info.wellbore_name = "AZNS-207 ST1" (type "sidetrack")
  -> wi["wellbore_name"]
  -> get_or_create_wellbore(well_id, "AZNS-207 ST1", type="sidetrack")  => Wellbore.id
  -> Section("8-1/2\"", wellbore_id=Wellbore.id)                         => Section.id
  -> DailyReport(wellbore_id=Wellbore.id, section_id=Section.id)
```

Alias recognition is locked in `TestCanonicalRecognition`: `Wellbore Name`,
`Wellbore`, `Well Bore`, `Bore Name`, `Hole Name` all resolve to
`well_info.wellbore_name`, while `Well Name → well_info.name` and
`Hole Section → well_info.section_name` are **not** hijacked.

---

## F. Ambiguity-refusal proof (§7 — the `.first()` hazard, FIXED)

**Defect found:** the Section resolver filtered
`(wellbore_id == known) | (wellbore_id IS NULL)` then took `.first()`. With a
known bore plus multiple candidate sections (bore-owned + NULL same-name), or
two NULL same-name sections under an unknown bore, `.first()` picked one by
**row order** and could adopt/backfill the wrong section.

**Fix** (`core/ddr_import_service.py`, deterministic replacement):

- Known bore → prefer the section **already owned by this bore** (unique). Else
  adopt a NULL-scope same-name section **only when exactly one exists**; two or
  more NULL candidates are ambiguous → create a fresh bore-owned section.
- Unknown bore → match a NULL-scope same-name section **only when unique**; else
  create a new section.
- Backfill of `wellbore_id` onto an adopted NULL section happens **only** in the
  unambiguous single-NULL case, and never overwrites an existing assignment.

Proven in `TestSectionAmbiguitySafety`:
- two NULL same-name sections, unknown bore → **not** adopted (3rd created, all
  stay NULL);
- known sidetrack bore vs a different bore's same-name section → distinct
  section per bore, original never re-owned;
- unique NULL same-name section → safely adopted + backfilled;
- same bore re-import → reuses its own section, no duplicate.

---

## G. Safety proof

- No silent mutation, fuzzy merge, or auto-sidetrack merge.
- No rig/date/report#/well-name/proximity used as identity.
- No arbitrary `.first()` among ambiguous canonical candidates (removed).
- No fabricated bore, section, parent, or kickoff. `parent_wellbore_id` is only
  set when the caller supplies it; nothing invents lineage.
- Missing discriminator → NULL preserved (`unknown ≠ zero ≠ default`).
- Blank/whitespace discriminator → no bore (`_safe_text` guard +
  `TestNoFabrication.test_blank_discriminator_is_not_a_bore`).
- No startup backfill; no test deletion; no xfail hiding; no broad-except.

---

## H. KPI impact

No KPI redesign. KPIs already flow through `DailyReport.wellbore_id` /
`section_id`; unknown/ambiguous reports remain NULL-scoped and are therefore
excluded from per-bore aggregation exactly as before. The change only *enables*
correct per-bore attribution when a source genuinely names the bore — it never
introduces a default or fallback scope.

---

## I. Re-import idempotency

`TestWellboreDiscriminatorFlow.test_re_import_same_named_wellbore_is_idempotent`
and `TestSectionAmbiguitySafety.test_known_bore_reuses_its_own_section` prove a
repeated import with the same discriminator reuses the same Wellbore and Section
(no duplicates). The existing source-fingerprint audit path is unchanged.

---

## J. Production-corpus limitation

There is no production `.db`/`.sqlite` corpus in the repository; all evidence is
from the real golden workbook and synthetic in-memory fixtures. The one real
DDR format available (OEOC) does not carry a wellbore discriminator, so the
end-to-end capture path is proven against synthetic sources that *do* — because
no real fixture exercising a bore-naming format exists to test against.

---

## K. Remaining gaps

- **FIXED:** canonical field gap (discriminator uncapturable); Section
  `.first()` ambiguity hazard.
- **DOCUMENTED / OUT-OF-SCOPE:** the OEOC format has no discriminator — nothing
  to map; correctly stays UNRESOLVED. No DB schema/migration was needed
  (`wellbore_name`/`wellbore_type` are transient extraction fields resolved to
  the existing `wellbore_id` column; no persistence gap). Pre-existing F401
  unused imports in `core/data_quality.py` are unrelated and left untouched.

---

## Files changed

- `core/canonical_schema.py` — added `well_info.wellbore_name` and
  `well_info.wellbore_type` FieldSpecs with wellbore/bore/hole-name aliases.
- `core/ddr_import_service.py` — deterministic Section identity resolution
  (removed the ambiguous `.first()`; unique-candidate adoption only).
- `tests/test_wellbore_discriminator_import.py` — 18 adversarial tests
  (recognition, end-to-end flow, no-fabrication, ambiguity safety, idempotency).
