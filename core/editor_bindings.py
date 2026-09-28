"""Explicit persistence boundaries for Save All/AutoSave (not a DB mirror).

Only registered inputs participate. Navigation, filters, export/calculation-only
views and dialogs which already commit immediately are not pending saves.
"""

from core.editor_state import EditSection
from core.save_outcome import SaveOutcome


def invoke(subject, method, *args, **kwargs):
    subject.last_save_outcome = None
    value = getattr(subject, method)(*args, **kwargs)
    detail = subject.last_save_outcome
    return detail if isinstance(detail, SaveOutcome) else value


def editor_snapshot(*roots):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QWidget,
        QTableWidget,
        QLineEdit,
        QComboBox,
        QAbstractSpinBox,
        QTextEdit,
        QPlainTextEdit,
        QAbstractButton,
    )

    def read(widget):
        if isinstance(widget, QTableWidget):
            return tuple(
                tuple(
                    read(widget.cellWidget(r, c))
                    if widget.cellWidget(r, c)
                    else (widget.item(r, c).text() if widget.item(r, c) else None)
                    for c in range(widget.columnCount())
                )
                for r in range(widget.rowCount())
            )
        if isinstance(widget, QAbstractSpinBox):
            return (widget.text(), widget.property("explicitly_edited"))
        if isinstance(widget, QLineEdit):
            return widget.text() if not widget.isReadOnly() else None
        if isinstance(widget, QComboBox):
            return (widget.currentData(), widget.currentText())
        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            return widget.toPlainText() if not widget.isReadOnly() else None
        if isinstance(widget, QAbstractButton):
            return widget.isChecked() if widget.isCheckable() else None
        return tuple(read(child) for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly))

    return tuple(read(root) for root in roots)


def validate_editor_inputs(*roots):
    from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit, QWidget

    for root in roots:
        for widget in [root, *root.findChildren(QWidget)]:
            if (
                isinstance(widget, (QAbstractSpinBox, QLineEdit))
                and not widget.isReadOnly()
                and not widget.hasAcceptableInput()
            ):
                raise ValueError(f"Invalid editor text {widget.text()!r}. Complete/correct the field before saving.")


def unsupported_editor(reason):
    raise NotImplementedError(reason)


def configure(tab):
    sections = {}
    kind = type(tab).__name__
    context_keys = (
        ("well",) if kind in ("WellInfoTab", "WellboreSchematicTab", "ProcedureWidget") else ("well", "report")
    )
    if kind in ("SectionDataWidget", "LogisticsWidget"):
        context_keys = ("well", "section", "report")

    def add(name, subject, method, *roots, reader=None, read_only=lambda: False):
        roots = roots or (subject,)
        section = EditSection(
            name,
            reader or (lambda: editor_snapshot(*roots)),
            method,
            read_only,
            validate=lambda: validate_editor_inputs(*roots),
            context=lambda: tuple(getattr(tab, f"current_{key}_id") for key in context_keys),
        )
        sections[name] = section
        subject._tracked_edit_sections = [*getattr(subject, "_tracked_edit_sections", ()), section]

    if kind in ("WellInfoTab", "DailyReportWidget"):
        add("Well" if kind == "WellInfoTab" else "Daily report", tab, tab.save_data)
    elif kind == "DrillingReportWidget":
        for name, child in (("Drilling Parameters", tab.drilling_tab), ("Mud", tab.mud_tab)):
            add(name, child, lambda child=child: invoke(child, "save_data_for_report", tab.current_report_id))
    elif kind == "DownholeWidget":
        add(
            "BHA",
            tab,
            lambda: tab.db.save_bha_report(
                tab.current_well,
                {
                    "report_id": tab.current_report_id,
                    "bha_name": tab.bha_name_input.text().strip(),
                    "bha_data": tab.bha_manager.get_all_data(),
                },
            ),
            tab.bha_table,
            tab.bha_name_input,
            read_only=lambda: getattr(tab, "_bha_legacy_read_only", False),
        )
        add(
            "Downhole Equipment",
            tab,
            lambda: tab.db.save_downhole_equipment(
                tab.current_well,
                {"report_id": tab.current_report_id, "equipment_data_json": tab.equipment_manager.get_all_data()},
            ),
            tab.equipment_table,
        )
        add(
            "Formation",
            tab,
            lambda: tab.db.save_formation_report(
                tab.current_well,
                {"report_id": tab.current_report_id, "formations": tab.formation_manager.get_all_data()},
            ),
            tab.formation_table,
        )
    elif kind == "EquipmentWidget":
        for name, child in (
            ("Rig Equipment", tab.rig_tab),
            ("Inventory", tab.inventory_tab),
            ("Drill Pipe", tab.pipe_tab),
            ("Solid Control", tab.solid_tab),
        ):
            add(name, child, lambda name=name: invoke(tab, "save_all_data", section_filter={name}))
    elif kind == "TrajectoryWidget":
        for name, child in (("Trip", tab.trip_sheet_tab), ("Survey", tab.survey_data_tab)):
            add(name, child, child.save_data)
    elif kind == "LogisticsWidget":
        child = tab.personnel_tab
        add("POB", child, child.save_pob_to_db, child.pob_table)
        add("Crew", child, child.save_crew_to_db, child.crew_table)
        add(
            "Transport note",
            child,
            child.save_transport_note,
            child.note_date,
            child.note_title,
            child.note_category,
            child.note_priority,
            child.transport_notes,
        )
        child = tab.fuel_water_tab
        fields = (
            "report_date",
            "fuel_type",
            "fuel_consumed",
            "fuel_stock",
            "fuel_received",
            "water_consumed",
            "water_stock",
            "water_received",
            "dw_consumed",
            "dw_stock",
            "dw_received",
            "fuel_camp_consumed",
            "fuel_camp_stock",
            "fuel_camp_received",
        )
        add("Fuel / Water", child, child.save_fuel_water_to_db, *(getattr(child, k) for k in fields))
        add("Bulk inventory", child, child.save_bulk_materials_to_db, child.bulk_table)
        child = tab.transport_tab
        add("Transport", child, child.save_transport_logs_to_db, child.transport_table)
    elif kind == "SafetyWidget":
        add(
            "BOP",
            tab.safety_bop_tab,
            lambda: invoke(tab.safety_bop_tab, "save_to_database", tab.current_well_id, tab.current_report_id),
        )
        add(
            "Waste",
            tab.waste_tab,
            lambda: invoke(tab.waste_tab, "save_to_database", tab.current_well_id, tab.current_report_id),
            tab.waste_tab.waste_table,
        )
    elif kind == "SectionDataWidget" and tab._tabs_ready:
        for name, child, method in (
            ("Cement", tab.cement_tab, "save_data"),
            ("Casing", tab.casing_tab, "save_data"),
            ("Tally", tab.casing_tally_tab, "save_tally_report"),
            ("Bit", tab.bit_tab, "save_data"),
        ):
            add(name, child, getattr(child, method))
        add("Failure reports", tab.failure_tab, tab.failure_tab.save_report)
    elif kind == "PlanningWidget":
        add("Lookahead", tab.lookahead_tab, tab.lookahead_tab.save_plan, tab.lookahead_tab.lookahead_table)
    elif kind == "ProcedureWidget":
        child = tab.editor_page
        general = (
            "status_combo",
            "title_edit",
            "type_combo",
            "revision_edit",
            "date_edit",
            "well_name_edit",
            "rig_name_edit",
            "field_edit",
            "objective_edit",
            "hse_edit",
            "checklist_table",
            "steps_table",
        )
        add(
            "Procedure",
            child,
            child.save_procedure,
            *(getattr(child, key) for key in general),
            *(widgets["name"] for widgets in child.approval_widgets.values()),
        )
        # These controls are not consumed by save_procedure. Do not falsely
        # acknowledge them just because the general procedure row was saved.
        unpersisted = (
            "current_depth",
            "mud_weight",
            "casing_shoe",
            "last_casing",
            "pjsm_datetime",
            "pjsm_location",
            "pjsm_conductor",
            "attendees_table",
            "topics_edit",
            "pjsm_hse",
            "action_items",
        )
        add(
            "Procedure supplementary fields",
            child,
            lambda: unsupported_editor(
                "PJSM and supplementary procedure fields have no complete persistence path in this editor. These edits remain pending; do not assume General Save stored them."
            ),
            *(getattr(child, key) for key in unpersisted),
            *(
                widget
                for widgets in child.approval_widgets.values()
                for key, widget in widgets.items()
                if key != "name"
            ),
        )
    elif kind == "WellboreSchematicTab":
        from dataclasses import asdict

        add(
            "Schematic",
            tab,
            lambda: unsupported_editor(
                "Manual schematic Save/Reload is not lossless: the current loader regenerates rather than restores saved elements. Save All did not write or acknowledge this edit; retain/export it until the round-trip path is repaired."
            ),
            reader=lambda: asdict(tab.schematic),
        )
    tab._tracked_edit_sections = list(sections.values())
    return sections
