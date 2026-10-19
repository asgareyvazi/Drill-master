"""Read-only audit of persisted monetary Float columns (M43, owner-gated migration).

Prepares facts for the owner decisions in docs/MONEY_MIGRATION.md; it never
writes. The database is opened with ``mode=ro`` and the report contains only
counts and currency codes, never amounts, descriptions, vendors or names.

    python tools/money/money_audit.py --db <copy-of-database> [--scale 2] [--output report.json]

Run it against a COPY of the database (backup first, see the migration doc).
"""
from __future__ import annotations

import argparse
import decimal
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import sqlite_connection  # noqa: E402
from core.cost_semantics import canonical_variance, normalize_currency  # noqa: E402
from core.engineering.result import EngineeringError  # noqa: E402
from core.money import to_decimal, to_minor_units  # noqa: E402

# Confirmed monetary columns (table, column, currency column or None).
MONEY_COLUMNS = (
    ("cost_records", "planned_cost", "currency"),
    ("cost_records", "actual_cost", "currency"),
    ("cost_records", "variance", "currency"),
    ("projects", "budget", "currency"),
    ("npt_reports", "cost_impact", None),
)


def _columns(connection, table):
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _audit_column(connection, table, column, currency_column, scale):
    present = _columns(connection, table)
    if column not in present:
        return {"status": "absent"}
    select_currency = f', "{currency_column}"' if currency_column in present else ", NULL"
    stats = {"status": "present", "rows": 0, "null": 0, "storage_types": {}, "non_finite": 0,
             "invalid": 0, "negative": 0, f"inexact_at_scale_{scale}": 0, "out_of_range": 0,
             "currencies": {}, "currency_unknown": 0}
    query = f'SELECT "{column}", typeof("{column}"){select_currency} FROM "{table}"'
    for value, storage, currency in connection.execute(query):
        stats["rows"] += 1
        stats["storage_types"][storage] = stats["storage_types"].get(storage, 0) + 1
        code = normalize_currency(currency) if currency_column else None
        if code:
            stats["currencies"][code] = stats["currencies"].get(code, 0) + 1
        else:
            stats["currency_unknown"] += 1
        if value is None:
            stats["null"] += 1
            continue
        if isinstance(value, float) and not math.isfinite(value):
            stats["non_finite"] += 1
            continue
        try:
            amount = to_decimal(value)
        except EngineeringError:
            stats["invalid"] += 1  # e.g. non-numeric text stored in a REAL column
            continue
        if amount < 0:
            stats["negative"] += 1
        try:
            _minor, exact = to_minor_units(amount, scale=scale, rounding=decimal.ROUND_HALF_EVEN)
        except EngineeringError:
            stats["out_of_range"] += 1
            continue
        if not exact:
            stats[f"inexact_at_scale_{scale}"] += 1
    return stats


def _variance_mismatches(connection):
    present = _columns(connection, "cost_records")
    if not {"planned_cost", "actual_cost", "variance"} <= present:
        return {"status": "absent"}
    stats = {"status": "present", "checked": 0, "differs_exactly": 0, "differs_at_cents": 0}
    for planned, actual, variance in connection.execute(
            'SELECT planned_cost, actual_cost, variance FROM cost_records'):
        stats["checked"] += 1
        try:
            expected = canonical_variance(planned, actual)
        except EngineeringError:
            stats["differs_exactly"] += 1
            stats["differs_at_cents"] += 1
            continue
        if expected != variance:
            stats["differs_exactly"] += 1
            if expected is None or variance is None or round(expected, 2) != round(variance, 2):
                stats["differs_at_cents"] += 1
    return stats


def audit(db_path, scale=2):
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(f"database not found: {path.name}")
    connection = sqlite_connection.connect(path, read_only=True)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        report = {"scale": scale, "rounding_for_exactness_check": "ROUND_HALF_EVEN", "columns": {}}
        for table, column, currency_column in MONEY_COLUMNS:
            key = f"{table}.{column}"
            report["columns"][key] = (_audit_column(connection, table, column, currency_column, scale)
                                      if table in tables else {"status": "absent"})
        report["cost_records_variance"] = (_variance_mismatches(connection)
                                           if "cost_records" in tables else {"status": "absent"})
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        report["sqlite_user_version"] = version
        return report
    finally:
        connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, help="path to a COPY of the database")
    parser.add_argument("--scale", type=int, default=2, help="decimal places to test exactness against")
    parser.add_argument("--output", help="write the JSON report here instead of stdout")
    args = parser.parse_args(argv)
    report = audit(args.db, scale=args.scale)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
