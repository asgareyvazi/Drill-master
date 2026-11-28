# M473–M474: Recovery of the M261–M290 mutation-only items (U3)

## Background

The M261–M290 report gives six Part II phases that received mutation coverage only:

| Phase | Module | Family | Count in the report |
|---|---|---|---|
| M275 | `core/engineering/engines/trajectory.py` | TR | 4 |
| M276 | `core/engineering/engines/anti_collision.py` | AC | 12 |
| M278 | `core/engineering/mud_volume_persistence.py` | MV | 4 |
| M279 | `core/engineering/casing_persistence.py` | CP | 5 |
| M282 | `core/engineering/engines/bit_performance.py` | BP | 7 |
| M283 | `core/engineering/engines/well_control.py` | WC | 7 |

The M403 traceability ledger lists these missions as `NOT VERIFIED — NO NAMED ARTEFACT`. That ledger is a snapshot of
M1–M400 and is left unchanged. The M400 and M460 roadmaps carried the item over as U3.

## M473: re-execution on the current code

The mutants are still defined in `tools/quality/mutation_m261_m290.py`. They were executed at commit `842c35c`, the
Phase C tip, with the M46 engine. Each mutant runs in a scratch copy, and its listed tests must fail.

```
python tools/quality/mutation_m261_m290.py --only <the 39 TR/AC/MV/CP/BP/WC ids> --json …
baseline exit=0 245 passed
mutants=39 killed=39 survived_non_equivalent=0 declared_equivalent=0 invalid=0 seconds=63
```

| Family | Killed / total | Invalid anchors |
|---|---|---|
| TR (M275) | 4/4 | 0 |
| AC (M276) | 12/12, including `AC-claims-iscwsa` (P19 not approved) | 0 |
| MV (M278) | 4/4 | 0 |
| CP (M279) | 5/5 | 0 |
| BP (M282) | 7/7 | 0 |
| WC (M283) | 7/7 (well control stays a TRAINING AID, P11) | 0 |

The machine-readable results are in `m473_u3_historical_mutation_rerun.json`, in this directory.

## M474: keeping the anchors runnable

`tests/test_m473_mutation_anchor_integrity.py` is a static test that runs in the normal suite. It checks the
following:

- The six U3 families still have exactly the counts in the report.
- Every anchor matches its file exactly once. An INVALID mutant is never counted as killed.
- Every listed test file exists.
- The same checks apply to every mutant of `mutation_m461_m520.py`, `mutation_m321_m360.py` and
  `mutation_m401_m460.py`.

If a later code change moves an anchor, the normal suite fails. Before this test, the problem would only have shown up
when someone next ran the mutation tool.

## Status

U3 is **closed for mutation coverage**: 39/39 mutants are killed on the current code, and the artefact is named.

This is not new qualification of the engines. The phases keep the status the M261–M290 report gave them (PARTIAL),
and the owner gates P8, P10, P11, P12/P18 and P19 are unchanged.

## Addendum (M494): anchors outside U3

A full anchor scan of `mutation_m261_m290.py` (89 mutants) finds **7 INVALID anchors outside the U3 families**. They
are in the IL family (M273 import lineage) and the WB family (M286 workbench), where later missions changed the code:

- IL-changed-since-hidden, IL-first-correction-expected, IL-open-item-checked;
- WB-archive-without-reason (2 matches), WB-first-mark-wins, WB-reused-id-inherits-archive,
  WB-clone-empty-inputs-accepted.

They were **not repaired** in M461–M520, which is out of scope for U3. An INVALID mutant is never counted as a kill,
and they are recorded as open item R4b in the M520 roadmap.

The 39 U3 mutants and every mutant of `mutation_m321_m360`, `mutation_m361_m400` (53), `mutation_m401_m460` and
`mutation_m461_m520` have valid anchors. `test_m473_mutation_anchor_integrity` now covers these four tools.

## Addendum 2 (M494, commit `750e3cd`): R4b repaired

The 7 drifted IL-* / WB-* mutants were re-anchored to the current code. Each keeps its original defect; only the
anchor text follows the code that later missions moved:

| Mutant | Current anchor | Why it moved |
|---|---|---|
| IL-changed-since-hidden | `_check`: `if _same_value(stored_now, expected):` → `if True:` | `d57f5b2` (M296–M306, value lineage) moved the stored-now check into `_check` |
| IL-first-correction-expected | `_check`: `corrections[-1]` → `corrections[0]` | same |
| IL-open-item-checked | `_check`: `if item.state != accepted_state: return NOT_APPLICABLE` disabled | same |
| WB-archive-without-reason | `_mark`: the single-record reason guard (the anchor now includes the error text, so it matches once; the bulk guard is unchanged) | `d57f5b2` (M296–M306, bulk actions) added a second, bulk guard |
| WB-first-mark-wins | `latest[key] = action` → `latest.setdefault(key, action)` (indentation changed) | `0c90a5b` (M365) restructured the loop |
| WB-reused-id-inherits-archive | `if key not in born or born[key] != snapshot:` → `if key not in born:` | `0c90a5b` (M365) inverted the condition into a `continue` |
| WB-clone-empty-inputs-accepted | `core/calculation_clone_contract.py` `clone_check`: the empty-inputs guard | `d57f5b2` (M296–M306, clone contract) moved the guard into the clone contract |

The IL mutants also run `tests/test_m300_m301_value_lineage.py`, and WB-clone-empty-inputs-accepted also runs
`tests/test_m303_m306_clone_contract_and_bulk.py`, because those are the suites that now own the moved code.

**Result** (`mutation_m261_m290.py --only <the 7 ids>`, Python 3.11.2): baseline 44 passed;
**mutants=7 killed=7 survived_non_equivalent=0 invalid=0**, 232 s.

All 89 anchors of `mutation_m261_m290.py` now match exactly once. `test_m473_mutation_anchor_integrity` covers five
tools (adding `mutation_m261_m290`) and passes 6/6. Roadmap item R4b is closed.
