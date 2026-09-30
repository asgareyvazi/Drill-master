"""Conservative section/header table detection for the generic Excel IR path.

A generic workbook has no template authority.  Header aliases can identify a
candidate table only when the required columns occupy one contiguous column
cluster; aliases on opposite sides of blank columns must not be stitched into
one canonical record.  Ambiguous/unsupported layouts are deliberately left
for review rather than guessed.
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


def _header_aliases(section):
    specs = {path: spec for path, spec in FIELD_SPECS.items() if path.startswith(section + ".")}
    aliases = {}
    for path, spec in specs.items():
        for alias in spec.aliases:
            key = header_key(alias)
            if key:
                aliases.setdefault(key, set()).add(path)
    return aliases


def _clusters(entries):
    """Partition (column, canonical path, header row) by every blank column.

    A missing header column is not evidence that two tables belong together.
    This may decline sparse-but-valid generic tables; explicit templates remain
    the path for layouts whose column ownership cannot be inferred safely.
    """
    clusters, current, last_col = [], [], None
    for entry in sorted(entries, key=lambda item: item[0]):
        col = entry[0]
        if current and col > last_col + 1:
            clusters.append(current)
            current = []
        current.append(entry)
        last_col = col
    if current:
        clusters.append(current)
    return clusters


def detect_tables(cells_by_sheet):
    """Return structurally bounded table rows and cells owned by those tables.

    Headers may occupy one or two rows.  Duplicate mappings, missing
    signatures, side-by-side signatures, blank row boundaries, and partial
    records are never promoted into a complete canonical table.
    """
    found, consumed = [], set()
    for sheet, cells in cells_by_sheet.items():
        last_row = max((row for row, _col in cells), default=0)
        for section, (required, storage) in SIGNATURES.items():
            aliases = _header_aliases(section)
            for row in range(1, last_row + 1):
                # Cells already owned by a previously detected table cannot
                # start another interpretation of the same source structure.
                selected = None
                for header_end in (row, row + 1):
                    header_entries = []
                    for (cell_row, col), value in cells.items():
                        if not row <= cell_row <= header_end or (sheet, cell_row, col) in consumed:
                            continue
                        paths = aliases.get(header_key(value), set())
                        if len(paths) == 1:
                            header_entries.append((col, next(iter(paths)), cell_row))
                    for cluster in _clusters(header_entries):
                        mapping = {}
                        duplicate_path = False
                        for col, path, _header_row in cluster:
                            previous = mapping.get(path)
                            if previous is not None and previous != col:
                                duplicate_path = True
                                break
                            mapping[path] = col
                        if duplicate_path:
                            continue
                        if not required.issubset({path.rsplit(".", 1)[-1] for path in mapping}):
                            continue
                        if section == "mud_chemical" and not any(
                            path.endswith((".used", ".received", ".on_hand")) for path in mapping
                        ):
                            continue
                        selected = (mapping, header_end, cluster)
                        break
                    if selected is not None:
                        break
                if selected is None:
                    continue

                mapping, header_end, header_cluster = selected
                records, end = [], header_end
                data_row = header_end + 1
                while data_row <= last_row:
                    values = {path: cells.get((data_row, col)) for path, col in mapping.items()}
                    present = [(path, value) for path, value in values.items() if value not in (None, "")]
                    if not present:
                        # A blank row is a hard section boundary.  Do not jump
                        # over it into a different vertical table.
                        break
                    if all(
                        isinstance(value, str)
                        and (header_key(value) in aliases or value.startswith("="))
                        for _path, value in present
                    ):
                        # Repeated header within a continued table.
                        data_row += 1
                        continue
                    if len(present) < 2:
                        # A partial row is not a complete record.  Its cells
                        # remain in the lossless IR for review; do not let the
                        # next section be absorbed as a table continuation.
                        break
                    record = dict(values)
                    record["_source_row"] = data_row
                    record["_source_cells"] = {
                        path: f"R{data_row}C{col}" for path, col in mapping.items()
                    }
                    records.append(record)
                    end = data_row
                    data_row += 1

                if not records:
                    continue
                found.append((sheet, storage, mapping, header_end + 1, end, records))
                min_col, max_col = min(mapping.values()), max(mapping.values())
                for owned_row in range(row, end + 1):
                    for col in range(min_col, max_col + 1):
                        if (owned_row, col) in cells:
                            consumed.add((sheet, owned_row, col))
    return found, consumed
