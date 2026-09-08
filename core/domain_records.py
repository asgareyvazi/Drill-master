"""Shared manual/import JSON record adapters. No Qt or persistence dependencies.

Keys are explicit; dictionary insertion order is never a column schema. Source
and unsupported fields remain in _provenance, never in a display cell.
"""
from copy import deepcopy
import re

from core.combo_identity import ComboOption, resolve_options
from core.value_normalizer import ValueNormalizer

CHEMICAL_TYPES = ("Viscosifier", "Weight Material", "Alkalinity", "Filtration Control", "Lubricant", "Shale Inhibitor")
CHEMICAL_ALIASES = {
    "Viscosifier": ("bentonite", "gel", "xanthan gum", "CMC-HV", "PAC-R", "organophilic clay"),
    "Weight Material": ("barite", "barytes", "hematite"),
    "Alkalinity": ("lime", "caustic soda", "sodium hydroxide", "soda ash", "sodium carbonate", "sodium bicarbonate"),
    "Filtration Control": ("API starch", "starch", "PAC-LV", "CMC-LV"),
    "Lubricant": ("bit lube",),
    "Shale Inhibitor": ("KCl", "potassium chloride"),
}


def chemical_type(name, explicit=None):
    options = [ComboOption(t, t, t, CHEMICAL_ALIASES[t]) for t in CHEMICAL_TYPES]
    return resolve_options(explicit or name, options, field="mud_chemical.type")


BHA_FIELDS = {
    "Tool Type": ("tool_type",), "Component Name": ("component_name", "Description", "description", "name"),
    "OD (in)": ("od",), "ID (in)": ("id",), "Length (m)": ("length",),
    "Serial No": ("serial", "serial_number"), "Weight (kg)": ("weight",),
    "Connection Type": ("connection_type", "connection"), "Make-up Torque (ft-lb)": ("make_up_torque", "torque"),
    "Remarks": ("remarks",), "Cumulative Length (m)": ("cum_length", "cumulative_length"),
}
DOWNHOLE_FIELDS = {
    "Equipment Name": ("equipment_name", "name"), "Type": ("equipment_type", "type"),
    "Serial No": ("serial_number",), "ID": ("equipment_id",), "Manufacturer": ("manufacturer",),
    "Install Date": ("install_date",), "Sliding Hours": ("sliding_hours",),
    "Rotation Hours": ("rot_hrs", "rotation_hours"), "Pumping Hours": ("pumping_hours",),
    "Total Hours": ("cum_hrs", "total_hours"), "Cycles": ("cycles",), "Last Service": ("last_service",),
    "Next Service": ("next_service",), "Status": ("status",), "Remarks": ("remarks",),
}
FORMATION_FIELDS = {
    "Formation Name": ("name", "formation_name"), "Lithology": ("lithology",), "Age": ("age",),
    "Top MD (m)": ("top_md", "md_top"), "Base MD (m)": ("base_md",), "Thickness (m)": ("thickness",),
    "Top TVD (m)": ("top_tvd", "tvd"), "Color": ("color",), "Description": ("description",), "Properties": ("properties",),
}


def is_metadata_value(value):
    return isinstance(value, (dict, list, tuple, set)) or (
        isinstance(value, str) and bool(re.match(r"^(?:[A-Za-z]:[\\/]|/|file://|\\\\)", value))
    )


def named_record(row, fields):
    """Project a source/legacy/manual row by name, retaining rejected data."""
    if not isinstance(row, dict):
        raise ValueError("JSON table record must be a named mapping")
    result = {}
    for target, aliases in fields.items():
        value = next((row[k] for k in (target, *aliases) if row.get(k) is not None), None)
        result[target] = None if is_metadata_value(value) else value
    provenance = deepcopy(row.get("_provenance", {}))
    if not provenance:
        provenance = {"source_record": deepcopy(row)}
    result["_provenance"] = provenance
    return result


def bha_record(row):
    result = named_record(row, BHA_FIELDS)
    if not result["Tool Type"]:
        name = str(result["Component Name"] or "").lower()
        rules = ((r"\bbit sub\b", "Sub (Bit Sub)"), (r"\b(?:xos|x-over)\b", "X-Over Sub"),
                 (r"\b(?:dc|drill collar)\b", "Drill Collar"), (r"\bhwdp\b", "HWDP"),
                 (r"\bs[.]\s*stab\b", "Stabilizer (String)"), (r"\bbit\b", "Bit"))
        result["Tool Type"] = next((kind for pattern, kind in rules if re.search(pattern, name)), None)
    for field in ("OD (in)", "ID (in)", "Length (m)", "Weight (kg)", "Make-up Torque (ft-lb)", "Cumulative Length (m)"):
        result[field] = ValueNormalizer.to_float(result[field])
    return result


def material_route(row):
    """Route using chemical section evidence before broad inventory labels."""
    source = row.get("_source_cells") or {}
    context = str((row.get("_source_location") or {}).get("table", "")).lower()
    if any(str(k).startswith("mud_chemical.") for k in source) or "mud" in context or row.get("product_type"):
        return "mud"
    name = str(row.get("material_name") or row.get("product") or "").strip().lower()
    if re.search(r"\b(?:diesel|fuel|water)\b", name):
        return "fuel_water"
    if chemical_type(name).accepted or re.search(r"\b(?:mud|bentonite|barite)\b", name):
        return "mud"
    return "review"


def chemical_record(row):
    name = row.get("product") or row.get("material_name") or row.get("product_type")
    resolution = chemical_type(name, row.get("type"))
    return {
        "product": name, "type": resolution.identity,
        "received": row.get("received"), "used": row.get("used"),
        "stock": row.get("on_hand", row.get("stock", row.get("current_stock"))),
        "unit": row.get("unit"), "_provenance": deepcopy(row),
    }, resolution


def optional_date(value):
    result = ValueNormalizer.normalize(value, "date")
    if not result.ok:
        raise ValueError(f"Invalid date {value!r}: {result.error}")
    return result.value


def collection_value(value, field):
    """Legacy nullable JSON collection contract: empty list or explicit error."""
    import json
    if value is None:
        return []
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError(f"{field} must contain a list of records")
    return value


def npt_record(source, companies=()):
    """NPT activation is independent of activity identity or company resolution."""
    from core.npt_catalog import NPT_CODES
    from core.combo_identity import normalize_label
    from core.canonical_mapper import review_item
    row = dict(source)
    code_options = [ComboOption(k, label, k) for k, label in NPT_CODES.items()]
    raw_code = row.get("npt_code") or row.get("npt_category") or row.get("main_code")
    code = resolve_options(raw_code, code_options, field="time_log.npt_code")
    status_npt = normalize_label(row.get("status")) in {"npt", "nonproductive", "nonproductive time", "non productive", "non productive time"}
    explicit = ValueNormalizer.to_bool(row.get("is_npt"))
    row["is_npt"] = explicit is True or status_npt or code.accepted
    reviews = []
    if not row["is_npt"]:
        return row, reviews
    def issue(field, value, reason):
        reviews.append(review_item(field=field, entity="time_log", original_value=value,
                                   location=row.get("_source_location"), reason=reason).to_dict())
    if code.accepted:
        row["main_code"] = code.identity
        row["npt_category"] = code.label
        row["_combo_resolution"] = {}  # NPT uses its own catalogue, not DDR ordinals
    else:
        issue("time_log.npt_code", raw_code, "NPT is active but an authoritative NPT code is missing/ambiguous")
    raw_company = row.get("contractor") or row.get("npt_company")
    # The source's attributed-company column is not an NPT category code.
    if not raw_company and not code.accepted:
        raw_company = row.get("npt_category")
    company = resolve_options(raw_company, [ComboOption(c, c, c) for c in sorted(set(companies)) if c], field="time_log.contractor")
    row["contractor"] = company.identity
    if not company.accepted:
        issue("time_log.contractor", raw_company, company.reason)
    return row, reviews


def isolate_import_rows(extracted):
    """Preflight typed child rows, preserving source errors for review.

    System errors still abort the transaction. This only isolates invalid input.
    """
    from core.canonical_mapper import review_item
    data = deepcopy(extracted)
    issues = []
    definitions = {
        "pob_records": ({"personnel_count": "integer", "date_in": "date", "date_out": "date"}, ("company_name",)),
        "service_companies": ({"personnel_count": "integer"}, ("company_name",)),
        "bop_components": ({"working_pressure": "number", "test_pressure": "number"}, ("name/component_name", "type/component_type", "working_pressure")),
        "waste_records": ({"volume": "number", "record_date": "date"}, ("waste_type", "volume")),
        "equipment_logs": ({"hours_worked": "number"}, ("equipment_name",)),
    }
    for collection, (fields, required) in definitions.items():
        accepted = []
        for index, row in enumerate(data.get(collection) or [], 1):
            errors = []
            if not isinstance(row, dict):
                errors.append(("", "Source row must be a mapping", "INVALID_SOURCE"))
            else:
                for names in required:
                    if not any(not ValueNormalizer.is_missing(row.get(k)) for k in names.split("/")):
                        errors.append((names, "Required source field missing; no value invented", "REVIEW_REQUIRED"))
                for field, kind in fields.items():
                    if field not in row:
                        continue
                    result = ValueNormalizer.normalize(row[field], kind)
                    if not result.ok:
                        errors.append((field, result.error, "INVALID_SOURCE"))
                    else:
                        row[field] = result.value
            if errors:
                for field, reason, status in errors:
                    issues.append(review_item(field=f"{collection}.{field}", entity=collection, original_value=extracted.get(collection, [])[index-1],
                                              location=row.get("_source_location", {"row": index}) if isinstance(row, dict) else {"row": index},
                                              reason=reason, status=status).to_dict())
            else:
                accepted.append(row)
        if collection in data:
            data[collection] = accepted
    return data, issues
