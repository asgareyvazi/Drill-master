"""M128: the W13 "Choke Schedule" page - drill-pipe pressure schedule while kill mud is pumped to the bit.

The schedule is the linear decline of the drill-pipe (standpipe) circulating pressure from the entered ICP
at 0 strokes to the entered FCP at the entered strokes-to-bit, in equal stroke steps (the Wait-and-Weight
convention); from the bit to surface the FCP is held.  The choke is adjusted to hold this drill-pipe
pressure - the values are NOT choke pressures.

WORKSHEET arithmetic of entered values only: ICP, FCP and strokes are never seeded or derived here (the Kill
Sheet page that derives them is a TRAINING AID), and the cumulative volume is shown only when a pump output
is entered.  Not a kill procedure and not an approved well-control document.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

METHOD_VERSION = "M128 drill-pipe pressure schedule v1"
MAX_INTERVALS = 20


def _positive(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be entered (a positive number)")
    return float(value)


def schedule(icp_psi: Any, fcp_psi: Any, strokes_to_bit: Any, intervals: Any,
             pump_output_bbl_stk: Optional[float] = None) -> Dict[str, Any]:
    """Rows from 0 strokes (ICP) to strokes-to-bit (FCP) in ``intervals`` equal steps (raises ``ValueError``)."""
    icp = _positive(icp_psi, "ICP")
    fcp = _positive(fcp_psi, "FCP")
    strokes = _positive(strokes_to_bit, "Strokes to bit")
    if isinstance(intervals, bool) or not isinstance(intervals, (int, float)) or intervals != int(intervals) \
            or not 1 <= int(intervals) <= MAX_INTERVALS:
        raise ValueError(f"intervals must be a whole number from 1 to {MAX_INTERVALS}")
    steps = int(intervals)
    output = None
    if pump_output_bbl_stk:                      # 0 / None = not entered: no volume column, never 0 bbl
        output = _positive(pump_output_bbl_stk, "Pump output")
    rows: List[Dict[str, Any]] = []
    for i in range(steps + 1):
        at = strokes * i / steps
        rows.append({"step": i, "strokes": at, "dp_psi": icp + (fcp - icp) * i / steps,
                     "percent_to_bit": 100.0 * i / steps,
                     "cum_volume_bbl": at * output if output is not None else None})
    return {
        "rows": rows,
        "results": {"initial_dp_psi": icp, "final_dp_psi": fcp, "strokes_per_step": strokes / steps,
                    "pressure_step_psi": (icp - fcp) / steps,
                    "psi_per_100_strokes": (icp - fcp) / strokes * 100.0,
                    "kill_mud_to_bit_bbl": strokes * output if output is not None else None},
    }
