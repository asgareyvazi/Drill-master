"""M419/M420: quasi-steady surge and swab pressure for a closed-end string, geometry-aware by annular section.

SCREENING. Method specification (``docs/engineering/SURGE_SWAB_METHOD_SPECIFICATION.md``):

Pipe moving at a steady speed v_p (ft/min, a magnitude; running in = surge, pulling out = swab). The string is
CLOSED-END (float, plugged bit or no flow through the bore): the fluid displaced below a depth z leaves through the
annulus there, so the annular flow in a section i is Q_i = v_p (pi/4) d_i^2, with d_i the string OD in that section.
Mean annular fluid velocity V_i = Q_i / A_i. The wall of the moving pipe drags fluid with it; the Burkhardt (1961)
effective velocity V_eff,i = V_i + K_c v_p (K_c the declared clinging constant) is used as the flow velocity in the
canonical R-HYD-2 annulus model (``core.hydraulics_hb_slot``: Herschel-Bulkley slot, declared transition band,
Colebrook). For a Newtonian fluid in laminar slot flow the Couette-Poiseuille solution gives exactly K_c = 0.5
(benchmark SS1); Burkhardt's laminar chart gives about 0.45 for typical annuli - K_c is declared, never defaulted.

The surge (or swab) pressure at the bit is the sum of the section friction losses; the two have the same magnitude
in this model and opposite sign. With a declared TVD the equivalent density is MW +/- dP / (g_ppg TVD), with the exact
hydrostatic gradient g_ppg = 0.0519480 psi/ft per ppg from SI definitions (the common 0.052 is its rounding).

Limits (stated, refused or disclosed): quasi-steady (no acceleration / deceleration peak, no fluid or formation
compressibility, no pipe elasticity: Lubinski-type transient surge is NOT IMPLEMENTED); open-ended pipe (flow split
between bore and annulus) is NOT IMPLEMENTED in v1 and refused; concentric annuli, isothermal; the R-HYD-2 limits
apply to every section (kappa >= 0.3, 0.1 <= n <= 1). If any section is NOT ASSESSED the total is NOT ASSESSED - a
partial sum is never shown as the total.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from core import hydraulics_hb_slot as hb

METHOD_ID = "m420.surge_swab"
METHOD_VERSION = "M420 quasi-steady surge/swab, closed-end string v1"
CALCULATOR = "Surge and swab (quasi-steady, closed-end)"
LABEL = ("SCREENING - quasi-steady surge / swab for a closed-end string: Burkhardt effective velocity with a declared "
         "clinging constant in the R-HYD-2 Herschel-Bulkley slot annulus model; no transient, open-end or "
         "compressibility effects")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
PIPE_ENDS = ("closed", "open")
PSI_FT_PER_PPG = hb.KGM3_PER_PPG * 9.80665 * hb.M_PER_FT / hb.PA_PER_PSI   # 0.0519480 psi/ft per ppg

FIELDS: Tuple[Tuple[str, str, bool], ...] = (
    ("trip_speed_ft_min", "ft/min", True), ("clinging_constant", "", True), ("density_ppg", "ppg", True),
    ("tau0_lbf_100ft2", "lbf/100ft²", True), ("k_lbf_sn_100ft2", "lbf·sⁿ/100ft²", True), ("n_index", "", True),
    ("roughness_in", "in", True), ("tvd_ft", "ft", False),
)
TEXT_FIELDS = (("transition_criterion", "", True), ("pipe_end", "", True))
SECTION_FIELDS: Tuple[Tuple[str, str], ...] = (("hole_id_in", "in"), ("pipe_od_in", "in"), ("length_ft", "ft"))
UNITS = {key: unit for key, unit, _required in FIELDS + TEXT_FIELDS}


class SurgeSwabError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(value: Any, key: str) -> Optional[float]:
    try:
        return hb._number(value, key)
    except hb.SlotError as exc:
        raise SurgeSwabError(str(exc)) from exc


def freeze(inputs: Mapping[str, Any], sections: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise SurgeSwabError(f"unknown input(s): {', '.join(sorted(unknown))}")
    frozen: Dict[str, Any] = {key: _number(inputs.get(key), key) for key, _u, _r in FIELDS}
    for key, _u, _r in TEXT_FIELDS:
        text = inputs.get(key)
        frozen[key] = text.strip() if isinstance(text, str) and text.strip() else None
    if frozen["transition_criterion"] is not None and frozen["transition_criterion"] not in hb.CRITERIA:
        raise SurgeSwabError(f"transition criterion {frozen['transition_criterion']!r} is not one of "
                             f"{', '.join(hb.CRITERIA)}")
    if frozen["pipe_end"] is not None and frozen["pipe_end"] not in PIPE_ENDS:
        raise SurgeSwabError(f"pipe end {frozen['pipe_end']!r} is not one of {', '.join(PIPE_ENDS)}")
    rows = []
    for index, section in enumerate(sections, start=1):
        extra = set(section) - {key for key, _unit in SECTION_FIELDS}
        if extra:
            raise SurgeSwabError(f"section {index}: unknown field(s) {', '.join(sorted(extra))}")
        row = {key: _number(section.get(key), f"section {index} {key}") for key, _unit in SECTION_FIELDS}
        if all(value is None for value in row.values()):
            continue
        rows.append(row)
    frozen["sections"] = rows
    return frozen


def inputs_sha256(frozen: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(frozen), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluate(inputs: Mapping[str, Any], sections: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    v = freeze(inputs, sections)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v), "method_version": METHOD_VERSION}
    missing = [key for key, _u, required in FIELDS + TEXT_FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    if v["pipe_end"] == "open":
        return {"status": NOT_ASSESSED, "reason": "open-ended string (bore / annulus flow split) is NOT IMPLEMENTED "
                                                  "in v1; only a closed-end string is evaluated", **base}
    if not v["sections"]:
        return {"status": NOT_ASSESSED, "reason": "no annular sections entered", **base}
    if v["trip_speed_ft_min"] < 0:
        raise SurgeSwabError("the trip speed is a magnitude and cannot be negative")
    if not 0.0 <= v["clinging_constant"] <= 1.0:
        raise SurgeSwabError("the clinging constant must be between 0 and 1")
    if v["tvd_ft"] is not None and v["tvd_ft"] <= 0:
        raise SurgeSwabError("TVD must be > 0 when declared")
    vp = v["trip_speed_ft_min"] / 60.0 * hb.M_PER_FT                      # m/s
    rows: List[Dict[str, Any]] = []
    for index, sec in enumerate(v["sections"], start=1):
        gaps = [key for key, _unit in SECTION_FIELDS if sec[key] is None]
        if gaps:
            return {"status": NOT_ASSESSED, **base, "sections": rows,
                    "reason": f"section {index}: not given: {', '.join(gaps)} (a partial sum is not a total)"}
        do, di = sec["hole_id_in"], sec["pipe_od_in"]
        if di <= 0 or do <= di:
            raise SurgeSwabError(f"section {index}: hole ID must exceed pipe OD > 0")
        area = math.pi / 4.0 * ((do * hb.M_PER_IN) ** 2 - (di * hb.M_PER_IN) ** 2)
        displaced = vp * math.pi / 4.0 * (di * hb.M_PER_IN) ** 2            # m3/s up the annulus
        v_fluid = displaced / area
        v_eff = v_fluid + v["clinging_constant"] * vp
        q_eff_gpm = v_eff * area / hb.M3S_PER_GPM
        try:
            section_result = hb.evaluate({
                "hole_id_in": do, "pipe_od_in": di, "length_ft": sec["length_ft"], "flow_rate_gpm": q_eff_gpm,
                "density_ppg": v["density_ppg"], "tau0_lbf_100ft2": v["tau0_lbf_100ft2"],
                "k_lbf_sn_100ft2": v["k_lbf_sn_100ft2"], "n_index": v["n_index"], "roughness_in": v["roughness_in"],
                "transition_criterion": v["transition_criterion"]})
        except hb.SlotError as exc:
            raise SurgeSwabError(f"section {index}: {exc}") from exc
        row = {"section": index, **sec, "fluid_velocity_ft_min": v_fluid / hb.M_PER_FT * 60.0,
               "effective_velocity_ft_min": v_eff / hb.M_PER_FT * 60.0, "equivalent_flow_gpm": q_eff_gpm,
               "status": section_result["status"], "regime": section_result.get("regime"),
               "pressure_psi": section_result.get("pressure_loss_psi"),
               "warnings": section_result.get("warnings") or [], "reason": section_result.get("reason")}
        rows.append(row)
        if section_result["status"] != hb.COMPUTED:
            return {"status": NOT_ASSESSED, **base, "sections": rows,
                    "reason": f"section {index}: {section_result.get('reason')} (a partial sum is not a total)"}
    total = sum(r["pressure_psi"] for r in rows)
    out = {"status": COMPUTED, **base, "sections": rows, "surge_psi": total, "swab_psi": total,
           "trip_speed_ft_min": v["trip_speed_ft_min"], "warnings": [w for r in rows for w in r["warnings"]],
           "reason": f"{len(rows)} section(s), closed-end, K_c {v['clinging_constant']:g}"}
    if v["tvd_ft"] is None:
        out.update(surge_emw_ppg=None, swab_emw_ppg=None, emw_reason="no TVD declared: equivalent density not "
                                                                     "assessed")
    else:
        delta = total / (PSI_FT_PER_PPG * v["tvd_ft"])
        out.update(surge_emw_ppg=v["density_ppg"] + delta, swab_emw_ppg=v["density_ppg"] - delta,
                   emw_reason=f"MW +/- dP / ({PSI_FT_PER_PPG:.7f} x TVD)")
    return out


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL, f"Method {METHOD_ID} {METHOD_VERSION}; {result['reason']}."]
    for row in result["sections"]:
        lines.append(f"Section {row['section']}: {row['hole_id_in']:g} x {row['pipe_od_in']:g} in over "
                     f"{row['length_ft']:g} ft - fluid {row['fluid_velocity_ft_min']:.1f} ft/min, effective "
                     f"{row['effective_velocity_ft_min']:.1f} ft/min, {row['regime']}, {row['pressure_psi']:.2f} psi.")
    lines.append(f"Surge (running in) +{result['surge_psi']:.2f} psi; swab (pulling out) -{result['swab_psi']:.2f} psi "
                 f"at {result['trip_speed_ft_min']:g} ft/min.")
    if result.get("surge_emw_ppg") is not None:
        lines.append(f"Equivalent density: surge {result['surge_emw_ppg']:.3f} ppg, swab {result['swab_emw_ppg']:.3f} "
                     f"ppg ({result['emw_reason']}).")
    else:
        lines.append(f"Equivalent density NOT ASSESSED: {result['emw_reason']}.")
    lines.extend(f"WARNING: {w}" for w in result.get("warnings") or [])
    return lines


RESULT_FIELDS = (("surge_psi", "psi"), ("swab_psi", "psi"), ("surge_emw_ppg", "ppg"), ("swab_emw_ppg", "ppg"))


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["sections"] = {"value": v["sections"], "unit": "in / in / ft", "label": "annular sections as entered"}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == COMPUTED:
        for key, unit in RESULT_FIELDS:
            results[key] = {"value": result.get(key), "unit": unit, "label": key}
        for row in result["sections"]:
            results[f"section{row['section']}_psi"] = {"value": row["pressure_psi"], "unit": "psi",
                                                       "label": f"section {row['section']} {row['regime']}"}
            results[f"section{row['section']}_regime"] = {"value": row["regime"], "label": "regime"}
    return inputs, results


def unit_of(key: str) -> str:
    if key.endswith("_psi"):
        return "psi"
    return dict(RESULT_FIELDS).get(key, "")


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    return cc.save_case(db, calculator=CALCULATOR,
                        name=f"Surge/swab at {result['trip_speed_ft_min']:g} ft/min, "
                             f"{len(result['sections'])} section(s)",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    sections = (inputs.get("sections") or {}).get("value") or []
    if not isinstance(sections, list) or inputs_sha256(freeze(values, sections)) != (
            inputs.get("inputs_sha256") or {}).get("value"):
        raise IntegrityError("the stored surge/swab inputs fail their SHA-256 check")
    return case_payload(evaluate(values, sections))[1]
