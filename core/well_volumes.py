"""M126: well volumes from the captured pump, drill-string and casing / open-hole tables.

W13 ``Volume › Well Volumes``. Before M126 the page ignored where each component sits: every pipe was
overlapped with every bore section by ``min(pipe length, section length)``, so a two-component string
counted part of the annulus twice; the bit depth was not used for the annulus; a missing pump rate gave a
lag time of 0 min. This method places the string explicitly and refuses what it cannot place.

Conventions (the same as ``AdvancedHydraulicsEngine``, so the two W13 pages agree):

* the drill-string table is listed from the **surface down**: the first row starts at 0 m MD, the last row
  ends at the bit; the summed lengths must reach the bit depth within ``STRING_CLOSURE_TOLERANCE_FT``;
* every depth from surface to the bit must lie in exactly one casing / open-hole row (its ID bounds the
  annulus there); a gap or an overlap is NOT ASSESSED - nothing is assumed about the missing interval;
* each component's OD must be smaller than the bore ID at every depth it occupies;
* capacities and times use the canonical ``AdvancedHydraulicsEngine`` relations (ID^2 / 1029.4 bbl/ft pipe,
  (Dh^2 - OD^2) / 1029.4 bbl/ft annulus, lag = volume / (gpm / 42), strokes = volume / output);
* times need a running pump (SPM > 0): flow rate = sum(output x SPM) - otherwise UNKNOWN, never 0;
  bottoms-up strokes are reported only when every running pump runs at the same SPM (strokes per pump);
* surface lines, pits and the hole below the bit are not part of the circulating volume.

Outputs are a calculation of the entered geometry - not a measured volume.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

METHOD_ID = "w13.volume.well_volumes"
METHOD_VERSION = "M126 well volumes v1"
FT_PER_M = 3.28084
GAL_PER_BBL = 42.0
STRING_CLOSURE_TOLERANCE_FT = 0.5     # the AdvancedHydraulicsEngine string-to-bit closure tolerance
RESULT_FIELDS = ("string_length_m", "string_volume_bbl", "annular_volume_bbl", "circulating_volume_bbl",
                 "flow_rate_gpm", "surface_to_bit_min", "lag_time_min", "circulation_time_min",
                 "bottoms_up_strokes")


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _positive(value: Any) -> bool:
    number = _num(value)
    return number is not None and number > 0


def assess(pumps: Sequence[Dict[str, Any]], string: Sequence[Dict[str, Any]],
           sections: Sequence[Dict[str, Any]], bit_depth_m: Any) -> Dict[str, Any]:
    """Volumes and times, or NOT ASSESSED with every reason. Rows use the W13 table keys
    (pump: name/output_bbl_stk/spm; pipe: type/od/id/length; bore: type/id/from/to)."""
    reasons: List[str] = []
    bit = _num(bit_depth_m)
    if bit is None or bit <= 0:
        reasons.append("bit depth is missing")
    pumps, string, sections = list(pumps or ()), list(string or ()), list(sections or ())
    if not string:
        reasons.append("the drill-string table is empty")
    for n, row in enumerate(string, 1):
        if not (_positive(row.get("od")) and _positive(row.get("id")) and _positive(row.get("length"))):
            reasons.append(f"string row {n}: OD, ID and length must be entered (positive)")
        elif row["id"] >= row["od"]:
            reasons.append(f"string row {n}: ID must be smaller than OD")
    if not sections:
        reasons.append("the casing / open-hole table is empty")
    for n, row in enumerate(sections, 1):
        top, bottom = _num(row.get("from")), _num(row.get("to"))
        if not _positive(row.get("id")):
            reasons.append(f"bore row {n}: ID / hole size must be entered (positive)")
        if top is None or bottom is None or top < 0 or bottom <= top:
            reasons.append(f"bore row {n}: From/To must be a positive interval")
    for n, row in enumerate(pumps, 1):
        spm, output = _num(row.get("spm")), _num(row.get("output_bbl_stk"))
        if spm is None or spm < 0:
            reasons.append(f"pump row {n}: SPM must be zero or positive")
        elif spm > 0 and not (output is not None and output > 0):
            reasons.append(f"pump row {n}: a running pump needs a positive output per stroke")
    if reasons:
        return _not_assessed(reasons)

    length_m = sum(float(row["length"]) for row in string)
    if abs(length_m - bit) * FT_PER_M > STRING_CLOSURE_TOLERANCE_FT:
        reasons.append(f"the drill-string lengths add up to {length_m:.2f} m but the bit depth is {bit:.2f} m "
                       "(the table is listed from the surface down and must reach the bit)")
    ordered = sorted(sections, key=lambda row: float(row["from"]))
    for previous, current in zip(ordered, ordered[1:]):
        if float(current["from"]) < float(previous["to"]) - 1e-9:
            reasons.append(f"bore rows {previous.get('type', '?')} and {current.get('type', '?')} overlap "
                           f"({float(current['from']):.2f}-{float(previous['to']):.2f} m); enter each interval once")
    if reasons:
        return _not_assessed(reasons)
    from core.hydraulics_engine import AdvancedHydraulicsEngine as engine   # canonical capacity / time relations

    # Explicit placement: component n spans [top_n, bottom_n] from the surface down, ending at the bit.
    placed, top = [], 0.0
    for n, row in enumerate(string, 1):
        bottom = bit if n == len(string) else top + float(row["length"])
        placed.append((n, row, top, bottom))
        top = bottom
    edges = {0.0, bit}
    for _n, _row, upper, lower in placed:
        edges.update(depth for depth in (upper, lower) if 0 < depth < bit)
    edges.update(float(r[k]) for r in ordered for k in ("from", "to") if 0 < float(r[k]) < bit)
    edges = sorted(edges)
    annulus, gaps = [], []
    for upper, lower in zip(edges, edges[1:]):
        if lower - upper <= 0:
            continue
        mid = 0.5 * (upper + lower)
        component = next(item for item in placed if item[2] <= mid <= item[3])
        bore = next((r for r in ordered if float(r["from"]) <= mid <= float(r["to"])), None)
        if bore is None:
            if gaps and gaps[-1][1] == upper:          # contiguous: one interval in the message
                gaps[-1] = (gaps[-1][0], lower)
            else:
                gaps.append((upper, lower))
            continue
        n, row = component[0], component[1]
        if float(bore["id"]) <= float(row["od"]):
            reasons.append(f"string row {n} ({row.get('type', '')}) OD {float(row['od']):.3f} in is not smaller "
                           f"than the bore ID {float(bore['id']):.3f} in at {upper:.2f}-{lower:.2f} m")
            continue
        capacity = engine.calc_annular_capacity_bbl_ft(float(bore["id"]), float(row["od"]))
        annulus.append({"kind": "annulus", "name": f"{row.get('type', '')} (row {n}) in {bore.get('type', '')}",
                        "top_m": upper, "bottom_m": lower, "hole_id_in": float(bore["id"]),
                        "pipe_od_in": float(row["od"]), "volume_bbl": capacity * (lower - upper) * FT_PER_M})
    if gaps:
        reasons.append("no casing / open-hole row covers " + ", ".join(f"{a:.2f}-{b:.2f} m" for a, b in gaps)
                       + " - the bore there is unknown")
    if reasons:
        return _not_assessed(reasons)

    string_rows = [{"kind": "string", "name": f"{row.get('type', '')} (row {n})", "top_m": t, "bottom_m": b,
                    "id_in": float(row["id"]),
                    "volume_bbl": engine.calc_pipe_capacity_bbl_ft(float(row["id"])) * (b - t) * FT_PER_M}
                   for n, row, t, b in placed]
    running = [row for row in pumps if float(row["spm"]) > 0]
    pump_rows = [{"kind": "pump", "name": str(row.get("name") or f"Pump {n}"),
                  "output_bbl_stk": _num(row.get("output_bbl_stk")), "spm": float(row["spm"]),
                  "rate_gpm": (float(row["output_bbl_stk"]) * float(row["spm"]) * GAL_PER_BBL
                               if float(row["spm"]) > 0 else 0.0)}
                 for n, row in enumerate(pumps, 1)]
    string_volume = sum(r["volume_bbl"] for r in string_rows)
    annular_volume = sum(r["volume_bbl"] for r in annulus)
    total = string_volume + annular_volume
    notes = []
    flow = sum(r["rate_gpm"] for r in pump_rows) if running else None
    if flow is None:
        notes.append("no running pump (SPM > 0): flow rate and times are UNKNOWN")
    strokes = None
    if running and len({float(r["spm"]) for r in running}) == 1:
        strokes = engine.calc_bottoms_up_strokes(annular_volume, sum(float(r["output_bbl_stk"]) for r in running))
    elif running:
        notes.append("running pumps have different SPM: bottoms-up strokes per pump are not one number")
    results = {"string_length_m": length_m, "string_volume_bbl": string_volume,
               "annular_volume_bbl": annular_volume, "circulating_volume_bbl": total, "flow_rate_gpm": flow,
               # canonical lag-time relation, only with a running pump (it returns 0 for no flow)
               "surface_to_bit_min": engine.calc_lag_time(string_volume, flow) if flow else None,
               "lag_time_min": engine.calc_lag_time(annular_volume, flow) if flow else None,
               "circulation_time_min": engine.calc_lag_time(total, flow) if flow else None,
               "bottoms_up_strokes": strokes}
    return {"status": "ASSESSED", "reasons": [], "notes": notes, "results": results,
            "components": pump_rows + string_rows + annulus}


def _not_assessed(reasons: List[str]) -> Dict[str, Any]:
    return {"status": "NOT ASSESSED", "reasons": reasons, "notes": [],
            "results": dict.fromkeys(RESULT_FIELDS), "components": []}
