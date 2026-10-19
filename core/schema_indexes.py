"""Secondary indexes for the SQLite schema (schema v6, M43).

Until v6 the schema had 163 foreign keys and no secondary index, so every
per-report, per-well and per-section lookup was a full table scan, and with
``PRAGMA foreign_keys=ON`` deleting a report scanned every child table.

Every entry below is justified by an access path that exists in the code (the
audit is recorded in docs/DATABASE_PERFORMANCE.md):

* REPORT_CHILD  - ``report_id`` of a ``daily_reports`` child (ON DELETE CASCADE):
  per-report loads, the revision snapshot (core/report_snapshot.py) and the
  cascade scan when a report is deleted.
* WELL_DATED    - ``(well_id, report_date)``: well-scoped loads that also filter
  or order by the report date; the composite also serves well_id-only lookups.
* WELL_SCOPE    - ``well_id`` lookups of well-scoped tables.
* SURVEY_ORDER  - ``(well_id, md)``: survey stations loaded per well ordered by MD.
* SECTION_SCOPE - ``section_id`` lookups (``daily_reports`` also orders by date).
* HIERARCHY     - project/company/wellbore/plan/procedure parent lookups.
* AUDIT         - audit trail by entity and the most-recent-first listing.

Deliberately NOT indexed: the 45 ``created_by``/``user_id`` -> users foreign
keys (no lookup filters on them; users are deactivated rather than deleted)
and low-use calculation links. Add an entry only with the query it serves.

The migration in ``DatabaseManager._apply_safe_schema_upgrades`` creates every
missing model index by name inside the migration transaction, after all column
upgrades, so fresh and upgraded databases get the same set.
"""
from __future__ import annotations

from sqlalchemy import Index

REPORT_CHILD = "report child: per-report loads, snapshot, cascade delete"
WELL_DATED = "well-scoped load filtered/ordered by report_date"
WELL_SCOPE = "well-scoped lookup"
SURVEY_ORDER = "survey stations per well ordered by MD"
SECTION_SCOPE = "section-scoped lookup"
HIERARCHY = "hierarchy parent lookup"
AUDIT = "audit trail lookup"

INDEX_PLAN: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("activity_codes", ('well_id',), WELL_SCOPE),
    ("approval_actions", ('report_id',), REPORT_CHILD),
    ("audit_logs", ('entity_type', 'entity_id'), AUDIT),
    ("audit_logs", ('timestamp',), AUDIT),
    ("bha_reports", ('report_id',), REPORT_CHILD),
    ("bha_reports", ('well_id',), WELL_SCOPE),
    ("bit_reports", ('report_id',), REPORT_CHILD),
    ("bit_reports", ('well_id',), WELL_SCOPE),
    ("bop_components", ('report_id',), REPORT_CHILD),
    ("bop_components", ('well_id',), WELL_SCOPE),
    ("bulk_materials", ('report_id',), REPORT_CHILD),
    ("bulk_materials", ('section_id',), SECTION_SCOPE),
    ("bulk_materials", ('well_id', 'report_date'), WELL_DATED),
    ("casing_reports", ('report_id',), REPORT_CHILD),
    ("casing_reports", ('section_id',), SECTION_SCOPE),
    ("casing_reports", ('well_id',), WELL_SCOPE),
    ("cement_reports", ('report_id',), REPORT_CHILD),
    ("cement_reports", ('section_id',), SECTION_SCOPE),
    ("cement_reports", ('well_id',), WELL_SCOPE),
    ("cost_records", ('well_id',), WELL_SCOPE),
    ("daily_reports", ('section_id', 'report_date'), SECTION_SCOPE),
    ("daily_reports", ('well_id', 'report_date'), WELL_DATED),
    ("daily_reports", ('wellbore_id',), HIERARCHY),
    ("downhole_equipment", ('report_id',), REPORT_CHILD),
    ("downhole_equipment", ('well_id',), WELL_SCOPE),
    ("drilling_parameters", ('report_id',), REPORT_CHILD),
    ("drilling_parameters", ('well_id', 'report_date'), WELL_DATED),
    ("equipment_logs", ('report_id',), REPORT_CHILD),
    ("equipment_logs", ('section_id',), SECTION_SCOPE),
    ("equipment_logs", ('well_id',), WELL_SCOPE),
    ("formation_reports", ('report_id',), REPORT_CHILD),
    ("formation_reports", ('well_id',), WELL_SCOPE),
    ("fuel_water_inventory", ('report_id',), REPORT_CHILD),
    ("fuel_water_inventory", ('well_id', 'report_date'), WELL_DATED),
    ("inventory_items", ('report_id',), REPORT_CHILD),
    ("inventory_items", ('well_id', 'report_date'), WELL_DATED),
    ("logistics_personnel", ('report_id',), REPORT_CHILD),
    ("logistics_personnel", ('section_id',), SECTION_SCOPE),
    ("logistics_personnel", ('well_id',), WELL_SCOPE),
    ("material_requests", ('report_id',), REPORT_CHILD),
    ("material_requests", ('section_id',), SECTION_SCOPE),
    ("material_requests", ('well_id',), WELL_SCOPE),
    ("mud_reports", ('report_id',), REPORT_CHILD),
    ("mud_reports", ('well_id', 'report_date'), WELL_DATED),
    ("npt_reports", ('report_id',), REPORT_CHILD),
    ("npt_reports", ('well_id',), WELL_SCOPE),
    ("operational_procedures", ('well_id',), WELL_SCOPE),
    ("planned_activities", ('plan_id',), HIERARCHY),
    ("planned_activities", ('section_id',), SECTION_SCOPE),
    ("planned_activities", ('well_id',), WELL_SCOPE),
    ("procedure_checklists", ('procedure_id',), HIERARCHY),
    ("procedure_steps", ('procedure_id',), HIERARCHY),
    ("projects", ('company_id',), HIERARCHY),
    ("report_revisions", ('report_id',), REPORT_CHILD),
    ("rop_analysis", ('report_id',), REPORT_CHILD),
    ("rop_analysis", ('well_id',), WELL_SCOPE),
    ("safety_reports", ('report_id',), REPORT_CHILD),
    ("safety_reports", ('well_id', 'report_date'), WELL_DATED),
    ("sections", ('well_id',), WELL_SCOPE),
    ("sections", ('wellbore_id',), HIERARCHY),
    ("service_companies", ('report_id',), REPORT_CHILD),
    ("service_companies", ('section_id',), SECTION_SCOPE),
    ("service_companies", ('well_id',), WELL_SCOPE),
    ("service_company_pob", ('report_id',), REPORT_CHILD),
    ("service_company_pob", ('section_id',), SECTION_SCOPE),
    ("service_company_pob", ('well_id',), WELL_SCOPE),
    ("service_notes", ('report_id',), REPORT_CHILD),
    ("service_notes", ('section_id',), SECTION_SCOPE),
    ("service_notes", ('well_id',), WELL_SCOPE),
    ("seven_days_lookahead", ('report_id',), REPORT_CHILD),
    ("seven_days_lookahead", ('section_id',), SECTION_SCOPE),
    ("seven_days_lookahead", ('well_id',), WELL_SCOPE),
    ("survey_points", ('report_id', 'md'), REPORT_CHILD),
    ("survey_points", ('well_id', 'md'), SURVEY_ORDER),
    ("time_depth_data", ('report_id',), REPORT_CHILD),
    ("time_depth_data", ('well_id',), WELL_SCOPE),
    ("time_logs_24h", ('report_id',), REPORT_CHILD),
    ("time_logs_morning", ('report_id',), REPORT_CHILD),
    ("trajectory_calculations", ('report_id',), REPORT_CHILD),
    ("trajectory_calculations", ('well_id',), WELL_SCOPE),
    ("trajectory_plots", ('report_id',), REPORT_CHILD),
    ("transport_logs", ('report_id',), REPORT_CHILD),
    ("transport_logs", ('well_id',), WELL_SCOPE),
    ("transport_notes", ('report_id',), REPORT_CHILD),
    ("transport_notes", ('well_id',), WELL_SCOPE),
    ("trip_sheet_entries", ('report_id',), REPORT_CHILD),
    ("trip_sheet_entries", ('section_id',), SECTION_SCOPE),
    ("trip_sheet_entries", ('well_id',), WELL_SCOPE),
    ("waste_records", ('report_id',), REPORT_CHILD),
    ("waste_records", ('well_id',), WELL_SCOPE),
    ("well_plans", ('well_id',), WELL_SCOPE),
    ("wellbore_schematics", ('report_id',), REPORT_CHILD),
    ("wellbore_schematics", ('well_id', 'report_date'), WELL_DATED),
    ("wellbores", ('well_id',), WELL_SCOPE),
    ("wells", ('project_id',), HIERARCHY),
)


def index_name(table: str, columns: tuple[str, ...]) -> str:
    return "ix_" + table + "_" + "_".join(columns)


def install(metadata) -> list:
    """Attach the planned indexes to ``metadata`` (idempotent)."""
    created = []
    for table_name, columns, _reason in INDEX_PLAN:
        table = metadata.tables[table_name]
        name = index_name(table_name, columns)
        if any(index.name == name for index in table.indexes):
            continue
        created.append(Index(name, *(table.c[column] for column in columns)))
    return created
