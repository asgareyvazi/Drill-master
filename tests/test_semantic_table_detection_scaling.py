"""Generic table detection scales linearly and keeps its structural guarantees (M43).

detect_tables used to rescan every cell of the sheet for each candidate header
row (six signatures x rows x two header heights), so a 20,000-row workbook spent
minutes in import. These tests bound the work by counting cell visits (no
timing) and fuzz structural invariants on seeded synthetic grids.
"""
import random

from core.canonical_schema import FIELD_SPECS
from core.semantic_tables import SIGNATURES, detect_tables


class CountingCells(dict):
    visits = 0

    def items(self):
        for item in super().items():
            CountingCells.visits += 1
            yield item


def _survey_sheet(rows):
    cells = {(1, 1): "MD", (1, 2): "Inc", (1, 3): "Azi"}
    for i in range(rows):
        cells.update({(2 + i, 1): float(i * 10), (2 + i, 2): 1.5, (2 + i, 3): 90.0})
    return cells


def test_cell_visits_do_not_grow_with_rows_times_cells():
    cells = CountingCells(_survey_sheet(3000))
    CountingCells.visits = 0
    tables, _ = detect_tables({"Survey": cells})
    assert len(tables) == 1 and len(tables[0][5]) == 3000
    # The former implementation visited ~ 6 * 2 * 3001 * 9003 (about 324 million) cells.
    assert CountingCells.visits <= 2 * len(cells)


def test_large_table_is_detected_completely_with_source_cells():
    tables, consumed = detect_tables({"Survey": _survey_sheet(20000)})
    (sheet, storage, mapping, first, last, records), = tables
    assert (sheet, storage, first, last) == ("Survey", "surveys", 2, 20001)
    assert len(records) == 20000
    assert records[-1]["_source_row"] == 20001 and records[-1]["_source_cells"]["survey.md"] == "R20001C1"
    assert len(consumed) == 3 * 20001


def _random_grid(rng):
    cells = {}
    rows, cols = rng.randint(1, 25), rng.randint(1, 9)
    for _ in range(rng.randint(0, rows * cols)):
        cells[(rng.randint(1, rows), rng.randint(1, cols))] = rng.choice([1, 2.5, "a", "", None, "=A1", "Remarks"])
    section = rng.choice(list(SIGNATURES))
    paths = [p for p in FIELD_SPECS if p.startswith(section + ".") and FIELD_SPECS[p].aliases]
    chosen = [p for p in paths if p.rsplit(".", 1)[-1] in SIGNATURES[section][0]]
    chosen += rng.sample(paths, min(len(paths), rng.randint(0, 3)))
    header_row, start = rng.randint(1, rows), rng.randint(1, 3)
    for j, path in enumerate(chosen):
        cells[(header_row, start + j)] = rng.choice(FIELD_SPECS[path].aliases)
        for k in range(1, rng.randint(1, 6)):
            cells[(header_row + k, start + j)] = rng.choice([1.0, 2, "v", None])
    items = list(cells.items())
    rng.shuffle(items)
    return dict(items)


def test_seeded_fuzz_structural_invariants():
    for seed in range(400):
        cells = _random_grid(random.Random(seed))
        tables, consumed = detect_tables({"S": cells})
        assert all(sheet == "S" and (row, col) in cells for sheet, row, col in consumed), seed
        for _sheet, _storage, mapping, first, last, records in tables:
            assert len(set(mapping.values())) == len(mapping), seed  # one column per field
            for record in records:
                row = record["_source_row"]
                assert first <= row <= last, seed
                present = [path for path in mapping if record[path] not in (None, "")]
                assert len(present) >= 2, seed  # partial rows are never promoted
                for path, col in mapping.items():
                    assert record[path] == cells.get((row, col)), seed  # value comes from its own cell
                    assert record["_source_cells"][path] == f"R{row}C{col}", seed
