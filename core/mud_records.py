"""Source/PCF-domain and manual-edit boundaries for the existing mud model."""
from copy import deepcopy
import math

from core.canonical_schema import get_engineering_bounds
from core.unit_manager import UnitManager
from core.value_normalizer import ValueNormalizer


def mud_density_pcf(source):
    """Normalize a source mud-weight value to the MudReport PCF domain.

    ``mud_report.mw`` is pcf in canonical import data and the database. Source
    ppg/SG/etc. values are accepted only with an explicit companion unit or a
    unit suffix; bare density magnitudes are ambiguous and must stay reviewable.
    The returned UnitRecord lineage is suitable for audit/provenance.
    """
    data = deepcopy(source)
    value = data.get("mw")
    if value in (None, ""):
        return data, None

    unit = str(data.get("mw_unit") or "").strip()
    if isinstance(value, str):
        magnitude, suffix = UnitManager.detect_unit(value)
        if suffix:
            if unit and UnitManager.normalize(unit) != UnitManager.normalize(suffix):
                try:
                    companion_pcf = UnitManager.convert(1.0, "density", unit, "pcf")
                    suffix_pcf = UnitManager.convert(1.0, "density", suffix, "pcf")
                    equivalent = math.isclose(companion_pcf, suffix_pcf, rel_tol=1e-9, abs_tol=1e-9)
                except ValueError:
                    equivalent = False
                if not equivalent:
                    raise ValueError(f"Conflicting mud density units: value says {suffix!r}, field says {unit!r}")
            value, unit = magnitude, suffix
        else:
            value = ValueNormalizer.to_float(value)
    if value is None:
        raise ValueError("Mud weight is not a valid finite numeric value")
    if not unit:
        raise ValueError("Mud weight has no explicit source unit; refusing to assume ppg or pcf")

    record = UnitManager.create_record("mud_report.mw", "density", unit, value, "pcf")
    normalized = record.normalized_value
    if normalized is None or not math.isfinite(float(normalized)):
        raise ValueError(f"Cannot resolve mud density unit {unit!r}; supply a supported density unit")
    if normalized <= 0:
        raise ValueError("Mud weight must be greater than zero pcf")
    lower, upper = get_engineering_bounds("mud_report.mw")
    if (lower is not None and normalized < lower) or (upper is not None and normalized > upper):
        raise ValueError(
            f"Mud weight {value!r} {unit} converts to {normalized!r} pcf outside canonical bounds {lower}–{upper} pcf"
        )

    data["mw"] = normalized
    data["mw_unit"] = "PCF"
    lineage = record.as_dict()
    lineage["source_unit"] = unit
    lineage["normalized_unit"] = "pcf"
    lineage["domain_unit"] = "pcf"
    return data, lineage


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
