"""Calculator bridge: UI → canonical engines → EngineeringResult.

The Engineering Calculator tab is a presentation/input layer.
All engineering formulas live in core/engineering.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .result import EngineeringResult, missing
from .core import (
    TrajectoryEngine,
    BitEngine,
    BHAEngine,
    HydraulicsEngine,
)
from .engines.well_control import WellControlEngine
from .engines.casing import CasingEngine
from .engines.cement import CementEngine
from .engines.mse import MSEEngine
from .engines.mud_volume import MudVolumeEngine
from .engines.torque_drag import TorqueDragEngine
from .engines.bit_performance import BitPerformanceEngine


class CalculatorBridge:
    """Single façade used by tabs/w13_Engineering_Calculator.py and AI tools."""

    trajectory = TrajectoryEngine
    bit = BitEngine
    bha = BHAEngine
    hydraulics = HydraulicsEngine
    well_control = WellControlEngine
    casing = CasingEngine
    cement = CementEngine
    mse = MSEEngine
    mud_volume = MudVolumeEngine
    torque_drag = TorqueDragEngine
    bit_performance = BitPerformanceEngine

    @classmethod
    def kick_tolerance(cls, **kwargs) -> EngineeringResult:
        return WellControlEngine.kick_tolerance(**kwargs)

    @classmethod
    def trip_margin(cls, **kwargs) -> EngineeringResult:
        return WellControlEngine.trip_margin(**kwargs)

    @classmethod
    def kick_volume(cls, **kwargs) -> EngineeringResult:
        return WellControlEngine.kick_volume(**kwargs)

    @classmethod
    def casing_strength(cls, **kwargs) -> EngineeringResult:
        return CasingEngine.evaluate(**kwargs)

    @classmethod
    def cement_volumes(cls, **kwargs) -> EngineeringResult:
        return CementEngine.job_volumes(**kwargs)

    @classmethod
    def mse(cls, **kwargs) -> EngineeringResult:
        return MSEEngine.calculate(**kwargs)

    @classmethod
    def mud_balance(cls, **kwargs) -> EngineeringResult:
        return MudVolumeEngine.balance(**kwargs)

    @classmethod
    def min_curvature_pair(cls, md1, inc1, azi1, md2, inc2, azi2) -> EngineeringResult:
        from .result import ok, failed, MissingInputError, EngineeringError
        import math
        try:
            pts = TrajectoryEngine.calculate(
                [{"md": md1, "inc": inc1, "azi": azi1}, {"md": md2, "inc": inc2, "azi": azi2}]
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))
        except Exception as exc:
            return failed(str(exc))
        if len(pts) < 2:
            return missing("surveys")
        a, b = pts[0], pts[1]
        closure_azi = None
        if b.hd:
            closure_azi = round(math.degrees(math.atan2(b.east, b.north)) % 360, 3)
        d_md = b.md - a.md
        if d_md > 0 and b.dls:
            dl_rad = math.radians(b.dls * d_md / 30.0)
            rf = 1.0 if abs(dl_rad) < 1e-12 else (2.0 / dl_rad) * math.tan(dl_rad / 2.0)
        else:
            rf = 1.0
        values = {
            "delta_tvd": round(b.tvd - a.tvd, 6),
            "delta_north": round(b.north - a.north, 6),
            "delta_east": round(b.east - a.east, 6),
            "dls_deg_30m": round(b.dls, 6),
            "ratio_factor": round(rf, 6),
            "tvd": b.tvd,
            "north": b.north,
            "east": b.east,
            "vs": b.vs,
            "hd": b.hd,
            "closure_azimuth_deg": closure_azi,
        }
        return ok(values["delta_tvd"], values=values, unit="m", method="Minimum Curvature")
