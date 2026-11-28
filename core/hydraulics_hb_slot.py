"""M415/M416 (R-HYD-2): annular pressure loss of a Herschel-Bulkley fluid, narrow-slot model, with a declared
laminar-turbulent transition band and Colebrook turbulent friction. Clean-room implementation.

SCREENING. Method specification (``docs/engineering/R_HYD_2_HB_SLOT_METHOD_SPECIFICATION.md``):

Geometry. A concentric annulus of outer diameter Do (hole / casing ID) and inner diameter Di (pipe OD) is treated as a
slot of gap delta = (Do - Di) / 2; hydraulic diameter Dh = Do - Di; mean velocity V = Q / (pi/4 (Do^2 - Di^2)).
The narrow-slot idealisation is used only for kappa = Di / Do >= 0.3 (Newtonian check: the slot f.Re = 24 differs from
the exact concentric-annulus value by < 2.5 % at kappa 0.3); smaller kappa is refused.

Rheology. tau = tau0 + K gamma^n (tau > tau0), declared tau0 >= 0, K > 0, 0.1 <= n <= 1.

Laminar (exact slot solution, derived here from the momentum balance tau(y) = G y and q = (2/G^2) int tau gamma dtau;
the same relation is Founargiotakis, Kelessidis & Maglione 2008, Can. J. Chem. Eng. 86:676, slot eqs.):

    V(tau_w) = delta / (2 tau_w^2) K^(-1/n) S^((n+1)/n) n [ S / (2n+1) + tau0 / (n+1) ],   S = tau_w - tau0

solved for tau_w by bisection. n = 1 reduces to the Buckingham slot form, tau0 = 0 to the power-law slot form, both
to plane Poiseuille V = G delta^2 / (12 mu). Local flow index n' = d ln tau_w / d ln(12 V / Dh) (analytic),
K' = tau_w / (12 V / Dh)^n', generalised Reynolds number Re_G = rho V^(2-n') Dh^n' / (K' 12^(n'-1)) = 12 rho V^2 /
tau_w,lam; laminar Fanning friction f = 24 / Re_G.

Transition band (declared, never defaulted):
* ``founargiotakis-2008``: Re1 = 3250 - 1150 n', Re2 = 4150 - 1150 n' (their eqs. 18-19); 0 < n' <= 1.
* ``erge-2015`` (concentric, e = 0): Re1 = 2100 n'^0.331 (1 + 1.402 kappa - 0.977 kappa^2),
  Re2 = 2900 n'^(-0.039 Re1^0.307) (Erge et al. 2015, eqs. 17-18, as documented in BoreTHM ``fluids.transition_band``,
  Apache-2.0 - method reference only; not re-checked against the paper: a stated verification gap, reported as NOT
  VERIFIED in every summary and case note since M482). Re1 holds for
  0.1 < n' < 1; Re2 was fitted at kappa 0.5 for 0.15 < n' < 0.4 - a flow at or above Re1 outside that n' range is
  refused (no extrapolation), and kappa != 0.5 is a warning.

Turbulent: Colebrook (1939), 1/sqrt(f_D) = -2 log10(eps / (3.7 Dh) + 2.51 / (Re sqrt(f_D))), Fanning = f_D / 4,
evaluated on Re_G (a Newtonian correlation on the generalised Reynolds number - an approximation, stated).
Transitional: f = f_lam(Re1) + (f_turb(Re2) - f_lam(Re1)) (Re_G - Re1) / (Re2 - Re1), so each correlation is used
only at its own end of the band. Pressure gradient dp/dL = 2 f rho V^2 / Dh = 4 tau_w / Dh.

Zero flow is a value: no flow, no frictional loss (0 psi); the yield onset 4 tau0 L / Dh is reported separately.
Nothing is assumed: every input is declared, missing -> NOT ASSESSED, non-finite or negative values are refused.
Isothermal, concentric, no pipe rotation or movement, no cuttings, no tool joints. Not API RP 13D.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

METHOD_ID = "m416.hb_slot_annulus"
METHOD_VERSION = "M416 Herschel-Bulkley slot annulus v1"
CALCULATOR = "Annular pressure loss (Herschel-Bulkley slot, R-HYD-2)"
LABEL = ("SCREENING - concentric-annulus friction loss, Herschel-Bulkley narrow-slot model with a declared transition "
         "band and Colebrook turbulent friction; isothermal, no eccentricity or pipe rotation; not API RP 13D")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
LAMINAR, TRANSITIONAL, TURBULENT, NO_FLOW = "LAMINAR", "TRANSITIONAL", "TURBULENT", "NO FLOW"
CRITERIA = ("founargiotakis-2008", "erge-2015")

# exact unit definitions (SI internally)
M_PER_IN = 0.0254
M_PER_FT = 0.3048
M3S_PER_GPM = 3.785411784e-3 / 60.0
KGM3_PER_PPG = 0.45359237 / 3.785411784e-3
PA_PER_HB_UNIT = 4.4482216152605 / (100.0 * M_PER_FT ** 2)        # 1 lbf/100 ft2 in Pa
PA_PER_PSI = 4.4482216152605 / M_PER_IN ** 2

KAPPA_MIN = 0.3
N_RANGE = (0.1, 1.0)
ERGE_RE2_N_RANGE = (0.15, 0.4)
#: M482: transition criteria whose coefficients have NOT been checked against the primary paper. The note is shown in
#: every summary and stored in the case note; it is not part of the replayed results (the numbers are unchanged).
UNVERIFIED_CRITERIA = {
    "erge-2015": ("Erge et al. 2015 transition coefficients NOT VERIFIED against a primary paper - transcribed from "
                  "the BoreTHM secondary reference, which cites SPE Drill. Complet. 30(3) 257-271 (DOI 10.2118/167950-"
                  "PA) eqs. 17-18; the transition paper J. Pet. Sci. Eng. 128:128-139 (DOI 10.1016/j.petrol.2015.02."
                  "007) is a distinct publication and which of the two holds these coefficients is unresolved (M541); "
                  "matches BoreTHM fluids.transition_band at e = 0; use for comparison only"),
}
COLEBROOK_TOL = 1e-12
COLEBROOK_MAX_ITER = 100
BISECTION_ITER = 200

#: scalar inputs: key, unit, required
FIELDS: Tuple[Tuple[str, str, bool], ...] = (
    ("hole_id_in", "in", True), ("pipe_od_in", "in", True), ("length_ft", "ft", True),
    ("flow_rate_gpm", "gpm", True), ("density_ppg", "ppg", True), ("tau0_lbf_100ft2", "lbf/100ft²", True),
    ("k_lbf_sn_100ft2", "lbf·sⁿ/100ft²", True), ("n_index", "", True), ("roughness_in", "in", True),
)
TEXT_FIELDS = (("transition_criterion", "", True),)
UNITS = {key: unit for key, unit, _required in FIELDS + TEXT_FIELDS}


class SlotError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(value: Any, key: str) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise SlotError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SlotError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise SlotError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise SlotError(f"unknown input(s): {', '.join(sorted(unknown))}")
    frozen: Dict[str, Any] = {key: _number(inputs.get(key), key) for key, _u, _r in FIELDS}
    criterion = inputs.get("transition_criterion")
    criterion = criterion.strip() if isinstance(criterion, str) and criterion.strip() else None
    if criterion is not None and criterion not in CRITERIA:
        raise SlotError(f"transition criterion {criterion!r} is not one of {', '.join(CRITERIA)}")
    frozen["transition_criterion"] = criterion
    return frozen


def verification_note(criterion: Optional[str]) -> Optional[str]:
    """M482: the NOT VERIFIED statement for a declared transition criterion (None when none applies)."""
    return UNVERIFIED_CRITERIA.get(criterion) if criterion else None


def inputs_sha256(frozen: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(frozen), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---- physics (SI) ------------------------------------------------------------------------------------------------
def slot_velocity(tau_w: float, tau0: float, k: float, n: float, delta: float) -> float:
    """Mean laminar velocity (m/s) in a slot of gap ``delta`` (m) at wall shear stress ``tau_w`` (Pa)."""
    if tau_w <= tau0:
        return 0.0
    s = tau_w - tau0
    return delta / (2.0 * tau_w ** 2) * k ** (-1.0 / n) * s ** ((n + 1.0) / n) * n * (s / (2 * n + 1) + tau0 / (n + 1))


def local_flow_index(tau_w: float, tau0: float, n: float) -> float:
    """n' = d ln tau_w / d ln V on the laminar slot curve (analytic)."""
    s = tau_w - tau0
    f = s ** ((n + 1.0) / n) * (s / (2 * n + 1) + tau0 / (n + 1))
    df = ((n + 1.0) / n) * s ** (1.0 / n) * (s / (2 * n + 1) + tau0 / (n + 1)) + s ** ((n + 1.0) / n) / (2 * n + 1)
    return 1.0 / (-2.0 + tau_w * df / f)


def laminar_wall_stress(v: float, tau0: float, k: float, n: float, delta: float) -> float:
    """tau_w (Pa) with slot_velocity(tau_w) = v (bisection to machine precision)."""
    lo = tau0
    hi = max(tau0 * 2.0, 1e-6)
    while slot_velocity(hi, tau0, k, n, delta) < v:
        hi *= 2.0
        if hi > 1e12:
            raise SlotError("laminar wall shear stress could not be bracketed")
    for _ in range(BISECTION_ITER):
        mid = 0.5 * (lo + hi)
        if slot_velocity(mid, tau0, k, n, delta) < v:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-15 * hi:
            break
    return 0.5 * (lo + hi)


def colebrook_darcy(re: float, relative_roughness: float) -> Tuple[Optional[float], int]:
    """Darcy friction factor by fixed-point iteration on 1/sqrt(f); (None, iterations) if it does not converge."""
    x = 1.0 / math.sqrt(0.02)
    for iteration in range(1, COLEBROOK_MAX_ITER + 1):
        arg = relative_roughness / 3.7 + 2.51 * x / re
        new = -2.0 * math.log10(arg)
        if abs(new - x) <= COLEBROOK_TOL * abs(new):
            return 1.0 / new ** 2, iteration
        x = new
    return None, COLEBROOK_MAX_ITER


def transition_band(criterion: str, n_prime: float, kappa: float) -> Tuple[float, float]:
    if criterion == "founargiotakis-2008":
        return 3250.0 - 1150.0 * n_prime, 4150.0 - 1150.0 * n_prime
    re1 = 2100.0 * n_prime ** 0.331 * (1.0 + 1.402 * kappa - 0.977 * kappa ** 2)
    re2 = 2900.0 * n_prime ** (-0.039 * re1 ** 0.307)
    return re1, re2


# ---- evaluation --------------------------------------------------------------------------------------------------
def evaluate(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    v = freeze(inputs)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v), "method_version": METHOD_VERSION,
            "verification_note": verification_note(v["transition_criterion"])}
    missing = [key for key, _u, required in FIELDS + TEXT_FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    do, di = v["hole_id_in"], v["pipe_od_in"]
    if di <= 0 or do <= 0:
        raise SlotError("hole ID and pipe OD must be > 0")
    if do <= di:
        raise SlotError("the hole / casing ID must exceed the pipe OD")
    for key in ("length_ft", "density_ppg", "k_lbf_sn_100ft2"):
        if v[key] <= 0:
            raise SlotError(f"{key} must be > 0")
    for key in ("flow_rate_gpm", "tau0_lbf_100ft2", "roughness_in"):
        if v[key] < 0:
            raise SlotError(f"{key} cannot be negative")
    n = v["n_index"]
    if not N_RANGE[0] <= n <= N_RANGE[1]:
        return {"status": NOT_ASSESSED, "reason": f"flow index n {n:g} outside the supported {N_RANGE[0]:g}-"
                                                  f"{N_RANGE[1]:g} (no shear-thickening, no extrapolation)", **base}
    kappa = di / do
    if kappa < KAPPA_MIN:
        return {"status": NOT_ASSESSED, "reason": f"diameter ratio {kappa:.3f} < {KAPPA_MIN:g}: the narrow-slot "
                                                  f"idealisation is not used for wide annuli", **base}
    dh = (do - di) * M_PER_IN
    delta = dh / 2.0
    area = math.pi / 4.0 * ((do * M_PER_IN) ** 2 - (di * M_PER_IN) ** 2)
    length = v["length_ft"] * M_PER_FT
    rho = v["density_ppg"] * KGM3_PER_PPG
    tau0 = v["tau0_lbf_100ft2"] * PA_PER_HB_UNIT
    k = v["k_lbf_sn_100ft2"] * PA_PER_HB_UNIT
    rel_rough = v["roughness_in"] * M_PER_IN / dh
    q = v["flow_rate_gpm"] * M3S_PER_GPM
    vel = q / area
    onset_psi = 4.0 * tau0 / dh * length / PA_PER_PSI
    common = {"kappa": kappa, "hydraulic_diameter_in": do - di, "yield_onset_psi": onset_psi,
              "velocity_ft_min": vel / M_PER_FT * 60.0}
    if q == 0.0:
        return {"status": COMPUTED, **base, **common, "regime": NO_FLOW, "pressure_loss_psi": 0.0,
                "gradient_psi_ft": 0.0, "re_generalised": None, "re1": None, "re2": None, "n_prime": None,
                "fanning_friction": None, "colebrook_iterations": None, "plug_ratio": None, "warnings": [],
                "reason": "no flow: no frictional loss; the yield onset 4 tau0 L / Dh is reported separately"}
    tau_lam = laminar_wall_stress(vel, tau0, k, n, delta)
    n_prime = local_flow_index(tau_lam, tau0, n)
    k_prime = tau_lam / (12.0 * vel / dh) ** n_prime
    re = 12.0 * rho * vel ** 2 / tau_lam
    criterion = v["transition_criterion"]
    warnings: List[str] = []
    if criterion == "erge-2015" and not 0.1 < n_prime < 1.0:
        return {"status": NOT_ASSESSED, **base, **common, "reason": f"Erge 2015 Re1 holds for 0.1 < n' < 1; "
                                                                    f"n' = {n_prime:.4f}"}
    re1, re2 = transition_band(criterion, n_prime, kappa)
    if criterion == "erge-2015":
        if re >= re1 and not ERGE_RE2_N_RANGE[0] < n_prime < ERGE_RE2_N_RANGE[1]:
            return {"status": NOT_ASSESSED, **base, **common, "re_generalised": re, "re1": re1, "n_prime": n_prime,
                    "reason": f"Re_G {re:.0f} >= Re1 {re1:.0f} needs the Erge Re2 correlation, fitted only for "
                              f"{ERGE_RE2_N_RANGE[0]:g} < n' < {ERGE_RE2_N_RANGE[1]:g}; n' = {n_prime:.4f}"}
        if re >= re1 and abs(kappa - 0.5) > 1e-9:
            warnings.append(f"Erge Re2 was fitted at kappa 0.5; this annulus has kappa {kappa:.3f}")
    f_lam_re = 24.0 / re
    iterations = None
    darcy = None
    if re < re1:
        regime, fanning = LAMINAR, f_lam_re
    else:
        re_turb = re if re > re2 else re2
        darcy, iterations = colebrook_darcy(re_turb, rel_rough)
        if darcy is None:
            return {"status": NOT_ASSESSED, **base, **common, "re_generalised": re, "re1": re1, "re2": re2,
                    "n_prime": n_prime, "reason": f"Colebrook did not converge in {COLEBROOK_MAX_ITER} iterations"}
        if re_turb < 4000.0:
            warnings.append(f"Colebrook evaluated at Re {re_turb:.0f} < 4000, below its fully turbulent domain")
        if re > re2:
            regime, fanning = TURBULENT, darcy / 4.0
        else:
            regime = TRANSITIONAL
            f1 = 24.0 / re1
            fanning = f1 + (darcy / 4.0 - f1) * (re - re1) / (re2 - re1)
    gradient = 2.0 * fanning * rho * vel ** 2 / dh               # Pa/m
    loss_psi = gradient * length / PA_PER_PSI
    return {"status": COMPUTED, **base, **common, "regime": regime, "pressure_loss_psi": loss_psi,
            "gradient_psi_ft": gradient * M_PER_FT / PA_PER_PSI, "re_generalised": re, "re1": re1, "re2": re2,
            "n_prime": n_prime, "k_prime_lbf_sn_100ft2": k_prime / PA_PER_HB_UNIT, "fanning_friction": fanning,
            "colebrook_darcy": darcy, "colebrook_iterations": iterations,
            "wall_shear_laminar_lbf_100ft2": tau_lam / PA_PER_HB_UNIT,
            "plug_ratio": tau0 / tau_lam, "warnings": warnings,
            "reason": f"{regime.lower()} by the {criterion} band (Re_G {re:.0f}; Re1 {re1:.0f}, Re2 {re2:.0f})"}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    note = result.get("verification_note")
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL] + ([f"NOT VERIFIED: {note}"] if note else [])
    lines = [LABEL, f"Method {METHOD_ID} {METHOD_VERSION}."]
    if note:
        lines.append(f"NOT VERIFIED: {note}.")
    lines.append(f"Regime {result['regime']}: {result['reason']}.")
    lines.append(f"Mean annular velocity {result['velocity_ft_min']:.1f} ft/min; diameter ratio {result['kappa']:.3f}.")
    lines.append(f"Friction loss {result['pressure_loss_psi']:.2f} psi ({result['gradient_psi_ft']:.5f} psi/ft).")
    if result.get("fanning_friction") is not None:
        lines.append(f"Fanning friction {result['fanning_friction']:.6f}; n' {result['n_prime']:.4f}; "
                     f"plug ratio tau0/tau_w {result['plug_ratio']:.3f}.")
    if result.get("colebrook_iterations"):
        lines.append(f"Colebrook Darcy factor {result['colebrook_darcy']:.6f} in {result['colebrook_iterations']} "
                     f"iteration(s).")
    lines.append(f"Yield onset (zero-flow limit) {result['yield_onset_psi']:.2f} psi - informational, not a flow loss.")
    lines.extend(f"WARNING: {w}" for w in result.get("warnings") or [])
    return lines


RESULT_FIELDS = (("regime", ""), ("pressure_loss_psi", "psi"), ("gradient_psi_ft", "psi/ft"),
                 ("velocity_ft_min", "ft/min"), ("re_generalised", ""), ("re1", ""), ("re2", ""), ("n_prime", ""),
                 ("fanning_friction", ""), ("colebrook_darcy", ""), ("plug_ratio", ""), ("yield_onset_psi", "psi"),
                 ("kappa", ""))


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    v = result["inputs"]
    inputs: Dict[str, Any] = {key: {"value": v[key], "unit": UNITS[key], "label": key,
                                    "source": "DECLARED" if v[key] is not None else "NOT_ENTERED"} for key in UNITS}
    inputs["inputs_sha256"] = {"value": result["inputs_sha256"], "unit": "", "label": "inputs SHA-256"}
    results: Dict[str, Any] = {"status": {"value": result["status"], "label": result.get("reason") or LABEL}}
    if result["status"] == COMPUTED:
        for key, unit in RESULT_FIELDS:
            results[key] = {"value": result.get(key), "unit": unit, "label": key}
        results["warnings"] = {"value": "; ".join(result.get("warnings") or []), "label": "warnings"}
    return inputs, results


def unit_of(key: str) -> str:
    return dict(RESULT_FIELDS).get(key, "")


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: not computed ({result.get('reason')}).")
    inputs, results = case_payload(result)
    v = result["inputs"]
    return cc.save_case(db, calculator=CALCULATOR,
                        name=f"HB slot annulus {v['hole_id_in']:g} x {v['pipe_od_in']:g} in, "
                             f"{v['flow_rate_gpm']:g} gpm, {result['regime']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=_case_note(LABEL, result))


def _case_note(label: str, result: Mapping[str, Any]) -> str:
    note = verification_note((result.get("inputs") or {}).get("transition_criterion"))
    return f"{label}; " + (f"NOT VERIFIED: {note}; " if note else "") + f"inputs SHA-256 {result['inputs_sha256']}"


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    if inputs_sha256(freeze(values)) != (inputs.get("inputs_sha256") or {}).get("value"):
        raise IntegrityError("the stored HB slot inputs fail their SHA-256 check")
    return case_payload(evaluate(values))[1]
