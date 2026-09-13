# DrillPipe Reference Catalog Operationalization + Provenance Visibility

Date: 2026-09-13
Branch: `arena/01a085e0-drill-master`
Commit under audit (baseline): `8042063`

This slice makes the persisted DrillPipe reference catalog **operationally
discoverable** — browse, search, inspect details + provenance — through the
existing Reference-Tables tab (w15), and documents the mandatory forensics. It
follows the prior vertical slice (`8042063`: vendor Excel → persisted catalog →
Quick Select → engine).

---

## A. EXECUTIVE VERDICT

**CERTIFIED WITH DOCUMENTED DEBT.**

The largest *unblocked* production gap — the catalog was persisted but had no
operational discovery/management UI — is now closed: an authoritative,
searchable catalog view with full per-record provenance lives in w15, reusing
existing infrastructure and the canonical helpers. Calculation→reference
traceability (the other candidate scope) is **architecturally blocked** because
the app has **no calculation-result persistence at all** (`W13.save_data()` is a
no-op); building that subsystem now is a §46 STOP condition and is deferred with
evidence, not silently skipped.

## B. REPOSITORY IDENTITY

- Branch: `arena/01a085e0-drill-master`
- Baseline HEAD: `8042063` (== remote tip, confirmed via `git ls-remote`)
- Parent chain: `8042063`←`aa84a35`←`0e0af51`←`1557a08`←`2b72ed7`←`7a662c2`
- A **session reset** occurred at the start of this task (local HEAD had
  reverted to `b05ea76` with a stale mixed tree); recovered with
  `git fetch` + `git reset --hard 8042063`, env rebuilt (`.venv` py3.11.2 +
  `qt-libs` stubs). Tree clean apart from untracked `.github/workflows/`.

## C. PREVIOUS REPORT VERIFICATION

| Claim | Verdict | Evidence |
|---|---|---|
| Import pipeline exists (`parse_workbook`→`from_vendor_row`→`import_specs`→`drill_pipe_specs`→Quick Select→engine) | **VERIFIED** | code inspection + runtime end-to-end (165.23 klbf) |
| Shipped at `8042063`, prev tip `aa84a35` | **VERIFIED** | `git diff --stat aa84a35 8042063` = exactly the 4 slice files |
| "No proper catalog management UI beyond import" | **VERIFIED** | repo exposes only `get_by_identity/get_spec/all/count`; no browse/search/detail UI existed |
| "Calc results don't record which reference produced inputs" | **VERIFIED (and deeper)** | there is **no calculation persistence at all** — `W13.save_data()` → `return True`; no result table |
| "New DB columns require explicit migration" | **VERIFIED** | `_apply_safe_schema_upgrades` auto-creates missing *tables*; new *columns* need the explicit `upgrades` list |
| "Unicode NFC absent" | **VERIFIED** | `_norm_header` folds case + collapses whitespace, no `unicodedata.normalize` |
| "Legacy cleanup found no deletions meeting the bar" | **VERIFIED** | re-audited independently; still no safe deletion (see F) |
| Added lint debt limited to `F405` from `import *` | **VERIFIED** | prior + this slice's new lint findings are all F403/F405 |

## D. CURRENT ARCHITECTURE (actual)

```
vendor .xlsx
  → core.engineering.drill_pipe_import.parse_workbook / import_workbook
  → DrillPipeSpec.from_vendor_row            (canonical normalize/validate/issues)
  → DrillPipeReferenceRepository.import_specs (tx-safe upsert, NEW/UNCHANGED/…)
  → drill_pipe_specs table (payload_json = lossless spec; columns = queryable)
  → repo.all()  ── deterministic engineering order
       ├─► dialogs.engineering_dialogs.build_reference_choices → AddPipeDialog
       │     Quick Select (◆) → reference_component_fields → wt_pipes
       │     → TorqueDragEngine  (165.23 klbf)
       └─► core.engineering.drill_pipe_catalog_view (NEW, Qt-free)
             → tabs/w15 Reference → Drill Pipe → ◆ Vendor Catalog
               browse · search/filter · details+provenance
```

## E. SOURCE-OF-TRUTH MATRIX

| Source | Actual role | Authoritative? | Production consumer | Action |
|---|---|---|---|---|
| `drill_pipe_specs` (persisted repo) | Vendor/company reference catalog | **YES** | Quick Select + new w15 catalog view | Operationalized (browse/search/detail) |
| `PIPE_DB` (W13) | Built-in generic nominal presets | No (fallback) | Quick Select (additive) | Kept; distinct namespace |
| `w15 _create_drillpipe_tab` static API 5DP table | Hard-coded nominal reference display | No | w15 display only | Relabeled "◇ Standard Presets"; kept as display |
| `DrillPipe.xlsx` W13 viewer (`_drill_pipe_df`) | Display-only vendor-sheet preview | No | W13 viewer tab | Unchanged (already relabeled) |

There remain **four** DrillPipe data surfaces, but only ONE is authoritative and
feeds calculations; the other three are clearly-labelled display/fallback and
disjoint from the calc path. No new competing source was introduced.

## F. DEAD / DUPLICATE / LEGACY FORENSICS

| Item | Classification | Evidence | Consumers | Replacement | Safe to remove | Action |
|---|---|---|---|---|---|---|
| Abandoned import/catalog attempts | **NONE** | `git log --all` is a clean linear chain; no reverted/superseded impl | — | — | — | Nothing to remove |
| Other Excel parsers (`ddr_import_service`, `profile_import_engine`, `import_router`, `mineru_engine`, `common_widgets`) | ACTIVE, different domain | Each parses DDR/profile/cost/document data, not DrillPipe | their own flows | — | No | Left untouched (not duplicates) |
| `core/excel_normalizer.py` | ACTIVE, reusable | DDR merged-cell cleaner | DDR import | — | No | Not needed for this slice |
| w15 static API 5DP DrillPipe table | LEGACY-BUT-REQUIRED (display) | hard-coded nominal data, no calc/repo consumer | w15 display | (persisted catalog is the authoritative one) | No | Relabelled ◇ Standard Presets, kept |
| `_create_drillpipe_tab` structure | REFACTORED (not removed) | replaced single static grid with sub-tabs (Vendor Catalog + Presets) | w15 | — | n/a | Extended in place |

**Result: no safe deletions identified.** The audit was performed; every
suspicious surface has an active display/fallback consumer or is a different
domain. Deletion bar (§40) not met for any item.

## G. BRANCH HYGIENE

Local branches: only `arena/01a085e0-drill-master` (the session branch).
`git branch -a` shows no stale local branches to classify. Remote branch
enumeration/deletion is out of scope and not performed (session is fixed to this
branch; deleting other Arena branches is not safe without owner review).
**No branch deletions performed.**

## H. CATALOG MANAGEMENT (delivered)

In **w15 → 🔩 Drill Pipe → ◆ Vendor Catalog**:

- **Browse** — every persisted spec with identity, deterministic order, columns:
  Manufacturer, Model, OD, ID, Weight, Grade, Connection, Source, Status.
- **Search/filter** — canonical (case-fold + whitespace-collapse) substring over
  all visible fields + fingerprint; reuses `_norm_header` (no 2nd normalizer).
- **Details / Provenance** — read-only dialog grouped Identity / Engineering /
  Provenance / Issues, showing source file+sheet, import row note, unmapped
  vendor columns, and any normalization issues. Exposes the **engineering
  fingerprint**, never a raw DB primary key (§8).
- **Refresh** — manual button + auto-refresh after a successful W13 import
  (loose, duck-typed sibling-tab call; no-op if absent).
- **Distinction (§21)** — ◆ Vendor Catalog vs ◇ Standard Presets sub-tabs;
  nominal presets never masquerade as vendor-certified records.
- **Empty / no-DB states** — explanatory messages, never a crash.

**Lifecycle / delete / edit were intentionally NOT added.** The schema has no
lifecycle state machine and no revision model; editing identity-forming fields
would change engineering identity (§13), and destructive delete of authoritative
reference data is unsafe without an approval/revision model the product does not
have. Documented as a product decision (§O), not silently skipped.

## I. IMPORT PIPELINE

Unchanged from `8042063` (verified still correct). The import button remains in
W13 (§10: not moved — that is the existing convention and the calc tab is where a
user assembles a string); it now triggers a best-effort catalog-view refresh.

## J. TRACEABILITY

**Audited, deferred with cause (§17, §46).** The app persists **no calculation
results** — `W13.save_data()` returns `True`; there is no T&D/weight result
table. You cannot attach a reference id to a persisted calculation that does not
exist. Building calculation persistence is a large, separate subsystem and a
§46 STOP condition ("calculation persistence architecture is insufficient for
safe traceability"). The catalog view *does* surface the durable engineering
identity fingerprint, which is the correct future foreign key when calc
persistence is built. No speculative traceability framework was added.

## K. DATABASE / MIGRATION

**No schema change in this slice.** The catalog view is read-only over the
existing `drill_pipe_specs` table (created by the existing auto-migration for
new Base tables). Fresh-DB init and existing-DB upgrade both already create the
table; no new column/migration was needed, so no migration risk was introduced.

## L. TEST EVIDENCE

Commands (headless Qt env sourced, `.venv`):

- `pytest tests/test_drill_pipe_catalog_view.py` → **8 passed**
- `pytest tests/test_drill_pipe_catalog_widget_smoke.py` → **1 passed**
  (subprocess-isolated real-widget smoke; avoids the shared-process Qt abort)
- All DrillPipe tests together (spec/repo/selection/import/catalog/smoke) →
  **79 passed**, no segfault
- Full suite `pytest -q` → **exit 0**, 1059 tests collected
  (was 1050 at `8042063`; +8 catalog-view, +1 subprocess smoke), no Qt abort
- `compileall core dialogs tabs tests` → clean
- `ruff --select E722,F821` → **0**
- Lint debt 5496 → 5523 (+27), all F403/F405 from the files' existing
  `from PySide6.QtWidgets import *` convention; new standalone modules pass ruff.

## M. ENGINEERING GROUND TRUTH

```
OD = 5.000 in, nominal weight = 19.5 ppf, MD 3048 m, MW 10 ppg, ff 0.3
manual input           → 165.23 klbf
catalog-selected input → 165.23 klbf   (MATCH)
```

The catalog view is observational; it does not alter numerical results.

## N. DEPENDENCY AUDIT

**No new dependency.** Uses stdlib + existing `PySide6` + existing canonical
helpers + `openpyxl` (already present). No seaborn/plotly/sklearn/etc.

## O. REMAINING DEBT

- **BLOCKER:** none.
- **PRODUCTION DEBT:** calculation-result persistence does not exist → no
  calc→reference traceability yet (largest remaining item; needs a result table
  + save path before a reference FK can be attached).
- **PRODUCT DECISION:** catalog lifecycle (active/retired) and edit/delete of
  authoritative references — needs a lifecycle/revision model the domain does
  not yet define; identity-forming edits must create a new record, not mutate.
- **DOCUMENTATION DEBT:** the systemic hard-coded reference pattern (§24)
  recurs across casing/collars/connections/bit/cement/mud in w15 — a future
  consolidation candidate, deliberately NOT abstracted now (§39: no proven
  multi-consumer need).
- **THEORETICAL / LOW-RISK:** Unicode NFC still absent — harmless for ASCII API
  designations; fix only if non-NFC vendor input is demonstrated.

## P. GIT EVIDENCE

See commit created by this task (SHA recorded in the session). Files changed:
`core/engineering/drill_pipe_catalog_view.py` (new),
`tabs/w15_Reference_Tables.py` (catalog sub-tab + view logic),
`tabs/w13_Engineering_Calculator.py` (post-import refresh hook),
`tests/test_drill_pipe_catalog_view.py` (new),
`tests/test_drill_pipe_catalog_widget_smoke.py` (new),
this document.

## Q. FINAL DECISION

**PROCEED WITH DEBT.** The single most important reason: the authoritative
catalog is now operationally discoverable with full provenance through existing
app architecture, with no new source-of-truth, no new dependency, and ground
truth preserved — while the one genuinely larger item (calc traceability) is
correctly identified as blocked by the absence of calculation persistence and
deferred rather than faked.
