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

Trigger names carry a version suffix; changing a rule means a new name (old
databases get the new trigger on their next start, and the old one is dropped).
Installed on every start inside the atomic schema migration
(``DatabaseManager._apply_safe_schema_upgrades``).
"""

from __future__ import annotations

GUARD_VERSION = 1
PLAN_STATUS_TRANSITIONS = {
    "draft": ("draft", "approved", "archived"),
    "approved": ("approved", "archived"),
    "archived": ("archived",),
}


def _frozen(columns) -> str:
    return " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in columns)


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
_SURVEY_FROZEN = ("id", "well_id", "revision", "mode", "source_type", "source_ref", "source_unit",
                  "azimuth_reference", "depth_datum", "stations_json", "station_count", "stations_sha256",
                  "results_json", "warnings_json", "method", "method_version", "note", "created_at")


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
    return {
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
        f"trg_survey_revision_immutable_v{v}": (
            f"CREATE TRIGGER trg_survey_revision_immutable_v{v} BEFORE UPDATE ON survey_revisions "
            f"WHEN {survey_change} BEGIN SELECT RAISE(ABORT, "
            "'survey_revisions: a saved survey revision is immutable'); END"),
        f"trg_calculation_source_link_immutable_v{v}": (
            f"CREATE TRIGGER trg_calculation_source_link_immutable_v{v} BEFORE UPDATE ON calculation_source_links "
            f"WHEN {link_change} BEGIN SELECT RAISE(ABORT, "
            "'calculation_source_links: a lineage record is immutable'); END"),
    }


_TABLE_OF = {"trg_plan_revision": "directional_plan_revisions", "trg_calculation_case": "calculation_cases",
             "trg_calculation_source_link": "calculation_source_links", "trg_survey_revision": "survey_revisions"}


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
