"""The M34 sweep family table, read verbatim from the frozen sweep evidence.

Comparability between the M34 inventory and the M35 re-sweep requires identical family
definitions; the scanning implementation itself is independent (see verify_inventory.py).
"""
from __future__ import annotations

import json
from pathlib import Path

SWEEP = Path(__file__).resolve().parents[2] / "docs/audits/m34-evidence/m34-fresh-sweep.json"


def load_families() -> dict[str, str]:
    return dict(json.loads(SWEEP.read_text())["families"])
