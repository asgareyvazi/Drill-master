#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-020 (45 MEDIUM records, class C).

Phase 2, twelfth batch: the engineering calculation surface - drill-pipe vendor parsing,
anti-collision screening, the API TR 5C3 casing engine, fishing plain-return wrappers,
MSE, the torque-drag screening engine, extended engineering helpers, the EngineeringResult
contract module itself, and the well-control kill-sheet canonical builder.

No flagged construct was closed as a production defect: every site was read in the
hash-verified tree and traced through input -> validation -> engine -> EngineeringResult ->
UI/AI/test, and each one either implements the unknown-vs-zero contract the repository
already documents (the kill-sheet gate, require_number/optional_number, the absent-vs-zero
casing loads, the finite-boundary _to_number) or is a guarded/labeled approximation
(the fish/funnel "0 on invalid input" wrappers, funnel PV/YP).

Three new findings are RECORDED, NOT PATCHED (no semantic change was silently invented):
NEW-P6-004/005/006 - the fishing plain-return wrappers and funnel_viscosity_to_pv_yp
return 0.0/estimate on engine failure, reachable from the W13 tab.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-020"

VC, INT, DUP, DDD, DEF, INS = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                               "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT",
                               "INSUFFICIENT_EVIDENCE")

# The kill-sheet records were derived from the tree at fd18a2b (blob sha256 proven equal to
# each record's source_sha256); the file gained the casing-id gate comment at ff2000a, so the
# current coalesce lines sit 5 lines lower.  Every other batch file is byte-identical to the
# current tree.
RECHECK_AGAINST: dict[str, str] = {
    "core/engineering/well_control_kill_sheet.py": "fd18a2b",
}
RECONSTRUCT: dict[str, tuple[str, str, tuple[int, ...]]] = {}

FINGERPRINT_SOURCE = "docs/audits/m34-evidence/m34-ledger.json"
LEDGER_AVAILABLE = (ROOT / FINGERPRINT_SOURCE).is_file()


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for {where}, already adjudicated under {sibling}: "
            f"{summary}",
            None)


def misfire(what: str) -> tuple[str, str, None]:
    return (DUP,
            f"Rule mis-fire, not a behaviour to adjudicate: {what}",
            None)


# ----------------------------------------------------------------- shared contract fragments
_REQ_NUM = (
    "core/engineering/result.py:104-116 `require_number` rejects None/blank/bool/non-numeric/"
    "non-finite with MissingInputError/EngineeringError and its docstring states 'Never invent "
    "0 for a missing engineering input'"
)
_OPT_NUM = (
    "`optional_number` (core/engineering/result.py:119-130) returns the number, None for a "
    "missing value and raises on a non-numeric or non-finite one"
)
_GUARD = (
    "the value was validated by require_number/optional_number immediately above, so the "
    "range test runs over a proven-finite float and is the validation itself, not a "
    "truthiness default"
)
_PROV_TREE = (
    "hash-provenance tree fd18a2b (blob sha256 == the record's source_sha256); the casing-id "
    "gate comment inserted at ff2000a shifted the coalesce lines +5"
)


# ----------------------------------------------------------------- adjudications
R: dict[str, tuple[str, str, str | None]] = {}


R["INV34-007452"] = (
    VC,
    "`if not math.isfinite(number):  # NaN / inf / 1e400 overflow` -> `return None` "
    "(core/engineering/drill_pipe.py:120-121) is the finite-boundary contract of `_to_number` "
    "itself, inside the docstring that states it: 'Parse a finite float, or None when the "
    "value is not a clean number... this does NOT judge the engineering domain (0/negative "
    "pass here); domain validity (OD>0 etc.) is enforced separately so we can distinguish "
    "not-a-number from a number outside the physical domain' (107-111).  This is the exact "
    "boundary batch-017 established and the same shape this audit's own 179b57f fix enforced "
    "in the import paths; the flag text sits on the guard that *implements* the rule family's "
    "demand, so closing it as a truthiness question would close the contract against itself.  "
    "Downstream: _to_inches and the component parser (330) propagate None and skip "
    "non-numeric rows - an unparseable cell never becomes a 0-inch segment.",
    None,
)

R["INV34-001514"] = (
    VC,
    "`return values[0] or None` closes `resolve_text` inside "
    "`DrillPipeSpec.from_vendor_row` (core/engineering/drill_pipe.py:302-316).  `values` is "
    "`[str(v).strip() for _, v in matches]` (308) where `matches = _present_matches(row, "
    "aliases)` already excludes the missing/unknown cells: `_is_missing` returns True for "
    "None, NaN and the unknown-token set {_UNKNOWN_TOKENS at 73: '', 'nan', 'none', 'null', "
    "'n/a', 'na', '-', '--', '?', 'tbd', 'unknown'} (76-90), and a cell whose stripped text "
    "falls in that set is filtered out.  So at line 316 the only falsy value `values[0]` can "
    "hold is the empty string that survived because the *raw* cell was not in the token set "
    "but strips to '' via a different whitespace form; `or None` maps exactly that residual "
    "blank to None - the declared 'not supplied' of the spec object - and passes every "
    "non-blank text (manufacturer/model/grade/connection, callers at 361-364) through "
    "verbatim.  Conflicts are reported as SpecIssue(ISSUE_CONFLICT) with the header/value "
    "evidence and return None (309-315).",
    None,
)

R["INV34-007457"] = dup(
    "INV34-001514",
    "the identical `return values[0] or None` at core/engineering/drill_pipe.py:316 "
    "(R-DEF-UNKNOWN/or-constant beside R-DEF-UNKNOWN/or-empty)",
    "the residual-blank -> None mapping of resolve_text under DrillPipeSpec.from_vendor_row, "
    "whose match filter (_is_missing + _UNKNOWN_TOKENS) leaves '' as the only falsy value",
)

R["INV34-001536"] = (
    VC,
    "`except Exception as exc:` in `AntiCollisionEngine.calculate_with_welleng` "
    "(core/engineering/engines/anti_collision.py:397-402) wraps ONLY the optional "
    "welleng-adapter metadata block: `values[\"welleng_available\"] = "
    "WellengAdapter.available()` (399) after the real screening "
    "(`result = cls.screen_clearance(reference, offset)`, 395) has already produced the "
    "authoritative EngineeringResult.  The handler does not swallow a failure - it *reports* "
    "it: `values[\"welleng_available\"] = False; values[\"welleng_error\"] = str(exc)` "
    "(401-402), i.e. the exception becomes a named diagnostic field, and "
    "WellengAdapter.available() itself converts ImportError to False (adapters/"
    "welleng_adapter.py:28-33).  The benchmark contract is explicit in the sibling "
    "torque-drag adapter block ('External packages are not used as the calculation backend. "
    "Compare independently if installed.', torque_drag.py:683-686): an adapter crash must "
    "never fail a result that does not depend on it.  Consumers: the W13 anti-collision tab "
    "consumes the EngineeringResult via CalculatorBridge.anti_collision "
    "(tabs/w13_Engineering_Calculator.py:4992) and surfaces failures as "
    "ENGINE_FAILED; calculate_with_welleng has no in-repo caller, so the metadata path is "
    "diagnostics-only.",
    None,
)

R["INV34-001580"] = (
    VC,
    "`return max(0.0, rating), regime, dt, ...` closes `CasingEngine._collapse_uncorrected` "
    "(core/engineering/engines/casing.py:64-79) - the API TR 5C3 four-regime collapse "
    "reduction over D/t (yield/plastic/transition/elastic, 67-78).  The inputs are gated "
    "before the call: `collapse` requires `od > 0, t > 0, yp > 0, t < od/2` via "
    "require_number (142-145), so `dt = od/t` is a positive finite float and each branch "
    "formula is the standard's own.  A physical clamp is the standard-compliant reading: "
    "outside the fitted D/t range the empirical curve can return a negative pressure, which "
    "is meaningless for a *pressure rating* (a rating below zero psi does not exist); the "
    "clamp states 'no collapse capacity attributable' and keeps the regime label so the "
    "consumer sees the branch that produced it.  The mathematical sign is not used elsewhere "
    "- `collapse_combined` re-derives its corrected value and clamps identically "
    "(pc_corr = max(0.0, pc_corr), 233).  Verified against the hand-computed ground truth in "
    "tests/test_casing_persistence.py (`_direct()` / burst 0.875*2*Yp*t/OD family) and the "
    "governing-rating assertions in tests/test_casing_absent_load_semantics.py:52-54 "
    "(collapse_uncorrected == collapse_combined == 4754.0 abs 1.0).",
    None,
)

R["INV34-001585"] = (
    VC,
    "`return max(0.0, (root - 0.5 * z) * yield_psi)` closes `CasingEngine.fyax` "
    "(core/engineering/engines/casing.py:82-94), the API 5C3 biaxial yield reduction whose "
    "docstring derives both signs (85-86).  The domain is enforced by the function itself: "
    "`if yield_psi <= 0: return 0.0` (88-89, a zero-strength pipe has zero reduced yield - a "
    "physical zero), `z = axial_stress_psi/yield_psi` (90), `if abs(z) >= 1.0: return 0.0` "
    "(91-92, outside the model's validity the strength is exhausted), and "
    "`root = sqrt(max(0.0, 1 - 0.75 z^2))` (93) already clamps the radicand.  For in-domain "
    "z the expression root - 0.5z is provably positive, so the outer max only pins the "
    "documented degenerate branches (exhausted/zero strength) at the physically-correct 0.0.  "
    "The consumer is the biaxial collapse path itself (225: `yp_ax = cls.fyax(yp, sa)`) with "
    "the caller-side handling 'yp_ax if yp_ax > 0 else yp' plus the explicit "
    "yield_exhausted regime (229-231).  The absent-vs-zero load semantics feeding `sa` are "
    "pinned by tests/test_casing_absent_load_semantics.py (reported None for absent, 0.0 "
    "only when supplied).",
    None,
)

R["INV34-001592"] = (
    VC,
    "`include_capped_end=True` (core/engineering/engines/casing.py:288) is a boolean "
    "keyword default of `triaxial_vme` meaning 'include the Pi*A_i - Pe*A_o capped-end axial "
    "stress term'.  It is a modelling switch documented at the point of consumption "
    "(309-311: `if include_capped_end: capped = (pi*ri^2 - pe*ro^2)/area`) and in the result "
    "assumptions ('Capped-end axial from Pi, Pe included when include_capped_end=True', "
    "334), not a numeric substitution for a missing measurement; the *measurements* "
    "(Pi, Pe, tension) are independently validated by require_number/optional_number.  No "
    "in-repo caller overrides the default; a caller who wants the open-face case passes "
    "False explicitly.  It never reaches a database column or an import boundary - it is an "
    "engine argument with the standard's default semantics.",
    None,
)

R["INV34-001622"] = (
    VC,
    "`modulus_psi: float = 30.0e6` (core/engineering/engines/fishing.py:314) is the steel "
    "Young's modulus default of `calculate_backoff_depth`, mirroring the engine default "
    "`FishingEngine.backoff_depth(..., modulus_psi=30.0e6)` (171-172) whose docstring states "
    "the formula L = dL*E*A/(W*12) and labels the whole construct 'legacy approximation - "
    "the pipe weight cancels... Screening use only' (174-179).  30e6 psi is the physical "
    "constant for steel, a *parameter*, not a measurement; the wrapper passes it through "
    "explicitly (321) so a caller can override.  See NEW-P6-006 for the wrapper's "
    "failure-return contract, recorded there with its reachability.",
    None,
)

R["INV34-008711"] = (
    VC,
    "`if not math.isfinite(area) or not math.isfinite(denominator) or area <= 0 or "
    "denominator <= 0: raise EngineeringError(...)` (core/engineering/engines/mse.py:62-63) "
    "is the MSE engine's own finite/zero-denominator refusal, exactly the boundary the "
    "audit demands: after `wob/n/tq >= 0` (53-54), `d > 0` (55-56) and the explicit "
    "'zero ROP makes MSE undefined' gate (`rop <= 0` -> EngineeringError, 57-58), this guard "
    "refuses overflow-scale geometry/rates instead of emitting a fabricated MSE.  The flag "
    "is the rule family's own remedy - the engine fails loudly on the undefined state and "
    "returns ok(...) with status/units only when the reduction is finite.  Callers consume "
    "the refusal: the persistence suites (test_mse_persistence.py, test_mse_cross_process.py) "
    "pin the result contract and the W3/W13 surfaces render the error path.",
    None,
)

R["INV34-001673"] = (
    VC,
    "`if not bha: raise MissingInputError(\"bha\")` (core/engineering/engines/torque_drag."
    "py:72-73) is the missing-input refusal of `TorqueDragEngine._validate`, twin of the "
    "survey refusal at 70-71.  The flag text is the refusal itself - a missing BHA string "
    "fails the calculation (result.failed via the calculate() except-chain at 323-326) "
    "instead of integrating an empty string into an invented hookload.  The subject type is "
    "`List[Dict]` (331-332); `not bha` over a list is the empty-or-None test the signature "
    "declares.",
    None,
)

R["INV34-001672"] = misfire(
    "`if not (0.0 <= ff <= 1.0):` (core/engineering/engines/torque_drag.py:75-76) is a "
    "chained range validation over `ff = require_number(friction_factor, ...)` (74) - the "
    "value is a proven-finite float one line above and the test is the domain check itself "
    "(EngineeringError 'friction_factor must be in [0, 1]').  " + _GUARD + " The "
    "R-TRUTH-UNKNOWN family targets bare truthiness on unproven optionality; a range guard "
    "over require_number output does not match that semantic."
)

R["INV34-001675"] = misfire(
    "`if not 0.0 <= bf <= 1.0:` (torque_drag.py:124-125) - same shape as INV34-001672: "
    "`bf = require_number(buoyancy_factor, ...)` at 118 and this is the documented domain "
    "check ('buoyancy_factor must be in [0, 1]') over a proven-finite float.  " + _GUARD
)

R["INV34-001677"] = misfire(
    "`if not 0.0 <= inc <= 90.0:` (torque_drag.py:126-127) - `inc = require_number("
    "inclination_deg, ...)` at 119; the flag is the declared domain check "
    "('inclination_deg must be in [0, 90]') of the W13 weight-card path.  " + _GUARD
)

R["INV34-001676"] = misfire(
    "`if not 0.0 <= ff <= 1.0:` (torque_drag.py:130-131) - third instance of the same "
    "range-validation shape in `_weight_card_from_air_weight` (ff from require_number at "
    "121).  " + _GUARD
)

R["INV34-001670"] = misfire(
    "`if not 0.0 <= bf <= 1.0:` (torque_drag.py:267-268) - the landing-load card's "
    "buoyancy-factor domain check over `bf = require_number(buoyancy_factor, ...)` (263).  "
    + _GUARD
)

R["INV34-001671"] = misfire(
    "`if not 0.0 <= ff <= 1.0:` (torque_drag.py:269-270) - the landing-load card's "
    "friction-factor domain check over `ff = require_number(friction_factor, ...)` (264).  "
    + _GUARD
)

R["INV34-001659"] = (
    VC,
    "`wob_klbf: float = 0.0` (core/engineering/engines/torque_drag.py:335, mirrored in "
    "calculate() at 356) is the WOB parameter of the torque-drag screening model.  The "
    "consumer path validates and documents the default: `wob_klbf_value = optional_number("
    "wob_klbf, \"wob_klbf\")` keeps None as unknown (370), a negative raises (371-372), and "
    "`wob = (wob_klbf_value or 0.0) * 1000.0` (373) is the *physical* 'no weight on bit' "
    "state of a static screening integration - the force term enters `_integrate` as "
    "`force = -wob_lbf` (502: compression at bit when WOB applied) and zero WOB is the "
    "legitimate pick-up/slack-off baseline the model computes, not a missing datum.  A "
    "caller wanting 'unknown' passes None and gets the same result - but the UI default of "
    "0 khlbf WOB for a static card is the standard convention, and the whole surface carries "
    "SCOPE = \"PARTIAL\" (52) plus the five warnings ('PARTIAL / SCREENING MODEL - not "
    "production-certified', 383-388) required by ENGINEERING_ARCHITECTURE.md, so no capability "
    "claim is inflated.  Persistence of these runs is pinned by tests/test_torque_drag_"
    "persistence.py (byte-identical recomputation + frozen-snapshot non-mutation).",
    None,
)

R["INV34-001657"] = (
    VC,
    "`except Exception as exc:` in `TorqueDragEngine.calculate_with_welleng` "
    "(core/engineering/engines/torque_drag.py:677-688) wraps only the optional "
    "adapter-metadata block AFTER `internal = cls.calculate(...)` (675) has produced the "
    "authoritative result and `payload = internal.as_dict()` copied it.  The handler "
    "*reports* the failure as a named field (`payload[\"values\"][\"adapter_error\"] = "
    "str(exc)`, 687-688) rather than dropping it, and the module states the benchmark "
    "contract inline ('External packages are not used as the calculation backend. Compare "
    "independently if installed.', 683-686).  A crash in optional metadata must not fail a "
    "screening result that never depended on it; the Screening warnings themselves travel "
    "inside the result values (383-388).  No in-repo caller calls calculate_with_welleng "
    "(grep over tabs/, dialogs/, core/, tests/: only the definition), so the path is "
    "diagnostics-only today.",
    None,
)

R["INV34-007485"] = (
    VC,
    "`class ExtendedEngineeringError(Exception): pass` (core/engineering/extended.py:26-27) "
    "is the module's typed error root: the mandatory body of an exception subclass (Python "
    "requires one statement; `pass` is it).  The class is *raised* throughout the module "
    "(corrosion_rate 165-172, slurry_density total-volume guard, funnel/mbt/lsryp guards, "
    "Bourgoyne-Young 732) and caught by the W13 handlers that render the message "
    "(e.g. tabs/w13_Engineering_Calculator.py:3356-3362 renders the corrosion result and its "
    "error path), so it is the reporting mechanism itself, not a swallowed operation.  This "
    "matches the 20-site family batch-018 swept ('8 are exception classes... a "
    "repository-wide idiom, none of which is a swallowed operation').",
    None,
)

R["INV34-007492"] = (
    VC,
    "`class EngineeringError(Exception): pass` (core/engineering/result.py:13-14) is the "
    "root of the whole engineering error hierarchy (MissingInputError subclasses it at 17): "
    "the mandatory `pass` body of an exception class in the module whose docstring declares "
    "'Every engine returns the same shape so UI, AI tools, export and tests can consume "
    "results without per-engine adapters' (2-4).  It is raised by require_number/"
    "optional_number (108-115, 123-129) and every engine, and converted to failed(...) "
    "results at the engine boundaries - the typed refusal mechanism of the canonical result "
    "contract, not a hidden swallow.",
    None,
)

R["INV34-001726"] = (
    VC,
    "`density_g_cm3: float = 7.86` (core/engineering/extended.py:160) is the steel coupon "
    "density default of `corrosion_rate`, documented in the docstring with the API RP 13B-1 "
    "formula and its units ('D = coupon density (g/cm^3, steel ~= 7.86)', 163-165).  It is "
    "a physical-material constant, not a substituted measurement; the function validates "
    "every operand (`area > 0`, `hours > 0`, `density > 0`, `weight_loss >= 0`, 166-172) and "
    "returns severity bands alongside the mpy value.  Production caller: "
    "tabs/w13_Engineering_Calculator.py:3356 passes the UI coupon fields and renders the "
    "result (3360-3361); tests/test_extended_engineering.py and "
    "tests/test_engineering_integrations.py:193 pin it.",
    None,
)

R["INV34-001725"] = (
    VC,
    "`cement_sg: float = 3.15` (core/engineering/extended.py:687) is the standard Class-G "
    "cement specific gravity (~3.15 g/cm^3) used to convert cement weight to volume in "
    "`slurry_density` - a physical material constant with the formula stated in the "
    "docstring (690-692).  The function validates the derived volume (`total_vol <= 0` -> "
    "ExtendedEngineeringError, 700-701) and labels its yield branch explicitly "
    "(`yield_m3_per_ton: ... if cement_weight_kg > 0 else 0`, 706-707 - a zero-ton batch "
    "has zero yield per ton by definition, and the zero is derived, not substituted for an "
    "unknown weight because the caller supplied the weight argument).  The w3c tab's "
    "slurry_density *field* (tabs/w3c_section_data.py:80) is an unrelated UI column of the "
    "cement report, not this helper's consumer.",
    None,
)

R["INV34-001728"] = (
    VC,
    "`porosity_pct: float = 20` (core/engineering/extended.py:725) is the formation-porosity "
    "parameter of the *simplified* Bourgoyne & Young ROP model, whose docstring states the "
    "calibration contract: 'Actual ROP prediction requires calibrated constants from offset "
    "wells. K is calibrated here to produce realistic field-order results (typically 5-50 "
    "m/hr...)' (729-731) and whose result dict returns the parameters and the note "
    "('Simplified model. Calibrate K, a, b, c with offset well data.', 745-747).  20% is a "
    "mid-range rock parameter, a model input with a published default, not a measurement "
    "substituted for missing data; the function refuses the undefined domain "
    "('Depth, WOB, and RPM must be > 0', 732-733).  Consumer: "
    "tests/test_extended_engineering.py:160-169 pins both the value and the invalid-input "
    "refusal; no tab consumes it today.",
    None,
)

R["INV34-001727"] = (
    VC,
    "`strength_factor: float = 1.0` (core/engineering/extended.py:726) is the "
    "formation-drillability multiplier of the same simplified Bourgoyne & Young model "
    "(k = 0.5 * strength_factor * (1 + porosity_pct/100), 736-737) - a dimensionless model "
    "parameter whose default 1.0 is the neutral identity of a multiplier, with the "
    "calibration disclaimer returned in the result (747) and the domain refusal at 732-733.  "
    "Same contract source as INV34-001728.",
    None,
)

R["INV34-007493"] = (
    VC,
    "`values=values or {}` (core/engineering/result.py:66) is the container normalisation of "
    "`ok(...)` - the canonical success constructor used by all 46 in-repo engine return "
    "sites.  `values` is declared `Optional[Dict[str, Any]]` (default None) and `or {}` "
    "yields the declared empty mapping for 'no multi-value payload', so every "
    "EngineeringResult.values is always a dict (as_dict()/JSON consumers never branch on "
    "None); a caller-supplied populated dict passes through unchanged.  This is a "
    "shape contract of the result envelope, not a numeric coercion: no measurement flows "
    "through this default (the single `value` field is passed verbatim at 65, None "
    "included, so an engine can succeed with value=None and the consumer sees unknown).  "
    "The contract module is the *source* of the audit's own semantics (require_number: "
    "'Never invent 0 for a missing engineering input', 105).",
    None,
)

R["INV34-007494"] = dup(
    "INV34-007493",
    "the identical list container default `assumptions=list(assumptions or [])` at "
    "core/engineering/result.py:70",
    "None -> declared empty list for the always-list shape of the result envelope; "
    "engine-supplied assumption strings pass through verbatim",
)

R["INV34-007495"] = dup(
    "INV34-007493",
    "the identical list container default `warnings=list(warnings or [])` at "
    "core/engineering/result.py:71",
    "None -> declared empty list; warnings also drive validation_status='warning' (62), so "
    "the envelope's status semantics never depend on the container default",
)

R["INV34-007496"] = dup(
    "INV34-007493",
    "the identical mapping container default `metadata=metadata or {}` at "
    "core/engineering/result.py:73",
    "None -> declared empty mapping for the always-dict metadata shape of the envelope",
)

R["INV34-007497"] = (
    VC,
    "`if not math.isfinite(number): raise EngineeringError(...)` closes `require_number` "
    "(core/engineering/result.py:104-116) - this IS the finite-boundary contract the whole "
    "engineering surface builds on, stated in the function's own docstring: 'Reject "
    "None/blank. Never invent 0 for a missing engineering input' (105).  The full refusal "
    "chain: None/'' -> MissingInputError (106-107), bool -> EngineeringError (108-109), "
    "non-numeric -> EngineeringError (110-113), NaN/inf -> EngineeringError (114-115).  "
    "Every engine site this batch examined validates through this gate first (torque_drag "
    "74/118-121/262-264, casing 99-101/142-144/199-201, mse 50-52, fishing free_point/"
    "backoff_depth, drill-pipe _to_number's sibling); the rule hit anchors the contract "
    "itself, so closing it as a truthiness question would close the repository's own "
    "unknown-vs-zero guarantee against itself.  Pinned by tests/test_m30_semantic_regressions"
    ".py and every engine suite that asserts EngineeringError on non-finite input.",
    None,
)

R["INV34-007499"] = (
    VC,
    "`if not math.isfinite(number): raise EngineeringError(...)` closes `optional_number` "
    "(core/engineering/result.py:119-130): the optional twin of require_number with the "
    "identical refusal chain except that None/'' returns None (120-121) - the declared "
    "'unknown' carrier of the surface (casing absent loads -> reported None per "
    "tests/test_casing_absent_load_semantics.py; actual_vs_plan compare -> status "
    "'unavailable'; kill-sheet builder -> missing_inputs gate).  A non-finite value is "
    "*not* mapped to unknown here: it raises, so a corrupted 'inf' source cell fails loudly "
    "instead of silently becoming 'not supplied' - exactly the distinction the contract "
    "requires (missing is unknown; invalid is an error).  The flag anchors the contract "
    "itself; not a truthiness defect.",
    None,
)

# kill-sheet coalesce records: the builder gate + refuse-instead mechanism
_KS_GATE = (
    "The kill-sheet boundary is not a silent-default surface: "
    "`build_canonical_kill_sheet_inputs` computes `missing_inputs = tuple(name for name, "
    "value in required_raw.items() if _num(value) is None)` (277, current tree) over exactly "
    "the inputs compute_kill_sheet consumes (the module comment states 'Inputs the composite "
    "computation actually consumes'), and `compute_kill_sheet` REFUSES the computation when "
    "any is missing: `if inp.missing_inputs: return KillSheetResult(success=False, "
    "error=...missing required kill-sheet inputs...)` (441-447, 'A kill sheet computed from "
    "absent kick data looks plausible and is wrong... Refuse instead').  The historical "
    "`or 0.0` substitutions therefore never reach a formula behind the engineer's back: "
    "an unknown required input produces success=False with the named fields, and the "
    "explicit-zero case (0.0 supplied) is a supplied value - "
    "tests/test_kill_sheet_casing_id_gate.py pins all three directions (absent refuses, "
    "present computes, explicit zero stays supplied).  The builder substitutes 0.0 only to "
    "satisfy the frozen dataclass field types ('The builder has always substituted 0.0 for "
    "its float fields (historical arithmetic is preserved), so without this the engine "
    "cannot tell recorded zero from never entered', 145-148) - provenance lives in "
    "missing_inputs."
)

for _rid, _field, _raw, _note in (
    ("INV34-009628", "tvd_ft", "tvd_m", "consumed by WC.kill_mw(mw_ppg, sidpp, inp.tvd_ft)"),
    ("INV34-009629", "md_ft", "md_m", "canonical echo/canonical-unit field of the frozen inputs"),
    ("INV34-009630", "shoe_tvd_ft", "shoe_tvd_m",
     "consumed by WC.maasp(shoe_tvd_ft=inp.shoe_tvd_ft)"),
    ("INV34-009631", "hole_size_in", "hole_size_in", "annular capacity input"),
    ("INV34-009632", "casing_id_in", "casing_id_in",
     "annulus input; its gate entry was ADDED by ff2000a exactly to close this class of gap"),
    ("INV34-009633", "mw_ppg", "mw_pcf", "hydrostatic/kill-mw input (converted once)"),
    ("INV34-009634", "frac_gradient_psi_ft", "frac_gradient_psi_ft",
     "MAASP max-allowable-mw input (None when absent -> maasp fails)"),
    ("INV34-009635", "sidpp_psi", "sidpp_psi", "ICP and kill_mw input"),
    ("INV34-009636", "sicp_psi", "sicp_psi", "kick-type classification input"),
    ("INV34-009637", "pit_gain_bbl", "pit_gain_bbl", "kick_volume input"),
    ("INV34-009638", "scr1_psi", "scr1_psi", "ICP/FCP input"),
    ("INV34-009639", "scr1_spm", "scr1_spm", "echo-only display metadata (deliberately ungated)"),
    ("INV34-009640", "scr2_psi", "scr2_psi", "echo-only display metadata (deliberately ungated)"),
    ("INV34-009641", "scr2_spm", "scr2_spm", "echo-only display metadata (deliberately ungated)"),
    ("INV34-009642", "pump_output_bbl_stk", "pump_output_bbl_stk",
     "stroke divisor; strokes guard `if pump_output > 0 else 0` keeps a missing/zero pump "
     "from dividing"),
):
    R[_rid] = (
        VC,
        f"`{_field}=(_num({_raw}) or 0.0)` (well_control_kill_sheet.py:286-305 register "
        f"lines; current tree {286 if _rid != 'INV34-009628' else 291}-310 via {_PROV_TREE[:1][0] if False else '+5 shift'}) "
        f"- {_note}.  " + _KS_GATE,
        None,
    )

R["INV34-009639"] = (
    VC,
    "`scr1_spm=(_num(scr1_spm) or 0.0)` (well_control_kill_sheet.py:302 current) is "
    "echo-only display metadata, deliberately absent from required_raw: the module comment "
    "states '``scr1_spm``/``scr2_spm`` are echo-only display metadata and are deliberately "
    "absent' (257-258) - the SPM values are rendered back to the engineer but consumed by "
    "no formula, so a missing SPM cannot fabricate a kill-sheet number.  " + _KS_GATE,
    None,
)

R["INV34-009640"] = (
    VC,
    "`scr2_psi=(_num(scr2_psi) or 0.0)` (well_control_kill_sheet.py:303 current) is "
    "echo-only: compute_kill_sheet unpacks only scr1 (`scr1 = inp.scr1_psi`, 456; ICP/FCP "
    "from scr1 at 495/500) and the handler unpacks scr2 purely to render it "
    "(tabs/w13_Engineering_Calculator.py:4344-4345).  The historical slow-pump-rate line is "
    "displayed, never consumed - the same gate contract as its siblings, with no formula "
    "behind the coalesce at all.  " + _KS_GATE,
    None,
)

R["INV34-009641"] = (
    VC,
    "`scr2_spm=(_num(scr2_spm) or 0.0)` (well_control_kill_sheet.py:304 current) - "
    "echo-only SPM metadata, deliberately ungated per the module comment (257-258); no "
    "formula consumes it.  " + _KS_GATE,
    None,
)


# ----------------------------------------------------------------- observations / new findings
NEW_FINDINGS: list[dict] = [
    {"id": "NEW-P6-004", "file": "core/engineering/engines/fishing.py", "line": 303,
     "severity": "MEDIUM",
     "status": "recorded, not patched",
     "summary": ("`calculate_string_stretch` returns `r.value if r.success else 0.0` - an "
                 "engine failure becomes a 0.00 in stretch reading in the W13 stuck-pipe "
                 "panel (calc via tabs/w13_Engineering_Calculator.py:100-103, rendered at "
                 "5241-5242 as 'String Stretch = {stretch:.2f} in').  A failed calculation "
                 "and a real zero stretch are not distinguishable in the display; the "
                 "EngineeringResult contract (missing/failed -> failed result with error) "
                 "is discarded at the plain-return boundary.  Docstring says '0 on invalid "
                 "input' (legacy behaviour) but the consumer cannot tell legacy-zero from "
                 "failure.")},
    {"id": "NEW-P6-005", "file": "core/engineering/engines/fishing.py", "line": 297,
     "severity": "MEDIUM",
     "status": "recorded, not patched",
     "summary": ("`calculate_free_point` returns `0.0` on engine failure "
                 "(and pre-guards pull_lbf <= 0 -> 0.0); the W13 stuck-pipe panel renders "
                 "'Free Point = {fp:.1f} ft' (tabs/w13_Engineering_Calculator.py:5234-5239) "
                 "so a failed free-point calculation displays as 0.0 ft - a fabricated "
                 "operational depth.  test_single_source_guard.py:138 pins the 0-on-invalid "
                 "legacy shape, so a fix must decide the legacy contract first (domain "
                 "decision + UI change), hence recorded not patched.")},
    {"id": "NEW-P6-006", "file": "core/engineering/engines/fishing.py", "line": 321,
     "severity": "MEDIUM",
     "status": "recorded, not patched",
     "summary": ("`calculate_backoff_depth` returns `0.0` on engine failure; its W13 caller "
                 "calc_backoff_depth (tabs/w13_Engineering_Calculator.py:260-265) rounds "
                 "and renders the same value, so a failed back-off free point reads as "
                 "0.0 ft.  Same family and same fix decision as NEW-P6-004/005.")},
]

OBSERVATIONS: list[dict] = [
    {"record": "INV34-009629 (md_ft)", "site": "core/engineering/well_control_kill_sheet.py",
     "observation": ("`md_ft` is a canonical echo/canonical-unit field of the frozen input "
                     "object: compute_kill_sheet consumes tvd_ft (kill_mw), shoe_tvd_ft "
                     "(maasp) and the pipes, but no `inp.md_ft` read exists in the "
                     "computation (grep).  It travels in as_dict()/snapshots for "
                     "reconstruction and rendering; recorded so the next sweep does not "
                     "mistake it for an ungated formula input.")},
    {"record": "kill-sheet gate coverage", "site": "core/engineering/well_control_kill_sheet.py:257-275",
     "observation": ("required_raw covers tvd/md/shoe/hole/casing_id/mw/frac/sidpp/sicp/"
                     "scr1/pit_gain/pump_output - exactly the consumed set; scr2_psi/scr1_spm/"
                     "scr2_spm are echo-only and casing_od_in is display-only (annulus uses "
                     "casing_id_in).  The casing_id entry was added by ff2000a with its own "
                     "regression suite; the gate is complete for the current computation.  "
                     "If a future change consumes scr2_psi or the pipes' od/id/length, the "
                     "gate must grow with it (the pipes coalesce at 245-247 also relies on "
                     "the annulus math, not on missing_inputs).")},
    {"record": "INV34-001536 / INV34-001657", "site": "core/engineering/adapters/",
     "observation": ("both welleng metadata handlers convert an adapter crash into a named "
                     "diagnostic field (welleng_error / adapter_error) instead of failing "
                     "the authoritative result; the benchmark wording is quoted in "
                     "torque_drag.py:683-686.  Recorded as the family contract for any "
                     "future optional-package surface.")},
    {"record": "sibling sweep: 0-on-failure plain wrappers", "site": "core/engineering/engines/fishing.py:296-322",
     "observation": ("the three plain wrappers (free_point, string_stretch, backoff_depth) "
                     "share the legacy '0 on invalid input' contract and the W13 panel "
                     "renders their numeric return directly; recorded as NEW-P6-004/005/006 "
                     "with reachability.  The same *shape* exists in "
                     "DrillingManager.calculate_rop (managers.py:403-408) but that tab "
                     "labels failures differently; a fix should cover the family through "
                     "one decision, not a scattered patch.")},
]


# ----------------------------------------------------------------- helpers (018/019 architecture)
def m34_norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def git_blob(rev: str, path: str) -> bytes:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed: {out.stderr.decode()[:200]}")
    return out.stdout


def provenance_tree(path: str, declared_sha: str) -> tuple[list[str], bytes, str]:
    key = (path, declared_sha)
    if key in _TREES:
        return _TREES[key]
    current = (ROOT / path).read_bytes()
    if hashlib.sha256(current).hexdigest() == declared_sha:
        result = (current.decode("utf-8", "replace").splitlines(), current,
                  "current tree: sha256(file) == the record's source_sha256")
    elif path in RECHECK_AGAINST:
        commit = RECHECK_AGAINST[path]
        data = git_blob(commit, path)
        result = (data.decode("utf-8", "replace").splitlines(), data,
                  f"provenance tree = {commit} (blob sha256 == the record's source_sha256; "
                  f"the file moved in ff2000a which added the casing-id gate comment)")
    else:
        raise SystemExit(f"{path}: no provenance tree known for sha256 {declared_sha[:16]}...")
    if hashlib.sha256(result[1]).hexdigest() != declared_sha:
        raise SystemExit(f"{path}: provenance tree sha256 mismatch")
    _TREES[key] = result
    return result


_TREES: dict[tuple[str, str], tuple[list[str], bytes, str]] = {}

_AST_CACHE: dict[str, object] = {}


def _parsed(source: str):
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if key not in _AST_CACHE:
        _AST_CACHE[key] = ast.parse(source)
    return _AST_CACHE[key]


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    tree = _parsed(source)
    parts = [p for p in (symbol or "").split(".") if p]
    if not parts:
        raise SystemExit(f"empty symbol {symbol!r}")
    index: dict[str, tuple[int, int]] = {}

    def visit(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                index[".".join(qualified)] = (child.lineno, child.end_lineno)
                visit(child, qualified)

    visit(tree, [])
    found = index.get(".".join(parts))
    if found is None:
        candidates = [n for n in ast.walk(tree)
                      if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name == parts[-1]]
        if len(candidates) != 1:
            raise SystemExit(f"symbol {symbol!r} not resolvable ({len(candidates)} candidates)")
        found = (candidates[0].lineno, candidates[0].end_lineno)
    return found


def record_scope(source: str, symbol: str, line: int) -> tuple[int, int]:
    if (symbol or "").strip():
        return symbol_body(source, symbol)
    tree = _parsed(source)
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.lineno <= line <= (node.end_lineno or node.lineno):
            if best is None or node.lineno >= best.lineno:
                best = node
    if best is None:
        return 1, len(source.splitlines())
    return best.lineno, best.end_lineno


def scope_symbol_forms(source: str, line: int) -> list[str]:
    tree = _parsed(source)
    forms: list[str] = []

    def walk(node, prefix):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = prefix + [child.name]
                if child.lineno <= line <= (child.end_lineno or node_end(child)):
                    forms.append(".".join(qualified))
                    forms.append(child.name)
                walk(child, qualified)

    walk(tree, [])
    return forms


def node_end(node) -> int:
    return getattr(node, "end_lineno", None) or node.lineno


def ast_segment_forms(source: str, line: int, limit: int = 60) -> list[str]:
    tree = _parsed(source)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue
        if not (node.lineno <= line <= (node.end_lineno or node.lineno)):
            continue
        segment = ast.get_source_segment(source, node)
        if not segment or len(segment) > 4000:
            continue
        normalized = m34_norm(segment)
        if normalized and normalized not in [f[1] for f in found]:
            found.append(((node.end_lineno or node.lineno) - node.lineno, normalized))
    found.sort(key=lambda item: (item[0], len(item[1])))
    return [text for _, text in found[:limit]]


def line_map(previous: list[str], current: list[str]) -> dict[int, int]:
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def text_matches(recorded: str, actual: str) -> bool:
    expected, candidate = (recorded or "").strip(), (actual or "").strip()
    if len(expected) >= 160:
        return candidate[:len(expected)] == expected
    return candidate == expected


def fingerprint_proof(record: dict, m34: dict, tree_source: str):
    symbol = record.get("symbol") or ""
    line = record["line"]
    forms: list[tuple[str, str]] = []
    for candidate in (symbol.split(".")[-1], symbol):
        if candidate and all(candidate != existing for _, existing in forms):
            forms.append(("short" if candidate == symbol.split(".")[-1] else "qualified",
                          candidate))
    for candidate in scope_symbol_forms(tree_source, line):
        if all(candidate != existing for _, existing in forms):
            forms.append((f"enclosing-scope:{candidate}", candidate))
    if not symbol and all("" != existing for _, existing in forms):
        forms.append(("empty-symbol", ""))

    expressions: list[tuple[str, str]] = []
    row = m34.get(record["id"]) if m34 else None
    if row and row.get("pattern"):
        expressions.append(("m34-pattern", m34_norm(row["pattern"])))
    recorded = m34_norm(record.get("current_source_line") or "")
    if recorded:
        expressions.append(("recorded-line", recorded))
    for segment in ast_segment_forms(tree_source, line):
        if all(segment != existing for _, existing in expressions):
            expressions.append(("ast-segment", segment))
    if not expressions:
        return None
    for expression_form, expression in expressions:
        for form, candidate in forms:
            payload = "|".join([record["file"],
                                (row.get("kind") if row else None) or record.get("kind") or "",
                                candidate, expression, "0"])
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() == record["context_fingerprint"]:
                return (form, expression_form)
    return "MISMATCH"


def check(batch: list[dict]):
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int, str]] = []
    current_cache: dict[str, list[str]] = {}
    current_src: dict[str, str] = {}
    tree_src: dict[tuple[str, str], str] = {}
    maps: dict[tuple[str, str], dict[int, int]] = {}
    m34: dict[str, dict] = {}
    if LEDGER_AVAILABLE:
        ledger = json.loads((ROOT / FINGERPRINT_SOURCE).read_text(encoding="utf-8"))
        for row in list(ledger.get("carried_records", [])) + list(ledger.get("new_records", [])):
            m34[row["id"]] = row
    stats = {"fingerprints_checked": 0, "fingerprints_verified": 0,
             "fingerprints_without_evidence": [], "fingerprints_by_form": {},
             "fingerprints_by_expression_form": {},
             "fingerprints_not_reproduced_but_hash_anchored": [], "trees": {},
             "ledger_mode": "m34-ledger patterns used first" if LEDGER_AVAILABLE
             else "ledger-free: recorded-line + AST-segment expression forms (the 11 MB M34 "
                  "ledger is not tracked in the repository)"}

    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        declared = record.get("source_sha256") or ""
        tree_lines, tree_bytes, provenance = provenance_tree(path, declared)
        stats["trees"].setdefault(path, provenance)
        source_key = (path, declared)
        if source_key not in tree_src:
            tree_src[source_key] = tree_bytes.decode("utf-8", "replace")
        if path not in current_src:
            src = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            current_src[path] = src
            current_cache[path] = src.splitlines()
        lines = current_cache[path]
        current_is_tree = hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == declared
        start, end = record_scope(current_src[path], record.get("symbol", ""), line)
        fstart, fend = (start, end) if current_is_tree else \
            record_scope(tree_src[source_key], record.get("symbol", ""), line)

        proof = fingerprint_proof(record, m34, tree_src[source_key])
        if proof is None:
            stats["fingerprints_without_evidence"].append(record["id"])
        else:
            stats["fingerprints_checked"] += 1
            stats["fingerprints_verified"] += int(proof != "MISMATCH")
            if proof == "MISMATCH":
                form = "MISMATCH"
            else:
                form, expression_form = proof
                stats["fingerprints_by_expression_form"][expression_form] = \
                    stats["fingerprints_by_expression_form"].get(expression_form, 0) + 1
            stats["fingerprints_by_form"][form] = stats["fingerprints_by_form"].get(form, 0) + 1

        hash_anchored = 0 < line <= len(tree_lines) \
            and text_matches(expected, tree_lines[line - 1]) and fstart <= line <= fend
        if proof == "MISMATCH":
            if hash_anchored:
                stats["fingerprints_not_reproduced_but_hash_anchored"].append(record["id"])
            else:
                problems.append(f"{record['id']}: context_fingerprint does not reproduce and "
                                f"the record is not hash-anchored")
                continue
        if proof is None and not current_is_tree:
            problems.append(f"{record['id']}: no fingerprint evidence and the file is not the "
                            f"recorded tree - refusing to adjudicate by line number alone")
            continue

        if 0 < line <= len(lines) and text_matches(expected, lines[line - 1]) \
                and start <= line <= end:
            continue

        if not (0 < line <= len(tree_lines)) or not text_matches(expected, tree_lines[line - 1]):
            got = tree_lines[line - 1].strip() if 0 < line <= len(tree_lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {got[:60]!r} in the provenance "
                            f"tree, register recorded {expected[:60]!r}")
            continue

        map_key = (path, declared)
        if map_key not in maps:
            maps[map_key] = line_map(tree_lines, lines)
        new_line = maps[map_key].get(line)
        if new_line is None or not text_matches(expected, lines[new_line - 1]) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed "
                            f"(symbol {record.get('symbol')!r} spans {start}-{end})")
            continue
        reanchored.append((record["id"], path, line, new_line, provenance))

    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored, stats


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        print("missing:", sorted({r["id"] for r in batch} - set(R)))
        print("extra:", sorted(set(R) - {r["id"] for r in batch}))
        return 1

    reanchored, stats = check(batch)

    counts: dict[str, int] = {}
    for record in batch:
        counts[R[record["id"]][0]] = counts.get(R[record["id"]][0], 0) + 1
    classes: dict[str, int] = {}
    for record in batch:
        classes[record["p6_class"]] = classes.get(record["p6_class"], 0) + 1

    items = [{
        "id": record["id"], "file": record["file"], "line": record["line"],
        "symbol": record.get("symbol"), "rule": record.get("rule"), "kind": record.get("kind"),
        "register_line_text": record.get("current_source_line"),
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": None, "commit": None,
    } for record in batch]

    by_file: dict[str, int] = {}
    for item in items:
        by_file[item["file"]] = by_file.get(item["file"], 0) + 1

    rule_totals: dict[str, int] = {}
    for r in register["records"]:
        rule_totals[r["rule"]] = rule_totals.get(r["rule"], 0) + 1
    open_by_rule: dict[str, int] = {}
    for r in register["records"]:
        if r["classification"] == "OPEN":
            open_by_rule[r["rule"]] = open_by_rule.get(r["rule"], 0) + 1

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("phase-2 class C (engineering semantics): "
                  + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))
                  + " - drill-pipe vendor parsing, anti-collision screening, the API TR 5C3 "
                    "casing engine, fishing plain-return wrappers, MSE, the torque-drag "
                    "screening engine, extended engineering helpers, the EngineeringResult "
                    "contract module and the well-control kill-sheet canonical builder"),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "records_by_file": dict(sorted(by_file.items())),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "observations": OBSERVATIONS,
        "sibling_search": {
            "target": ("numeric parameter defaults that could substitute for unknowns, "
                       "numeric coalesce (`or 0.0`) at persistence/registration boundaries, "
                       "bare truthiness over validated values, `pass` bodies, broad "
                       "exception handlers, max(0.0, ...) reductions, container defaults "
                       "in the result envelope"),
            "method": ("every flagged construct read at its own site and traced "
                       "input -> validation -> engine -> EngineeringResult -> UI/AI/test; "
                       "populations recomputed from the register (rule_totals / "
                       "open_by_rule below); the six range-guard misfires share one "
                       "evidence shape (require_number above, domain check itself), the "
                       "four result-envelope defaults share one evidence shape, and the "
                       "fifteen kill-sheet coalesces share the missing_inputs gate "
                       "evidence anchored on the first record"),
            "counts": {
                "register_records_total": len(register["records"]),
                "rule_totals": rule_totals,
                "open_by_rule_before_this_batch": open_by_rule,
            },
            "findings": [
                {"site": "kill-sheet builder (15 records)",
                 "status": ("the `or 0.0` coalesces are provenance-preserving field "
                            "defaults behind the missing_inputs refuse-instead gate; "
                            "absent vs explicit-zero is pinned by "
                            "test_kill_sheet_casing_id_gate.py and the ff2000a fix is the "
                            "in-repo precedent for growing the gate when consumption "
                            "changes")},
                {"site": "torque-drag range guards (6 records)",
                 "status": ("all six are chained range checks over require_number output "
                            "one line above - rule mis-fires, closed as "
                            "DUPLICATE/FALSE-POSITIVE with the guard-shape evidence")},
                {"site": "result envelope (4 records)",
                 "status": ("container defaults implement the always-dict/always-list "
                            "shape of EngineeringResult; the numeric `value` field is "
                            "never defaulted")},
                {"site": "0-on-failure wrappers (3 records -> NEW-P6-004/005/006)",
                 "status": ("recorded with reachability (W13 stuck-pipe panel renders "
                            "their numeric return); fixing requires a legacy-contract "
                            "domain decision plus UI change, so they are recorded not "
                            "patched in an audit batch")},
                {"site": "scope semantics",
                 "status": ("none of the batch's nine files references SelectionManager or "
                            "any current_* selection state (grep: 0 hits) - the engineering "
                            "surface is a pure calculation boundary whose scope comes from "
                            "its arguments; no report/section/well scope leakage exists in "
                            "this population")},
            ],
        },
        "tests": ("no production code was changed in this batch, so no new regression was "
                  "written and no mutation validation applies; the evidence-cited suites "
                  "were executed (kill-sheet gate, casing absent-load semantics, "
                  "single-source guard, extended engineering, anti-collision, torque-drag "
                  "persistence, MSE, drill-pipe spec/import, engineering core/ground "
                  "truth) - see the batch ledger entry for the exact counts; the batch "
                  "script itself ran with the provenance and fingerprint gates active"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "tools/m36/p6_batch_020.py",
                           "core/engineering/drill_pipe.py",
                           "core/engineering/engines/anti_collision.py",
                           "core/engineering/engines/casing.py",
                           "core/engineering/engines/fishing.py",
                           "core/engineering/engines/mse.py",
                           "core/engineering/engines/torque_drag.py",
                           "core/engineering/extended.py",
                           "core/engineering/result.py",
                           "core/engineering/well_control_kill_sheet.py"],
        "staleness": {
            "checked": len(batch), "stale": len(reanchored), "re_anchored": len(reanchored),
            "method": ("every record's declared source_sha256 selects the tree its line "
                       "numbers belong to: 8 of the 9 files are byte-identical to the "
                       "current tree; the well_control_kill_sheet.py records (15) belong to "
                       "the tree at commit fd18a2b, whose blob sha256 was proven equal to "
                       "the declared source_sha256, and their lines were re-anchored into "
                       "the current tree with difflib (the file gained the casing-id gate "
                       "comment at ff2000a, a +5 shift inside the same function).  The "
                       "recorded text must match at the recorded line of its tree inside "
                       "the symbol's AST range; in addition every record's context "
                       "fingerprint was re-derived under the "
                       "path|kind|symbol|norm(expression)|ordinal contract."),
            "re_anchored_items": [
                {"id": i, "file": p, "register_line": a, "current_line": b, "tree": prov}
                for i, p, a, b, prov in reanchored],
            "provenance_trees": stats["trees"],
            "fingerprint_proof": {
                "checked": stats["fingerprints_checked"],
                "verified": stats["fingerprints_verified"],
                "records_without_a_reproducible_fingerprint": stats["fingerprints_without_evidence"],
                "records_without_a_reproducing_fingerprint_but_hash_anchored":
                    stats["fingerprints_not_reproduced_but_hash_anchored"],
                "symbol_forms_that_reproduced": stats["fingerprints_by_form"],
                "expression_forms_that_reproduced": stats["fingerprints_by_expression_form"],
                "method": stats["ledger_mode"]},
        },
        "method": ("all 45 records were read at their own sites in the hash-verified tree "
                   "(current, or fd18a2b for the kill sheet) and traced to consumers before "
                   "classification: the drill-pipe finite boundary and vendor-cell "
                   "resolution, the anti-collision/td adapter metadata handlers against "
                   "their benchmark contract, the API 5C3 collapse/fyax reductions against "
                   "their domain gates and ground-truth tests, the fishing wrappers and "
                   "their W13 renderers, the MSE refusal chain, the T&D validation/defaults "
                   "against the PARTIAL/SCREENING scope contract, the extended "
                   "physical-constant defaults against their callers, the result envelope "
                   "against its 46 return sites, and the kill-sheet builder against the "
                   "refuse-instead gate and its regression suite.  The deciding contract is "
                   "quoted in `evidence` for every record; no line of production code was "
                   "changed."),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, re-anchored "
          f"{len(reanchored)}, defects fixed {len(payload['defects_fixed'])}, fingerprints "
          f"{stats['fingerprints_verified']}/{stats['fingerprints_checked']}")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
