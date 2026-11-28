"""M538: exact laminar axial flow of a Herschel-Bulkley fluid in a CONCENTRIC annulus (stationary walls), for any
diameter ratio 0.01 <= kappa <= 0.99 - in particular the wide annuli kappa < 0.3 that the M416 narrow-slot model
refuses. Separate method id and version; M416 is unchanged. Clean-room implementation derived here from the momentum
balance (the problem is the classical one of Fredrickson & Bird 1958, Ind. Eng. Chem. 50(3):347, for Bingham and
power-law fluids, and of Hanks 1979, Ind. Eng. Chem. Fundam. 18(3):191, DOI 10.1021/i260071a024, for yield-
pseudoplastic fluids; those papers are cited as method references only - no equation or table was copied from them).

SCREENING. Laminar only. Isothermal, incompressible, fully developed, concentric, no pipe rotation or axial pipe
movement, no tool joints or cuttings. Not API RP 13D.

Derivation (r measured from the axis, outer radius Ro, inner radius Ri = kappa Ro, x = r / Ro, G = -dp/dz > 0):

* Momentum: (1/r) d(r tau)/dr = -G  =>  tau(x) = T (x - lambda^2 / x),  T = G Ro / 2, where lambda Ro is the radius
  at which the shear stress (and the velocity gradient) vanishes.
* Rheology: |tau| = tau0 + K gamma^n for |tau| > tau0, gamma = |du/dr|; |tau| <= tau0 is unsheared (plug).
* Plug edges: T (x - lambda^2/x) = +-tau0  =>  x_+- = +-b + sqrt(b^2 + lambda^2),  b = tau0 / (2T); so
  x_+ - x_- = tau0 / T and flow needs tau0 / T < 1 - kappa (the yield onset G = 4 tau0 / Dh, Dh = Do - Di).
* lambda follows from one plug velocity: Ro int_{x+}^{1} gamma_out dx = Ro int_{kappa}^{x-} gamma_in dx, with
  gamma_out = ((T (x - lambda^2/x) - tau0) / K)^(1/n), gamma_in = ((T (lambda^2/x - x) - tau0) / K)^(1/n).
  The difference is strictly decreasing in lambda^2 between lambda^2 = kappa^2 + kappa tau0 / T (x- = kappa) and
  lambda^2 = 1 - tau0 / T (x+ = 1): solved by bisection.
* Flow rate, integrating Q = 2 pi int u r dr by parts (the plug terms cancel exactly):
  Q = pi Ro^3 [ int_{x+}^{1} x^2 gamma_out dx - int_{kappa}^{x-} x^2 gamma_in dx ].
* Q(G) is strictly increasing; the declared Q is matched by bisection on log G. Integrals: composite Gauss-Legendre
  (32 panels x 16 nodes per region; the integrands are continuous and vanish at the plug edges).

Mean wall shear stress tau_w = G Dh / 4 (force balance on the annular fluid). Local flow index n' = d ln tau_w /
d ln V (central difference on the exact Q(G) curve). Generalised Reynolds number, slot-equivalent as in M416:
Re_G = 12 rho V^2 / tau_w. Laminar validity check (declared, the same band M416 uses): Founargiotakis, Kelessidis &
Maglione 2008, Re1 = 3250 - 1150 n'. Re_G >= Re1 -> NOT ASSESSED (this method has no transitional or turbulent
branch and never extrapolates).

Zero flow is a value: no flow, no frictional loss (0 psi); the yield onset 4 tau0 L / Dh is reported separately.
Every input is declared (missing -> NOT ASSESSED); non-finite, negative or inconsistent values are refused.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

METHOD_ID = "m538.hb_annulus_exact"
METHOD_VERSION = "M538 Herschel-Bulkley concentric annulus exact laminar v1"
CALCULATOR = "Annular pressure loss (Herschel-Bulkley exact concentric annulus, laminar)"
LABEL = ("SCREENING - laminar friction loss of a Herschel-Bulkley fluid in a concentric annulus, exact solution of the "
         "momentum balance for 0.01 <= kappa <= 0.99; laminar only (Re_G >= Re1 refused); isothermal, no "
         "eccentricity, pipe rotation or pipe movement; not API RP 13D")
COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
LAMINAR, NO_FLOW = "LAMINAR", "NO FLOW"

M_PER_IN = 0.0254
M_PER_FT = 0.3048
M3S_PER_GPM = 3.785411784e-3 / 60.0
KGM3_PER_PPG = 0.45359237 / 3.785411784e-3
PA_PER_HB_UNIT = 4.4482216152605 / (100.0 * M_PER_FT ** 2)        # 1 lbf/100 ft2 in Pa
PA_PER_PSI = 4.4482216152605 / M_PER_IN ** 2

KAPPA_RANGE = (0.01, 0.99)
N_RANGE = (0.1, 1.0)
PANELS, NODES = 32, 16
LAMBDA_ITER = 200
GRADIENT_ITER = 400
REL_TOL = 1e-13
N_PRIME_STEP = 1e-4

FIELDS: Tuple[Tuple[str, str, bool], ...] = (
    ("hole_id_in", "in", True), ("pipe_od_in", "in", True), ("length_ft", "ft", True),
    ("flow_rate_gpm", "gpm", True), ("density_ppg", "ppg", True), ("tau0_lbf_100ft2", "lbf/100ft²", True),
    ("k_lbf_sn_100ft2", "lbf·sⁿ/100ft²", True), ("n_index", "", True),
)
UNITS = {key: unit for key, unit, _required in FIELDS}

_GL_X, _GL_W = np.polynomial.legendre.leggauss(NODES)


class AnnulusError(ValueError):
    """Inputs that cannot be evaluated (the message says why)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _number(value: Any, key: str) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise AnnulusError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnnulusError(f"{key} {value!r} is not a number") from exc
    if not math.isfinite(number):
        raise AnnulusError(f"{key} must be finite")
    return number


def freeze(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    unknown = set(inputs) - set(UNITS)
    if unknown:
        raise AnnulusError(f"unknown input(s): {', '.join(sorted(unknown))}")
    return {key: _number(inputs.get(key), key) for key, _u, _r in FIELDS}


def inputs_sha256(frozen: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(frozen), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ---- physics (SI, dimensionless radius x = r / Ro) ------------------------------------------------------------------
def _integral(func, a: float, b: float) -> float:
    """Composite Gauss-Legendre integral of a vectorised ``func`` over [a, b] (0 for an empty interval)."""
    if b <= a:
        return 0.0
    edges = np.linspace(a, b, PANELS + 1)
    half = 0.5 * (edges[1:] - edges[:-1])
    mid = 0.5 * (edges[1:] + edges[:-1])
    x = (mid[:, None] + half[:, None] * _GL_X[None, :]).ravel()
    w = (half[:, None] * _GL_W[None, :]).ravel()
    return float(np.dot(w, func(x)))


def _shear_rates(t: float, lam2: float, tau0: float, k: float, n: float):
    def outer(x):
        return np.power(np.maximum(t * (x - lam2 / x) - tau0, 0.0) / k, 1.0 / n)

    def inner(x):
        return np.power(np.maximum(t * (lam2 / x - x) - tau0, 0.0) / k, 1.0 / n)

    return outer, inner


def _plug_edges(t: float, lam2: float, tau0: float) -> Tuple[float, float]:
    b = tau0 / (2.0 * t)
    root = math.sqrt(b * b + lam2)
    return root - b, root + b


def solve_lambda(t: float, kappa: float, tau0: float, k: float, n: float) -> float:
    """lambda^2 (dimensionless) at the stress scale T = G Ro / 2 (Pa); requires tau0 / T < 1 - kappa."""
    lo = kappa * kappa + kappa * tau0 / t
    hi = 1.0 - tau0 / t
    if not lo < hi:
        raise AnnulusError("no flow at this pressure gradient (below the yield onset)")
    for _ in range(LAMBDA_ITER):
        mid = 0.5 * (lo + hi)
        outer, inner = _shear_rates(t, mid, tau0, k, n)
        x_minus, x_plus = _plug_edges(t, mid, tau0)
        balance = _integral(outer, x_plus, 1.0) - _integral(inner, kappa, x_minus)
        if balance > 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-15 * hi:
            break
    return 0.5 * (lo + hi)


def flow_state(gradient_pa_m: float, ro_m: float, kappa: float, tau0: float, k: float, n: float) -> Dict[str, float]:
    """The exact laminar state at pressure gradient G (Pa/m): Q (m3/s), lambda, plug edges, plug velocity (m/s)."""
    t = gradient_pa_m * ro_m / 2.0
    if tau0 / t >= 1.0 - kappa:
        return {"q": 0.0, "lambda2": None, "x_minus": None, "x_plus": None, "plug_velocity": 0.0}
    lam2 = solve_lambda(t, kappa, tau0, k, n)
    outer, inner = _shear_rates(t, lam2, tau0, k, n)
    x_minus, x_plus = _plug_edges(t, lam2, tau0)
    q = math.pi * ro_m ** 3 * (_integral(lambda x: x * x * outer(x), x_plus, 1.0)
                               - _integral(lambda x: x * x * inner(x), kappa, x_minus))
    plug = ro_m * _integral(outer, x_plus, 1.0)
    return {"q": q, "lambda2": lam2, "x_minus": x_minus, "x_plus": x_plus, "plug_velocity": plug}


def annulus_flow_rate(gradient_pa_m: float, ro_m: float, kappa: float, tau0: float, k: float, n: float) -> float:
    return flow_state(gradient_pa_m, ro_m, kappa, tau0, k, n)["q"]


def solve_gradient(q: float, ro_m: float, kappa: float, tau0: float, k: float, n: float) -> float:
    """G (Pa/m) with annulus_flow_rate(G) = q > 0 (bisection on log G to a relative 1e-13)."""
    onset = 2.0 * tau0 / (ro_m * (1.0 - kappa))
    lo = onset if onset > 0 else 1e-12
    hi = max(lo * 2.0, 1.0)
    while annulus_flow_rate(hi, ro_m, kappa, tau0, k, n) < q:
        hi *= 4.0
        if hi > 1e15:
            raise AnnulusError("the pressure gradient could not be bracketed")
    for _ in range(GRADIENT_ITER):
        mid = math.sqrt(lo * hi) if lo > 0 else 0.5 * hi
        if annulus_flow_rate(mid, ro_m, kappa, tau0, k, n) < q:
            lo = mid
        else:
            hi = mid
        if hi - lo <= REL_TOL * hi:
            break
    return 0.5 * (lo + hi)


# ---- evaluation --------------------------------------------------------------------------------------------------
def evaluate(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    v = freeze(inputs)
    base = {"label": LABEL, "inputs": v, "inputs_sha256": inputs_sha256(v), "method_version": METHOD_VERSION}
    missing = [key for key, _u, required in FIELDS if required and v[key] is None]
    if missing:
        return {"status": NOT_ASSESSED, "reason": f"missing: {', '.join(missing)}", **base}
    do, di = v["hole_id_in"], v["pipe_od_in"]
    if di <= 0 or do <= 0:
        raise AnnulusError("hole ID and pipe OD must be > 0")
    if do <= di:
        raise AnnulusError("the hole / casing ID must exceed the pipe OD")
    for key in ("length_ft", "density_ppg", "k_lbf_sn_100ft2"):
        if v[key] <= 0:
            raise AnnulusError(f"{key} must be > 0")
    for key in ("flow_rate_gpm", "tau0_lbf_100ft2"):
        if v[key] < 0:
            raise AnnulusError(f"{key} cannot be negative")
    n = v["n_index"]
    if not N_RANGE[0] <= n <= N_RANGE[1]:
        return {"status": NOT_ASSESSED, "reason": f"flow index n {n:g} outside the supported {N_RANGE[0]:g}-"
                                                  f"{N_RANGE[1]:g} (no shear-thickening, no extrapolation)", **base}
    kappa = di / do
    if not KAPPA_RANGE[0] <= kappa <= KAPPA_RANGE[1]:
        return {"status": NOT_ASSESSED, "reason": f"diameter ratio {kappa:.4f} outside {KAPPA_RANGE[0]:g}-"
                                                  f"{KAPPA_RANGE[1]:g}", **base}
    ro = do * M_PER_IN / 2.0
    dh = (do - di) * M_PER_IN
    area = math.pi / 4.0 * ((do * M_PER_IN) ** 2 - (di * M_PER_IN) ** 2)
    length = v["length_ft"] * M_PER_FT
    rho = v["density_ppg"] * KGM3_PER_PPG
    tau0 = v["tau0_lbf_100ft2"] * PA_PER_HB_UNIT
    k = v["k_lbf_sn_100ft2"] * PA_PER_HB_UNIT
    q = v["flow_rate_gpm"] * M3S_PER_GPM
    vel = q / area
    onset_psi = 4.0 * tau0 / dh * length / PA_PER_PSI
    common = {"kappa": kappa, "hydraulic_diameter_in": do - di, "yield_onset_psi": onset_psi,
              "velocity_ft_min": vel / M_PER_FT * 60.0}
    if q == 0.0:
        return {"status": COMPUTED, **base, **common, "regime": NO_FLOW, "pressure_loss_psi": 0.0,
                "gradient_psi_ft": 0.0, "re_generalised": None, "re1": None, "n_prime": None,
                "wall_shear_mean_lbf_100ft2": None, "zero_shear_radius_in": None, "plug_inner_radius_in": None,
                "plug_outer_radius_in": None, "plug_velocity_ft_min": None, "warnings": [],
                "reason": "no flow: no frictional loss; the yield onset 4 tau0 L / Dh is reported separately"}
    g = solve_gradient(q, ro, kappa, tau0, k, n)
    state = flow_state(g, ro, kappa, tau0, k, n)
    q_hi = annulus_flow_rate(g * (1.0 + N_PRIME_STEP), ro, kappa, tau0, k, n)
    q_lo = annulus_flow_rate(g * (1.0 - N_PRIME_STEP), ro, kappa, tau0, k, n)
    n_prime = (math.log1p(N_PRIME_STEP) - math.log1p(-N_PRIME_STEP)) / math.log(q_hi / q_lo)
    tau_w = g * dh / 4.0
    re = 12.0 * rho * vel ** 2 / tau_w
    re1 = 3250.0 - 1150.0 * n_prime
    if re >= re1:
        return {"status": NOT_ASSESSED, **base, **common, "re_generalised": re, "re1": re1, "n_prime": n_prime,
                "reason": f"Re_G {re:.0f} >= Re1 {re1:.0f} (Founargiotakis 2008 band): this method is laminar only "
                          "and does not extrapolate; use M416 for transitional / turbulent flow (kappa >= 0.3)"}
    gradient_psi_ft = g * M_PER_FT / PA_PER_PSI
    return {"status": COMPUTED, **base, **common, "regime": LAMINAR,
            "pressure_loss_psi": g * length / PA_PER_PSI, "gradient_psi_ft": gradient_psi_ft,
            "re_generalised": re, "re1": re1, "n_prime": n_prime,
            "wall_shear_mean_lbf_100ft2": tau_w / PA_PER_HB_UNIT,
            "zero_shear_radius_in": math.sqrt(state["lambda2"]) * ro / M_PER_IN,
            "plug_inner_radius_in": state["x_minus"] * ro / M_PER_IN,
            "plug_outer_radius_in": state["x_plus"] * ro / M_PER_IN,
            "plug_velocity_ft_min": state["plug_velocity"] / M_PER_FT * 60.0, "warnings": [],
            "reason": f"laminar (Re_G {re:.0f} < Re1 {re1:.0f}); exact concentric-annulus solution"}


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    lines = [LABEL, f"Method {METHOD_ID} {METHOD_VERSION}.", f"Regime {result['regime']}: {result['reason']}.",
             f"Mean annular velocity {result['velocity_ft_min']:.1f} ft/min; diameter ratio {result['kappa']:.4f}.",
             f"Friction loss {result['pressure_loss_psi']:.2f} psi ({result['gradient_psi_ft']:.6f} psi/ft)."]
    if result["regime"] == LAMINAR:
        lines.append(f"Mean wall shear stress {result['wall_shear_mean_lbf_100ft2']:.3f} lbf/100ft²; n' "
                     f"{result['n_prime']:.4f}; zero-shear radius {result['zero_shear_radius_in']:.4f} in; plug "
                     f"{result['plug_inner_radius_in']:.4f}-{result['plug_outer_radius_in']:.4f} in.")
    lines.append(f"Yield onset (zero-flow limit) {result['yield_onset_psi']:.2f} psi - informational, not a flow loss.")
    lines.extend(f"WARNING: {w}" for w in result.get("warnings") or [])
    return lines


RESULT_FIELDS = (("regime", ""), ("pressure_loss_psi", "psi"), ("gradient_psi_ft", "psi/ft"),
                 ("velocity_ft_min", "ft/min"), ("re_generalised", ""), ("re1", ""), ("n_prime", ""),
                 ("wall_shear_mean_lbf_100ft2", "lbf/100ft²"), ("zero_shear_radius_in", "in"),
                 ("plug_inner_radius_in", "in"), ("plug_outer_radius_in", "in"), ("plug_velocity_ft_min", "ft/min"),
                 ("yield_onset_psi", "psi"), ("kappa", ""))


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
                        name=f"HB exact annulus {v['hole_id_in']:g} x {v['pipe_od_in']:g} in, "
                             f"{v['flow_rate_gpm']:g} gpm, {result['regime']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=well_id, user_id=user_id, note=f"{LABEL}; inputs SHA-256 {result['inputs_sha256']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    values = {key: (inputs.get(key) or {}).get("value") for key in UNITS}
    if inputs_sha256(freeze(values)) != (inputs.get("inputs_sha256") or {}).get("value"):
        raise IntegrityError("the stored HB exact-annulus inputs fail their SHA-256 check")
    return case_payload(evaluate(values))[1]
