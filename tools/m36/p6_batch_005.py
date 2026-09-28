#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-005 (45 HIGH records, mixed HIGH, classes C/D).

Same contract as p6_batch_004.py.  This batch is dominated by the kill-sheet canonical builder
(26 of 45 records = 13 statements x 2 rules), whose gate was completed by this batch's own fix
commit, so its records are re-anchored through the diff line map derived from that fix (never
hand-adjusted) and the recorded text is first verified against the fix's parent revision.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-005"
KILL_SHEET_FIX = "ff2000a"      # this batch's casing-ID gate fix
KS = "core/engineering/well_control_kill_sheet.py"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

RECHECK_AGAINST = {KS: KILL_SHEET_FIX}


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for the statement adjudicated under {sibling} "
            f"({where}); the register's two rules fired on one construct, so this id adds no "
            f"independent behaviour. Adjudicated once under {sibling}: {summary}",
            None)


KS_GATE = ("the builder lists the inputs the composite computation actually consumes (257) and "
           "``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from "
           "absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes \"no "
           "overpressure\"). Refuse instead.' (436-443), returning "
           "``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. ")
KS_SENTINEL = ("The widgets hand the builder None for their not-supplied sentinel "
               "(\"Read a kill-sheet input; the sentinel reads back as ``None``\", "
               "tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.")
KS_ECHO = ("``scr1_spm``/``scr2_spm`` are documented echo-only display metadata (257-258), and a "
           "grep of the module shows ``scr2_psi`` is never read by ``compute_kill_sheet`` either "
           "(only ``scr1_psi`` at 456); an absent value in these display fields reaches nothing "
           "computed.")

R: dict[str, tuple[str, str, str | None]] = {}

# --------------------------------------------------------------------------- kill sheet (26)
_KS_GATED = {
    "INV34-001765": (288, "tvd_m"), "INV34-001753": (289, "hole_size_in"),
    "INV34-001755": (291, "mw_pcf"), "INV34-001752": (292, "frac_gradient_psi_ft"),
    "INV34-001767": (293, "sidpp_psi"), "INV34-001766": (294, "sicp_psi"),
    "INV34-001759": (295, "pit_gain_bbl"), "INV34-001761": (296, "scr1_psi"),
    "INV34-001760": (300, "pump_output_bbl_stk"),
}
for _id, (_line, _field) in _KS_GATED.items():
    R[_id] = (VC, f"`{_field}` is one of the gated raw inputs (``required_raw``, 259-272) and {KS_GATE}"
                  f"An absent value therefore cannot reach the arithmetic as 0.0: it refuses. "
                  f"{KS_SENTINEL}", None)
R["INV34-001762"] = (VC, f"`scr1_spm` is echoed, not consumed: {KS_ECHO} {KS_GATE}The defect it "
                         f"could otherwise carry is impossible here (nothing computed reads it), and "
                         f"the module says so in the same comment that lists the gate.", None)
R["INV34-001763"] = (VC, f"`scr2_psi` is not consumed by the composite computation (verified: the "
                         f"module reads ``scr1_psi`` at 456 and never ``scr2_psi`` - it exists for "
                         f"the second-circulation echo), so an absent value cannot affect a computed "
                         f"result. {KS_ECHO}", None)
R["INV34-001764"] = (VC, f"`scr2_spm` is echoed, not consumed: {KS_ECHO}", None)
R["INV34-001751"] = (DEF,
    "GENUINE DEFECT, found here and fixed in this batch's code commit "
    f"{KILL_SHEET_FIX}. ``casing_id_in`` is a *required* keyword of the builder (no default, 215) "
    "and it IS consumed - ``csg_id = inp.casing_id_in`` (454) feeds the annular loop (475-479) - "
    "yet it was the one consumed input missing from ``required_raw`` while the comment above that "
    f"gate claims to list exactly the consumed inputs (257). {KS_SENTINEL} An unfilled casing-ID "
    "field therefore became 0.0: ``ann_id_val > od`` is false, no annular volume (and no annular "
    "displacement strokes derived from it) is produced, and the sheet still reports "
    "``success=True`` - the fabricated-but-plausible answer the module's own refusal exists to "
    "prevent (436-443). Fix: add the input to the gate; an explicit 0.0 remains a supplied value.",
    "none for this defect; the sheet now refuses with the input named in the error message")

for _id, (_line, _field) in {**{"INV34-007522": (288, "tvd_m"), "INV34-007523": (289, "hole_size_in"),
                               "INV34-007525": (291, "mw_pcf"), "INV34-007526": (292, "frac_gradient_psi_ft"),
                               "INV34-007527": (293, "sidpp_psi"), "INV34-007528": (294, "sicp_psi"),
                               "INV34-007529": (295, "pit_gain_bbl"), "INV34-007530": (296, "scr1_psi"),
                               "INV34-007531": (297, "scr1_spm"), "INV34-007532": (298, "scr2_psi"),
                               "INV34-007533": (299, "scr2_spm"), "INV34-007534": (300,
                                                                                    "pump_output_bbl_stk")}}.items():
    _primary = {288: "INV34-001765", 289: "INV34-001753", 291: "INV34-001755", 292: "INV34-001752",
                293: "INV34-001767", 294: "INV34-001766", 295: "INV34-001759", 296: "INV34-001761",
                297: "INV34-001762", 298: "INV34-001763", 299: "INV34-001764", 300: "INV34-001760"}[_line]
    R[_id] = dup(_primary, f"{KS}:{_line} - the same `{_field}` statement, rule pair "
                           f"R-DEF-RETURN-NUM/or-zero twice on one line",
                 f"`{_field}`: {R[_primary][1][:150]}...")
R["INV34-007524"] = dup("INV34-001751", f"{KS}:290 - the same casing-ID statement, rule pair "
                                        "R-DEF-RETURN-NUM/or-zero twice on one line",
                        "one statement, one defect, one fix (commit "
                        f"{KILL_SHEET_FIX}); the defect is recorded under INV34-001751")

# --------------------------------------------------------------------------- time_utils (6)
_TIME_RESTORE = ("`_on_editing_finished` cannot commit invalid text: after both parse attempts the "
                 "method restores the last accepted value explicitly - 'if invalid, return the "
                 "previous value' (84-88), re-rendering ``24:00`` or the stored "
                 "``_hour``/``_minute``. The swallowed ValueError is the *expected* outcome of "
                 "testing whether the typed text parses at all.")
R["INV34-002873"] = (INT, _TIME_RESTORE + " The swallow is compensated in the same method, so the "
                                          "failure it hides cannot reach the widget's value.", None)
R["INV34-007842"] = dup("INV34-002873", "core/time_utils.py:68/69 - the same handler (rule pair "
                                        "R-EXC-PASS + R-PASS-EXC on one `except ValueError` line)",
                        "invalid input restores the previous value (84-88)")
R["INV34-002874"] = (INT, _TIME_RESTORE + " (This is the compact HHMM branch of the same method; the "
                                          "same restore-at-the-end applies to both branches.)", None)
R["INV34-007843"] = dup("INV34-002874", "core/time_utils.py:81/82 - the same handler (rule pair)",
                        "invalid input restores the previous value (84-88)")
R["INV34-002875"] = (INT,
    "`TimeValidator.validate` never *accepts* through the swallow: Acceptable is returned only after "
    "the range check succeeds (166-167); anything that fails falls through to the explicit prefix "
    "checks and ends in ``QValidator.Invalid`` (176-186, 'Arbitrary text such as ``abc`` must be "
    "invalid rather than silently accepted'), with out-of-range times ('25:99') at best "
    "Intermediate - and Intermediate/Invalid text cannot be committed because the editing-finished "
    "handler restores the previous value (84-88).", None)
R["INV34-007845"] = dup("INV34-002875", "core/time_utils.py:168/169 - the same handler (rule pair)",
                        "the validator still ends in Invalid/Intermediate, never Acceptable")

# --------------------------------------------------------------------------- hydraulics (2)
R["INV34-001957"] = (INT,
    "The swallowed ValueError is ``calc_critical_flow_rate``'s declared input guard - 'Hole size "
    "and pipe OD must be > 0', 'Hole size must be > pipe OD', 'MW and PV must be > 0', 'Yield point "
    "cannot be negative' (raised at the top of the function) - and the fields it protects default "
    "to 0.0/\"\" ('not computed'), which the single consumer treats as *no data* rather than as a "
    "measured zero: tabs/w13_Engineering_Calculator.py:1588 renders the critical-flow block only "
    "``if getattr(r, \"critical_flow_rate_gpm\", 0) > 0``. Value and section name are assigned "
    "together inside the same ``try`` (392-394), so a skipped section can never be reported under "
    "another section's name; a computed Qc is strictly positive (velocity x area), so 0.0 is never "
    "a legitimate measurement.", None)
R["INV34-007572"] = dup("INV34-001957", "core/hydraulics_engine.py:395/396 - the same handler "
                                        "(rule pair R-EXC-PASS + R-PASS-EXC)",
                        "the guard is the engine's declared invalid-input check and 0.0 means 'not "
                        "computed' to its only consumer")

# --------------------------------------------------------------------------- inventory (2)
_INV = ("`derive_closing`'s docstring defines the result contract - 'Closing stock = opening + "
        "received - used, or None when opening unknown. Never returns a fabricated 0.0 when the "
        "opening is unknown.' - and the module documents movement semantics separately: "
        "``normalize_movement`` 'Absent movement means zero; malformed/nonfinite/bool input is an "
        "error.' (67-70). The ``or 0.0`` therefore implements two documented rules: an unknown "
        "opening propagates as None (62-63) and an absent movement is a real zero.")
R["INV34-002049"] = (VC, _INV + " ``received`` is the movement operand adjudicated here.", None)
R["INV34-002050"] = dup("INV34-002049", "core/inventory_semantics.py:64 - the same statement, "
                                        "rule R-DEF-RETURN-NUM twice (``received`` and ``used`` "
                                        "operands of one expression)", _INV)

# --------------------------------------------------------------------------- w13 (6)
R["INV34-008826"] = (INT,
    "Zero is not a legitimate value for this parameter (a 0 pcf mud is physically meaningless), and "
    "the zero-input answer is a pinned legacy contract rather than an invention: "
    "tests/test_single_source_guard.py:107-108 states 'no input -> legacy 0 (no crash, no invented "
    "value)' and asserts ``calc_buoyancy_factor(0.0) == 0.0``. The canonical engine refuses the "
    "same input explicitly ('mud_density_ppg must be > 0', "
    "core/engineering/engines/torque_drag.py), so the wrapper's ``not x or x <= 0`` guard is "
    "equivalent to the engine's own rule for every float, including None.", None)
_W13_BF = ("The wrapped call is the canonical engine delegate, whose only documented failures are "
           "physically invalid input (``require_number`` for non-finite, and 'mud_density_ppg must "
           "be > 0' / steel-density checks in TorqueDragEngine.buoyancy_factor) and whose fallback "
           "here is the same pinned legacy zero as the no-input path "
           "(tests/test_single_source_guard.py:107-108). The caller feeds it a spin box bounded at "
           "0..200 pcf (``self._make_dspin(90, 0, 200, 1, \" pcf\")``, 3554), while the engine only "
           "raises at a mud density at or above the steel density (490 pcf) - so the branch is "
           "unreachable through the delivered UI and cannot fabricate a card. Residual (recorded, "
           "not a defect claim): if the mud-weight bound were ever raised near steel density, the "
           "0.0 fallback would render as a zero hook load instead of the engine's reason.")
R["INV34-004595"] = (INT, _W13_BF, None)
R["INV34-004597"] = dup("INV34-004595", "tabs/w13_Engineering_Calculator.py:125 - the same handler "
                                        "(second rule on the same `except Exception` line)",
                        "unreachable through the delivered spin-box range; 0.0 is the pinned legacy "
                        "answer")
R["INV34-004606"] = dup("INV34-004595", "tabs/w13_Engineering_Calculator.py:125 - the same handler "
                                        "(third rule on the same line)", "as above")
_W13_RECALC = ("The engine's refusal is the documented contract (TrajectoryEngine requires "
               "monotonic MD and detects duplicate/non-monotonic input), and the handler's response "
               "is to recompute nothing: the raw MD/inc/azi the user typed stay in the model, the "
               "derived columns are only written on success (4936-4940 / 5100-5105), and these "
               "survey lists are not persisted anywhere (no save path references "
               "``ac_offset_surveys``/``dd_surveys`` - verified by grep), so the outcome is a "
               "preview with unfilled derived columns rather than a stored wrong number. Residual "
               "(recorded, not a defect claim): the reason is not surfaced to the user and a "
               "previous successful computation's columns can remain visible next to edited raw "
               "values until a successful recompute; the engine's error is dropped. Neither is a "
               "fabricated value, and no module contract requires a message here.")
R["INV34-008222"] = (INT, _W13_RECALC + " Site: ``_ac_recalculate`` (anti-collision offset well).",
                     None)
R["INV34-008226"] = (INT, _W13_RECALC + " Site: ``_dd_recalculate_from`` (directional-drilling "
                                        "survey table).", None)

# --------------------------------------------------------------------------- w3 (2)
_W3 = ("The parameter's domain is the widget's own entry range: ``safe_val`` loads operator-entry "
       "spin boxes whose floor is a legal zero (e.g. ``self.wob_min.setRange(0, 100)``, 475) and "
       "whose 'empty' state is that same 0 (``clear_form`` sets 0), and zero is a legal WOB/RPM/"
       "torque value - so the default cannot fabricate a measurement. The same function shows the "
       "deliberate split: ``safe_opt`` carries the documented contract 'Stored value, or None when "
       "the report holds no recorded number.' (916-917) and is what the *recorded/computed* field "
       "uses (``_set_calc(self.tfa_value, safe_opt(\"tfa\"))``, 962). Residual (recorded, not a "
       "defect claim): re-saving a report whose stored value was NULL normalises that entry field to "
       "0 (a legal domain value); if the product ever needs 'not recorded' for entry fields, that is "
       "a sentinel-widget feature, not a defect in this loader.")
R["INV34-008852"] = (VC, _W3, None)
R["INV34-008876"] = dup("INV34-008852", "tabs/w3_drilling_report.py:1628 - the identical "
                                        "``safe_val`` helper in MudReportTab's load_from_dict",
                        _W3)

# --------------------------------------------------------------------------- test oracle (1)
R["INV34-011052"] = (VC,
    "A test-local reduction, and the assertion pins the sum it feeds: "
    "``total = sum(r.duration or 0 for r in rows)`` is immediately checked against "
    "``pytest.approx(24.0)`` (382) after asserting there are exactly 7 rows with the last one "
    "ending at 00:00 and a 0.5 h duration (376-380). A NULL duration would therefore make the total "
    "short of 24.0 and fail the test (it cannot mask a missing measurement), and the test's subject "
    "is the 24:00 row's storage, not the ``or 0`` idiom.", None)


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    """Exact line range of ``symbol`` from the AST (keyword-only signatures break heuristics)."""
    import ast

    parts = [p for p in (symbol or "").split(".") if p]
    name = parts[-1] if parts else ""
    tree = ast.parse(source)
    candidates = [n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not candidates:
        raise SystemExit(f"symbol {symbol!r} not found")
    if len(parts) > 1:
        owner = parts[-2]
        owned = [n for n in candidates
                 if any(isinstance(a, ast.ClassDef) and a.name == owner for a in ast.walk(tree)
                        if n in ast.walk(a))]
        candidates = owned or candidates
    node = min(candidates, key=lambda n: n.lineno)
    return node.lineno, node.end_lineno


def line_map(commit: str, path: str, current: list[str]) -> dict[int, int]:
    previous = git_show(f"{commit}^", path)
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def check(batch: list[dict]) -> list[tuple[str, str, int, int]]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int]] = []
    cache: dict[str, list[str]] = {}
    sources: dict[str, str] = {}
    maps: dict[str, dict[int, int]] = {}
    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        if path not in cache:
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            sources[path] = text
            cache[path] = text.splitlines()
        lines = cache[path]

        if 0 < line <= len(lines) and _norm(lines[line - 1]) == _norm(expected):
            continue

        commit = RECHECK_AGAINST.get(path)
        if commit is None:
            actual = lines[line - 1].strip() if 0 < line <= len(lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {actual!r}, register recorded "
                            f"{expected!r}")
            continue

        previous = git_show(f"{commit}^", path)
        if _norm(previous[line - 1]) != _norm(expected):
            problems.append(f"{record['id']}: {commit}^ has {previous[line - 1].strip()!r} at "
                            f"{path}:{line}, register recorded {expected!r}")
            continue

        if path not in maps:
            maps[path] = line_map(commit, path, lines)
        new_line = maps[path].get(line)
        start, end = symbol_body(sources[path], record.get("symbol", ""))
        if new_line is None or _norm(lines[new_line - 1]) != _norm(expected) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed")
            continue
        reanchored.append((record["id"], path, line, new_line))
    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        print("missing:", sorted({r["id"] for r in batch} - set(R)))
        print("extra:", sorted(set(R) - {r["id"] for r in batch}))
        return 1

    reanchored = check(batch)

    counts: dict[str, int] = {}
    for record in batch:
        classification = R[record["id"]][0]
        counts[classification] = counts.get(classification, 0) + 1
    classes: dict[str, int] = {}
    for record in batch:
        classes[record["p6_class"]] = classes.get(record["p6_class"], 0) + 1

    items = [{
        "id": record["id"], "file": record["file"], "line": record["line"],
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": ("tests/test_kill_sheet_casing_id_gate.py (3 tests; mutation-validated)"
                 if R[record["id"]][0] == DEF else None),
        "commit": KILL_SHEET_FIX if R[record["id"]][0] == DEF else None,
    } for record in batch]

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("mixed HIGH - " + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))
                  + " (kill-sheet canonical inputs 26 records / 13 statements, time parsing 6, "
                    "calculator wrappers 6, hydraulics 2, inventory semantics 2, report loaders 2, "
                    "one test oracle)"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [
            "INV34-001751 / INV34-007524 - core/engineering/well_control_kill_sheet.py:290 "
            "(`casing_id_in=_num(casing_id_in) or 0.0`): a required, consumed input was missing from "
            "the builder's required_raw gate, so an unfilled casing-ID field (the widget sentinel "
            "reads back as None) silently removed the annular volume - and the annular displacement "
            "strokes derived from it - from a sheet that still reported success. Fixed in ff2000a; "
            "regression tests/test_kill_sheet_casing_id_gate.py (mutation-killed: reverting the gate "
            "yields 'assert () == (\"casing_id_in\",)', a truthiness-based gate also fails). "
            "One statement, one defect, two register records."
        ],
        "new_findings": [],
        "tests": ("focused kill-sheet suite (this file + test_well_control_kill_sheet{,_cross_process,"
                  "_persistence} + test_well_control_icp_fcp_consolidation) 45 tests PASS after the "
                  "fix; the new regression file is 3/3 and mutation-validated (gate removed and "
                  "truthiness gate both fail, restored byte-identical 30d03000...5eb5f20fe); ruff "
                  "clean on both changed files"),
        "head": record_head(),
        "commit": KILL_SHEET_FIX,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_005.py"],
        "staleness": {
            "checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
            "method": ("recorded text must match the current line; the kill-sheet records (whose "
                       "gate this batch itself completed in ff2000a) are first verified against "
                       "ff2000a^ and then re-anchored through the line map derived from the real "
                       "diff (difflib equal-blocks); no record is skipped, renumbered by hand or "
                       "accepted on a snippet alone"),
            "re_anchored_items": [{"id": i, "file": f, "recorded_line": a, "current_line": b}
                                  for i, f, a, b in reanchored],
        },
        "method": ("each record read at its own site in the current tree; the deciding contract is "
                   "quoted in `evidence`; when a register record is the second rule on one "
                   "construct, the batch says so and adjudicates it once"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}, defects fixed {len(payload['defects_fixed'])}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
