"""Method catalogue (M92): one read-only view over every calculation method in the product.

Sources (nothing is retyped; versions and method strings are read from the code that runs):

* engine classes in ``core/engineering/engines`` (their ``METHOD`` attribute) and the hydraulics module;
* the W13 calculator contracts (``core.calculator_contracts``), including legacy versions still runnable,
  and every W13 calculator WITHOUT a contract (``NOT_SUPPORTED``);
* the specialist method registry (``core.specialist_methods``, M79 criteria);
* directional, survey, architecture and analysis methods (their module version constants).

Each entry shows ID, family, status, product label, version, reference, licence, limits, approval and
blocker. **Approval is never granted from the application**: it can only come from ``OWNER_APPROVALS``,
an immutable mapping in the source that is empty in this build, so every method reads
"NOT APPROVED — OWNER REVIEW REQUIRED". The catalogue has no approve action (no self-approval).

``usage(db, well_id)`` counts stored W13 calculation cases per (method, version) so the catalogue shows
which methods produced data in the open database.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, List, Optional, Tuple

CATALOGUE_VERSION = "M92 method catalogue v1"
STATUSES = ("IMPLEMENTED", "NOT SUPPORTED", "NOT IMPLEMENTED", "OWNER REVIEW REQUIRED")
LABELS = ("SCREENING", "WORKSHEET", "TRAINING AID", "PLANNING AID", "REFERENCE-ONLY")
NOT_APPROVED = "NOT APPROVED — OWNER REVIEW REQUIRED"
OWN_CODE = "own code (product licence)"
# method_id -> owner approval record. Changed only by the owner in the source, never by the application.
OWNER_APPROVALS = MappingProxyType({})
COLUMNS = ("Method ID", "Title", "Family", "Source", "Status", "Label", "Version", "Reference", "Licence",
           "Limits", "Approval", "Blocker", "Module")


@dataclass(frozen=True)
class CatalogueEntry:
    method_id: str
    title: str
    family: str
    source: str              # which registry the entry comes from
    status: str
    label: str               # product label (SCREENING / WORKSHEET / ...) or ""
    version: str
    reference: str
    licence: str
    limits: str
    blocker: str = ""
    module: str = ""

    @property
    def approval(self) -> str:
        record = OWNER_APPROVALS.get(self.method_id)
        return f"APPROVED — {record}" if record else NOT_APPROVED

    @property
    def blockers(self) -> str:
        parts = [self.blocker] if self.blocker else []
        if self.approval == NOT_APPROVED:
            parts.append("owner engineering approval")
        return "; ".join(parts)

    def row(self) -> List[str]:
        return [self.method_id, self.title, self.family, self.source, self.status, self.label or "—",
                self.version or "—", self.reference or "—", self.licence or "—", self.limits or "—",
                self.approval, self.blockers or "—", self.module or "—"]


def _label(*texts: str) -> str:
    upper = " ".join(texts).upper()
    return next((label for label in LABELS if label in upper), "")


def _engines() -> List[CatalogueEntry]:
    from core.engineering.engines.anti_collision import AntiCollisionEngine
    from core.engineering.engines.bit_performance import BitPerformanceEngine
    from core.engineering.engines.casing import CasingEngine
    from core.engineering.engines.cement import CementEngine
    from core.engineering.engines.fishing import FishingEngine
    from core.engineering.engines.mse import MSEEngine
    from core.engineering.engines.mud_volume import MudVolumeEngine
    from core.engineering.engines.torque_drag import TorqueDragEngine
    from core.engineering.engines.well_control import WellControlEngine

    base = "core/engineering/engines/"
    specs = (
        ("engine.casing", "Casing pipe-body strength", "Casing", CasingEngine, "casing.py", "",
         "API TR 5C3 pipe-body equations (subset)",
         "Pipe body only; no connection ratings, no triaxial design factors, no ductile rupture", ""),
        ("engine.cement", "Cement volumes and column hydrostatic", "Cement", CementEngine, "cement.py", "WORKSHEET",
         "Oilfield capacity constant 1029.4 (in² → bbl/ft); stacked-column hydrostatic",
         "Nominal geometry unless a caliper is declared; no slurry data is invented", ""),
        ("engine.mse", "Mechanical specific energy", "Bit / MSE", MSEEngine, "mse.py", "",
         "Teale, R. (1965), Int. J. Rock Mech. Min. Sci. 2, 57–73",
         "Surface torque/WOB as entered; no efficiency factor", ""),
        ("engine.torque_drag", "Soft-string torque and drag", "Torque & drag", TorqueDragEngine, "torque_drag.py",
         "SCREENING", "Johancsik, Friesen and Dawson (1984), SPE 11380",
         "Soft-string; no stiffness, no contact-force model", "stiff-string model blocked (see tnd.stiff_string)"),
        ("engine.well_control", "Kill sheet and well-control arithmetic", "Well control", WellControlEngine,
         "well_control.py", "TRAINING AID", "IWCF / IADC well-control manuals; Bourgoyne et al. (1986)",
         "Training and check aid; not a kill-sheet approval", "owner decision on kill-sheet status"),
        ("engine.fishing", "Free point, stretch and back-off", "Fishing", FishingEngine, "fishing.py", "SCREENING",
         "Hooke's law stretch over pipe area (legacy chart approximations)",
         "Single pipe size, no friction, no tapered strings", "no field benchmark"),
        ("engine.mud_volume", "Mud weight-up, dilution and mixing", "Mud", MudVolumeEngine, "mud_volume.py", "",
         "Mass and volume balance", "Ideal mixing; no hidden defaults", ""),
        ("engine.bit_performance", "Bit run roll-up from daily reports", "Bit / MSE", BitPerformanceEngine,
         "bit_performance.py", "", "Arithmetic roll-up of recorded bit data", "Uses recorded values only", ""),
        ("engine.anti_collision", "Centre-to-centre separation", "Directional", AntiCollisionEngine,
         "anti_collision.py", "SCREENING", "Linear-interpolated 3-D centreline distance",
         "SCREENING — NO ISCWSA UNCERTAINTY — NOT APPROVED; no separation factor",
         "ISCWSA error model (see wellpath.iscwsa_error_model)"),
    )
    out = []
    for method_id, title, family, cls, module, label, reference, limits, blocker in specs:
        method = str(getattr(cls, "METHOD", "") or "")
        out.append(CatalogueEntry(method_id, title, family, "engine", "IMPLEMENTED", label or _label(method), method,
                                  reference, OWN_CODE, limits, blocker, base + module))
    out.append(CatalogueEntry(
        "engine.hydraulics", "Pipe/annulus pressure losses and bit hydraulics", "Hydraulics", "engine", "IMPLEMENTED",
        "", "core/hydraulics_engine.py (Bingham / power-law; bit ΔP = gpm²·MW/(10858·TFA²))",
        "Not recorded in the source; bit hydraulics checked against Bernoulli with Cd 0.95 (M90 goldens)",
        OWN_CODE, "Surge/swab is SCREENING; concentric annulus only", "published reference not recorded",
        "core/hydraulics_engine.py"))
    return out


def _contracts() -> List[CatalogueEntry]:
    from core import calculator_contracts as cc

    out = []
    for contract in list(cc.CONTRACTS.values()) + list(cc.LEGACY_CONTRACTS):
        legacy = contract in cc.LEGACY_CONTRACTS
        out.append(CatalogueEntry(
            contract.method_id + (" (legacy)" if legacy else ""), contract.calculator, "W13 calculator",
            "calculator contract" + (" (legacy version, still runnable)" if legacy else ""), "IMPLEMENTED",
            _label(contract.limits, contract.method_version), contract.method_version, contract.reference,
            OWN_CODE, contract.limits or "see the contract fields and units", "",
            "core/calculator_contracts.py"))
    for calculator, reason in cc.NOT_SUPPORTED.items():
        leaf, _meaning = cc.leaf_class(calculator)      # M125: TRAINING AID / REFERENCE-ONLY / NOT_SUPPORTED
        out.append(CatalogueEntry(
            "w13.unsupported." + calculator.lower().replace(" › ", ".").replace(" ", "_"), calculator,
            "W13 calculator", "calculator without contract", "NOT SUPPORTED", _label(leaf, reason), "", "", OWN_CODE,
            "Cases are stored as captured and are NOT REPRODUCIBLE", reason, "tabs/w13_Engineering_Calculator.py"))
    return out


def _specialist() -> List[CatalogueEntry]:
    from core import specialist_methods as sm

    return [CatalogueEntry(m.method_id, m.title, "Specialist", "specialist registry (M79)", m.status,
                           _label(m.limits), sm.REGISTRY_VERSION, m.reference, m.licence, m.limits,
                           m.blocked_by + (f" (unmet: {', '.join(m.unmet)})" if m.unmet else ""), m.module or "")
            for m in sm.METHODS]


def _workflow_methods() -> List[CatalogueEntry]:
    from core import cost_semantics, operational_analysis, operational_time, survey_revisions, trajectory_compare
    from core import well_architecture
    from core import well_plan_designer as wpd

    return [
        CatalogueEntry("directional.minimum_curvature", "Plan trajectory (minimum curvature)", "Directional",
                       "plan designer", "IMPLEMENTED", "PLANNING AID", f"{wpd.PLAN_VERSION}; {wpd.METHOD}",
                       "Minimum curvature (canonical TrajectoryCalculator); independent goldens in tests",
                       OWN_CODE, "Constant-curvature arcs; no uncertainty", "", "core/well_plan_designer.py"),
        CatalogueEntry("directional.target_solver", "Curve-hold target solver", "Directional", "plan designer",
                       "IMPLEMENTED", "PLANNING AID", wpd.SOLVER_VERSION,
                       "Closed-form tangent construction (M86 tests)", OWN_CODE,
                       "Build/drop/hold/turn with DLS and inclination limits; structured infeasibility", "",
                       "core/well_plan_designer.py"),
        CatalogueEntry("directional.multi_segment_solver", "Multi-target and S-profile solver", "Directional",
                       "plan designer", "IMPLEMENTED", "PLANNING AID", wpd.MULTI_SOLVER_VERSION,
                       "Chained closed-form curve-hold legs; closed-form S-profile; verified by the canonical "
                       f"engine to {wpd.TARGET_TOLERANCE_M} m (M106 tests, forward-constructed goldens)", OWN_CODE,
                       "Passes through target centres; nothing is minimised (no optimality claim); S-profile needs "
                       "a vertical tie-in; DLS and inclination limits are hard (never clipped); no uncertainty",
                       "", "core/well_plan_designer.py"),
        CatalogueEntry("directional.plan_vs_actual", "Plan vs actual and closest approach", "Directional",
                       "trajectory compare", "IMPLEMENTED", "SCREENING", trajectory_compare.METHOD_VERSION,
                       "Centre-to-centre distance between trajectories", OWN_CODE,
                       "SCREENING — NO ISCWSA UNCERTAINTY — NO SEPARATION FACTOR — NOT APPROVED; well-to-well needs "
                       "pinned survey revisions on grid north with an RKB/RT/MSL datum, else NOT ASSESSED (M129); "
                       "M52 records re-run under their own version",
                       "ISCWSA error model (see wellpath.iscwsa_error_model)", "core/trajectory_compare.py"),
        CatalogueEntry("survey.revision", "Immutable survey revisions", "Survey", "survey revisions", "IMPLEMENTED",
                       "", survey_revisions.SURVEY_REVISION_VERSION, "Station hash verified on read", OWN_CODE,
                       "Depth datum shifted only by explicit elevations; CRS recorded, not transformed", "", "core/survey_revisions.py"),
        CatalogueEntry("survey.azimuth_transform", "Azimuth reference transform", "Survey", "survey revisions",
                       "IMPLEMENTED", "", survey_revisions.TRANSFORM_VERSION,
                       "Declination / grid convergence with stated source and sign", OWN_CODE,
                       "Explicit values only; no online declination; unknown reference is never true north",
                       "CRS / map-projection transforms NOT IMPLEMENTED", "core/survey_revisions.py"),
        CatalogueEntry("survey.datum_transform", "Vertical depth-datum shift", "Survey", "survey revisions",
                       "IMPLEMENTED", "", survey_revisions.DATUM_TRANSFORM_VERSION,
                       "Both datum elevations against one stated reference, with source", OWN_CODE,
                       "Vertical first station only; never drops stations; new revision, source untouched",
                       "geodetic datum / CRS transforms NOT IMPLEMENTED (see SURVEY_REFERENCE_SCOPE.md)",
                       "core/survey_revisions.py"),
        CatalogueEntry("architecture.casing_inputs", "Casing inputs from the architecture revision", "Casing",
                       "well architecture", "IMPLEMENTED", "", well_architecture.CASING_SOURCE_VERSION,
                       "Provenance per value (architecture / derived / user / unknown)", OWN_CODE,
                       "Yield never inferred from the grade", "", "core/well_architecture.py"),
        CatalogueEntry("architecture.cement_annulus", "Cement annulus worksheet", "Cement", "well architecture",
                       "IMPLEMENTED", "WORKSHEET", well_architecture.CEMENT_WORKSHEET_VERSION,
                       "Segment annulus volumes with declared caliper and explicit excess", OWN_CODE,
                       "Excess on open hole only and only when declared; re-run from the frozen revision after its "
                       "SHA-256 check (M109); WORKSHEET — NOT A CEMENT DESIGN APPROVAL", "",
                       "core/well_architecture.py"),
        CatalogueEntry("analysis.time_log_summary", "Time-log hours and NPT reduction", "Operations",
                       "operational time", "IMPLEMENTED", "", operational_time.TIME_SUMMARY_VERSION,
                       "Arithmetic over recorded durations and NPT flags", OWN_CODE,
                       "Unknown durations are never zero; a NULL NPT flag never proves productive time", "",
                       "core/operational_time.py"),
        CatalogueEntry("analysis.cost_per_currency", "Cost totals per currency", "Operations", "cost semantics",
                       "IMPLEMENTED", "", cost_semantics.COST_SEMANTICS_VERSION,
                       "Arithmetic over recorded planned/actual cost", OWN_CODE,
                       "No currency conversion; unknown currency is never assumed (money migration owner-gated)",
                       "", "core/cost_semantics.py"),
        CatalogueEntry("analysis.operational", "Operational analysis", "Operations", "operational analysis",
                       "IMPLEMENTED", "", operational_analysis.OA_VERSION,
                       "Arithmetic over stored reports (footage, time-weighted ROP, NPT, bit runs, cost)", OWN_CODE,
                       "Missing ≠ 0; no currency conversion; MSE per well only", "",
                       "core/operational_analysis.py"),
    ]


def _case_services() -> List[CatalogueEntry]:
    """M392: workflow services that store replayable calculation cases (``core.history_replay`` adapters)."""
    from core import casing_axial_loads, cement_job_reconciliation, ddr_hydraulics_check, hydraulics_workflow
    from core import mse_drilloff, survey_plan_deviation, torque_drag_sensitivity, well_control_volumetric
    from core import bit_dull_grade, drilloff_fitted, drilloff_robust, hydraulics_hb_slot, surge_swab
    from core import hydraulics_hb_annulus_exact

    def entry(module, title, family, reference, limits, blocker=""):
        label = _label(getattr(module, "LABEL", ""))
        return CatalogueEntry(module.METHOD_ID, title, family, "calculation case service", "IMPLEMENTED", label,
                              module.METHOD_VERSION, reference, OWN_CODE, limits, blocker,
                              f"core/{module.__name__.rsplit('.', 1)[-1]}.py")

    return [
        entry(ddr_hydraulics_check, "DDR recorded vs recomputed bit hydraulics", "Hydraulics",
              "AdvancedHydraulicsEngine.calc_bit_hydraulics at the recorded flow range",
              "Missing recorded values -> NOT_COMPUTED; no inferred nozzles"),
        entry(cement_job_reconciliation, "Cement job vs architecture reconciliation", "Cement",
              "Gauge annulus from the frozen architecture; CementEngine.displacement",
              "Declared yield units only; WORKSHEET - not a cement design approval"),
        entry(torque_drag_sensitivity, "T&D friction-factor sensitivity", "Torque and drag",
              "TorqueDragEngine per declared friction factor", "Observation bracketed, never interpolated; "
              "not a calibrated friction factor"),
        entry(hydraulics_workflow, "Hydraulics pressure budget, sensitivities, plan vs actual, CCI", "Hydraulics",
              "W13 circulating-system engine; CCI = K x AV x MW / 400000",
              "Refused until inputs are confirmed; ECD only with complete annular geometry; CCI <= 35 deg"),
        entry(survey_plan_deviation, "Survey vs plan centreline deviation and targets", "Directional",
              "Minimum-curvature interpolation on the plan; right / high / distance",
              "Centreline only; refuses a datum or azimuth-reference mismatch; no uncertainty",
              "ISCWSA error model (see wellpath.iscwsa_error_model)"),
        entry(casing_axial_loads, "Casing axial-load components and worn-wall ratings", "Casing",
              "Lubinski / Bourgoyne closed forms; CasingEngine burst and collapse on the worn wall",
              "Pipe body only; E, alpha, nu declared; no triaxial envelope, connection rating or casing buckling"),
        entry(mse_drilloff, "Drill-off test founder point and step MSE", "Drilling performance",
              "Dupriest & Koederitz (SPE 92194) step test; Teale MSE via MSEEngine; efficiency = CCS / MSE",
              "Constant RPM within a declared tolerance; stated slope-fraction rule; no CCS correlation"),
        entry(well_control_volumetric, "Volumetric method bleed schedule and gas migration", "Well control",
              "IWCF / IADC volumetric method; gradient = density / 144",
              "Single bubble, constant capacity, no gas law; stops at a declared casing limit",
              "Kill sheet / well-control operational use (P11)"),
        entry(hydraulics_hb_slot, "Annular friction loss, Herschel-Bulkley slot (R-HYD-2)", "Hydraulics",
              "Founargiotakis et al. 2008 slot solution and transition band; Erge et al. 2015 band (declared, NOT "
              "VERIFIED - primary paper unresolved, M541); "
              "Colebrook (Darcy = 4 x Fanning)",
              "Concentric annulus, kappa >= 0.3, 0.1 <= n <= 1; no eccentricity, rotation or temperature/pressure "
              "rheology; transitional = linear blend; Erge Re2 refused outside its fitted n' range"),
        entry(hydraulics_hb_annulus_exact, "Annular friction loss, Herschel-Bulkley exact concentric annulus (laminar)",
              "Hydraulics",
              "Momentum balance tau = (G Ro / 2)(x - lambda^2 / x) with HB plug edges, solved exactly (Fredrickson & "
              "Bird 1958; Hanks 1979, method references); laminar check Founargiotakis et al. 2008 Re1",
              "Laminar only (Re_G >= Re1 refused); concentric, 0.01 <= kappa <= 0.99, 0.1 <= n <= 1; no eccentricity, "
              "rotation, pipe movement or temperature/pressure rheology; M416 unchanged"),
        entry(surge_swab, "Surge and swab pressure, quasi-steady closed-end", "Hydraulics",
              "Burkhardt (1961) effective velocity V + K_c v_p with a declared clinging constant; R-HYD-2 HB slot loss",
              "Quasi-steady only (no fluid inertia, compressibility or pressure waves); closed-end string only - open "
              "end NOT ASSESSED; concentric, no tool-joint detail"),
        entry(drilloff_fitted, "Drill-off founder, fitted two-segment line", "Drilling performance",
              "Continuous hinge least squares (ROP = a + bW + c max(W - W*, 0)); founder rule as declared",
              "Separate from M372 (unchanged); >= 5 distinct-WOB steps at constant RPM; residuals > 3 s flagged, "
              "not removed; no CCS correlation"),
        entry(drilloff_robust, "Drill-off founder, robust L1 two-segment line", "Drilling performance",
              "Continuous hinge by least absolute deviations (exact vertex search; Bloomfield & Steiger 1983); "
              "founder rule as declared",
              "Separate from M372 and M423 (unchanged); 6-30 distinct-WOB steps at constant RPM; declared WOB basis "
              "(surface or downhole), never converted; LAD optimum may be non-unique; not robust to WOB errors; "
              "not a validated downhole method"),
        entry(bit_dull_grade, "Bit dull grade record (IADC)", "Drilling performance",
              "IADC dull grading system (roller-cone 1987; fixed-cutter IADC/SPE 23939, 1992) code set",
              "Record, validation and per-well ordering only; no remaining-life or wear prediction"),
    ]


def catalogue() -> List[CatalogueEntry]:
    entries = _engines() + _contracts() + _specialist() + _workflow_methods() + _case_services()
    return sorted(entries, key=lambda e: (e.family, e.method_id))


def violations(entries: Optional[List[CatalogueEntry]] = None) -> List[str]:
    """Entries that would mislead: unknown status, duplicates, missing evidence or a self-granted approval."""
    entries = catalogue() if entries is None else entries
    out, seen = [], set()
    for e in entries:
        if e.method_id in seen:
            out.append(f"{e.method_id}: duplicate id")
        seen.add(e.method_id)
        if e.status not in STATUSES:
            out.append(f"{e.method_id}: unknown status {e.status!r}")
        if e.status == "IMPLEMENTED" and not (e.version and e.limits and e.module):
            out.append(f"{e.method_id}: implemented without version, limits or module")
        if e.status == "IMPLEMENTED" and not e.reference:
            out.append(f"{e.method_id}: implemented without a reference statement")
        if e.status != "IMPLEMENTED" and not e.blocker:
            out.append(f"{e.method_id}: not implemented without a recorded blocker")
        if e.label and e.label not in LABELS:
            out.append(f"{e.method_id}: unknown label {e.label!r}")
    for method_id in OWNER_APPROVALS:
        if method_id not in seen:
            out.append(f"{method_id}: approval for an unknown method")
    return out


def usage(db, well_id: Optional[int] = None) -> Dict[Tuple[str, str], int]:
    """Stored W13 cases per (method, method_version), for one well or the whole database."""
    from sqlalchemy import func

    from core.database import CalculationCase

    with db.session_scope() as session:
        query = session.query(CalculationCase.method, CalculationCase.method_version, func.count(CalculationCase.id))
        if well_id is not None:
            query = query.filter(CalculationCase.well_id == well_id)
        return {(m, v): int(n) for m, v, n in query.group_by(CalculationCase.method, CalculationCase.method_version)}


def usage_for(entry: CatalogueEntry, counts: Dict[Tuple[str, str], int]) -> Optional[int]:
    """Cases recorded with this entry's method id and version (None when the entry is not a case method)."""
    if entry.source.startswith("calculator contract"):
        method_id = entry.method_id.replace(" (legacy)", "")
        return counts.get((method_id, entry.version), 0)
    return None


def export_csv(path: str, entries: Optional[List[CatalogueEntry]] = None) -> int:
    entries = catalogue() if entries is None else entries
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["# catalogue", CATALOGUE_VERSION])
        writer.writerow(["# status", "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"])
        writer.writerow(COLUMNS)
        for entry in entries:
            writer.writerow(entry.row())
    return len(entries)


__all__ = ["CATALOGUE_VERSION", "CatalogueEntry", "COLUMNS", "NOT_APPROVED", "OWNER_APPROVALS", "catalogue",
           "export_csv", "usage", "usage_for", "violations"]
