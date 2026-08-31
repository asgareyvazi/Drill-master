"""Generic header-driven table-to-record extraction for unknown company workbooks.

Professional Features:
- Row independent extraction for every table
- Time Log: From, To, Duration, Main Phase, Main Code, Sub Code, NPT, Contractor, Description
- Survey: MD, Inclination, Azimuth, TVD, North, East, VS, HD, DLS, Tool
- BHA: Component, OD, ID, Length, Weight, Serial, Position, Cumulative Length
- Bit: Bit No, Bit Size, Bit Type, IADC, Manufacturer, Serial, Nozzle, TFA
- Mud Chemicals: Product, Type, Received, Used, On Hand, Unit + Ledger
- Equipment: Equipment, Category, Serial, Manufacturer, Status, Service Date, Hours
- Logistics: Company, Service Type, Personnel, Date In, Date Out, Status
- Safety, BOP, Cost, Services, etc.

Universal alias handling: no dependency on fixed sheet names or cell positions.
"""

import re
from typing import Dict, List, Any

# Comprehensive aliases for all record types as per spec
ALIASES = {
    "time_log": {
        "time_from": ("from", "time from", "start", "time start", "from time"),
        "time_to": ("to", "time to", "end", "time end", "to time"),
        "duration": ("hrs", "hours", "duration", "hr", "h"),
        "main_phase": ("main phase", "phase", "main phase code", "operation phase"),
        "main_code": ("main code", "code", "activity code", "main activity code", "phase code"),
        "sub_code": ("sub code", "sub-code", "secondary code", "sub activity"),
        "is_npt": ("npt", "non productive", "trouble", "npt flag"),
        "npt_category": ("npt category", "npt code", "trouble code"),
        "contractor": ("contractor", "company", "responsible", "attributed to"),
        "activity_description": ("description", "activity", "rig activity", "operation", "remarks", "comment"),
    },
    "survey": {
        "md": ("md", "m.d", "measured depth", "depth", "m.d. (m)"),
        "inc": ("inc", "incl", "inclination", "inc (deg)", "inclination (deg)"),
        "azi": ("azi", "azimuth", "azimuth (deg)", "azi (deg)", "direction"),
        "tvd": ("tvd", "true vertical depth", "tvd (m)"),
        "north": ("north", "northing", "n/s", "north (m)"),
        "east": ("east", "easting", "e/w", "east (m)"),
        "vs": ("vs", "vertical section", "vs (m)"),
        "hd": ("hd", "horizontal displacement", "hd (m)", "departure"),
        "dls": ("dls", "dogleg", "dog leg severity", "dls (deg/30m)", "build rate"),
        "tool": ("tool", "survey tool", "tool type", "mwd", "gyro"),
    },
    "bha": {
        "component_name": ("component", "item", "bha component", "tool", "description"),
        "od": ("od", "o.d.", "outer diameter", "od (in)", "diameter"),
        "id": ("id", "i.d.", "inner diameter", "id (in)"),
        "length": ("length", "len", "length (m)", "length (ft)", "l"),
        "weight": ("weight", "wt", "weight (kg)", "ppf", "weight per foot"),
        "serial": ("serial", "serial number", "serial no", "s/n"),
        "position": ("position", "pos", "no", "number"),
        "cumulative_length": ("cumulative", "cum length", "total length", "cum"),
    },
    "bit": {
        "bit_no": ("bit no", "bit number", "bit #", "bit no.", "bit num"),
        "bit_size": ("bit size", "size", "diameter", "bit dia", "bit size (in)"),
        "bit_type": ("bit type", "type", "bit model", "model"),
        "iadc_code": ("iadc", "iadc code", "code"),
        "manufacturer": ("manufacturer", "make", "brand", "mfg", "bit manufacture"),
        "serial_number": ("serial", "serial number", "bit serial", "s/n"),
        "nozzle": ("nozzle", "nozzles", "jet", "nozzle size"),
        "tfa": ("tfa", "total flow area", "flow area"),
    },
    "bulk": {
        "material_name": ("material", "mat. type", "material type", "product", "chemical", "product name"),
        "material_type": ("type", "category", "product type"),
        "received": ("received", "in", "received qty", "delivery"),
        "used": ("used", "consumed", "consumption", "used qty"),
        "current_stock": ("on hand", "stock", "remaining", "balance", "current", "closing"),
        "initial_stock": ("opening", "initial", "on hand previous", "opening stock"),
        "unit": ("unit", "uom", "unit of measure"),
    },
    "equipment": {
        "equipment_name": ("equipment", "item", "component", "equipment name", "tool name"),
        "equipment_type": ("category", "type", "equipment type", "group"),
        "serial_number": ("serial", "serial number", "id", "s/n", "serial no"),
        "manufacturer": ("manufacturer", "make", "brand", "mfg"),
        "status": ("status", "condition", "state"),
        "service_date": ("service date", "date", "last service", "service"),
        "hours_worked": ("hours", "daily hrs", "rot. hrs", "running hours", "hours worked"),
    },
    "logistics": {
        "company_name": ("company", "service company", "contractor", "vendor", "supplier"),
        "service_type": ("service", "service type", "job", "service description"),
        "personnel_count": ("personnel", "pob", "people", "headcount", "count"),
        "date_in": ("date in", "arrival", "in date", "mobilization"),
        "date_out": ("date out", "departure", "out date", "demobilization"),
        "status": ("status", "state"),
    },
    "service": {
        "company_name": ("company", "service company", "contractor", "vendor"),
        "service_type": ("service", "service type", "job", "operation"),
        "personnel_count": ("personnel", "pob", "count"),
        "date_in": ("date in", "start", "in"),
        "date_out": ("date out", "end", "out"),
        "description": ("description", "remarks", "comment"),
    },
    "bop": {
        "component_name": ("component", "bop component", "item", "name"),
        "component_type": ("type", "bop type", "ram type", "category"),
        "working_pressure": ("working pressure", "wp", "pressure", "w.p.", "rated"),
        "size": ("size", "diameter", "bore"),
        "last_test_date": ("last test", "test date", "last test date"),
        "test_pressure": ("test pressure", "pressure tested"),
        "status": ("status", "result", "condition"),
    },
    "cost": {
        "category": ("category", "cost category", "type", "cost type"),
        "description": ("description", "item", "cost item", "details"),
        "planned_cost": ("planned", "budget", "planned cost", "afe"),
        "actual_cost": ("actual", "actual cost", "spent", "cost"),
        "vendor": ("vendor", "supplier", "company"),
    },
}


def _norm(value: str) -> str:
    """Normalize for fuzzy matching: lower, alnum only."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _match(header: str, aliases: tuple) -> bool:
    h = _norm(header)
    if not h:
        return False
    for alias in aliases:
        a = _norm(alias)
        if not a:
            continue
        # Exact or substring both ways
        if h == a or a in h or h in a:
            return True
        # For short aliases (<=3 chars), require word boundary to avoid false positives
        if len(a) <= 3:
            # Check if header contains alias as separate token
            header_lower = str(header).lower()
            if re.search(rf"\b{re.escape(alias)}\b", header_lower):
                return True
    return False


def map_table(cells: Dict[tuple, Any], region: Dict, record_type: str) -> List[Dict]:
    """Map a detected table region to records of given type using header aliases."""
    aliases = ALIASES.get(record_type, {})
    headers = region.get("headers", [])
    columns = region.get("columns", [])

    # Build column mapping: field -> col index
    mapping: Dict[str, int] = {}
    for index, header in enumerate(headers):
        if not header or not str(header).strip():
            continue
        for field, names in aliases.items():
            if field in mapping:
                continue  # already mapped
            if _match(header, names):
                col_num = columns[index].get("column", region.get("min_col", 1) + index) if index < len(columns) else region.get("min_col", 1) + index
                mapping[field] = col_num

    if not mapping:
        return []

    records = []
    header_rows = region.get("header_rows", 1)
    min_row = region.get("min_row", 1)
    max_row = region.get("max_row", 1)

    # Data starts after header rows
    data_start = min_row + header_rows

    for row in range(data_start, max_row + 1):
        record = {}
        for field, col in mapping.items():
            record[field] = cells.get((row, col))

        # Skip empty rows
        if not any(v not in (None, "") for v in record.values()):
            continue

        # Skip rows that look like totals
        first_val = str(record.get(list(mapping.keys())[0], "")).lower() if mapping else ""
        if "total" in first_val and len(first_val) < 20:
            continue

        record.update(
            {
                "source_sheet": region.get("sheet", ""),
                "source_row": row,
                "record_type": record_type,
                "source_cell": f"{region.get('sheet','')}!Row{row}",
            }
        )
        records.append(record)

    return records


def extract_records(cells_by_sheet: Dict[str, Dict], snapshot: Dict) -> Dict[str, List[Dict]]:
    """Extract all record types from all tables in snapshot.

    Returns dict with keys for all tabs: surveys, bulk_materials, equipment_logs, service_companies, time_logs, bha, bit, etc.
    """
    output = {
        "surveys": [],
        "bulk_materials": [],
        "equipment_logs": [],
        "service_companies": [],
        "time_logs_24h": [],
        "bha_components": [],
        "bit_records": [],
        "bop_components": [],
        "cost_records": [],
        "logistics_records": [],
    }

    for region in snapshot.get("tables", []):
        title = str(region.get("title", "")).lower()
        headers = " ".join(str(h).lower() for h in region.get("headers", []))
        text = f"{title} {headers}"
        detected_class = str(region.get("detected_class", "")).lower()

        # Determine record type based on title/headers/class
        record_type = None

        # Priority: use detected_class first
        class_to_type = {
            "daily report": "time_log",
            "survey": "survey",
            "bha": "bha",
            "bit": "bit",
            "mud": "bulk",
            "logistics": "logistics",
            "services": "service",
            "bop": "bop",
            "cost": "cost",
            "equipment": "equipment",
        }
        for cls_name, r_type in class_to_type.items():
            if cls_name in detected_class:
                record_type = r_type
                break

        if not record_type:
            # Fallback keyword detection
            if any(x in text for x in ("from", "to", "hrs", "duration")) and any(y in text for y in ("phase", "code", "activity", "operation")):
                record_type = "time_log"
            elif any(x in text for x in ("survey", "inclination", "azimuth", "md", "tvd")) and any(y in text for y in ("inc", "azi", "north", "east")):
                record_type = "survey"
            elif any(x in text for x in ("bha", "bottom hole assembly", "stabilizer", "drill collar")):
                record_type = "bha"
            elif any(x in text for x in ("bit", "iadc", "nozzle", "tfa")) and "bha" not in text:
                record_type = "bit"
            elif any(x in text for x in ("bulk", "material", "chemical", "received", "on hand", "bentonite", "barite")):
                record_type = "bulk"
            elif any(x in text for x in ("equipment", "serial", "solid control", "shaker")):
                record_type = "equipment"
            elif any(x in text for x in ("service company", "contractor", "service type")) and "bop" not in text:
                record_type = "service"
            elif any(x in text for x in ("bop", "blow out", "wellhead", "ram", "annular")):
                record_type = "bop"
            elif any(x in text for x in ("cost", "afe", "expense", "budget")):
                record_type = "cost"
            elif any(x in text for x in ("pob", "personnel", "logistics", "fuel", "water")):
                record_type = "logistics"

        if not record_type:
            continue

        sheet_name = region.get("sheet", "")
        cells = cells_by_sheet.get(sheet_name, {})

        records = map_table(cells, region, record_type)

        # Map to output keys
        key_map = {
            "survey": "surveys",
            "bulk": "bulk_materials",
            "equipment": "equipment_logs",
            "service": "service_companies",
            "time_log": "time_logs_24h",
            "bha": "bha_components",
            "bit": "bit_records",
            "bop": "bop_components",
            "cost": "cost_records",
            "logistics": "logistics_records",
        }
        output_key = key_map.get(record_type)
        if output_key and records:
            output[output_key].extend(records)

    return output


def extract_with_provenance(cells_by_sheet: Dict[str, Dict], snapshot: Dict, file_path: str = "") -> Dict[str, Any]:
    """Extract with full provenance for Review Matrix.

    Returns records plus provenance info for each field.
    """
    records = extract_records(cells_by_sheet, snapshot)
    provenance = []

    for region in snapshot.get("tables", []):
        for col in region.get("columns", []):
            header = col.get("header", "")
            for sample_idx, sample in enumerate(col.get("samples", [])[:3]):
                provenance.append(
                    {
                        "file": file_path,
                        "sheet": region.get("sheet", ""),
                        "detected_table": region.get("title", "") or region.get("detected_class", ""),
                        "source_cell": f"Col{col.get('column','')} Row{region.get('min_row',0)+1+sample_idx}",
                        "original_value": sample,
                        "normalized_value": sample,
                        "unit": "",
                        "target_field": header,
                        "confidence": col.get("confidence", 0.7),
                        "decision": "REVIEW",
                        "transform": "table-mapping",
                    }
                )

    return {"records": records, "provenance": provenance}
