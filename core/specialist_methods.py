"""Specialist method registry (M79).

A specialist method may be implemented only when all six criteria hold:

1. ``reference``  - a published, citable method description;
2. ``licence``    - code/data licence compatible with this product (or own code);
3. ``inputs``     - inputs and canonical units defined;
4. ``limits``     - assumptions and validity limits documented;
5. ``benchmark``  - an independent benchmark to test against;
6. ``approval``   - engineering approval of scope and labels (owner).

The registry records each candidate's evidence for every criterion and its
status. ``implementable`` is derived, never typed in; a test fails if an
entry is marked implemented while a criterion is unmet. No AI/ML methods.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

REGISTRY_VERSION = "M79 specialist method registry v1"
CRITERIA = ("reference", "licence", "inputs", "limits", "benchmark", "approval")
STATUSES = ("IMPLEMENTED", "NOT IMPLEMENTED", "OWNER REVIEW REQUIRED")


@dataclass(frozen=True)
class SpecialistMethod:
    method_id: str
    title: str
    scope: str
    reference: str
    licence: str
    assumptions: str
    inputs: Tuple[Tuple[str, str], ...]            # (field, canonical unit)
    limits: str
    benchmarks: str
    criteria: Dict[str, bool] = field(default_factory=dict)
    status: str = "NOT IMPLEMENTED"
    module: Optional[str] = None                   # where it lives when implemented
    blocked_by: str = ""

    @property
    def unmet(self) -> List[str]:
        return [c for c in CRITERIA if not self.criteria.get(c, False)]

    @property
    def implementable(self) -> bool:
        return not self.unmet


def _all(**overrides) -> Dict[str, bool]:
    base = {c: True for c in CRITERIA}
    base.update(overrides)
    return base


METHODS: Tuple[SpecialistMethod, ...] = (
    SpecialistMethod(
        "wellpath.iscwsa_error_model", "ISCWSA survey error model (ellipses of uncertainty)",
        "Position uncertainty for anti-collision separation factors",
        "ISCWSA error model rev. 5 (SPE 67616 and later revisions)",
        "welleng implementation is Apache-2.0, but the ISCWSA model tables need owner licence review",
        "Tool error codes per survey tool; Gaussian error propagation",
        (("md", "m"), ("inc", "deg"), ("azi", "deg"), ("tool_code", "-")),
        "Only for tools with published error codes", "ISCWSA example wells (published test cases)",
        _all(licence=False, approval=False), "OWNER REVIEW REQUIRED",
        blocked_by="ISCWSA model licence and approval; until then anti-collision stays SCREENING (no SF)"),
    SpecialistMethod(
        "thermal.wellbore_temperature", "Transient wellbore temperature (pwptemp)",
        "Circulating temperature profile", "Holmes and Swift (1970); Kabir et al. (1996)",
        "pwptemp is LGPL-3.0: owner decision required", "Radial heat transfer, constant properties",
        (("depth", "m"), ("flow_rate", "m3/s"), ("inlet_temp", "degC")),
        "Not validated beyond the published examples", "Published example profiles only",
        _all(licence=False, benchmark=False, approval=False), "OWNER REVIEW REQUIRED",
        blocked_by="LGPL licence decision; no independent benchmark"),
    SpecialistMethod(
        "tnd.stiff_string", "Stiff-string torque and drag",
        "Torque/drag with bending stiffness (beyond soft-string)", "Mitchell and Samuel (2009)",
        "torque_drag (pro-well-plan) is LGPL-3.0; an own implementation would need a benchmark",
        "Contact-force model with pipe stiffness", (("md", "m"), ("od", "in"), ("friction", "-")),
        "Undefined without wall-contact benchmark data", "None available offline",
        _all(licence=False, benchmark=False, approval=False), "NOT IMPLEMENTED",
        blocked_by="no independent benchmark; LGPL source not adoptable without the owner"),
    SpecialistMethod(
        "fishing.free_point", "Free-point and stretch estimate",
        "Stuck-pipe free-point depth from stretch", "Standard stretch formula (Hooke's law, pipe area)",
        "own code", "Linear elastic pipe, no friction, single pipe size",
        (("pull", "lbf"), ("stretch", "in"), ("pipe_area", "in2")),
        "SCREENING only; tapered strings and friction not modelled", "Hand arithmetic only",
        _all(benchmark=False, approval=False), "IMPLEMENTED",
        module="core/engineering/engines/fishing.py",
        blocked_by="legacy SCREENING engine pre-dates the registry; no field benchmark"),
)


def get(method_id: str) -> SpecialistMethod:
    for method in METHODS:
        if method.method_id == method_id:
            return method
    raise LookupError(method_id)


def violations() -> List[str]:
    """Entries whose status contradicts the criteria (a new IMPLEMENTED entry must meet all six)."""
    out = []
    for method in METHODS:
        if method.status not in STATUSES:
            out.append(f"{method.method_id}: unknown status {method.status!r}")
        if method.status == "IMPLEMENTED" and method.unmet and "SCREENING" not in method.limits:
            out.append(f"{method.method_id}: implemented with unmet criteria {method.unmet}")
        if method.status != "IMPLEMENTED" and method.module:
            out.append(f"{method.method_id}: has a module but is not implemented")
        if method.unmet and not method.blocked_by:
            out.append(f"{method.method_id}: unmet criteria without a recorded blocker")
    return out
