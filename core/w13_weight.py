"""M127: the W13 Weight page - weight card and soft-string torque & drag on a pinned survey revision.

Both calculations run through ``TorqueDragEngine``:

* the weight card - air weight of the entered components, buoyancy factor, hook load and a
  straight-hole pickup / slack-off for ONE inclination and friction factor (``calculate_weight_card``);
* the Johancsik soft-string T&D (``calculate``) along the stations of a survey revision.

T&D needs a survey revision of the selected well chosen explicitly on the page.  The revision must
pass ``survey_revisions.verify_for_use`` (station hash, results hash, full results re-computation)
and its stations are pinned - copied together with the revision identity and the station SHA-256.
A re-run checks the pinned stations against that hash before using them, so T&D never reads the
Multi-Survey table of another page, a later revision or edited stations.  Without a pin the T&D
results are UNKNOWN (``None``), never zero.

Not a stiff-string, contact or dynamic model; buoyancy BF = 1 - MW/65.5 (no pressure-area term);
the weight card converts pcf to ppg with 7.48 (the 7.48 / 7.48052 choice is an open owner decision).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

METHOD_VERSION = "M127 weight card and soft-string T&D v1"
PIN_VERSION = "M127 survey pin v1"
PIN_KEYS = ("revision_id", "revision", "well_id", "wellbore_id", "depth_datum", "azimuth_reference",
            "source_unit", "stations_sha256", "survey_method_version")
COMPONENT_KEYS = ("type", "od", "id", "length", "weight", "grade", "connection")
TD_RESULTS = ("td_pickup_klbf", "td_slackoff_klbf", "td_rotating_klbf", "td_sliding_klbf",
              "td_surface_torque_ft_lbf", "td_buoyed_weight_klbf", "td_neutral_point_md_m", "td_buckling_flag")


class SurveyPinError(ValueError):
    """A survey revision or a stored pin cannot be used for torque and drag."""


def pin_from_revision(revision: Optional[Mapping[str, Any]], *, well_id: Any,
                      wellbore_id: Any = None) -> Dict[str, Any]:
    """The pin of a verified survey revision of ``well_id`` (raises ``SurveyPinError``)."""
    from core import survey_revisions as sr

    try:
        sr.verify_for_use(dict(revision) if revision else None, "torque and drag")
    except sr.SurveyRevisionError as exc:
        raise SurveyPinError(str(exc)) from exc
    if well_id is None or revision.get("well_id") != well_id:
        raise SurveyPinError(f"Survey revision {revision.get('revision')} belongs to another well.")
    owner = revision.get("wellbore_id")
    if owner is not None and wellbore_id is not None and owner != wellbore_id:
        raise SurveyPinError(f"Survey revision {revision.get('revision')} belongs to wellbore #{owner}, "
                             f"not the selected wellbore #{wellbore_id}.")
    pin = {
        "pin_version": PIN_VERSION, "revision_id": revision.get("id"), "revision": revision.get("revision"),
        "well_id": revision.get("well_id"), "wellbore_id": owner,
        "depth_datum": revision.get("depth_datum"), "azimuth_reference": revision.get("azimuth_reference"),
        "source_unit": revision.get("source_unit"), "stations_sha256": revision.get("stations_sha256"),
        "survey_method_version": revision.get("method_version"),
        "stations": [{"md": s["md"], "inc": s["inc"], "azi": s["azi"]} for s in revision.get("stations") or []],
    }
    pin_stations(pin)            # the copy must hash to the revision's own station hash
    return pin


def _finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: a non-numeric station value is None and the pin is refused
        return None
    return number if math.isfinite(number) else None


def pin_stations(pin: Optional[Mapping[str, Any]]) -> List[Dict[str, float]]:
    """The pinned stations (MD m, angles deg) after the SHA-256 check; raises ``SurveyPinError``."""
    from core import survey_revisions as sr

    if not isinstance(pin, Mapping):
        raise SurveyPinError("No survey revision is pinned.")
    stations = []
    for index, row in enumerate(pin.get("stations") or []):
        values = [_finite((row or {}).get(key)) if isinstance(row, Mapping) else None for key in ("md", "inc", "azi")]
        if None in values:
            raise SurveyPinError(f"Pinned station {index + 1} is not a set of finite numbers.")
        stations.append(dict(zip(("md", "inc", "azi"), values)))
    if len(stations) < 2:
        raise SurveyPinError("The pinned survey has fewer than two stations.")
    if sr.stations_sha256(stations) != pin.get("stations_sha256"):
        raise SurveyPinError(f"The pinned stations of survey revision {pin.get('revision')} do not match its "
                             f"station SHA-256; they cannot be used.")
    return stations


def pin_label(pin: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(pin, Mapping):
        return "No survey revision pinned - torque and drag NOT ASSESSED"
    scope = f"wellbore #{pin['wellbore_id']}" if pin.get("wellbore_id") is not None else "well-level (no wellbore)"
    return (f"Survey rev {pin.get('revision')} (#{pin.get('revision_id')}), {scope}, datum "
            f"{pin.get('depth_datum') or 'unknown'}, azimuth {pin.get('azimuth_reference') or 'unknown'}, "
            f"{len(pin.get('stations') or [])} stations, SHA-256 {str(pin.get('stations_sha256') or '')[:12]}…")


def engine_components(pipes: Any) -> List[Dict[str, Any]]:
    """The entered components as the engine reads them (catalogue fingerprints kept for traceability)."""
    out = []
    for pipe in pipes or []:
        if not isinstance(pipe, Mapping):
            raise ValueError("a drill-string component is not a mapping")
        comp = {"name": pipe.get("type") or "pipe"}
        comp.update({key: pipe.get(key) for key in COMPONENT_KEYS})
        if pipe.get("reference_fingerprint"):
            comp["reference_fingerprint"] = pipe["reference_fingerprint"]
        out.append(comp)
    return out


def weight_card(values: Mapping[str, Any]):
    from core.engineering.engines.torque_drag import TorqueDragEngine

    return TorqueDragEngine.calculate_weight_card(
        components=[dict(p) for p in values.get("pipes") or []], mud_density_pcf=values.get("mw"),
        inclination_deg=values.get("inclination"), top_drive_weight_klbf=values.get("tds"),
        friction_factor=values.get("friction"))


def torque_drag(values: Mapping[str, Any], mud_density_ppg: float):
    """The engine result on the pinned stations, or ``None`` when no survey is pinned."""
    from core.engineering.engines.torque_drag import TorqueDragEngine

    if values.get("survey") is None:
        return None
    stations = pin_stations(values.get("survey"))
    hole = values.get("hole_id")
    return TorqueDragEngine.calculate(
        stations, engine_components(values.get("pipes")), mud_density_ppg=mud_density_ppg,
        friction_factor=values.get("friction"), wob_klbf=values.get("wob"),
        wellbore_id_in=hole if hole else None)


def results(values: Mapping[str, Any]) -> Dict[str, Optional[float]]:
    """Weight-card results and, with a pinned survey, the T&D summary (raises ``ValueError``)."""
    if not values.get("pipes"):
        raise ValueError("NOT ASSESSED: no drill-string component entered")
    card = weight_card(values)
    if not card.success:
        raise ValueError(card.error or "weight card failed")
    v = card.values
    out: Dict[str, Optional[float]] = {
        "air_weight_klbf": v["total_air_weight_lbs"] / 1000.0,
        "axial_air_weight_klbf": v["axial_air_weight_klbf"],
        "buoyancy_factor": v["buoyancy_factor"], "buoyed_weight_klbf": v["buoyed_weight_klbf"],
        "hook_load_klbf": v["hook_load_lbs"] / 1000.0, "pickup_klbf": v["pickup_lbs"] / 1000.0,
        "slackoff_klbf": v["slackoff_lbs"] / 1000.0,
    }
    out.update({key: None for key in TD_RESULTS})
    td = torque_drag(values, v["mud_density_ppg"])
    if td is not None:
        if not td.success:
            raise ValueError(f"torque and drag: {td.error}")
        t = td.values
        out.update({
            "td_pickup_klbf": t["hookload_pickup"], "td_slackoff_klbf": t["hookload_slackoff"],
            "td_rotating_klbf": t["hookload_rotating"], "td_sliding_klbf": t["hookload_sliding"],
            "td_surface_torque_ft_lbf": t["surface_torque_rotating_ft_lbf"],
            "td_buoyed_weight_klbf": t["total_buoyed_weight"],
            "td_neutral_point_md_m": t.get("neutral_point_md_m"),
            "td_buckling_flag": 1.0 if (t.get("buckling") or {}).get("any") else 0.0,
        })
    return out
