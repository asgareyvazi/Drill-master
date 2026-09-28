"""Conservative section/header table detection for the generic Excel IR path.

No workbook names, sheet positions, or source coordinates are catalogued here.
Canonical field aliases identify columns; section-specific minimum signatures
prevent a single generic 'Name' or 'Type' cell from defining a table.
"""
import re
from core.canonical_schema import FIELD_SPECS

SIGNATURES = {
    "survey": ({"md", "inc", "azi"}, "surveys"),
    "bha": ({"component_name", "od", "length"}, "bha_components"),
    "mud_chemical": ({"product_type", "unit"}, "bulk_materials"),
    "bop": ({"name", "working_pressure", "size"}, "bop_components"),
    "formation": ({"name", "lithology"}, "formation_data"),
    "service": ({"company_name", "service_type"}, "service_companies"),
}


def header_key(value):
    text = str(value or "").strip().casefold()
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def detect_tables(cells_by_sheet):
    """Return detected row maps plus cells consumed as table presentation."""
    found, consumed = [], set()
    for sheet, cells in cells_by_sheet.items():
        last_row = max((r for r, c in cells), default=0)
        for section, (required, storage) in SIGNATURES.items():
            specs = {path: spec for path, spec in FIELD_SPECS.items() if path.startswith(section + ".")}
            headers = {}
            for path, spec in specs.items():
                for alias in spec.aliases:
                    key = header_key(alias)
                    if key:
                        headers.setdefault(key, set()).add(path)
            skip_until = 0
            for row in range(1, last_row + 1):
                if row <= skip_until:
                    continue
                mapping = {}
                header_end = row
                # One/two-row headers, including unit-only second lines.
                for header_row in (row, row + 1):
                    for (r, col), value in cells.items():
                        if r != header_row:
                            continue
                        candidates = headers.get(header_key(value), set())
                        if len(candidates) == 1:
                            path = next(iter(candidates))
                            mapping.setdefault(path, col)
                    if required.issubset({p.split(".")[-1] for p in mapping}):
                        header_end = header_row
                        break
                if not required.issubset({p.split(".")[-1] for p in mapping}):
                    continue
                if section == "mud_chemical" and not any(p.endswith((".used", ".received", ".on_hand")) for p in mapping):
                    continue
                records, blanks = [], 0
                end = header_end
                for data_row in range(header_end + 1, last_row + 1):
                    values = {path: cells.get((data_row, col)) for path, col in mapping.items()}
                    present = [v for v in values.values() if v not in (None, "")]
                    if not present:
                        blanks += 1
                        if blanks >= 3:
                            break
                        continue
                    blanks = 0
                    if all(isinstance(v, str) and (header_key(v) in headers or v.startswith("=")) for v in present):
                        continue
                    # A section title, rather than a populated multi-column
                    # record, terminates the table. Malformed numeric rows
                    # with multiple supplied fields remain reviewable.
                    if len(present) < 2:
                        break
                    values["_source_row"] = data_row
                    values["_source_cells"] = {p: f"R{data_row}C{c}" for p, c in mapping.items()}
                    records.append(values)
                    end = data_row
                if records:
                    found.append((sheet, storage, mapping, header_end + 1, end, records))
                    consumed.update((sheet, r, c) for r in range(row, end + 1) for c in mapping.values())
                    skip_until = end
    return found, consumed
