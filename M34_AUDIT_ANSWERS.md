# M34 — The 60 Required Answers

Each answer is a statement about **this repository as measured in this mission**, with the artifact that carries
the evidence named in-line. Where an answer is "no" or "not proven", it says so plainly.

## A. Recovery of Mission 33

1. **What state was M33 in when this mission started?** `M33 — PARTIAL, two claims falsified`: real artifacts and
   three verified code fixes survived; its tooling, its wheel and its commit-SHA evidence did not
   (`M34_M33_RECOVERY.md`).
2. **Did M33 commit anything?** No. HEAD is still `c28bbef…`, 0 files staged, and the reflog contains only the
   clone, the checkout and the branch creation.
3. **Is the worktree still what M33 left?** Yes — the tracked-file diff sha256 `79c05d864f8b900e…` equals the
   hash M33's own final staging record captured (`M34_PREWORKSPACE_MANIFEST.json`).
4. **Are M33's three code fixes intact?** Yes, all three are byte-identical to M33's recorded post-fix hashes,
   and each passes contract probes plus its regression test (`m34-fix-reverification.json`).
5. **Was any M33 artifact lost between sessions?** Nothing in the repository: 0 of the 230 recorded untracked
   paths are missing; 260 are present now (the extras are M34's own evidence and tools).
6. **Can M33 be re-run?** No — its toolchain lived outside the repository and is gone. M34 rebuilt the toolchain
   **in-repo** (`tools/m34/`) so this cannot recur.
7. **Were M33's item fingerprints reproducible?** No. Calibration reproduced at most 8.3 % (best variant 4.8 %)
   of M33 fingerprints over untouched records; the mismatch is recorded and M34 uses its own identity.
8. **Which M33 claims did this mission falsify?** The claim that `core/operational_time.py` and
   `core/safety_semantics.py` "are tracked in that commit" (`a9d7dede…`, which does not resolve) and the claim
   that the outside-checkout wheel smoke returned 0 with the checkout absent.
9. **Is M33's own verdict still right?** Yes: NOT RELEASE-CERTIFIABLE — and it must be strengthened by the
   packaging blocker M34 proved.
10. **What did M34 keep from M33?** Its per-item records as *prior disposition evidence*, its evidence directory
    untouched, its two test files, and every M33 `DEFECT-FIXED`/`REMOVED-WITH-EVIDENCE`/`EXTERNAL` record with
    its evidence retained.

## B. Evidence base

11. **What is the inventory of record?** `docs/audits/m34-evidence/m34-ledger.json` — **11 554** records, one per
    occurrence, each with INV-ID, path, symbol, family, line, context fingerprint, source sha256, domain,
    priority, disposition, rule, root cause and evidence.
12. **How many items came from M33 and how many are new?** 8 933 carried at SAME-FILE-HASH, 1 M33 record without
    a line, **2 620** genuinely new sweep hits; **3 182** sweep hits were de-duplicated because an M33 record
    already held that `(path, family, line)`.
13. **Is the fresh sweep real?** Yes — 336 files, 5 802 hits, 21 families, executed in this mission
    (`m34-fresh-sweep.json`), not inherited.
14. **Are the old counts (2232/6860/3518/8934) used as targets?** No. They are carried as *claims* in
    `m34-reconciliation.json`; the only numbers used are re-derived ones.
15. **Can any item be closed by moving a line?** No — carrying requires the file's sha256 to still match the
    recorded hash; a changed file forces re-adjudication.
16. **How many dispositions are terminal?** 10 330 of 11 554.
17. **How many are open?** **1 224** UNDER-REVIEW; **0** EVIDENCE-INCOMPLETE.
18. **Of the open items, how many are HIGH or CRITICAL?** **371 HIGH, 0 CRITICAL.**
19. **Was anything mass-closed?** No. The largest single rule result is the *prose* correction (1 483
    occurrences individually verified to sit inside a comment or docstring), and a count that changed never
    deleted an M33 record: the M33 evidence is retained on every re-adjudicated item.
20. **How did M33's open items fare?** 2 837 inherited → 1 248 became VERIFIED-CORRECT, 519 INTENTIONAL-BY-DESIGN,
    **1 070 remain open** — i.e. 1 248 of M33's "open" items were decidable from facts M33's rules never read.

## C. Engine defaults and the Qt clamp

21. **Why 99.99?** It is Qt's default maximum for a bare `QDoubleSpinBox` — reproduced independently here:
    `setValue(150)` leaves 99.99.
22. **Who set 99.99?** Nobody in this repository; it is a framework default, which is exactly why it silently
    truncates engineering values above it.
23. **What is the engineering range?** Per field, declared in `core/validators.py` — e.g. `avg_rop` is 0–500 m/hr.
24. **Was a magic number substituted?** No. The widget receives the *documented* domain maximum at the call site
    (`_calc_spin(QDoubleSpinBox(), 500)`) and "not computed" is an explicit sentinel minimum carrying the text
    "Not computed".
25. **Is the clamp fixed?** Yes, and it is mutation-proven: deleting the raise-the-maximum guard
    (`M34-M-CLAMPRESTORE`) or the explicit domain maximum (`M34-M-QT99CLAMP`) fails the clamp test.
26. **Is the UI/persistence boundary clean for derived values?** Yes for the fields audited: `_calc_value`
    returns `None` for an untouched field, so `collect_data` persists *unknown*, never 0 (M32-FIX-008 verified,
    `M34-M-TABPERSIST` killed).
27. **What did `casing.py` do before and after?** Before: an absent axial/internal-pressure load produced and
    reported a stress as if the load were zero. After: `None` plus explicit `*_supplied` flags and warnings.
28. **Is a "supplied as zero" load still a measured zero?** Yes, and the mutant that merges the two cases
    (`M34-M-CASING-ZERONONE`) is killed.
29. **What about `torque_drag.py` and `torque_drag_persistence.py`?** Their defaults are declared physical
    inputs, the engines report their inputs back, and absent inputs persist as `NULL` — verdicts
    NO-LIMIT-REQUIRED / BY-DESIGN, recorded per item.
30. **What about `data_quality.py`?** An unrecorded duration no longer becomes 0 h: coverage reports
    `value=None, status="unknown"` with the reason; two tests, one mutant killed.

## D. Domain sweeps (Parts F–N)

31. **Time semantics?** Missing durations stay missing through NPT derivation, activity-code usage, the legacy
    validator and the coverage metric; negative/malformed values are rejected by the input contracts; each
    branch has a regression test.
32. **Engineering input contracts?** 350 `default-zero-param` records: 290 INTENTIONAL with the declared default
    named, 47 open with the missing domain declaration named, 13 otherwise terminal; plus 229
    numeric-coalesce/float-or-zero records, 3 open.
33. **UI/persistence boundary?** `setvalue-zero` 77 (45 INTENTIONAL with the construction/reset/load path named,
    26 open), `get-default` 1 065, `snapshot-serialize` 343 — each open record states the missing declaration.
34. **Exporter comparison?** The Excel exporter's blank-duration contract is verified and mutation-tested; the
    remaining exporter surfaces fall inside the `get-default`/`snapshot-serialize` families with per-record
    verdicts.
35. **Snapshot/historical integrity after new nullable fields?** 327 of 343 records terminal; 16 open with the
    missing absence-state declaration named.
36. **Error-handling re-sweep (false success)?** Done with try-body context: handlers protecting cleanup/advisory
    probes are INTENTIONAL with the protected call named; handlers that swallow where a caller can observe
    success stay open and HIGH (98 + 74 + 52 records).
37. **NULL/zero secondary sweep?** Folded into the ledger families (`or-zero` 236, `numeric-coalesce` 65,
    `or-constant` 110, `get-default` 1 065) with per-record verdicts.
38. **Safety semantics?** `core/safety_semantics.py` is one of the two untracked modules; its consumers are
    covered by the packaging defect below, and no safety number is fabricated by the code paths audited.
39. **Currency?** 206/206 `currency-arithmetic` records VERIFIED: no unlabelled mixed-currency total was found;
    every sum is guarded by an explicit currency contract.
40. **Scope/ownership?** Guards active and mutation-proven load-bearing; NULL ownership deliberately means
    *unknown* and is never fabricated into a foreign key.

## E. Fix integrity and tests

41. **Are the M32 fixes still real?** 10/10 VERIFIED by contract probe + their own test; two files differ from
    M32's recorded hash because M33 changed them, stated on the record.
42. **Are the M33 fixes still real?** 3/3 VERIFIED the same way.
43. **Does mutation testing support them?** Yes: 16 mutants designed from the contracts, **15 killed**, 1
    documented equivalent survivor, all files restored byte-identically (`harness_self_check.all_restored`).
44. **Any vacuous assertions or dishonest skips?** None found: `skip-call` 25/25 resolved (17 external with the
    dependency named in the call, 8 prose/scaffolding); no `assert True` executable hits; a failed import is
    never converted into a pass.
45. **What does the full suite say on the final tree?** **1 814 passed, 0 failed, 0 errors, 4 skipped (external
    inputs), 309.9 s, exit 0** (`m34-full-suite-junit.xml`).
46. **Do the four skips matter?** They are real-DDR xlsx/PDF, real MinerU and the Windows bundle — all external,
    all named, none counted as a pass.

## F. Release engineering

47. **Is the lock exact from a clean environment?** Yes: a throwaway venv installed `requirements-lock.txt`
    **26/26 exact**, `pip check` clean.
48. **Does the wheel build from what a release can contain?** Yes — built from `git ls-files` only:
    `drillmaster-1.0.0-py3-none-any.whl`, 1 036 029 B, sha256 `5d5211600372ced4…`, all required entries present,
    no `tests/`.
49. **Does the wheel run outside the checkout?** **No — it aborts with
    `ModuleNotFoundError: No module named 'core.operational_time'`.** Two production modules are untracked while
    tracked code imports them. This is a **blocking repository defect**.
50. **Is Commit 1 self-contained?** The Commit-1 population (86 files, including the two modules) compiles,
    collects, passes its targeted tests and **passes the full suite (1 814 / 0 failed) inside a tree that
    contains no audit record** — so Commit 1 does not depend on Commit 2.
51. **What belongs to Commit 2?** The M30–M34 audit records, evidence and reports, and the `tools/m34/`
    analysis toolchain — behaviour-neutral material, listed file-by-file with its reason in
    `m34-commit-staging-simulation.json`.
52. **Any file whose inclusion is unclear?** Any file my classifier could not place is emitted as
    `REVIEW-REQUIRED` in the decision list; nothing is included by silence.
53. **Lint state?** `ruff --select E722,F821` → **0 defects**; the debt ratchet over `core dialogs tabs tests` is
    **5 338 ≤ ceiling 5 375** (`verify_release.verify_lint`'s exact scope). No ceiling was raised.
54. **Compile/collect?** `compileall` clean; **1 818** tests collected on the final tree.
55. **Git cleanliness?** 89 modified tracked / 260 untracked / 0 deleted / 0 staged; `git diff --check` clean; no
    cache artifacts; **no secrets** matched the five credential patterns; the only mutant-marker strings sit in
    `tools/m34/` and `m34-mutation-controls.json` (the harness and its result), none in production or test code.
56. **Docs truth scan?** Every SHA, count, branch and status claim in the living docs was classified
    (`m34-doc-claim-audit.json`): 11 CURRENT-VERIFIED, 98 HISTORICAL, 15 to check against the final run, 45
    needing a status review, and **36 SHAs that do not resolve locally** → those are `UNRESOLVED`, never
    presented as ancestry.

## G. Gates, verdict and what remains

57. **Closure gate?** **FALSE** — inventory 11 554 ≠ terminal 10 330, UNREVIEWED 1 224,
    EVIDENCE-INCOMPLETE **0**.
58. **Blocker gate?** **FALSE on HIGH** — CRITICAL 0, HIGH 371 open, plus one proven PACKAGING DEFECT (the
    tracked-only wheel cannot start).
59. **Is the external boundary honestly stated?** Yes: Windows runtime, native Qt, installer and real
    production documents were **not run**; the four suite skips and the 17 external records say so, and no
    external item is used to excuse a repository item.
60. **What is the verdict, and what would change it?** **NOT RELEASE-CERTIFIABLE — repository-verifiable
    semantic inventory not closed, and the tracked-only release artefact cannot start.** It changes when
    (a) `core/operational_time.py` + `core/safety_semantics.py` (and their tests) are added to the Commit-1
    population, and (b) the 1 224 open items — 371 HIGH — are adjudicated from a domain decision that states,
    per field, whether a legitimate 0/falsy value is possible and whether a swallowed failure may be invisible
    to the operator.
