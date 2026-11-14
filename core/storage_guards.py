"""M70: storage-level immutability guards (SQLite triggers).

The ORM authorization hooks (``core.authorization``) only apply to enforced
sessions. Engineering history must stay immutable for *every* writer — ORM
unit-of-work, ORM bulk ``update()``, Core statements and raw SQL — so the
history tables also carry ``BEFORE UPDATE`` triggers:

* ``directional_plan_revisions``: every column except ``status`` is frozen;
  ``status`` may only move draft → approved → archived (draft → archived too);
  an archived revision can never change status again.
* ``calculation_cases`` and ``calculation_source_links``: no column changes.

Foreign keys declared ``ON DELETE SET NULL`` fire an UPDATE on the child row.
That one change is allowed only when the referenced row really no longer
exists, so deleting a wellbore, a parent revision or a user keeps working while
a direct "set it to NULL" is still rejected.

M96 closed two paths that bypassed the UPDATE guards (found by the persistence audit):

* ``INSERT OR REPLACE`` (and ``REPLACE INTO``) on an existing id or unique key deleted the stored row and
  inserted a new one - an immutable result could be overwritten.  ``BEFORE INSERT`` guards reject an insert
  whose id or unique key already exists (BEFORE triggers run before REPLACE's conflict deletion).
* A direct ``DELETE`` of a single history row.  ``BEFORE DELETE`` guards allow a delete only when the owning
  row is already gone - i.e. the ``ON DELETE CASCADE`` of a deleted well / case, which SQLite runs after the
  parent row is removed (none of these tables has an ORM cascade).  Well-less (global) calculation cases can
  therefore never be deleted.

M136 made ``audit_logs`` append-only for every writer (the ORM policy already refused UPDATE/DELETE in enforced
sessions only): ``BEFORE UPDATE`` and ``BEFORE DELETE`` always abort, and ``INSERT OR REPLACE`` on an existing id
is rejected. No application path updates or deletes an audit record. Limit: anyone who can write the database
file can drop the triggers — tamper evidence against file access needs an external key (owner gate).

Trigger names carry a version suffix; changing a rule means a new name (old
databases get the new trigger on their next start, and the old one is dropped).
Installed on every start inside the atomic schema migration
(``DatabaseManager._apply_safe_schema_upgrades``).
"""

from __future__ import annotations

GUARD_VERSION = 1
#: M116 (D32): ``results_sha256`` (added by M105) was not in the frozen list, so the recorded hash of the derived
#: results could be rewritten together with tampered results. Version 2 freezes it; older databases get the v2
#: trigger on their next start and the v1 trigger is dropped (``install``).
SURVEY_GUARD_VERSION = 2
AUDIT_GUARD_VERSION = 1
#: M189: a PUBLISHED tubular reference set and its items are immutable at the storage layer too (the application
#: refused changes since M157, raw SQL did not). Drafts stay editable; a published set is never deleted.
TUBULAR_GUARD_VERSION = 1
_TUBULAR_SET_FROZEN = ("id", "name", "version", "status", "content_fingerprint", "notes", "created_at",
                       "published_at")
PLAN_STATUS_TRANSITIONS = {
    "draft": ("draft", "approved", "archived"),
    "approved": ("approved", "archived"),
    "archived": ("archived",),
}


def _frozen(columns) -> str:
    return " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in columns)


_ARCH_FROZEN = ("id", "well_id", "revision", "components_json", "component_count", "components_sha256",
                "validation_json", "schema_version", "note", "created_at")


def _nullable_reference(column: str, table: str) -> str:
    """Changed, and not the FK ``SET NULL`` action for a row that is gone."""
    return (f"(NEW.{column} IS NOT OLD.{column} AND NOT (NEW.{column} IS NULL AND "
            f"NOT EXISTS (SELECT 1 FROM {table} WHERE id = OLD.{column})))")


def _transition_violation() -> str:
    allowed = " OR ".join(
        f"(OLD.status = '{old}' AND NEW.status IN ({', '.join(repr(n) for n in new)}))"
        for old, new in PLAN_STATUS_TRANSITIONS.items())
    return f"NEW.status IS NOT OLD.status AND NOT ({allowed})"


_PLAN_FROZEN = ("id", "well_id", "plan_key", "name", "revision", "method", "method_version",
                "inputs", "results", "note", "created_at")
_CASE_FROZEN = ("id", "well_id", "calculator", "name", "method", "method_version", "inputs",
                "results", "note", "created_at")
_LINK_FROZEN = ("id", "case_id", "source_table", "source_id", "source_well_id", "source_method",
                "source_method_version", "recalc_method", "recalc_method_version",
                "verification_status", "method_changed", "link_type", "created_at")
#: M123 (D6): an audited MSE lineage repair. ``report_id`` may only be cleared (the D33 report-delete unlink, which
#: runs while the report row still exists) and ``wellbore_id`` only by the FK ``SET NULL`` of a deleted wellbore;
#: ``value_label`` keeps the repaired value readable afterwards.
_MSE_REPAIR_FROZEN = ("id", "mse_calculation_id", "well_id", "field", "md_m", "md_entered_value", "md_entered_unit",
                      "value_label", "before_value", "evidence", "reason", "confirmed_by", "confirmed_at",
                      "method_version")
#: M134: an audited NPT reconciliation decision; every column is frozen (the row ids are evidence, not references).
_NPT_DECISION_FROZEN = ("id", "well_id", "register_ids_json", "time_log_ids_json", "rows_sha256", "decision",
                        "group_label", "evidence", "reason", "confirmed_by", "confirmed_at", "method_version")
#: M178: a saved trajectory view revision; only the nullable references may be cleared by their FK SET NULL.
_VIEW_FROZEN = ("id", "well_id", "view_key", "revision", "action", "status", "name", "source_kind",
                "source_report_id", "source_sha256", "settings_json", "stations_json", "station_count",
                "stations_sha256", "trajectory_json", "method", "method_version", "note", "created_at")
_SURVEY_FROZEN = ("id", "well_id", "revision", "mode", "source_type", "source_ref", "source_unit",
                  "azimuth_reference", "depth_datum", "stations_json", "station_count", "stations_sha256",
                  "results_json", "results_sha256", "warnings_json", "method", "method_version", "note",
                  "created_at")


def trigger_statements() -> dict[str, str]:
    """Trigger name → CREATE statement, for the tables that exist in the model."""
    v = GUARD_VERSION
    plan_change = " OR ".join([
        _frozen(_PLAN_FROZEN),
        _nullable_reference("wellbore_id", "wellbores"),
        _nullable_reference("parent_id", "directional_plan_revisions"),
        _nullable_reference("created_by", "users"),
    ])
    case_change = " OR ".join([
        _frozen(_CASE_FROZEN),
        _nullable_reference("wellbore_id", "wellbores"),
        _nullable_reference("parent_id", "calculation_cases"),
        _nullable_reference("created_by", "users"),
    ])
    link_change = " OR ".join([
        _frozen(_LINK_FROZEN),
        _nullable_reference("source_wellbore_id", "wellbores"),
    ])
    survey_change = " OR ".join([
        _frozen(_SURVEY_FROZEN),
        _nullable_reference("wellbore_id", "wellbores"),
        _nullable_reference("parent_id", "survey_revisions"),
        _nullable_reference("created_by", "users"),
    ])
    architecture_change = " OR ".join([
        _frozen(_ARCH_FROZEN),
        _nullable_reference("wellbore_id", "wellbores"),
        _nullable_reference("survey_revision_id", "survey_revisions"),
        _nullable_reference("parent_id", "well_architecture_revisions"),
        _nullable_reference("created_by", "users"),
    ])
    view_change = " OR ".join([
        _frozen(_VIEW_FROZEN),
        _nullable_reference("wellbore_id", "wellbores"),
        _nullable_reference("parent_id", "trajectory_view_revisions"),
        _nullable_reference("survey_revision_id", "survey_revisions"),
        _nullable_reference("created_by", "users"),
    ])
    repair_change = " OR ".join([
        _frozen(_MSE_REPAIR_FROZEN),
        _nullable_reference("wellbore_id", "wellbores"),
        "(NEW.report_id IS NOT OLD.report_id AND NEW.report_id IS NOT NULL)",
    ])
    guards = {
        f"trg_plan_revision_immutable_v{v}": (
            f"CREATE TRIGGER trg_plan_revision_immutable_v{v} BEFORE UPDATE ON directional_plan_revisions "
            f"WHEN {plan_change} BEGIN SELECT RAISE(ABORT, "
            "'directional_plan_revisions: a saved revision is immutable (only status may change)'); END"),
        f"trg_plan_revision_status_v{v}": (
            f"CREATE TRIGGER trg_plan_revision_status_v{v} BEFORE UPDATE OF status ON directional_plan_revisions "
            f"WHEN {_transition_violation()} BEGIN SELECT RAISE(ABORT, "
            "'directional_plan_revisions: status transition not allowed'); END"),
        f"trg_calculation_case_immutable_v{v}": (
            f"CREATE TRIGGER trg_calculation_case_immutable_v{v} BEFORE UPDATE ON calculation_cases "
            f"WHEN {case_change} BEGIN SELECT RAISE(ABORT, "
            "'calculation_cases: a saved case is immutable'); END"),
        f"trg_survey_revision_immutable_v{SURVEY_GUARD_VERSION}": (
            f"CREATE TRIGGER trg_survey_revision_immutable_v{SURVEY_GUARD_VERSION} BEFORE UPDATE ON survey_revisions "
            f"WHEN {survey_change} BEGIN SELECT RAISE(ABORT, "
            "'survey_revisions: a saved survey revision is immutable'); END"),
        f"trg_well_architecture_immutable_v{v}": (
            f"CREATE TRIGGER trg_well_architecture_immutable_v{v} BEFORE UPDATE ON well_architecture_revisions "
            f"WHEN {architecture_change} BEGIN SELECT RAISE(ABORT, "
            "'well_architecture_revisions: a saved architecture revision is immutable'); END"),
        f"trg_calculation_source_link_immutable_v{v}": (
            f"CREATE TRIGGER trg_calculation_source_link_immutable_v{v} BEFORE UPDATE ON calculation_source_links "
            f"WHEN {link_change} BEGIN SELECT RAISE(ABORT, "
            "'calculation_source_links: a lineage record is immutable'); END"),
        f"trg_mse_lineage_repair_immutable_v{v}": (
            f"CREATE TRIGGER trg_mse_lineage_repair_immutable_v{v} BEFORE UPDATE ON mse_lineage_repairs "
            f"WHEN {repair_change} BEGIN SELECT RAISE(ABORT, "
            "'mse_lineage_repairs: an audited lineage repair is immutable'); END"),
        f"trg_npt_event_decision_immutable_v{v}": (
            f"CREATE TRIGGER trg_npt_event_decision_immutable_v{v} BEFORE UPDATE ON npt_event_decisions "
            f"WHEN {_frozen(_NPT_DECISION_FROZEN)} BEGIN SELECT RAISE(ABORT, "
            "'npt_event_decisions: an audited decision is immutable'); END"),
        f"trg_trajectory_view_immutable_v{v}": (
            f"CREATE TRIGGER trg_trajectory_view_immutable_v{v} BEFORE UPDATE ON trajectory_view_revisions "
            f"WHEN {view_change} BEGIN SELECT RAISE(ABORT, "
            "'trajectory_view_revisions: a saved view revision is immutable'); END"),
        **_tubular_guards(),
        f"trg_audit_log_append_only_v{AUDIT_GUARD_VERSION}": (
            f"CREATE TRIGGER trg_audit_log_append_only_v{AUDIT_GUARD_VERSION} BEFORE UPDATE ON audit_logs "
            "BEGIN SELECT RAISE(ABORT, 'audit_logs: an audit record is append-only'); END"),
    }
    guards.update(_insert_and_delete_guards())
    return guards


def _tubular_guards() -> dict[str, str]:
    t = TUBULAR_GUARD_VERSION
    set_change = " OR ".join([_frozen(_TUBULAR_SET_FROZEN), _nullable_reference("created_by", "users")])
    published = "EXISTS (SELECT 1 FROM tubular_reference_sets WHERE id = {}.set_id AND status = 'PUBLISHED')"
    return {
        f"trg_tubular_set_frozen_v{t}": (
            f"CREATE TRIGGER trg_tubular_set_frozen_v{t} BEFORE UPDATE ON tubular_reference_sets "
            f"WHEN OLD.status = 'PUBLISHED' AND ({set_change}) BEGIN SELECT RAISE(ABORT, "
            "'tubular_reference_sets: a published reference set is immutable'); END"),
        f"trg_tubular_set_nodelete_v{t}": (
            f"CREATE TRIGGER trg_tubular_set_nodelete_v{t} BEFORE DELETE ON tubular_reference_sets "
            "WHEN OLD.status = 'PUBLISHED' BEGIN SELECT RAISE(ABORT, "
            "'tubular_reference_sets: a published reference set is never deleted'); END"),
        f"trg_tubular_item_frozen_v{t}": (
            f"CREATE TRIGGER trg_tubular_item_frozen_v{t} BEFORE UPDATE ON tubular_reference_items "
            f"WHEN {published.format('OLD')} OR {published.format('NEW')} BEGIN SELECT RAISE(ABORT, "
            "'tubular_reference_items: an item of a published set is immutable'); END"),
        f"trg_tubular_item_noinsert_v{t}": (
            f"CREATE TRIGGER trg_tubular_item_noinsert_v{t} BEFORE INSERT ON tubular_reference_items "
            f"WHEN {published.format('NEW')} BEGIN SELECT RAISE(ABORT, "
            "'tubular_reference_items: a published set takes no new items'); END"),
        f"trg_tubular_item_nodelete_v{t}": (
            f"CREATE TRIGGER trg_tubular_item_nodelete_v{t} BEFORE DELETE ON tubular_reference_items "
            f"WHEN {published.format('OLD')} BEGIN SELECT RAISE(ABORT, "
            "'tubular_reference_items: an item of a published set is never deleted'); END"),
    }


# prefix -> (table, (constraint name, unique key) pairs besides id, SQL condition under which a DELETE is the
# owner's cascade)
_OWNED = {
    "trg_plan_revision": ("directional_plan_revisions", (("uq_directional_plan_revision", ("plan_key", "revision")),),
                          "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    "trg_calculation_case": ("calculation_cases", (),
                             "OLD.well_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    "trg_calculation_source_link": ("calculation_source_links", (),
                                    "NOT EXISTS (SELECT 1 FROM calculation_cases WHERE id = OLD.case_id) OR "
                                    "(OLD.source_well_id IS NOT NULL AND "
                                    "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.source_well_id))"),
    "trg_survey_revision": ("survey_revisions", (("uq_survey_revision", ("well_id", "revision")),),
                            "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    "trg_well_architecture": ("well_architecture_revisions",
                              (("uq_well_architecture_revision", ("well_id", "revision")),),
                              "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    "trg_mse_lineage_repair": ("mse_lineage_repairs", (),
                               "NOT EXISTS (SELECT 1 FROM mse_calculations WHERE id = OLD.mse_calculation_id) OR "
                               "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    "trg_npt_event_decision": ("npt_event_decisions", (), "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    "trg_trajectory_view": ("trajectory_view_revisions",
                            (("uq_trajectory_view_revision", ("view_key", "revision")),),
                            "NOT EXISTS (SELECT 1 FROM wells WHERE id = OLD.well_id)"),
    # M136: an audit record has no owner whose deletion may take it along - never deleted ("0" = never).
    "trg_audit_log": ("audit_logs", (), "0"),
}
INSERT_GUARD_VERSION = 1
DELETE_GUARD_VERSION = 1


def _insert_and_delete_guards() -> dict[str, str]:
    out = {}
    for prefix, (table, unique_keys, owner_gone) in _OWNED.items():
        name = f"{prefix}_noreplace_v{INSERT_GUARD_VERSION}"
        out[name] = (f"CREATE TRIGGER {name} BEFORE INSERT ON {table} "
                     f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) "
                     f"BEGIN SELECT RAISE(ABORT, '{table}: a stored record cannot be replaced'); END")
        for constraint, key in unique_keys:
            # Same wording as SQLite's own constraint error, so callers that report a concurrent revision on
            # a UNIQUE clash keep doing so (the plain INSERT used to fail on the constraint itself).
            match = " AND ".join(f"{c} = NEW.{c}" for c in key)
            name = f"{prefix}_nodupkey_v{INSERT_GUARD_VERSION}"
            out[name] = (f"CREATE TRIGGER {name} BEFORE INSERT ON {table} "
                         f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {match}) "
                         f"BEGIN SELECT RAISE(ABORT, 'UNIQUE constraint failed: {constraint} "
                         f"(a stored revision cannot be replaced)'); END")
        name = f"{prefix}_nodelete_v{DELETE_GUARD_VERSION}"
        out[name] = (f"CREATE TRIGGER {name} BEFORE DELETE ON {table} WHEN NOT ({owner_gone}) "
                     f"BEGIN SELECT RAISE(ABORT, '{table}: a stored record is deleted only with its owner'); END")
    return out


_TABLE_OF = {"trg_plan_revision": "directional_plan_revisions", "trg_calculation_case": "calculation_cases",
             "trg_calculation_source_link": "calculation_source_links", "trg_survey_revision": "survey_revisions",
             "trg_well_architecture": "well_architecture_revisions",
             "trg_mse_lineage_repair": "mse_lineage_repairs", "trg_npt_event_decision": "npt_event_decisions",
             "trg_trajectory_view": "trajectory_view_revisions", "trg_audit_log": "audit_logs",
             "trg_tubular_set": "tubular_reference_sets", "trg_tubular_item": "tubular_reference_items"}


def install(raw) -> list[str]:
    """Create missing guard triggers on a raw sqlite3 connection (inside the caller's transaction).

    Older versions of a guard (same prefix, other ``_vN``) are dropped. Returns
    the names created.
    """
    created = []
    existing = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
    tables = {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    wanted = trigger_statements()
    for name, statement in wanted.items():
        prefix = name.rsplit("_v", 1)[0]
        table = next(t for p, t in _TABLE_OF.items() if prefix.startswith(p))
        if table not in tables:
            continue
        for old in sorted(existing):
            if old.startswith(prefix + "_v") and old not in wanted:
                raw.execute(f'DROP TRIGGER "{old}"')
        if name not in existing:
            raw.execute(statement)
            created.append(name)
    return created


def installed(raw) -> set[str]:
    return {row[0] for row in raw.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()}
