"""Generic header-driven table-to-record extraction for unknown company workbooks."""
import re

ALIASES = {
    "survey": {"md": ("md", "m.d", "measured depth"), "inc": ("inc", "incl", "inclination"), "azi": ("azi", "azimuth"), "tvd": ("tvd",), "north": ("north",), "east": ("east",), "dls": ("dls",)},
    "bulk": {"material_name": ("material", "mat. type", "material type", "product"), "used": ("used", "consumed"), "received": ("received", "in"), "current_stock": ("on hand", "stock", "remaining")},
    "equipment": {"equipment_name": ("equipment", "item", "component"), "equipment_id": ("serial", "serial number", "id"), "hours_worked": ("daily hrs", "hours", "rot. hrs")},
    "service": {"company_name": ("company", "service company", "contractor"), "service_type": ("service", "service type", "job")},
}

def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

def _match(header, aliases):
    h = _norm(header)
    return any(_norm(alias) in h or h in _norm(alias) for alias in aliases)

def map_table(cells, region, record_type):
    aliases = ALIASES.get(record_type, {})
    headers = region.get("headers", [])
    columns = region.get("columns", [])
    mapping = {}
    for index, header in enumerate(headers):
        for field, names in aliases.items():
            if _match(header, names):
                mapping[field] = columns[index].get("column", region["min_col"] + index) if index < len(columns) else region["min_col"] + index
    if not mapping:
        return []
    records = []
    for row in range(region["min_row"] + 1, region["max_row"] + 1):
        record = {field: cells.get((row, col)) for field, col in mapping.items()}
        if any(value not in (None, "") for value in record.values()):
            record.update({"source_sheet": region["sheet"], "source_row": row, "record_type": record_type})
            records.append(record)
    return records

def extract_records(cells_by_sheet, snapshot):
    output = {"surveys": [], "bulk_materials": [], "equipment_logs": [], "service_companies": []}
    for region in snapshot.get("tables", []):
        title = str(region.get("title", "")).lower()
        headers = " ".join(str(h).lower() for h in region.get("headers", []))
        text = f"{title} {headers}"
        record_type = "survey" if any(x in text for x in ("survey", "inclination", "azimuth")) else "bulk" if any(x in text for x in ("bulk", "material", "received", "on hand")) else "equipment" if any(x in text for x in ("equipment", "serial", "solid control")) else "service" if any(x in text for x in ("service company", "contractor")) else None
        if not record_type: continue
        records = map_table(cells_by_sheet.get(region["sheet"], {}), region, record_type)
        key = {"survey": "surveys", "bulk": "bulk_materials", "equipment": "equipment_logs", "service": "service_companies"}[record_type]
        output[key].extend(records)
    return output
