#!/usr/bin/env python3
"""M117 - user-journey index: every journey A-Z cites the tests that walk it, and each citation's level is
COMPUTED from the test source, not declared.

A cited test is **widget** level when the test function, or a fixture / helper defined in the same file that it
reaches (transitively), uses a name imported from ``tabs``, ``dialogs``, ``main_window`` or
``PySide6.QtWidgets`` (module-level or local import), or references a module-level string that is a child
script importing them (subprocess journeys). Otherwise it is **service** level. A citation that does not
resolve to a test function is **missing**.

``docs/engineering/M117_USER_JOURNEYS.md`` holds the journey table between ``<!-- journeys:begin -->`` and
``<!-- journeys:end -->``; ``--write`` regenerates it, ``--check`` fails when it is stale.
SYNTHETIC test data only; offscreen Linux tests - not a Windows desktop or field acceptance.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[2]
DOC = Path("docs/engineering/M117_USER_JOURNEYS.md")
BEGIN, END = "<!-- journeys:begin -->", "<!-- journeys:end -->"
WIDGET_MODULES = ("tabs", "dialogs", "main_window", "PySide6.QtWidgets")
SCRIPT_WIDGET_IMPORT = re.compile(r"(?:from|import)\s+(?:tabs|dialogs|main_window|PySide6\.QtWidgets)\b")

#: journey letter -> (title, [citations "tests/file.py::test_name"])
JOURNEYS: Dict[str, tuple] = {
    "A": ("Context selection reaches every tab, no leak", [
        "tests/test_m102_context_probes.py::test_switch_to_another_well_leaves_no_alpha_value_anywhere",
        "tests/test_m102_context_probes.py::test_every_tab_receives_the_full_context",
    ]),
    "B": ("Async job and a context switch", [
        "tests/test_m103_context_jobs.py::test_oa_switch_during_the_job_shows_nothing_of_either_well",
        "tests/test_m103_context_jobs.py::test_oa_close_during_the_job_joins_the_worker",
    ]),
    "C": ("DDR manual edit, save and reload", [
        "tests/test_m52_ddr_manual_edit.py::test_a_reordered_time_log_survives_save_and_reload",
    ]),
    "D": ("DDR import cancel saves nothing", [
        "tests/test_import_dialog_reentrancy.py::test_preview_cancel_persists_nothing",
        "tests/test_m111_isolated_parse.py::test_cancel_during_an_isolated_parse_saves_nothing_and_stops_the_child",
    ]),
    "E": ("Source file changed during preview", [
        "tests/test_m84_ddr_identity_cleanup.py::test_a_file_changed_during_preview_is_never_saved",
    ]),
    "F": ("Survey reference and datum declared", [
        "tests/test_m85_survey_references.py::test_panel_requires_declaration_and_converts_with_explicit_values",
    ]),
    "G": ("Survey integrity: tampered results refused", [
        "tests/test_m117_widget_journeys.py::test_journey_g_a_tampered_survey_is_shown_as_such_and_refused_for_use",
    ]),
    "H": ("Azimuth transform as a new revision", [
        "tests/test_m85_survey_references.py::test_panel_requires_declaration_and_converts_with_explicit_values",
    ]),
    "I": ("Multi-segment plan through all targets", [
        "tests/test_m106_multi_segment_solver.py::test_designer_panel_solves_through_all_targets_and_an_s_profile",
    ]),
    "J": ("Infeasible plan explained, not approximated", [
        "tests/test_m106_multi_segment_solver.py::test_designer_panel_solves_through_all_targets_and_an_s_profile",
    ]),
    "K": ("Compare only in the same reference/scope", [
        "tests/test_m105_survey_references.py::test_the_compare_panel_refuses_a_plan_in_another_reference_and_labels_undeclared_ones",
        "tests/test_m108_history_coverage.py::test_history_tab_compare_shows_the_full_field_table",
    ]),
    "L": ("W13 calculation saved and re-run", [
        "tests/test_m87_w13_contracts.py::test_bit_case_save_reopen_rerun_clone_export_and_verify",
        "tests/test_m107_w13_contracts.py::test_balanced_plug_parity",
    ]),
    "M": ("Legacy record NOT_REPRODUCIBLE", [
        "tests/test_m117_widget_journeys.py::test_journey_m_a_legacy_record_is_not_reproducible_in_the_history_tab",
    ]),
    "N": ("Lineage navigation in history", [
        "tests/test_m88_history_lineage.py::test_history_tab_opens_a_linked_record_on_another_page",
        "tests/test_m70_verification_lineage.py::test_history_tab_lineage_navigation",
    ]),
    "O": ("Architecture to casing with lineage", [
        "tests/test_m89_architecture_casing_cement.py::test_w13_casing_from_architecture_reaches_history_with_lineage",
    ]),
    "P": ("Cement worksheet re-run as a linked case", [
        "tests/test_m109_cement_worksheet.py::test_a_rerun_is_stored_as_a_new_linked_case_and_the_original_is_unchanged",
    ]),
    "Q": ("Wellbore-scoped operational analysis", [
        "tests/test_m102_context_probes.py::test_wellbore_reaches_every_tab_and_resets_on_a_well_switch",
        "tests/test_m104_operational_kpis.py::test_the_panel_shows_the_kpi_register_first",
    ]),
    "R": ("Operational analysis drill-down", [
        "tests/test_m94_e2e_journeys.py::test_journey_context_to_operational_analysis_drilldown_and_switch",
        "tests/test_m91_operational_analysis.py::test_w12_page_refresh_drilldown_invalidation_and_export",
    ]),
    "S": ("Plan vs actual in scope", [
        "tests/test_m55_directional.py::test_the_viewer_sends_a_designed_plan_to_plan_vs_actual",
    ]),
    "T": ("Single report export (W11)", [
        "tests/test_m94_e2e_journeys.py::test_journey_report_export_through_w11_carries_the_selected_well_only",
    ]),
    "U": ("Multi-report professional workbooks", [
        "tests/test_m117_widget_journeys.py::test_journey_u_w11_writes_one_professional_workbook_per_report",
    ]),
    "V": ("Method catalogue (read-only)", [
        "tests/test_m92_method_catalogue.py::test_help_menu_opens_a_read_only_catalogue",
    ]),
    "W": ("RTL and LTR", [
        "tests/test_m94_e2e_journeys.py::test_journey_persian_well_report_right_to_left",
        "tests/test_m53_dashboard.py::test_dashboard_is_english_and_left_to_right_even_in_an_rtl_application",
    ]),
    "X": ("Offline use", [
        "tests/test_m117_widget_journeys.py::test_journey_x_the_documents_tab_works_with_no_network",
    ]),
    "Y": ("Backup and restore", [
        "tests/test_db_maintenance_ui.py::test_backup_and_restore_ui_flow_in_subprocess",
    ]),
    "Z": ("Delete isolation", [
        "tests/test_m117_widget_journeys.py::test_journey_z_deleting_one_well_leaves_every_other_well_intact",
    ]),
}


def _is_widget_module(module: Optional[str]) -> bool:
    return bool(module) and any(module == m or module.startswith(m + ".") for m in WIDGET_MODULES)


#: an application object alone is not a user-facing widget
NOT_A_WIDGET = {"QApplication"}


def _widget_names(tree: ast.AST) -> Set[str]:
    """Names bound to widget modules/classes (``QApplication`` excluded)."""
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if _is_widget_module(node.module):
                names.update(a.asname or a.name for a in node.names if a.name not in NOT_A_WIDGET)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_widget_module(alias.name) and not alias.name.startswith("PySide6"):
                    names.add((alias.asname or alias.name).split(".")[0])
    return names


def _qtwidgets_aliases(tree: ast.AST) -> Set[str]:
    """Aliases of the ``PySide6.QtWidgets`` module itself (``from PySide6 import QtWidgets``)."""
    out: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "PySide6":
            out.update(a.asname or a.name for a in node.names if a.name == "QtWidgets")
        elif isinstance(node, ast.Import):
            out.update(a.asname for a in node.names if a.name == "PySide6.QtWidgets" and a.asname)
    return out


def _uses_module_widget(node: ast.AST, aliases: Set[str]) -> bool:
    """``QtWidgets.X`` with X a widget class (not ``QApplication``)."""
    return any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in aliases
               and n.attr not in NOT_A_WIDGET for n in ast.walk(node))


def _script_strings(tree: ast.Module) -> Set[str]:
    out = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):                       # X = "..." or X = textwrap.dedent("...")
            strings = [n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if any(SCRIPT_WIDGET_IMPORT.search(text) for text in strings):
                out.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return out


def classify(path: Path, test_name: str) -> str:
    """'widget', 'service' or 'missing' for one test function in ``path``."""
    if not path.exists():
        return "missing"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if test_name not in functions:
        return "missing"
    widget = _widget_names(tree) | _script_strings(tree)
    aliases = _qtwidgets_aliases(tree)
    seen: Set[str] = set()
    todo: List[str] = [test_name]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        node = functions[name]
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        used |= {a.arg for a in node.args.args}                    # fixtures requested by parameter name
        if used & widget or _widget_names(node) or _uses_module_widget(node, aliases | _qtwidgets_aliases(node)):
            return "widget"
        todo.extend(u for u in used if u in functions and u not in seen)
    return "service"


def evaluate(root: Path = ROOT) -> Dict[str, dict]:
    result = {}
    for letter, (title, citations) in JOURNEYS.items():
        levels = {}
        for citation in citations:
            file_part, _, test_name = citation.partition("::")
            levels[citation] = classify(root / file_part, test_name)
        if not citations or "missing" in levels.values():
            level = "missing"
        else:
            level = "widget" if "widget" in levels.values() else "service"
        result[letter] = {"title": title, "citations": levels, "level": level}
    return result


def table(result: Dict[str, dict]) -> str:
    lines = [BEGIN, "", "| Journey | Level | Tests (computed level) |", "|---|---|---|"]
    for letter, entry in result.items():
        cites = "<br>".join(f"`{c}` ({lvl})" for c, lvl in entry["citations"].items())
        lines.append(f"| {letter} — {entry['title']} | {entry['level']} | {cites} |")
    widget = sum(1 for e in result.values() if e["level"] == "widget")
    lines += ["", f"Journeys walked through real widgets: {widget} of {len(result)}.", "", END]
    return "\n".join(lines)


def _replace(text: str, block: str) -> str:
    start, end = text.index(BEGIN), text.index(END) + len(END)
    return text[:start] + block + text[end:]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    result = evaluate()
    block = table(result)
    doc = ROOT / DOC
    if args.write:
        doc.write_text(_replace(doc.read_text(encoding="utf-8"), block), encoding="utf-8")
    if args.check and _replace(doc.read_text(encoding="utf-8"), block) != doc.read_text(encoding="utf-8"):
        print("journey table is stale: run tools/quality/journey_index.py --write")
        return 1
    for letter, entry in result.items():
        print(f"{letter} {entry['level']:8s} {entry['title']}")
    return 0 if all(e["level"] != "missing" for e in result.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
