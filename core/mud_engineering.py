"""M133: mud evaluation from the DDR mud reports (W12 Analysis › Mud evaluation).

Every value carries its provenance class:

* ``LAB``     – recorded in the DDR mud report (``mud_reports``), or a Fann reading the user typed WITH a lab
                reference (sheet / sample id); the value is a measurement.
* ``ASSUMED`` – typed by the user and marked as an assumption (no measurement behind it).
* ``DERIVED`` – computed here from LAB values (formula shown); ``DERIVED FROM ASSUMED`` when any input was
                assumed.
* ``UNKNOWN`` – not recorded; never replaced by a default or a zero.

Rheology: Bingham comes from the recorded PV / YP (or from θ600 / θ300 readings when they are entered); the
power-law n / K from θ600 / θ300 (the readings, or the dial values implied by the recorded PV / YP, labelled so).
Both use the canonical ``MudProperties`` engine of the W13 Rheology contract; nothing new is fitted.
Herschel-Bulkley is NOT ASSESSED: this build has no validated HB fit, and a Bingham or power-law result is
never presented as one; 2θ3 − θ6 is shown as the low-shear yield point (LSRYP) only.

An evaluation is saved as an immutable calculation case (History re-runs it from its frozen inputs and says
when the DDR mud report changed or was deleted since saving).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

MUD_METHOD = "m133.mud_evaluation"
MUD_VERSION = "M133 mud evaluation v1"
MUD_CALCULATOR = "Mud evaluation"
MUD_LABEL = "SCREENING — MUD EVALUATION FROM DDR MUD REPORTS — NOT A MUD PROGRAMME OR AN APPROVAL"
HB_STATUS = ("NOT ASSESSED — this build has no validated Herschel-Bulkley fit; a Bingham or power-law result "
             "is not an HB result")
VALUE_TOLERANCE = 1e-9   # re-run comparison of values recomputed from the same frozen inputs (float noise only)

LAB, ASSUMED, DERIVED, DERIVED_ASSUMED, UNKNOWN = "LAB", "ASSUMED", "DERIVED", "DERIVED FROM ASSUMED", "UNKNOWN"
LINKED, UNLINKED = "DDR", "LEGACY — NO DDR LINK"

# (field, label, unit as on the DDR mud form). Gel strengths have no unit on the form: the field convention is
# stated, not assumed silently.
RECORDED_FIELDS: Tuple[Tuple[str, str, str], ...] = (
    ("mw", "Mud weight", "pcf"), ("pv", "Plastic viscosity", "cP"), ("yp", "Yield point", "lbf/100 ft²"),
    ("funnel_vis", "Funnel viscosity", "s/qt"),
    ("gel_10s", "Gel 10 s", "lbf/100 ft² (form shows no unit; field convention)"),
    ("gel_10m", "Gel 10 min", "lbf/100 ft² (form shows no unit; field convention)"),
    ("fl", "Filtrate (API)", "cc/30 min"), ("cake_thickness", "Cake thickness", "mm"), ("ph", "pH", "-"),
    ("temperature", "Temperature", "°C"), ("solid_percent", "Solids", "%"), ("oil_percent", "Oil", "%"),
    ("water_percent", "Water", "%"), ("chloride", "Chloride", "ppm"), ("calcium", "Calcium", "ppm"),
    ("kcl", "KCl", "ppb"), ("mbt", "MBT", "lb/bbl"), ("pf_mf", "Pf/Mf", "mL"),
    ("total_hardness", "Total hardness", "ppm"), ("flowline_temp", "Flowline temperature", "°C"),
)
READINGS: Tuple[Tuple[str, str], ...] = (("t600", "θ600"), ("t300", "θ300"), ("t200", "θ200"), ("t100", "θ100"),
                                         ("t6", "θ6"), ("t3", "θ3"))
COLUMNS = ("Property", "Value", "Unit", "Class", "Source / formula")
LIST_COLUMNS = ("Date", "Sample time", "Report", "Wellbore", "Mud type", "MW (pcf)", "PV (cP)", "YP", "Link")


class MudEvaluationError(ValueError):
    """An evaluation that cannot be made or saved (the message says why)."""


@dataclass(frozen=True)
class MudSample:
    """One DDR mud report row, frozen (a worker DTO: no session or ORM object crosses threads)."""
    id: int
    well_id: int
    report_id: Optional[int]
    wellbore_id: Optional[int]
    report_date: str
    sample_time: str
    mud_type: str
    values: Tuple[Tuple[str, Optional[float]], ...]

    def value(self, key: str) -> Optional[float]:
        return dict(self.values).get(key)

    @property
    def link(self) -> str:
        return LINKED if self.report_id else UNLINKED

    def frozen(self) -> Dict[str, Any]:
        return {"mud_report_id": self.id, "well_id": self.well_id, "report_id": self.report_id,
                "wellbore_id": self.wellbore_id, "report_date": self.report_date, "sample_time": self.sample_time,
                "mud_type": self.mud_type, "values": dict(self.values)}

    def table_row(self) -> Tuple[Any, ...]:
        return (self.report_date, self.sample_time or None, self.report_id, self.wellbore_id, self.mud_type or None,
                self.value("mw"), self.value("pv"), self.value("yp"), self.link)


def values_sha256(values: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _number(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: an unreadable stored value is UNKNOWN, never a default
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _sample(row, wellbore_id) -> MudSample:
    return MudSample(id=row.id, well_id=row.well_id, report_id=row.report_id, wellbore_id=wellbore_id,
                     report_date=row.report_date.isoformat() if row.report_date else "",
                     sample_time=row.sample_time.strftime("%H:%M") if row.sample_time else "",
                     mud_type=row.mud_type or "",
                     values=tuple((key, _number(getattr(row, key))) for key, _label, _unit in RECORDED_FIELDS))


def load_samples(db, well_id: int, wellbore_id: Optional[int] = None) -> List[MudSample]:
    """Mud reports of one well; with an explicit wellbore only those whose DDR belongs to it (unlinked legacy
    rows and other wellbores are left out, never attributed to the selection)."""
    from core.database import DailyReport, MudReport

    with db.session_scope() as session:
        bore_of = dict(session.query(DailyReport.id, DailyReport.wellbore_id)
                       .filter(DailyReport.well_id == well_id).all())
        rows = (session.query(MudReport).filter(MudReport.well_id == well_id)
                .order_by(MudReport.report_date, MudReport.sample_time, MudReport.id).all())
        samples = [_sample(row, bore_of.get(row.report_id)) for row in rows]
    if wellbore_id:
        samples = [s for s in samples if s.report_id and s.wellbore_id == wellbore_id]
    return samples


def load_sample(db, mud_report_id: int) -> Optional[MudSample]:
    from core.database import DailyReport, MudReport

    with db.session_scope() as session:
        row = session.get(MudReport, mud_report_id)
        if row is None:
            return None
        bore = None
        if row.report_id:
            report = session.get(DailyReport, row.report_id)
            bore = report.wellbore_id if report is not None else None
        return _sample(row, bore)


# ---- evaluation ------------------------------------------------------------------------------------------
@dataclass
class Row:
    key: str
    label: str
    value: Optional[float]
    unit: str
    cls: str
    source: str

    def as_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "unit": self.unit, "class": self.cls, "label": self.label, "source": self.source}


@dataclass
class Evaluation:
    sample: Dict[str, Any]
    readings: Dict[str, Dict[str, Any]]
    rows: List[Row] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def row(self, key: str) -> Optional[Row]:
        return next((r for r in self.rows if r.key == key), None)

    def results(self) -> Dict[str, Any]:
        out = {r.key: r.as_dict() for r in self.rows}
        out["hb"] = {"value": None, "unit": "", "class": UNKNOWN, "label": "Herschel-Bulkley", "source": HB_STATUS}
        out["label"] = {"value": MUD_LABEL, "unit": ""}
        return out


def clean_readings(readings: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Typed Fann readings: each needs a class (LAB with a lab reference, or ASSUMED); anything else is
    refused with the reason (an untagged number is never used)."""
    out: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    for key, label in READINGS:
        entry = (readings or {}).get(key)
        if not entry:
            continue
        value = _number(entry.get("value"))
        cls = entry.get("class")
        reference = str(entry.get("reference") or "").strip()
        if value is None:
            problems.append(f"{label}: not a number")
        elif value < 0:
            problems.append(f"{label}: a dial reading cannot be negative")
        elif cls not in (LAB, ASSUMED):
            problems.append(f"{label}: mark it LAB (measured) or ASSUMED")
        elif cls == LAB and not reference:
            problems.append(f"{label}: a LAB reading needs its lab reference (sheet or sample id)")
        else:
            out[key] = {"value": value, "class": cls, "reference": reference}
    return out, problems


def _derived_class(classes: Iterable[str]) -> str:
    return DERIVED_ASSUMED if ASSUMED in set(classes) else DERIVED


def evaluate(sample: Dict[str, Any], readings: Optional[Dict[str, Any]] = None) -> Evaluation:
    """Classify the recorded values and derive what follows from them (``sample`` = ``MudSample.frozen()``)."""
    from core.hydraulics_engine import MudProperties

    clean, problems = clean_readings(readings)
    if problems:
        raise MudEvaluationError("; ".join(problems))
    values = sample.get("values") or {}
    source = (f"DDR mud report #{sample.get('mud_report_id')} ({sample.get('report_date')}"
              + (f" {sample['sample_time']}" if sample.get("sample_time") else "")
              + (f", DDR #{sample['report_id']})" if sample.get("report_id") else ", no DDR link)"))
    ev = Evaluation(sample=sample, readings=clean)
    for key, label, unit in RECORDED_FIELDS:
        value = values.get(key)
        ev.rows.append(Row(key, label, value, unit, LAB if value is not None else UNKNOWN,
                           source if value is not None else "not recorded in the mud report"))
    for key, label in READINGS:
        entry = clean.get(key)
        if entry:
            ev.rows.append(Row(key, f"Fann {label}", entry["value"], "dial", entry["class"],
                               f"typed; lab reference {entry['reference']}" if entry["class"] == LAB
                               else "typed as an assumption (no measurement)"))
        else:
            ev.rows.append(Row(key, f"Fann {label}", None, "dial", UNKNOWN,
                               "not recorded (the DDR mud report has no dial readings)"))

    mw, pv, yp = values.get("mw"), values.get("pv"), values.get("yp")
    if mw is not None and mw > 0:
        ev.rows.append(Row("mw_ppg", "Mud weight", MudProperties(mw_pcf=mw).mw_ppg, "ppg", DERIVED,
                           "MW pcf / 7.48052 (MudProperties.mw_ppg)"))
    else:
        ev.rows.append(Row("mw_ppg", "Mud weight", None, "ppg", UNKNOWN, "no recorded mud weight"))

    # Bingham / power law: from θ600/θ300 readings when both were typed, else from the recorded PV/YP.
    if "t600" in clean and "t300" in clean:
        t600, t300 = clean["t600"]["value"], clean["t300"]["value"]
        basis = _derived_class((clean["t600"]["class"], clean["t300"]["class"]))
        origin = "the typed θ600 / θ300"
    elif pv is not None and yp is not None:
        t600, t300 = 2.0 * pv + yp, pv + yp
        basis = DERIVED
        origin = "the dial values implied by the recorded PV / YP (θ600 = 2PV + YP, θ300 = PV + YP)"
        ev.rows.append(Row("t600_implied", "θ600 implied by PV / YP", t600, "dial", DERIVED, "2 PV + YP"))
        ev.rows.append(Row("t300_implied", "θ300 implied by PV / YP", t300, "dial", DERIVED, "PV + YP"))
    else:
        t600 = t300 = None
        basis, origin = UNKNOWN, ""
    rheology = None
    if t600 is not None:
        try:
            rheology = MudProperties.calculate_fann_rheology(theta600=t600, theta300=t300)
        except ValueError as exc:
            ev.notes.append(f"Rheology NOT ASSESSED from {origin}: {exc}")
    if rheology is not None:
        if "t600" in clean and "t300" in clean:
            ev.rows.append(Row("pv_readings", "PV from readings", rheology["pv_cp"], "cP", basis, "θ600 − θ300"))
            ev.rows.append(Row("yp_readings", "YP from readings", rheology["yp_lbf100ft2"], "lbf/100 ft²", basis,
                               "θ300 − PV"))
            for key, recorded, fresh in (("pv", pv, rheology["pv_cp"]), ("yp", yp, rheology["yp_lbf100ft2"])):
                if recorded is not None and abs(recorded - fresh) > VALUE_TOLERANCE:
                    ev.notes.append(f"{key.upper()} from the readings ({fresh:g}) differs from the recorded "
                                    f"{key.upper()} ({recorded:g}); both are shown, neither is replaced.")
        ev.rows.append(Row("n", "Power-law n", rheology["power_law_n"], "-", basis,
                           f"3.32 log10(θ600/θ300) from {origin}"))
        ev.rows.append(Row("k", "Power-law K", rheology["power_law_k_cp_s_nminus1"], "cP·s^(n−1)", basis,
                           f"510 θ300 / 511^n from {origin}"))
    else:
        for key, label, unit in (("n", "Power-law n", "-"), ("k", "Power-law K", "cP·s^(n−1)")):
            ev.rows.append(Row(key, label, None, unit, UNKNOWN, "needs θ600 / θ300 or recorded PV and YP"))

    if "t3" in clean and "t6" in clean:
        cls = _derived_class((clean["t3"]["class"], clean["t6"]["class"]))
        ev.rows.append(Row("lsryp", "Low-shear yield point (LSRYP)",
                           2.0 * clean["t3"]["value"] - clean["t6"]["value"], "lbf/100 ft²", cls,
                           "2θ3 − θ6; a low-shear indicator, NOT a Herschel-Bulkley yield stress"))
    else:
        ev.rows.append(Row("lsryp", "Low-shear yield point (LSRYP)", None, "lbf/100 ft²", UNKNOWN,
                           "needs θ3 and θ6"))

    if pv is not None and yp is not None and yp > 0:
        ev.rows.append(Row("pv_yp", "PV / YP", pv / yp, "-", DERIVED, "recorded PV / recorded YP"))
    g10s, g10m = values.get("gel_10s"), values.get("gel_10m")
    if g10s is not None and g10m is not None and g10s > 0:
        ev.rows.append(Row("gel_ratio", "Gel 10 min / 10 s", g10m / g10s, "-", DERIVED, "recorded gels"))
    solids, oil, water = values.get("solid_percent"), values.get("oil_percent"), values.get("water_percent")
    if None not in (solids, oil, water):
        total = solids + oil + water
        ev.rows.append(Row("retort_total", "Retort total", total, "%", DERIVED, "solids + oil + water"))
        if abs(total - 100.0) > VALUE_TOLERANCE:
            ev.notes.append(f"The retort fractions total {total:g} %, not 100 %: check the mud report entries.")
    else:
        ev.rows.append(Row("retort_total", "Retort total", None, "%", UNKNOWN, "a retort fraction is not recorded"))
    if oil is not None and water is not None and oil > 0:
        ev.rows.append(Row("owr_oil", "Oil / water ratio (oil part)", 100.0 * oil / (oil + water), "%", DERIVED,
                           "100 oil / (oil + water)"))
    ev.notes.append("Herschel-Bulkley: " + HB_STATUS + ".")
    return ev


# ---- persistence (immutable case) and re-run ---------------------------------------------------------------
def frozen_inputs(sample: MudSample, readings: Dict[str, Dict[str, Any]], *, well_id: int,
                  wellbore_id: Optional[int]) -> Dict[str, Any]:
    if sample.well_id != well_id:
        raise MudEvaluationError(f"Mud report #{sample.id} belongs to well #{sample.well_id}, not to the selected "
                                 f"well #{well_id}.")
    if wellbore_id and sample.wellbore_id != wellbore_id:
        raise MudEvaluationError(f"Mud report #{sample.id} is not in a DDR of the selected wellbore "
                                 f"#{wellbore_id}; it is not attributed to it.")
    frozen = sample.frozen()
    return {"sample": frozen, "values_sha256": values_sha256(frozen["values"]), "readings": readings,
            "well_id": well_id, "wellbore_id": wellbore_id}


def save_evaluation(db, sample: MudSample, readings: Optional[Dict[str, Any]] = None, *, well_id: int,
                    wellbore_id: Optional[int] = None, name: str = "",
                    user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store an evaluation as a new immutable case; the wellbore only when the caller scoped one explicitly."""
    from core import calculation_cases as cc

    clean, problems = clean_readings(readings)
    if problems:
        raise MudEvaluationError("; ".join(problems))
    inputs = frozen_inputs(sample, clean, well_id=well_id, wellbore_id=wellbore_id)
    ev = evaluate(inputs["sample"], clean)
    return cc.save_case(db, calculator=MUD_CALCULATOR,
                        name=name or f"Mud report #{sample.id} ({sample.report_date})", inputs=inputs,
                        results=ev.results(), method=MUD_METHOD, method_version=MUD_VERSION, well_id=well_id,
                        wellbore_id=wellbore_id, user_id=user_id, note=MUD_LABEL)


def source_status(db, inputs: Dict[str, Any]) -> str:
    sample = (inputs or {}).get("sample") or {}
    if db is None or not sample.get("mud_report_id"):
        return "mud report not re-read here"
    current = load_sample(db, sample["mud_report_id"])
    if current is None:
        return f"DDR SOURCE CHANGED: mud report #{sample['mud_report_id']} no longer exists"
    now = current.frozen()["values"]
    if values_sha256(now) == inputs.get("values_sha256"):
        return "mud report unchanged since saving"
    old = sample.get("values") or {}
    changed = [f"{key} {old.get(key)} → {now.get(key)}" for key in sorted(now) if old.get(key) != now.get(key)]
    return "DDR SOURCE CHANGED: " + (", ".join(changed) or "the stored values differ")


def verify_case(db, inputs: Dict[str, Any], results: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Repeat the evaluation from the frozen inputs; report a mud-report change (never silently re-based)."""
    blank = {"method_matches": None, "current_method": f"{MUD_METHOD} {MUD_VERSION}", "values": {},
             "differences": [], "not_compared": []}
    if version != MUD_VERSION:
        return {**blank, "status": "NOT_REPRODUCIBLE", "detail": f"method version {version!r} is not available"}
    if not isinstance(inputs, dict) or not isinstance(inputs.get("sample"), dict) or not isinstance(results, dict):
        return {**blank, "status": "UNREADABLE", "detail": "the stored case is not a mud evaluation payload"}
    try:
        ev = evaluate(inputs["sample"], inputs.get("readings"))
    except MudEvaluationError as exc:
        return {**blank, "status": "UNREADABLE", "detail": str(exc)}
    fresh = {r.key: r.value for r in ev.rows}
    differences, not_compared = [], []
    for key, value in fresh.items():
        stored = (results.get(key) or {}).get("value") if key in results else "missing"
        if value is None and stored is None:
            continue
        if not isinstance(value, (int, float)) or not isinstance(stored, (int, float)) \
                or abs(stored - value) > VALUE_TOLERANCE:
            differences.append({"field_id": key, "stored": stored, "current": value})
    for key in results:
        if key not in fresh and key not in ("hb", "label"):
            not_compared.append(key)
    source = source_status(db, inputs)
    detail = (f"{len(differences)} field(s) differ" if differences
              else "evaluation repeated from the frozen mud report values")
    return {"status": "DIFFERENT" if differences else "MATCH", "method_matches": True,
            "current_method": f"{MUD_METHOD} {MUD_VERSION}", "detail": f"{detail}; {source}. {MUD_LABEL}.",
            "values": {k: v for k, v in fresh.items() if v is not None}, "differences": differences,
            "not_compared": not_compared, "ddr_source": source}


def save_rerun(db, source_case_id: int, inputs: Dict[str, Any], outcome: Dict[str, Any], *,
               well_id: Optional[int], wellbore_id: Optional[int], name: str,
               user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a verified re-run as a NEW case linked ``rerun_of`` the original (same frozen inputs)."""
    from core import calculation_cases as cc

    if outcome.get("status") not in ("MATCH", "DIFFERENT"):
        raise MudEvaluationError(f"Nothing to store: re-run status {outcome.get('status')}.")
    ev = evaluate(inputs["sample"], inputs.get("readings"))
    return cc.save_case(
        db, calculator=MUD_CALCULATOR, name=f"{name} (re-run)", inputs=inputs, results=ev.results(),
        method=MUD_METHOD, method_version=MUD_VERSION, well_id=well_id, wellbore_id=wellbore_id, user_id=user_id,
        note=f"{MUD_LABEL}; re-run of case #{source_case_id}: {outcome['status']}; {outcome.get('ddr_source', '')}",
        source_link={"link_type": "rerun_of", "source_table": "calculation_cases", "source_id": source_case_id,
                     "source_method": MUD_METHOD, "source_method_version": MUD_VERSION,
                     "recalc_method": MUD_METHOD, "recalc_method_version": MUD_VERSION,
                     "verification_status": outcome["status"], "method_changed": False})
