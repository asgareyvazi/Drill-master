#!/usr/bin/env python3
"""Repeatable mutation run for the M141-M170 guards (DDR continuation contract, review queue, CONTEXT_BLOCKED).

Each mutant removes ONE guard in a scratch copy of the working tree and must be KILLED by the listed tests.
Engine: ``tools/quality/mutation_m46.py`` (green baseline first; an anchor that does not match exactly once is
reported INVALID, never killed). The repository is never modified.

Usage::

    python tools/quality/mutation_m141_m170.py [--json OUT] [--only ID[,ID...]]

SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

CONT = "core/ddr_continuation.py"
IQ = "core/import_quality.py"
SVC = "core/ddr_import_service.py"
PIPE = "core/ddr_import_pipeline.py"
DB = "core/database.py"
DLG = "dialogs/excel_import_dialog.py"
PROF = "core/profile_import_engine.py"
MGR = "core/managers.py"
SO = "core/save_outcome.py"
T147 = ["tests/test_m147_m152_ddr_continuation.py"]
T153 = ["tests/test_m153_context_blocked_autosave.py"]
TR = "core/engineering/tubular_reference.py"
WIO = "core/workbook_io.py"
W13 = "tabs/w13_Engineering_Calculator.py"
T157 = ["tests/test_m157_m160_tubular_reference.py"]

MUTANTS = [
    # ---- M148 continuation contract: every eligibility condition is load-bearing ----
    Mutant("M148-profile-ignored", CONT, "    if not allowed:\n        return \"The report profile",
           "    if False:\n        return \"The report profile", T147,
           "a profile that forbids continuations still attaches them"),
    Mutant("M148-header-footer-attached", CONT, "    if _HEADER_FOOTER.search(analysis.text):\n",
           "    if False:\n", T147, "a repeated header / page footer / total line is attached as activity text"),
    Mutant("M148-order-not-proven", CONT, "        if a <= b:\n", "        if False:\n", T147,
           "rows out of source order are attached to a parent below them"),
    Mutant("M148-missing-row-accepted", CONT,
           "        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (a, b)):\n",
           "        if False:\n", T147,
           "a row without a source position is attached although order cannot be proven"),
    Mutant("M148-line-break-lost", CONT, 'f"{current}\\n{text}"', 'f"{current} {text}"', T147,
           "the continuation text is glued onto the parent without its line break"),
    Mutant("M149-accept-continuation-applied", CONT,
           '            if decision in {"ACCEPT", "CONFIRMED"}:\n',
           '            if False:\n', T147, "ACCEPT on a continuation is applied instead of being refused"),
    Mutant("M148-ownership-not-reproven", CONT, "            if current is None or current.index != index:\n",
           "            if current is None:\n", T147,
           "a stale review id attaches to whichever row now sits at its position"),
    # ---- M150 safe partial import ----
    Mutant("M150-defer-made-canonical", IQ,
           '        if decision not in FINAL_REVIEW_DECISIONS and decision != "DEFER":\n',
           '        if decision not in FINAL_REVIEW_DECISIONS:\n', T147,
           "a deferred proposal is written into the canonical record"),
    Mutant("M150-partial-without-consent", DLG,
           "            if not self._ask_partial_import(pending):\n                return\n",
           "            pass\n", T147, "unresolved rows are deferred and the import proceeds without asking"),
    Mutant("M150-morning-reviews-dropped", PIPE, 'extracted.get("time_logs_morning") or []',
           "[]", T147, "morning-report continuation rows are never reviewed or attached"),
    # ---- M149 persistent review queue ----
    Mutant("M149-foreign-well-resolved", DB, "            if item is None or item.well_id != well_id:\n",
           "            if item is None:\n", T147, "a review item of another well can be decided"),
    # ---- M147 profile route: no silent merge ----
    Mutant("M147-profile-narrative-dropped", PROF, "                logs.append(record)\n                continue\n",
           "                continue\n", T147, "the profile route again drops narrative rows instead of reviewing them"),
    # ---- M153 CONTEXT_BLOCKED: guard kept, skip only hidden + clean ----
    Mutant("M153-dirty-tab-skipped", MGR,
           '            return (not ready()) and (not visible()) and getattr(widget, "is_dirty", None) is False\n',
           "            return (not ready()) and (not visible())\n", T153,
           "an edited (or unknown) hidden tab is skipped silently: held-back edits are no longer reported"),
    Mutant("M153-visible-tab-skipped", MGR,
           '            return (not ready()) and (not visible()) and getattr(widget, "is_dirty", None) is False\n',
           '            return (not ready()) and getattr(widget, "is_dirty", None) is False\n', T153,
           "a visible tab whose load failed is skipped instead of reported"),
    Mutant("M153-guard-removed", SO, "            elif callable(ready) and not ready():\n                explain",
           "            elif False:\n                explain", T153,
           "the CONTEXT_BLOCKED guard is disabled: stale widgets save into the new context"),
    Mutant("M153-explanation-missing", SO, '                    + (f" ({detail})" if detail else ""),\n',
           '                    + "",\n', T153, "CONTEXT_BLOCKED no longer says what is pending"),
    # ---- M157-M160 tubular reference library and workbook warnings ----
    Mutant("M157-published-set-mutable", TR,
           '        if ref.status != DRAFT:\n            raise TubularReferenceError(f"{ref.name} v{ref.version} is published',
           '        if False:\n            raise TubularReferenceError(f"{ref.name} v{ref.version} is published', T157,
           "items can be added to a published (immutable) reference version"),
    Mutant("M158-licence-not-required", TR, '        for name in ("manufacturer", "document", "licence"):\n',
           '        for name in ("manufacturer", "document"):\n', T157,
           "a manufacturer row from a public page is stored without an explicit licence"),
    Mutant("M157-zero-accepted", TR, "math.isfinite(value) or value <= 0:", "math.isfinite(value) or value < 0:",
           T157, "0 is stored as an engineering value instead of being refused (missing must stay unavailable)"),
    Mutant("M157-wall-contradiction-accepted", TR, "abs((od - inner) / 2.0 - wall) > 0.001",
           "abs((od - inner) / 2.0 - wall) > 1.0", T157, "contradictory OD / ID / wall values are stored"),
    Mutant("M159-draft-citable", TR, '    if row.get("set_status") != PUBLISHED or not row.get("set_fingerprint"):\n',
           "    if False:\n", T157, "a calculation can cite a draft that may still change"),
    Mutant("M159-snapshot-tamper-undetected", TR, '    if _sha(body) != snapshot.get("snapshot_fingerprint"):\n',
           "    if False:\n", T157, "a stored snapshot can be relabelled without detection"),
    Mutant("M160-dv-warning-leaks", WIO,
           "        if issubclass(item.category, UserWarning) and DATA_VALIDATION_EXTENSION in str(item.message):\n",
           "        if False:\n", T157, "the misleading openpyxl data-validation warning reaches the user again"),
    Mutant("M160-other-warnings-swallowed", WIO,
           "        warnings.warn_explicit(item.message, item.category, item.filename, item.lineno)\n",
           "        pass\n", T157, "unrelated workbook warnings are silently swallowed"),
    Mutant("M160-absent-file-warning", W13, '        logger.info("Optional DrillPipe vendor reference unavailable.',
           '        logger.warning("Optional DrillPipe vendor reference unavailable.', T157,
           "an absent optional file is logged as a fault on every start again"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
