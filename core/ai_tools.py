"""
AI Tools Interface - AI calls deterministic engineering engines

Architecture:
AI should NOT be the engineering calculator.
Use AI for:
- understanding user intent
- interpreting Excel ambiguity
- mapping unknown labels
- explaining results
- identifying missing information
- suggesting engineering actions
- generating reports
- reasoning over validated numerical results

Use deterministic engines for:
- formulas
- numerical calculations
- unit conversion
- engineering validation
- limits
- consistency checks

Implement AI tool/function interface so that AI can call engineering functions.

Example:
AI → identify required calculation → call Engineering Engine → receive numerical result → validate result → AI explains/interprets result
Never allow LLM to invent engineering formulas when deterministic calculation exists.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class AIToolRegistry:
    """Registry of tools that AI can call."""

    def __init__(self, db_manager=None):
        self.db = db_manager
        self._tools = {
            "calculate_trajectory": {
                "description": "Calculate well trajectory using Minimum Curvature Method",
                "required_inputs": ["surveys: list of {md, inc, azi}"],
                "optional_inputs": ["vs_azimuth", "dls_unit"],
                "engine": "TrajectoryEngine",
                "contract": "TrajectoryEngine requires monotonic MD, detects duplicate/non-monotonic",
            },
            "calculate_tfa": {
                "description": "Calculate Total Flow Area from bit nozzles",
                "required_inputs": ["nozzles: list of 32nds"],
                "engine": "BitEngine",
            },
            "calculate_annular_velocity": {
                "description": "Calculate annular velocity in ft/min",
                "required_inputs": ["flow_rate_gpm", "hole_id_in", "pipe_od_in"],
                "formula": "AV = 24.51 * Q / (Dh^2 - Dp^2)",
                "engine": "HydraulicsEngine",
            },
            "calculate_ecd": {
                "description": "Calculate Equivalent Circulating Density",
                "required_inputs": ["mw_ppg", "annular_pressure_loss_psi", "tvd_ft"],
                "formula": "ECD = MW + APL / (0.052 * TVD)",
                "engine": "HydraulicsEngine",
            },
            "calculate_kill_mw": {
                "description": "Calculate kill mud weight from SIDPP",
                "required_inputs": ["original_mw_ppg", "sidpp_psi", "tvd_ft"],
                "formula": "Kill MW = Original MW + SIDPP / (0.052 * TVD)",
                "engine": "WellControlEngine",
            },
            "calculate_maasp": {
                "description": "Calculate Maximum Allowable Annular Surface Pressure",
                "required_inputs": ["max_allowable_mw_ppg", "current_mw_ppg", "shoe_tvd_ft"],
                "engine": "WellControlEngine",
            },
            "analyze_rop_degradation": {
                "description": "Analyze ROP degradation with evidence",
                "required_inputs": ["rop_values: list of ROP"],
                "evidence": "Source Reports, Date Range, Metrics, Confidence, Reason",
                "engine": "OperationsIntelligenceEngine",
            },
            "validate_time_logs": {
                "description": "Validate 24h time logs: overlap, gap, total 24h, midnight crossing, duplicate",
                "required_inputs": ["time_logs: list of {time_from, time_to, duration}"],
                "engine": "TimeLogValidator",
            },
            "convert_unit": {
                "description": "Convert units with preservation of original and normalized",
                "required_inputs": ["value", "quantity", "from_unit", "to_unit"],
                "example": "1.50 SG → 12.52 ppg, preserved as Original: 1.50 SG, Normalized: 12.52, Canonical: ppg",
                "engine": "UnitManager",
            },
            "check_mud_ledger": {
                "description": "Check mud chemical ledger: Opening, Received, Used, Returned, Adjusted, Closing",
                "required_inputs": ["well_id"],
                "formula": "Closing = Opening + Received + Adjusted - Used - Returned, Opening(day+1)=Closing(day)",
                "alerts": "Negative Stock, Low Stock, Unusual Consumption, No Movement, Duplicate Material, Unit Mismatch",
                "engine": "MudChemicalLedger",
            },
            "calculate_bha": {
                "description": "Calculate BHA cumulative length and weight",
                "required_inputs": ["components: list of {component, od, id, length, weight}"],
                "engine": "BHAEngine",
            },
            "calculate_anti_collision": {
                "description": "Calculate anti-collision clearance between wells",
                "required_inputs": ["reference_trajectory", "offset_trajectory"],
                "engine": "AntiCollisionEngine",
                "note": "Full ISCWSA requires welleng package after benchmark",
            },
            "calculate_torque_drag": {
                "description": "Johancsik soft-string SCREENING torque and drag",
                "required_inputs": ["survey", "bha", "mud_density_ppg", "friction_factor"],
                "engine": "TorqueDragEngine",
                "note": "PARTIAL / SCREENING MODEL — not production-certified. welleng is benchmark-only.",
            },
            "calculate_kick_tolerance": {
                "description": "IWCF kick tolerance (volume). Influx gradient is required — no silent default.",
                "required_inputs": ["mw_ppg", "shoe_tvd_ft", "current_tvd_ft", "frac_mw_ppg or lot_pressure_psi", "influx_gradient_psi_ft or influx_emw_ppg"],
                "optional_inputs": ["annular_capacity_bbl_ft", "bha_annular_capacity_bbl_ft", "bha_length_ft", "formation_emw_ppg"],
                "engine": "WellControlEngine",
            },
            "calculate_trip_margin": {
                "description": "Trip margin = MW − pore EMW (ppg and psi)",
                "required_inputs": ["mw_ppg", "formation_emw_ppg or (formation_pressure_psi and tvd_ft)"],
                "engine": "WellControlEngine",
            },
            "calculate_mse": {
                "description": "Teale Mechanical Specific Energy (120π oilfield units)",
                "required_inputs": ["wob_lbf", "rpm", "torque_ft_lbf", "rop_ft_hr", "bit_diameter_in"],
                "engine": "MSEEngine",
            },
            "calculate_casing_strength": {
                "description": "PARTIAL API 5C3 subset: Barlow burst 0.875, four-regime collapse, pipe-body tensile",
                "required_inputs": ["od_in", "yield_psi", "wall_in or id_in"],
                "engine": "CasingEngine",
                "note": "Not full API TR 5C3 (no triaxial, connections, temperature).",
            },
            "calculate_cement_volumes": {
                "description": "PARTIAL cement job-volume calculator (not a cement design engine)",
                "required_inputs": ["hole_size_in", "casing_od_in", "open_hole_length_ft", "excess_pct"],
                "engine": "CementEngine",
            },
            "calculate_mud_balance": {
                "description": "Mud volume balance",
                "required_inputs": ["active_volume_bbl"],
                "engine": "MudVolumeEngine",
            },
            "calculate_kick_volume": {
                "description": "Kick height/volume from pit gain and annular capacity",
                "required_inputs": ["pit_gain_bbl", "annular_capacity_bbl_ft"],
                "engine": "WellControlEngine",
            },
        }

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def get_tool(self, name: str) -> Optional[Dict]:
        return self._tools.get(name)

    def call_tool(self, name: str, **kwargs) -> Dict[str, Any]:
        """AI calls engineering function through this interface.

        Returns result with validation, never invented.
        If missing input: returns MISSING_INPUT error.
        If unsupported: returns UNSUPPORTED_CALCULATION.
        """
        tool = self.get_tool(name)
        if not tool:
            return {"success": False, "error": f"UNSUPPORTED_CALCULATION: tool {name} not found", "available_tools": self.list_tools()}

        try:
            if name == "calculate_trajectory":
                from core.engineering.core import TrajectoryEngine
                surveys = kwargs.get("surveys")
                if not surveys:
                    return {"success": False, "error": "MISSING_INPUT: surveys required"}
                vs_azi = kwargs.get("vs_azimuth", 0.0)
                dls_unit = kwargs.get("dls_unit", "deg/30m")
                points = TrajectoryEngine.calculate(surveys, vs_azimuth=vs_azi, dls_unit=dls_unit)
                return {
                    "success": True,
                    "values": [p.__dict__ for p in points],
                    "unit": "m, deg",
                    "assumptions": ["Minimum Curvature Method", "VS azimuth 0 default"],
                    "engine": "TrajectoryEngine",
                }

            elif name == "calculate_tfa":
                from core.engineering.core import BitEngine
                nozzles = kwargs.get("nozzles")
                if not nozzles:
                    return {"success": False, "error": "MISSING_INPUT: nozzles required"}
                tfa = BitEngine.calculate_tfa(nozzles)
                return {"success": True, "value": tfa, "unit": "in²", "engine": "BitEngine"}

            elif name == "calculate_annular_velocity":
                from core.engineering.core import HydraulicsEngine
                q = kwargs.get("flow_rate_gpm")
                dh = kwargs.get("hole_id_in")
                dp = kwargs.get("pipe_od_in")
                if q is None or dh is None or dp is None:
                    return {"success": False, "error": "MISSING_INPUT: flow_rate_gpm, hole_id_in, pipe_od_in required"}
                av = HydraulicsEngine.calculate_annular_velocity(q, dh, dp)
                return {"success": True, "value": av, "unit": "ft/min", "formula": "24.51*Q/(Dh^2-Dp^2)", "engine": "HydraulicsEngine"}

            elif name == "calculate_ecd":
                from core.engineering.core import HydraulicsEngine
                mw = kwargs.get("mw_ppg")
                apl = kwargs.get("annular_pressure_loss_psi")
                tvd = kwargs.get("tvd_ft")
                if mw is None or apl is None or tvd is None:
                    return {"success": False, "error": "MISSING_INPUT: mw_ppg, annular_pressure_loss_psi, tvd_ft required"}
                ecd = HydraulicsEngine.calculate_ecd(mw, apl, tvd)
                return {"success": True, "value": ecd, "unit": "ppg", "formula": "MW + APL/(0.052*TVD)", "engine": "HydraulicsEngine"}

            elif name == "calculate_kill_mw":
                from core.engineering.core import WellControlEngine
                orig = kwargs.get("original_mw_ppg")
                sidpp = kwargs.get("sidpp_psi")
                tvd = kwargs.get("tvd_ft")
                if orig is None or sidpp is None or tvd is None:
                    return {"success": False, "error": "MISSING_INPUT: original_mw_ppg, sidpp_psi, tvd_ft required"}
                kill = WellControlEngine.calculate_kill_mw(orig, sidpp, tvd)
                return {"success": True, "value": kill, "unit": "ppg", "formula": "Original MW + SIDPP/(0.052*TVD)", "engine": "WellControlEngine"}

            elif name == "calculate_maasp":
                from core.engineering.core import WellControlEngine
                max_mw = kwargs.get("max_allowable_mw_ppg")
                curr_mw = kwargs.get("current_mw_ppg")
                shoe_tvd = kwargs.get("shoe_tvd_ft")
                if curr_mw is None or shoe_tvd is None:
                    return {"success": False, "error": "MISSING_INPUT: current_mw_ppg, shoe_tvd_ft required"}
                maasp = WellControlEngine.calculate_maasp(max_mw, curr_mw, shoe_tvd, kwargs.get("leak_off_psi"))
                return {"success": True, "value": maasp, "unit": "psi", "engine": "WellControlEngine"}

            elif name == "validate_time_logs":
                from core.import_quality import TimeLogValidator
                logs = kwargs.get("time_logs")
                if not logs:
                    return {"success": False, "error": "MISSING_INPUT: time_logs required"}
                report = TimeLogValidator.validate_logs(logs)
                return {
                    "success": report.failed == 0 and len(report.errors) == 0,
                    "total": report.total,
                    "failed": report.failed,
                    "errors": [e.__dict__ for e in report.errors],
                    "warnings": [w.__dict__ for w in report.warnings],
                    "engine": "TimeLogValidator",
                }

            elif name == "convert_unit":
                from core.unit_manager import UnitManager
                val = kwargs.get("value")
                qty = kwargs.get("quantity")
                from_u = kwargs.get("from_unit")
                to_u = kwargs.get("to_unit")
                if val is None or qty is None or from_u is None or to_u is None:
                    return {"success": False, "error": "MISSING_INPUT: value, quantity, from_unit, to_unit required"}
                try:
                    converted = UnitManager.convert(val, qty, from_u, to_u)
                    record = UnitManager.create_record("ai_tool.convert", qty, from_u, val, to_u)
                    return {
                        "success": True,
                        "original": record.original_value,
                        "normalized": record.normalized_value,
                        "source_unit": record.source_unit,
                        "canonical_unit": record.canonical_unit,
                        "conversion_rule": record.conversion_rule,
                        "engine": "UnitManager",
                    }
                except ValueError as ve:
                    return {"success": False, "error": f"UNSUPPORTED_CALCULATION: {ve}"}

            elif name == "check_mud_ledger":
                from core.mud_ledger import MudChemicalLedger
                well_id = kwargs.get("well_id")
                if not well_id:
                    return {"success": False, "error": "MISSING_INPUT: well_id required"}
                ledger = MudChemicalLedger(self.db)
                entries = ledger.get_ledger_for_well(well_id)
                alerts = ledger.validate(entries)
                history = ledger.get_history(well_id)
                return {
                    "success": True,
                    "entries": [e.to_dict() for e in entries[:20]],
                    "alerts": alerts,
                    "history": history,
                    "engine": "MudChemicalLedger",
                }

            elif name == "calculate_bha":
                from core.engineering.core import BHAEngine
                comps = kwargs.get("components")
                if not comps:
                    return {"success": False, "error": "MISSING_INPUT: components required"}
                total_len, total_wt, enriched = BHAEngine.calculate_cumulative(comps)
                return {
                    "success": True,
                    "total_length": total_len,
                    "total_weight": total_wt,
                    "components": enriched,
                    "unit": "m, klbf",
                    "engine": "BHAEngine",
                }

            elif name == "analyze_rop_degradation":
                from core.engineering.core import OperationsIntelligenceEngine
                rops = kwargs.get("rop_values")
                if not rops:
                    return {"success": False, "error": "MISSING_INPUT: rop_values required"}
                insight = OperationsIntelligenceEngine.analyze_rop_trend(rops)
                return {"success": True, "insight": insight, "engine": "OperationsIntelligenceEngine"}

            elif name == "calculate_anti_collision":
                from core.engineering.engines.anti_collision import AntiCollisionEngine
                ref = kwargs.get("reference_trajectory")
                off = kwargs.get("offset_trajectory")
                if not ref or not off:
                    return {"success": False, "error": "MISSING_INPUT: reference_trajectory and offset_trajectory required"}
                result = AntiCollisionEngine.calculate_clearance(ref, off)
                return {"success": True, **result, "engine": "AntiCollisionEngine"}

            elif name == "calculate_torque_drag":
                from core.engineering.bridge import CalculatorBridge
                survey = kwargs.get("survey")
                bha = kwargs.get("bha")
                mud = kwargs.get("mud_density_ppg", kwargs.get("mud_density"))
                ff = kwargs.get("friction_factor")
                if not survey or not bha:
                    return {"success": False, "error": "MISSING_INPUT: survey and bha required"}
                result = CalculatorBridge.torque_drag.calculate(survey, bha, mud, ff)
                out = result.as_dict()
                out["engine"] = "TorqueDragEngine"
                return out

            elif name == "calculate_kick_tolerance":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.kick_tolerance(**kwargs)
                d = out.as_dict()
                d["engine"] = "WellControlEngine"
                return d

            elif name == "calculate_trip_margin":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.trip_margin(**kwargs)
                d = out.as_dict()
                d["engine"] = "WellControlEngine"
                return d

            elif name == "calculate_mse":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.mse(**kwargs)
                d = out.as_dict()
                d["engine"] = "MSEEngine"
                return d

            elif name == "calculate_casing_strength":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.casing_strength(**kwargs)
                d = out.as_dict()
                d["engine"] = "CasingEngine"
                return d

            elif name == "calculate_cement_volumes":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.cement_volumes(**kwargs)
                d = out.as_dict()
                d["engine"] = "CementEngine"
                return d

            elif name == "calculate_mud_balance":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.mud_balance(**kwargs)
                d = out.as_dict()
                d["engine"] = "MudVolumeEngine"
                return d

            elif name == "calculate_kick_volume":
                from core.engineering.bridge import CalculatorBridge
                out = CalculatorBridge.kick_volume(**kwargs)
                d = out.as_dict()
                d["engine"] = "WellControlEngine"
                return d

            else:
                return {"success": False, "error": f"UNSUPPORTED_CALCULATION: {name} not implemented yet"}

        except Exception as exc:
            logger.error(f"AI tool {name} failed: {exc}", exc_info=True)
            return {"success": False, "error": str(exc), "tool": name}


# Global registry for AI
ai_tool_registry = AIToolRegistry()
