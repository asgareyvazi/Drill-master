# M201–M230 – Advanced integrity, engineering completion, data provenance and product qualification

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**

| Item | Value |
|---|---|
| Repository / branch | `asgareyvazi/Drill-master` / `arena/72010272-drill-master` (the only branch written) |
| Mission base | `a38c54c` (M171–M200 report) |
| Code commits | `3497a91` (M203–M207, M221, M224) · `c47a791` (M208/M209, M213, M214) · `da53eb6` (M215) · `ac81b04` (M213 residual, M216–M218) · `b67d4e1` (D70, M210 test, M215 extras, catalogue) · `50e6b03` (M220/D72, M223, M227, M229, D71 residual) · `9f784a8` (D73, M184 doc) · `63780a6` (M210 killing tests, D75, D74 row) · `39b4d52` (D74 instrumentation) · `a2a0201` (M210 test for `CON-unsupported-claimed`, full mutation evidence of `39b4d52`) · **final code `2764071`** (D76 test fix). Product code is identical from `63780a6` to `2764071`: the last three commits change tests and documentation only |
| Report commit | the commit that adds this file (§V) |
| Protected branches | `drill-Master` = `e3fa42a`, every other `arena/*` head unchanged; no tags; no force-push (§V) |

Statuses used: PASS, PARTIAL, OPEN, BLOCKED, OWNER REVIEW REQUIRED, NOT RUN, OBSERVED — NOT REPRODUCED. Every
statement names the code, test, commit, evidence file or CI run behind it. The `08-DDR` workbook and the protected
PDF were never opened, parsed, indexed, copied or scanned; real-DDR acceptance stays **NOT RUN**.

---

## A. Baseline (M201)

- Start: `git fetch`, `git ls-remote origin`: our branch = `a38c54c`; `drill-Master` = `e3fa42a` (holds the
  confidential PDF — not opened); other `arena/*` heads `02dd3e1`, `c7e7697`, `ad7ea0d`, `b05ea76`, `c28bbef`,
  `7f0186e`, `4336ea3`; 0 tags; 1 worktree; 0 stashes. `git status` clean, `git log -1`, `git branch -vv`,
  `git worktree list`, `git stash list` recorded at the start.
- **Sandbox resets: four** (at the start, after `da53eb6`, after `50e6b03`, and after `39b4d52`). Each reset moved
  HEAD back to the graft base `4336ea3` and removed `.venv`, the Qt stub libraries, background processes and `/tmp`;
  the fourth also removed the git-ignored run directory (`htmlcov/`). Each was recovered without discarding work:
  `git fetch`; `git update-ref refs/heads/arena/72010272-drill-master <remote> <stale>` (compare-and-swap);
  `git read-tree HEAD`; `git branch --set-upstream-to`; `git add -N` for new files. The tracked work tree was intact
  each time. The environment was rebuilt from `requirements-lock.txt` plus the CI tool pins (pytest 9.1.1,
  ruff 0.16.6, build 1.6.1, coverage 7.16.2) and `tools/qt_headless_env.sh`.
- The third reset killed the background mutation runs and a full-suite run (§H, §J). The fourth reset removed the
  first no-coverage suite log of `39b4d52` and the first mutation run on it; the suite was repeated and its D74
  evidence from the first run was transcribed verbatim from the printed output
  (`m201-m230-evidence/d74_run1_39b4d52_transcribed.txt`).

## B. Phase status

| Phase | Status | Evidence |
|---|---|---|
| M201 baseline | PASS | §A |
| M202 defect register | PASS | §C–§G, `docs/engineering/PRODUCT_CAPABILITY_MATRIX.md` rows D61 (residual), D66–D76 |
| M203 D61 adversarial | PASS — D61 RESOLVED (residual fixed) | §C |
| M204 write routes | PASS (found and fixed D69, D70) | §C, §T |
| M205 `weight_ppf or 0.0` | PASS (re-trace found and fixed D73) | §D |
| M206 preset provenance | PASS | §E |
| M207 versioned schematic JSON | PASS | §D |
| M208 D63 investigation | OBSERVED — NOT REPRODUCED | §F |
| M209 D51 diagnostics | OPEN | §G |
| M210 old catalogues | **PASS** — all 12 deferred catalogues (570 mutants, not 541 — §H) complete on the final tree: 567 KILLED, 3 SURVIVED by design in m50 and killed in m52; the 9 survivors found during the mission (m46 `L-duplicate-classify`, the 7 of m201_m230, m83_m96 `CON-unsupported-claimed`) killed by new tests; 1 anchor re-anchored for a genuine code move | §H |
| M211 every catalogue | **PASS** — 16 / 16 `complete=True` on `2764071`: 1086 mutants, 1082 KILLED, 1 declared EQUIVALENT, 0 INVALID, 3 SURVIVED (the m50 trio above) | §I |
| M212 full suite, exact SHA | **PARTIAL** — `2764071`: CI 3.11 / 3.12 + coverage / 3.13 green; local 5514 passed, **1 failed (D74**, mechanism identified: memory exhaustion of the 4 GB sandbox; growth not yet attributed), 4 opt-in skips; the local coverage run was OOM-killed (on `39b4d52`), so coverage comes from CI | §J |
| M213 workbook limits | PASS | §K |
| M214 header mapping | PASS (D66) | §K |
| M215 scalar correction | PASS (D67) | §K |
| M216 identity / context switch | PASS (D68) | §K |
| M217 day-by-day + carry-forward | PASS (D71; its fuel / water residual closed as D75) | §K |
| M218 DDR → analysis lineage | PASS (D69) | §K |
| M219 tubular source re-audit | PASS — no new evidence, nothing changed | §M |
| M220 importer hardening | PASS (D72) | §M |
| M221 field provenance | PASS | §L |
| M222 library → engine inputs | PASS | §N |
| M223 library → architecture → cement | PASS | §N |
| M224 versioned defaults | PASS | §L |
| M225 W13 27-leaf re-audit | PASS (9 / 10 / 4 / 1 / 1 / 2 kept) | §O |
| M226 MSE lineage, datum / CRS | PASS (audit); D6 and D11 stay PARTIAL; P10 OWNER REVIEW REQUIRED | §P |
| M227 data-quality workspace | PASS | §Q |
| M228 P1–P19 | OWNER REVIEW REQUIRED (all 19) | §R |
| M229 35-step journey | PASS (and D75 found and fixed) | §S, §K |
| M230 final gates, CI, report | **PARTIAL** — on the final code SHA `2764071`: CI 4 / 4 green (the 3.12 coverage leg after one re-run of a leg cancelled at the 60-minute limit), all 16 mutation catalogues complete, gates pass, hygiene verified; **but** the local final suite still has 1 failure (D74 OPEN). CI on the report SHA: §V | §U, §V |

## C. D61 and the storage write routes (M203, M204)

- **D61 residual, reproduced** (`docs/mission-reports/m201-m230-evidence/d61_replace_probe_before_fix.txt`,
  probe source `d61_replace_probe_source.py.txt`): of 68 adversarial statements against a published tubular set
  and its items — UPDATE, DELETE, INSERT, INSERT OR REPLACE, REPLACE INTO, `ON CONFLICT DO UPDATE`, on the primary
  key and on the unique keys; move to a draft; status back to DRAFT; changed fingerprint; empty and populated set;
  duplicate name + version; app session, raw `sqlite3`, `recursive_triggers` OFF and ON — **18 were accepted**:
  every REPLACE / upsert form deletes the stored row through conflict resolution, which fires delete triggers only
  with `recursive_triggers` ON.
- **Fix (`3497a91`)**: `trg_tubular_{set,item}_noreplace_v1` and `_nodupkey_v1` in `core/storage_guards.py`
  refuse an INSERT whose id or unique key already exists. They do not depend on `recursive_triggers`.
  After the fix **68 / 68 refused** with the pragma OFF and ON (`d61_replace_probe_after_fix.txt`).
  Draft edit / import / publish, next version, snapshots, backup / restore and well deletion unchanged
  (`tests/test_m203_tubular_replace_guards.py`, 11 tests, 4-way parametrized over the connection kinds). The commit
  message of `3497a91` says "D65"; the register files this as the **D61 residual** and no D65 id exists.
- In `63780a6` the attack list gained two statements that only the id guard can refuse — REPLACE on the same id
  with **another** unique key (set name / version; item fingerprint) — and a draft-row variant, after the
  m201_m230 catalogue showed that the id guard was not pinned on its own (mutant `M203-tubular-noreplace`, §H).
- **M204 write-route matrix** (`tests/test_m204_immutable_write_paths.py`, 34 cases): ORM, bulk, Core, raw SQL,
  REPLACE, upsert and cascade writes into published tubular sets / items, `trajectory_view_revisions`, survey and
  architecture revisions, calculation cases, document source links and audit logs. All refused where the record
  is immutable. It found **D69**: `ReportRevision` snapshots could be UPDATEd / REPLACEd by raw SQL, Core
  statements and unenforced sessions (15 of 19 tests failed before; `d69_report_revision_mutable_before_fix.txt`);
  fixed in `ac81b04` by `trg_report_revision_immutable_v1` and `trg_report_revision_noreplace_v1`.
- **Restore / migration / cascade** (`tests/test_m204_restore_migration_cascade.py`, 3): found **D70** — a
  same-version backup without the current guards was restored unguarded
  (`d70_restore_without_current_guards_before_fix.txt`); fixed in `b67d4e1`: `_stage` → `_migrate_staged` →
  `_guard_staged` installs every current guard on the staged copy.
- No cryptographic claim is made: a file writer can still `DROP TRIGGER` (`core/security_posture.NON_CLAIMS`, P13).

## D. Weight None and the versioned schematic (M205, M207)

- **M205**: every consumer of casing `weight_ppf` was traced (W3b render and table, schematic JSON save / load /
  export, architecture `to_schematic` / `from_schematic`, casing inputs, cement, weight). An unknown weight stays
  None in the domain, serialises as `null`, survives save / load / export, and is shown as "not recorded"; a 0 is
  only a drawing placeholder. Explicit weights, including an entered 0, survive. Evidence
  `tests/test_m205_m207_schematic_provenance.py` (14 original tests; 22 collected in `39b4d52`).
- **D73 (found by the M205 re-trace in this mission, fixed in `9f784a8`)**: a schematic casing that asked for
  cement but lacked the cement top or bottom was loaded with the missing end as 0.0 (cement to surface; a liner
  hung at 900 m got cement from 0 m), nothing was reported, and `from_schematic` turned it into an architecture
  cement component (a missing bottom became the shoe depth). Before-fix evidence
  `d73_schematic_missing_cement_interval_before_fix.txt`. Now cement is shown only for a known interval
  (top < bottom), a missing end is reported in `missing` and not drawn, and the architecture never substitutes a
  depth; an entered top of 0 stays 0. 5 tests, 4 of which fail on `50e6b03`; in `63780a6` a test of a schematic
  built in code (as W3b does, without `loads`) was added after the catalogue showed that `from_schematic`'s own
  guard was not pinned (mutant `M205-architecture-cement-guess`, §H).
- **M207**: `drillmaster-schematic-v2` (`core/schematic_document.py`) carries per-casing bindings (set, version,
  fingerprints), field origins and missing values; a tampered binding is dropped and reported; a document of
  another well is refused unless explicitly accepted and is then reported as foreign; legacy files stay readable
  as user values with an unknown weight. The two stale limitations in
  `docs/engineering/M184_M189_REFERENCE_INTEGRATION.md` §3 are marked as superseded.

## E. Preset provenance (M206)

`core/engineering/value_provenance.py` (`legacy-preset-provenance-v1`): `INVENTORY` lists every built-in preset
table and default (`PIPE_DB`, the W3b template, the W13 presets, hard-coded defaults) with its code location.
Operator-visible labels: **`LEGACY_PRESET — SOURCE UNVERIFIED`** (copied preset values, while unchanged) and
**`LEGACY — SOURCE UNKNOWN`** (defaults). A preset value can be replaced from the library; a snapshot keeps the
origin it was made with. `test_a_preset_is_never_reported_as_manufacturer_data`,
`test_add_pipe_and_casing_dialogs_show_and_store_the_preset_label`,
`test_w3b_template_is_labelled_until_replaced_from_the_library`. No preset value, formula or historical result
was changed.

## F. D63 (M208)

`stability_probe_d51_d63.json` (tool `stability_probe_m208`, code `3497a91`, Python 3.11.2, offscreen,
faulthandler on with a 120 s dump timeout): 6 iterations over `test_m132_trajectory_layers.py`,
`test_m178_trajectory_views.py`, `test_trajectory_3d.py`, `test_trajectory_3d_lifecycle_m46.py`; every run exited
0; no signal, no dump. **D63 stays OBSERVED — NOT REPRODUCED.** No retry, timeout increase, SIGSEGV suppression
or exit-139 tolerance was added. No D63 signature appeared in any later full-suite run of this mission.

## G. D51 (M209)

The same probe covered `tests/test_m132_trajectory_layers.py:199` with faulthandler dumps on: no hang in 6 runs,
so no new frame was captured. **D51 stays OPEN**; it is kept separate from D63 (and from D74, §J); no timeout was
raised.

## H. The deferred mutants (M210)

**Reconciliation of "541".** The M171–M200 report (§U) listed "m46 … m101_m120 (541 mutants in 13 catalogues)" as
not re-run. Counting the catalogue files at that report's commit
(`git show a38c54c:tools/quality/mutation_<c>.py | grep -c 'Mutant("'`) gives **12 catalogues and 570 mutants**:
m46 29, m47 26, m48 44, m49 38, m50 55, m51 29, m52 70, m53_m56 38, m61_m67 19, m70_m76 18, m83_m96 20
(= **386**), plus m101_m120 **184**. 541 = 570 − 29, i.e. the old figure left out m46's mutants while counting
its file; the "13" also miscounted. This mission re-ran **all 12 (570 mutants)**.

**Anchors.** Before each run every anchor of every catalogue was checked for exactly one occurrence (1086 mutants
in 16 catalogue files). One older anchor had become ambiguous: `m83_m96` `SG-replace-allowed` matched twice,
because M203 (`3497a91`) added the same `WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id)` clause for the
tubular guards. It was re-anchored in `63780a6` to its original site by including the next line ("a stored record
cannot be replaced") — same mutation, same fault class. No other older catalogue changed in this mission
(`git diff a38c54c..HEAD -- tools/quality/` touches only `mutation_m201_m230.py` and `mutation_m83_m96.py`). Without
the re-anchor the mutant would have been INVALID, which is never counted as killed.

**Runs during the mission.**

| Tree | Catalogues | Outcome |
|---|---|---|
| `50e6b03` | m46 28 / 29 → the survivor `L-duplicate-classify` (a lost race on the unique constraint not reported as duplicate) killed by a deterministic test added in `b67d4e1` (`mutation_m46_L-duplicate-classify_after_test.json`); m47 26 / 26, m48 44 / 44, m49 38 / 38 (all complete) | evidence `mutation_m46.json` … `mutation_m49.json` |
| `50e6b03` | m50 onward | killed by the third sandbox reset — no result |
| `9f784a8` | m201_m230: complete, 51 mutants, **44 killed, 7 survived**; m46 29 / 29 | `mutation_m201_m230_9f784a8_7_survivors.json` |
| `63780a6` | (stopped after the D74 recurrence: the final tree had to change) | — |
| `39b4d52` (first) | m201_m230 and m46 finished, then the run directory was removed by the fourth sandbox reset | — (results lost, not counted) |
| `39b4d52` (second) | **all 16 catalogues, 1086 mutants, 16 / 16 `complete=True`**: 1081 KILLED, 1 declared EQUIVALENT, 0 INVALID, 4 SURVIVED (below) | `m201-m230-evidence/mutation_final_39b4d52/` |
| `a2a0201` | `--only` runs: `CON-unsupported-claimed` KILLED; after the D76 test change the 16 D59 mutants of m121_m140 KILLED (`complete=False` by design of `--only`). An `--only` call with an empty id list started the whole m121_m140 catalogue by mistake; it was stopped by its time limit and is not counted | `mutation_m83_m96_CON-unsupported-claimed_after_test.json`, `mutation_m121_m140_D59_after_d76.json` |
| **`2764071` (final code)** | **all 16 catalogues, 16 / 16 complete** | §I |

**The 7 survivors on `9f784a8`** — each got a test proving the guard it removes (`63780a6`); a partial run of the
7 on the working tree killed 7 / 7, and the full re-run is in §I:

| Mutant | What it removed | Killing test |
|---|---|---|
| `M203-tubular-noreplace` | the id guard of the tubular noreplace trigger | REPLACE on the same id with another set name / version or item fingerprint (`test_m203`) |
| `M213-declared-shape-precheck` | the read-only (declared-dimension) shape check before cells are read | an oversized used range is refused with only the read-only open recorded (`test_m213`) |
| `M214-short-alias-phrase` | the "1–2 character aliases are exact-only" rule | `"Bit OD"`, `"Joint ID"`, `"Pump No 2"` do not match `od` / `id` / `2` (`test_m214`) |
| `M215-claim-reopen` | `claim_review_item` before a reopen | two operators reopening the same item → exactly one REOPENED (`test_m215`) |
| `M215-claim-resolve` | `claim_review_item` before a queue decision | two operators resolving the same continuation → exactly one decision (`test_m215`) |
| `M220-workbook-shape-limit` | the M213 sheet / cell limits in the tubular importer | an over-limit used range is refused and the source is unchanged (`test_m220`) |
| `M205-architecture-cement-guess` | `from_schematic`'s known-interval guard | a schematic built in code with an unknown interval yields no cement component (`test_m205_m207`) |

None was declared equivalent. 4 new mutants `D75-*` were added for D75 (§K); the catalogue now has 55.

**Survivors of the complete run on `39b4d52`** (none declared equivalent):

- `m50` `R-file-name-context-dropped`, `R-absent-ignores-context`, `A-sentence-inherits-any-size` — known since M52:
  `mutation_m50.py` runs M50's own test list, and the M51 / M52 code reaches these behaviours through later gates, so
  the M50 tests no longer observe them. `mutation_m52.py` carries the **byte-identical** anchors and replacements with
  the M52 tests that pin them, and m52 was **70 / 70 KILLED** in the same run (M52 report §7; capability matrix,
  "Mutation (all suites)"). They are counted as SURVIVED in the m50 row and not as killed.
- `m83_m96` `CON-unsupported-claimed` (`core/calculator_contracts.py` `calculator_status` returns "SUPPORTED" instead
  of "NOT_SUPPORTED" for a calculator without a contract) — **new**. It was killed at `c5ea349` (M118 evidence). Since
  M125 (`56d5f6c`) the case-bar label begins with the leaf class — "Class: NOT_SUPPORTED — … Contract status: …" — so
  the M87 check `"NOT_SUPPORTED" in label` was satisfied by the class alone while the contract status said SUPPORTED.
  A genuine test weakness, not an equivalent mutant: the operator-visible status would be wrong. In `a2a0201`
  `tests/test_m87_w13_contracts.py::test_not_supported_calculators_say_so_and_store_unversioned` also asserts
  "Contract status: NOT_SUPPORTED — " in the label and `calculator_status()` == NOT_SUPPORTED for every NOT_SUPPORTED
  leaf; `--only` run: **KILLED** (1 failed, 30 passed; `mutation_m83_m96_CON-unsupported-claimed_after_test.json`).
  No product code changed. With D76 (§U) this is why the final code SHA moved from `39b4d52` to `a2a0201` and then
  `2764071`, and why every catalogue was run again on `2764071` (§I).

The declared equivalent `m121_m140` `SEC-empty-password-unlocks` keeps its individual justification from
M121–M140 (stored in the catalogue and in every result file); it is not counted as killed.

## I. Mutation totals (M211)

All 16 catalogues (1086 mutants) were run on the committed final code tree **`2764071`**, one after another, by a
resumable chain that skips nothing unless the runner's own JSON says `complete=True` (`progress_2764071.txt`: start
11:47:07, chain done 15:10:06 UTC). Every result file was read for the runner's `complete` flag and its four lists
(`killed`, `survived_non_equivalent`, `declared_equivalent`, `invalid`), whose sizes add up to the catalogue size.
Evidence: `docs/mission-reports/m201-m230-evidence/mutation_final_2764071/` (and `mutation_final_39b4d52/` for the
previous complete run).

| Catalogue | Mutants | KILLED | SURVIVED | EQUIVALENT (declared) | INVALID | `complete` | Baseline (unmutated) | Notes |
|---|---|---|---|---|---|---|---|---|
| `m201_m230` | 55 | 55 | 0 | 0 | 0 | `True` | exit 0, 240 passed, 15 warnings |  |
| `m46` | 29 | 29 | 0 | 0 | 0 | `True` | exit 0, 84 passed, 14 warnings |  |
| `m47` | 26 | 26 | 0 | 0 | 0 | `True` | exit 0, 100 passed, 14 warnings |  |
| `m48` | 44 | 44 | 0 | 0 | 0 | `True` | exit 0, 206 passed, 14 warnings |  |
| `m49` | 38 | 38 | 0 | 0 | 0 | `True` | exit 0, 180 passed |  |
| `m50` | 55 | 52 | 3 | 0 | 0 | `True` | exit 0, 200 passed, 14 warnings | survived: `R-file-name-context-dropped`, `R-absent-ignores-context`, `A-sentence-inherits-any-size` |
| `m51` | 29 | 29 | 0 | 0 | 0 | `True` | exit 0, 94 passed |  |
| `m52` | 70 | 70 | 0 | 0 | 0 | `True` | exit 0, 215 passed, 14 warnings |  |
| `m53_m56` | 38 | 38 | 0 | 0 | 0 | `True` | exit 0, 114 passed, 14 warnings |  |
| `m61_m67` | 19 | 19 | 0 | 0 | 0 | `True` | exit 0, 149 passed |  |
| `m70_m76` | 18 | 18 | 0 | 0 | 0 | `True` | exit 0, 144 passed |  |
| `m83_m96` | 20 | 20 | 0 | 0 | 0 | `True` | exit 0, 192 passed, 14 warnings |  |
| `m101_m120` | 184 | 184 | 0 | 0 | 0 | `True` | exit 0, 296 passed, 19 warnings |  |
| `m141_m170` | 28 | 28 | 0 | 0 | 0 | `True` | exit 0, 64 passed, 14 warnings |  |
| `m171_m200` | 103 | 103 | 0 | 0 | 0 | `True` | exit 0, 294 passed, 14 warnings |  |
| `m121_m140` | 330 | 329 | 0 | 1 | 0 | `True` | exit 0, 415 passed, 14 warnings | equivalent: `SEC-empty-password-unlocks` |
| **Total** | **1086** | **1082** | **3** | **1** | **0** | 16 / 16 | | |

- **The 12 deferred catalogues (570 mutants, §H): 567 KILLED, 0 EQUIVALENT, 0 INVALID, 3 SURVIVED** — the three m50
  knowledge mutants, which are killed by the byte-identical mutants of `m52` in the same run (70 / 70). They are not
  counted as killed in m50.
- The declared EQUIVALENT `SEC-empty-password-unlocks` is justified individually in the catalogue and in the result
  file (an empty password is refused by three independent layers; the killed variants cover each). INVALID and
  EQUIVALENT are never counted as KILLED.
- Difference from the `39b4d52` run: `m83_m96` 19 → 20 KILLED (`CON-unsupported-claimed`, §H). Every other count is
  unchanged.

## J. Exact-SHA full suite and gates (M212)

Gates on the final code SHA `2764071` (pre-suite phase of `verify_release.py --expected-sha 2764071…`, log
`m201-m230-evidence/full_suite_2764071_local_nocov.log.txt`): `git rev-parse HEAD` = expected SHA; `git status
--porcelain=v1 --untracked-files=all` empty; branch `arena/72010272-drill-master`; `git diff --check` and
`git diff --cached --check` clean; every locked dependency at its pinned version; `pip check` clean; source /
packaging version consistent; `ruff --select E722,F821 .` **All checks passed**; lint debt **0, ceiling 0**
(`core dialogs tabs tests`); `compileall` clean. Before each commit: `exception_scan.py --check` (ceiling not raised),
`constant_inventory.py --check`, `dependency_audit.py --check` (26 locked, 0 FAIL), privacy check **1573 files,
0 findings**. Schema / migration compatibility and the inventories run inside the suite
(`tests/test_database_migration_acceptance.py`, `tests/test_canonical_schema*.py`, `tests/test_m113_constant_inventory.py`,
`tests/test_m101_warning_inventory.py`).

| Run | Tree | Result | Evidence |
|---|---|---|---|
| `50e6b03` local, coverage | committed | **never finished** — killed by the third sandbox reset | — |
| `9f784a8` local, coverage | committed | collected 5509: 5504 passed, **1 failed (D74)**, 4 skipped; 3872 s | `m201-m230-evidence/full_suite_9f784a8_local_coverage.log.txt` |
| `63780a6` local, coverage | committed | collected 5519: 5514 passed, **1 failed (D74)**, 4 skipped; 3872 s | `m201-m230-evidence/full_suite_63780a6_local_coverage.log.txt` |
| `39b4d52` local, coverage | committed | **aborted**: the kernel OOM killer killed pytest at ~80 % (anon RSS 3.57 GB of 3.94 GB, no swap); no counts | `m201-m230-evidence/d74_run1_39b4d52_transcribed.txt` (log lost in reset 4) |
| `39b4d52` local, no coverage, run 1 | committed | collected 5519: 5514 passed, **1 failed (D74)**, 4 skipped; 2968.86 s pytest, 3024 s total | `d74_run1_39b4d52_transcribed.txt` (log lost in reset 4) |
| `39b4d52` local, no coverage, run 2 | committed | collected 5519: 5514 passed, **1 failed (D74)**, 4 skipped; 3270.63 s pytest, 3336 s total | `full_suite_39b4d52_local_nocov_run2.log.txt`, `load_samples_39b4d52_local_nocov_run2.txt` |
| `a2a0201` local, no coverage | committed | collected 5519: 5514 passed, **1 failed (D74)**, 4 skipped; 2989.18 s pytest | `full_suite_a2a0201_local_nocov.log.txt`, `load_samples_a2a0201_local_nocov.txt` |
| **`2764071` local, no coverage (final code)** | committed, clean | **collected 5519: 5514 passed, 1 failed (D74), 4 skipped, 0 errors**; 3009.80 s pytest, 3041 s total; warnings 33 in 9 groups, matching pytest's total | `full_suite_2764071_local_nocov.log.txt`, `load_samples_2764071_local_nocov.txt` |
| **`2764071` CI 3.12 + coverage** | exact SHA | ✅ (`verify_release` saw failed = 0, errors = 0); coverage 72.22 % | §U |

Environment of every local run: Python 3.11.2, Linux, `QT_QPA_PLATFORM=offscreen`, PySide6 6.8.1.1, pytest 9.1.1,
`DRILLMASTER_ENV=test`, 2 CPUs, 3.94 GB RAM, no swap. The 4 skips are opt-in: the 2 real-DDR acceptance tests
(`tests/test_ddr_acceptance.py`, XLSX and PDF — **NOT RUN**), the real MinerU integration
(`tests/test_mineru_real_integration.py`) and the Windows bundle smoke (`tests/test_packaging_smoke.py`, Windows
only) — **none is counted as a pass**. The JUnit report of `verify_release` lives in a temporary directory that it
deletes after reconciling it with pytest's own counts (the "Pytest release counts" line); the JUnit evidence of the
CI legs is their annotations (§U).

**D74 — mechanism identified in this mission (stays OPEN).** The single local failure of every run is
`tests/test_m95_ux_responsiveness.py::test_the_measurement_tool_runs_and_reports_every_path`: the measurement child
(`tools/quality/ux_responsiveness_m95.py`) did not finish within the test's 300 s. It finishes in 10 s alone and
the test file passes alone (13 tests, 22 s). After the second occurrence the test was instrumented (`39b4d52`): the
child runs under `-X faulthandler` and, at the unchanged 300 s budget, receives SIGABRT so faulthandler prints every
thread's stack. The next occurrence captured it (`d74_run1_39b4d52_transcribed.txt`):

- the child was **not blocked**: in four occurrences its main thread stood at four different points of its normal
  path — still inside `MainWindow.__init__` → `create_time_depth_tab` → pyqtgraph `AxisItem.setTextPen` (`39b4d52`
  run 1), in the measuring loop `ux_responsiveness_m95.py:69` `_idle` (`39b4d52` run 2), and in the home tab's
  `_on_loaded` → `_fill_kpis` → `dashboard_widgets.py:147` `set_kpi` (`2764071`); the only other thread was the idle
  backup scheduler (`core/db_maintenance.py:900`, `Event.wait`);
- a per-minute sampler showed **MemAvailable 23.7 MB → 5.1 MB** (run 1) and **0 kB** (run 2) while the child ran, the parent pytest process at
  **3.49 GB RSS** of 3.94 GB, and the child at 23–58 % CPU, alternating `R` / `D` (waiting on page-in);
- the parent grows steadily over the run (0.67 GB at 5 min, 1.19 GB at 10 min, 2.63 GB at 25 min, 3.49 GB at
  40 min, 3.58 GB at the end); under `coverage run` the same growth ended in the OOM kill above.

So the child is starved of memory on this swap-less 4 GB sandbox: every page it touches evicts another (Qt / Python
code pages), and MainWindow construction crawls. It is **not** a product hang and not a lock: a separate probe held
an exclusive lock on the inherited `DRILLMASTER_DB_PATH` database and the tool still finished in 10 s
(`d74_hypothesis_locked_parent_db.txt`). The CI legs, on larger runners, pass the same test. No retry, timeout
increase or skip was added. **D74 stays OPEN**: the cause of the failure is identified, but the growth of the
long-lived pytest process to ~3.5 GB is not yet attributed to specific tests or fixtures (observation, not a proven
cause: the module-scoped M70 `window` fixture, imported by ten test modules, builds a full MainWindow each time and
never calls `MonkeyPatch.undo()`).

## K. DDR workflow (M213–M218)

| Phase | Result | Evidence |
|---|---|---|
| M213 | Generic workbook limits: 50 MiB file, 500 MiB uncompressed, 1000 sheets, 5 M cells per sheet, 30 M cells in total; a profile may only tighten them and its limits reach the extractor; the declared dimensions are checked before any cell is loaded; the dialog reports a refused file | `core/workbook_io.py`; `tests/test_m213_excel_limits.py` (8) |
| M214 (D66) | One header fills at most one field (exact name ignoring case / punctuation / a parenthesised unit, or a whole-word alias phrase of 3+ characters); a tie is ambiguous and unmapped; fuzzy / spatial candidates stay REVIEW_REQUIRED | `core/table_record_mapper.py`; `tests/test_m214_header_mapping.py` (9), `tests/test_table_mapper.py`; `d66_*` |
| M215 (D67) | Concurrency (apply, resolve and reopen races), changed report, reopen, missing target, identity field, foreign well, ambiguous target, audit failure: the review item is claimed under the write lock by an ORM statement; the second decision is refused | `core/review_scalar_correction.py`; `tests/test_m215_scalar_correction_adversarial.py` (16); `d67_*` |
| M216 (D68) | Identity and lineage fields; the target is re-checked immediately before the save; a well switch during extraction / preview never reaches the save; a routed file does not retarget the batch | `dialogs/excel_import_dialog.py`; `tests/test_m216_import_context_switch.py` (4); `d68_*` |
| M217 (D71) | Day-by-day authoring with `ddr-carry-forward-v1`: 10 carryable sections, 17 never carried (with reasons), explicit confirmation, existing rows never replaced, states NEW / CARRIED / CONFIRMED / IMPORTED / DERIVED / MISSING, audited lineage. The fuel / water preview leaves the day's movements None (`50e6b03`) | `core/ddr_carry_forward.py`, `dialogs/carry_forward_dialog.py`; `tests/test_m217_day_by_day_carry_forward.py` (22); `d71_*` |
| M218 (D69) | DDR → analysis lineage: a report revision is immutable for every writer; a later revision never alters saved snapshots | `tests/test_m218_ddr_revision_lineage.py` (19); `d69_*` |

**D75 (P2, found while closing the D71 residual, fixed in `63780a6`).** The residual had first been written down
as display-only ("W7 shows a None movement as 0"). Checking the save path proved it was not: a fuel / water movement
stored as NULL (unreported consumption or receipt — the DDR importer and the carry-forward preview leave it NULL)
loaded into W7 as 0.00 L, and saving the day **without any edit** stored consumed = received = 0.0 and a remaining
balance derived from them (stock 1000 L, NULL movements → `fuel_remaining` 1000.0;
`m201-m230-evidence/d75_w7_unknown_movement_before_fix.txt`, probe source
`d75_w7_unknown_movement_probe_source.py.txt`, after-fix output `d75_w7_unknown_movement_after_fix.txt`).
`save_fuel_water_inventory` also turned an explicit None movement into 0.0. Fix: the eight movement boxes carry the
stock boxes' unknown mark "—"; a loaded NULL shows "—" and saves back as NULL; remaining / runway are computed only
from known stock and movements (`_balance`); the save API keeps a None movement NULL. Kept: a fresh or cleared form
still starts at 0 (the existing "no movement" contract of `tests/test_w7_null_zero_ui_smoke.py`), and a caller that
omits a movement key keeps the legacy 0.0. `tests/test_m229_w7_unknown_movements.py` (2 tests: the W7 round-trip
including the preview → Save path, and the save API) fail on `9f784a8` and pass after; 4 mutants `D75-*`.

## L. Identity and provenance (M221, M224)

- **M221**: `FIELD_ORIGINS` = MANUFACTURER / USER / DERIVED / LEGACY_PRESET_UNVERIFIED / UNKNOWN. A library origin is
  the origin the published item declares, only while the bound value is unchanged; DERIVED lists its inputs;
  nothing is inferred (no rating from a grade, no 0 for missing).
  `test_library_origin_is_the_items_declared_origin_only_while_unchanged`.
- **M224**: the registry is versioned (`REGISTRY_VERSION = "legacy-preset-provenance-v1"`); a stored record keeps its
  version, so a later table change never rewrites history. No global formula changed.

## M. Importer and source rights (M219, M220)

- **M219**: no new source evidence appeared during the mission, so the M181 conclusion stands unchanged: no permitted
  oilfield tubular dataset was found; no API / ISO table, vendor sheet or derived catalogue was added. P18 stays
  OWNER REVIEW REQUIRED. The library still ships empty.
- **M220 (D72)**: the audit probe (`d72_tubular_import_hidden_content_before_fix.txt`) showed 6 kinds of silently
  accepted content. Now: a hidden sheet, hidden header row or hidden mapped column, an over-limit (archive or used
  range) or non-zip workbook, a repeated JSON key and invalid JSON **block** the file; a hidden row or a value
  without a header makes the row **INVALID**; a hidden unmapped column is listed as ignored. Formula cells stay
  INVALID; a published set is never updated in place; the source file is never rewritten (SHA-256 checked).
  `tests/test_m220_tubular_import_hardening.py` (10); the M181 and M190 suites still pass.

## N. Engineering integration (M222, M223)

- **M222**: library values reach the Volumes, Hydraulics, Weight and Casing Strength inputs unchanged; editing a
  bound value drops the binding; saved history stays frozen and re-runs MATCH
  (`tests/test_m184_m189_reference_integration.py`, `tests/test_m190_tubular_journey.py`).
- **M223**: lineage library item → frozen architecture revision (pins the binding) → cement worksheet case (pins
  `architecture_revision_id` and `components_sha256`); a newer library version or a newer architecture revision
  leaves the case unchanged and `verify_cement_case` stays MATCH; the scalar cement group has no library picker
  (the picker lives on Casing Strength only); the result stays labelled WORKSHEET.
  `tests/test_m223_library_architecture_cement_lineage.py` (3).

## O. W13 (M225)

27 leaves re-audited against `tests/test_m125_w13_classification.py:52`, which enforces the distribution
CONTRACT 9 / SCREENING 10 / WORKSHEET 4 / TRAINING AID 1 / REFERENCE-ONLY 1 / NOT_SUPPORTED 2. No leaf changed
class in this mission; the cement worksheet remains WORKSHEET.

## P. MSE and datum / CRS (M226)

- MSE lineage re-audit: `core/repositories/mse_repository.py` is the only writer of MSE runs (`LINEAGE_VERSION = 2`);
  `git diff 7c2da89..HEAD` is empty for it, `core/parameter_trends.py` and `core/operational_analysis.py`. The
  lineage tests pass (`test_m123_mse_lineage.py`, `test_mse_cross_process.py`, `test_mse_history_viewmodel.py`,
  `test_mse_persistence.py`, `test_mse_save_widget_smoke.py`, `test_m104_operational_kpis.py`: 58 tests).
  **D6 stays PARTIAL** (legacy runs without lineage stay NOT DEPTH-REPRODUCIBLE until an audited repair).
- **D11 stays PARTIAL**: only the explicit vertical datum shift exists; CRS is not modelled. The P10 package is ready
  at `docs/engineering/M196_OWNER_DECISION_PACKAGES.md:162` (default (a): declared references only).
  OWNER REVIEW REQUIRED.

## Q. Data-quality workspace (M227)

- `core/data_quality_workspace.py` (`data-quality-workspace-v1`), `dialogs/data_quality_dialog.py`, Tools ›
  "🩺 Data Quality Workspace" in the real MainWindow. Read-only: the session is rolled back; the table has no
  edit triggers and no editable cells.
- Categories: daily report without end-of-day depth or section (ERROR); open DDR review items, one row per report
  (WARNING); a section carried forward and not confirmed (WARNING); a survey station without inclination or azimuth
  (ERROR). Scoped to the selected well.
- "Open" navigates to the owning screen: the Daily Report tab with the report loaded, or the review queue of exactly
  that report (`can_import`, as Tools › Import Review Queue).
- `tests/test_m227_data_quality_workspace.py` (2): every category with its source, the other well sees only its own
  record, navigation through the real window, and a byte-identical database dump before and after.
  The pre-existing score service `core/data_quality.py` (W12) is unchanged; no workflow was duplicated.
- The first test run hung for 900 s on a modal "Select a well first" box because `navigate_to` alone does not set
  the window's current well; the test now selects through the hierarchy path, and every modal is patched.

## R. P1–P19 (M228)

All 19 packages in `docs/engineering/M196_OWNER_DECISION_PACKAGES.md` remain **OWNER REVIEW REQUIRED**; no owner
decision was received and none is fabricated. New evidence relevant to the owner:

| Package | New evidence this mission |
|---|---|
| P10 Datum / CRS | unchanged; D11 PARTIAL |
| P12 Method approvals | cement worksheet lineage pinned (M223); still WORKSHEET, not approved |
| P13 Encryption / HMAC | more storage guards (D61 residual, D69, D70); the file-writer non-claim still applies |
| P17 Windows / field acceptance | a green Windows CI job is not interactive acceptance; NOT RUN |
| P18 Tubular data source | M219: no new evidence; the library ships empty |
| P1–P9, P11, P14–P16, P19 | no change |

The one owner decision taken during the mission concerns CI, not a package: the 60-minute job limit is kept (§U).

## S. End-to-end journey (M229)

`tests/test_m229_product_journey.py` — one test, 35 numbered steps, real MainWindow (M70 fixture: real file
database, real authorization, admin session), synthetic data only:

1 menus · 2 workbook copy + SHA · 3 real DDR pipeline · 4 wrong well → VALIDATION_ERROR, nothing saved · 5 audited
decision files it under the selected well · 6 persisted review queue · 7 review dialog · 8 hierarchy selection +
workspace lists the open review · 9 workspace opens that report's queue · 10 audited attach, decided stays decided ·
11 source unchanged · 12 manual next day, carry-forward refused without confirmation, carried with it · 13 workspace
shows the unconfirmed carry, gone after confirmation · 14 surveys in the real viewer · 15 saved view · 16 reopen
MATCH · 17 survey edit → DIFFERENT, snapshot untouched · 18 library draft from a synthetic CSV · 19 publish,
immutable, CSV untouched · 20 architecture revision pins the binding · 21 W13 follows the well · 22 Volumes (closed
form, case, MATCH) · 23 Hydraulics (case, MATCH) · 24 Weight (case, MATCH) · 25 Casing Strength: yield unknown → not
rated, user yield recorded · 26 cement worksheet from the revision, WORKSHEET, MATCH, no picker · 27 newer library
version reported, values kept · 28 history lists every case · 29 second well: W13, workspace, saved views, cases and
review items do not leak · 30 verified backup through the window · 31 modification after the backup · 32 no worker
running · 33 restore through the window's own slot · 34 restored file holds the pre-backup data, not the later case
· 35 no orphaned worker, sources untouched. The W7 fuel / water round-trip of unknown movements (D75) is covered by
`tests/test_m229_w7_unknown_movements.py`.

## T. Migration and backup

D70 (§C) is the migration / restore finding of this mission. `tests/test_m204_restore_migration_cascade.py`,
`tests/test_db_maintenance_ui.py`, `tests/test_m198_backup_restore_qualification.py` and steps 30–35 of M229 pass.
All schema changes are additive triggers installed on new, upgraded and restored databases; D75 changed no schema
(the movement columns were already nullable).

## U. CI

Job ids from `gh api repos/asgareyvazi/Drill-master/commits/<sha>/check-runs`; facts from the job annotations.

| SHA | Source gate: 3.11 / 3.12 + coverage / 3.13 | Windows release gate |
|---|---|---|
| `9f784a8` | run 43696405353: ✅ 132757863904 / ✅ 132757864219 (54 min) / ✅ 132757864128 | run 43696405351 ✅ 132757830078 |
| `63780a6` | run 43704965887: ✅ 132783963211 / ✅ 132783963319 (55 min; coverage 72.22 %, 78057 / 108088) / ✅ 132783963402 | run 43704965898 ✅ 132783963466 |
| `39b4d52` | run 43710577087: ✅ 132801022874 / **cancelled at the 60-minute job limit** 132801022911 and again in the `--failed` re-run 132818113022 / ✅ 132801022687 | run 43710577084 ✅ 132801022614 |
| `a2a0201` | run 43840196482: ✅ 133206659859 / **failure** 133206660412 (46 min): 5514 passed, **1 failed — D76**, 4 skipped / ✅ 133206660213 | run 43840196433 ✅ 133206660248 |
| **`2764071` (final code)** | run 43853272754: ✅ 133251010294 / attempt 1 **cancelled at the 60-minute limit** 133251010677; `gh run rerun --failed` attempt 2 **✅ 133284380851** (12:02:42–12:49:35 UTC, 47 min; product coverage **72.22 %**, 78060 / 108088 over 286 files; floor 45.50 %; warnings 33 in 9 groups, matching pytest's total) / ✅ 133251010698 (attempt 2 lists the two green jobs again as 133284383902 and 133284383361) | run 43853272742 ✅ 133251007181 |

- **Final code SHA `2764071`: 4 / 4 green on the exact SHA**, the 3.12 coverage leg after one re-run of a leg that
  was cancelled at the job limit. The duration of that leg varies widely between runs of near-identical trees (46,
  47, 54, 55 min, and > 60 min three times); the job logs are stored on a host this sandbox cannot reach, so the
  variance could not be attributed. **Owner decision (asked during the mission): keep `timeout-minutes: 60`**; no CI
  file was changed. A cancelled leg was never counted as green.
- **D76 (P3, found by CI on `a2a0201`, RESOLVED in `2764071`)**: the only failure of the `a2a0201` coverage leg was
  `tests/test_d59_stale_partial.py::test_an_identical_manifest_audited_under_another_name_is_refused_not_classified_audited`
  (manifest hashes differed). The test built two packages with only `well_package._now` frozen and required
  byte-identical manifests, but the EOWR HTML, bit-run and NPT parts embed the real clock (`core/report_provenance.py:131`
  to the second, the EOWR footer to the minute), so it failed whenever the two builds straddled a wall-clock second —
  likelier on the slower coverage runner; 3.11, 3.13 and the local run passed it. Reproduced deterministically by
  starting the second build after the next second boundary (differing parts `eowr_html`, `bit_runs`, `npt`;
  `m201-m230-evidence/d76_d59_twin_manifest_timing_before_fix.txt`). The twin is now a byte-identical copy of the
  audited folder under another name, which is exactly the state under test; the REFUSED / AUDITED / refused-recovery
  assertions are unchanged; the straddling probe passes 3 / 3; the 16 D59 mutants that use the file are 16 / 16 KILLED
  (`mutation_m121_m140_D59_after_d76.json`). No retry, timeout or skip. The product documents that package parts are
  not byte-reproducible, so no product change was needed.
- **Coverage**: 72.22 % on the final code SHA (78060 / 108088; `63780a6`: 78057 / 108088; `9f784a8`: 78070 / 108107).
  The floor file `.github/coverage-floor.json` enforces 45.50 % (a non-decreasing floor); the measured baseline at the
  end of M171–M200 was 70.46 %, so measured coverage rose by 1.76 points without changing the population or the omit
  lists.
- Windows manifests (all **UNSIGNED**, Python 3.12.10, PyInstaller 6.11.1, Inno 6.7.1): `63780a6` installer 85 288 932 B,
  sha256 `49d15714368d…`; `39b4d52` 85 329 092 B, `32458c3bbcdf…`; **`2764071` 85 293 906 B, sha256
  `aa4056d13042…58fcab`**. M52 lifecycle stress 5 / 5 on each: 119 tests per fresh interpreter, 0 failures, native crash
  False, peak 234–238 MB, 0 processes left, 0 new dumps. A green Windows job is not interactive acceptance (P17 NOT RUN).

## V. Commits, remote, workspace

Commits of the mission on `arena/72010272-drill-master` (`git log --oneline a38c54c..2764071`, 11 commits, all pushed,
none rewritten): `3497a91`, `c47a791`, `da53eb6` (its CI failed on m169; fixed in `ac81b04`), `ac81b04`, `b67d4e1`,
`50e6b03`, `9f784a8`, `63780a6`, `39b4d52`, `a2a0201`, **`2764071`** (final code). The report commit adds only this file
on top of `2764071`.

State before the report commit (`git fetch`, `git ls-remote origin`, `git status`, `git stash list`, `git worktree list`,
`git tag`):

| Check | Result |
|---|---|
| HEAD = upstream | `2764071` = `origin/arena/72010272-drill-master` |
| Work tree | clean (`git status --porcelain` empty apart from the evidence files committed with this report) |
| Stash / worktrees / tags | 0 / 1 (the checkout itself) / 0 |
| `drill-Master` | `e3fa42a` (unchanged; never opened) |
| other `arena/*` heads | `02dd3e1`, `c7e7697`, `ad7ea0d`, `b05ea76`, `c28bbef`, `7f0186e`, `4336ea3` (unchanged) |
| Force-push, history rewrite, tags, releases, signing, settings / secrets changes | none |
| Files in git | no database, model, temporary file or DDR workbook; privacy check 0 findings |

CI on the report commit is checked after the push; the result cannot be recorded inside the commit it describes and is
given in the closing message of the mission.

Evidence committed with this report: `m201-m230-evidence/mutation_final_2764071/` (16 result files and the chain
progress), `full_suite_2764071_local_nocov.log.txt`, `load_samples_2764071_local_nocov.txt`.

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**

---

## Addendum (M231 / M232, written after delivery)

- **Delivery.** This report was first committed as `0d824e4` on top of `2764071`. The push was refused ("No anonymous
  write access": the sandbox had no git credential helper). The sandbox was then reset and the repository re-cloned, so the
  unpushed commit object no longer exists. The 20 files it contained survived unchanged in the work tree (report, 2 suite
  files, 16 mutation result files + chain progress); they were committed again with the same message as **`eaa003f`**
  (parent `2764071`) and pushed by fast-forward; `git ls-remote origin` and the GitHub REST API both returned
  `eaa003f2e94d1637116958f00218eb490cd7d973`.
- **Capability matrix reconciled (M232).** The matrix row "Mutation (M210 / M211)" still quoted the intermediate
  `39b4d52` run (4 survivors). It now gives the final `2764071` run (1082 KILLED, 1 EQUIVALENT, 0 INVALID, 3 SURVIVED,
  16 / 16 complete) and keeps the `39b4d52` run as superseded history; rows for M212 (PARTIAL), M230 (PARTIAL) and D76
  were added. No result in this report changed.

