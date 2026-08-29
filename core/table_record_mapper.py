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
from core.canonical_schema import FIELD_SPECS, lookup_alias

# Build ALIASES from canonical_schema — Single Source of Truth
# No independent alias dictionaries allowed
def _build_aliases_from_canonical():
    """Build table_record_mapper aliases from canonical schema."""
    # Map canonical section prefixes to table_record_mapper record types
    section_map = {
        "time_log": "time_log",
        "survey": "survey",
        "bha": "bha",
        "drilling_params": "bit",
        "bulk_material": "bulk",
        "equipment": "equipment",
        "logistics": "logistics",
        "safety": "safety",
        "bop": "bop",
        "cost": "cost",
        "service": "service",
        "formation": "formation",
        "downhole": "downhole",
        "mud_report": "mud",
    }
    
    aliases = {}
    for spec in FIELD_SPECS.values():
        section = spec.path.split(".")[0]
        key = spec.path.split(".", 1)[1] if "." in spec.path else spec.path
        record_type = section_map.get(section)
        if record_type and spec.aliases:
            if record_type not in aliases:
                aliases[record_type] = {}
            aliases[record_type][key] = tuple(spec.aliases)
    
    return aliases

ALIASES = _build_aliases_from_canonical()


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
