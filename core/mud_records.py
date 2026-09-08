"""Source/PCF-domain and manual-edit boundaries for the existing mud model."""
from copy import deepcopy
from core.unit_manager import UnitManager
from core.value_normalizer import ValueNormalizer


def mud_density_pcf(source):
    data = deepcopy(source)
    value = data.get("mw")
    if value in (None, ""):
        return data, None
    unit = data.get("mw_unit")
    if isinstance(value, str):
        magnitude, suffix = UnitManager.detect_unit(value)
        if suffix:
            value, unit = magnitude, suffix
        else:
            value = ValueNormalizer.to_float(value)
    if unit:
        record = UnitManager.create_record("mud_report.mw", "density", unit, value, "pcf")
        if record.normalized_value is None:
            raise ValueError(f"Cannot resolve mud density unit {unit!r}; supply a supported density unit")
        data["mw"] = record.normalized_value
        data["mw_unit"] = "PCF"
        lineage = record.as_dict()
        lineage["domain_unit"] = "pcf"
        return data, lineage
    return data, None  # no unit inference; extraction review remains authoritative


def preserve_widget_values(source, displayed, submitted, touched=()):
    """Round-trip untouched source values, including NULL, through widgets.

    ``displayed`` is captured after load. Widgets may need a numeric minimum
    or a time to render, but that placeholder is not a supplied measurement.
    Explicit editing, including entering zero, bypasses source restoration.
    """
    result = deepcopy(submitted)
    for key in submitted:
        if key in source and key in displayed and key not in touched and submitted[key] == displayed[key]:
            result[key] = deepcopy(source[key])
    return result


def chemical_balance(record):
    """Derived ledger result stays separate from source closing stock."""
    from core.engineering.core import ChemicalLedgerEntry
    from core.value_normalizer import ValueNormalizer
    values = {}
    for key in ("opening_stock", "received", "used", "returned", "adjusted"):
        normalized = ValueNormalizer.normalize(record.get(key), "number")
        if not normalized.ok:
            return {"status": "INVALID_SOURCE", "field": key, "closing_stock": None}
        if normalized.value is None:
            return {"status": "REVIEW_REQUIRED", "field": key, "closing_stock": None}
        values[key] = normalized.value
    entry = ChemicalLedgerEntry(product=record.get("product", ""), **values)
    return {"status": "SUCCESS", "closing_stock": entry.closing_stock, "alerts": entry.alerts()}
