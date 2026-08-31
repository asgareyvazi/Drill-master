"""Engineering Core - deterministic calculations + optional adapters.

ONE ENGINE → ONE FORMULA → ONE RESULT

UI and AI tools must call these engines. They must not re-implement formulas.
"""

from .registry import capability_registry
from .result import (
    EngineeringResult,
    EngineeringError,
    MissingInputError,
    UnsupportedCalculationError,
)
from .core import (
    TrajectoryEngine,
    TrajectoryPoint,
    BitEngine,
    BHAEngine,
    HydraulicsEngine,
    WellControlEngine,
    OperationsIntelligenceEngine,
    MudLedgerEngine,
    ChemicalLedgerEntry,
    CalculationResult,
)
from .engines.casing import CasingEngine
from .engines.cement import CementEngine
from .engines.mse import MSEEngine
from .engines.mud_volume import MudVolumeEngine
from .engines.torque_drag import TorqueDragEngine
from .engines.bit_performance import BitPerformanceEngine
from .bridge import CalculatorBridge

__all__ = [
    "capability_registry",
    "EngineeringResult",
    "EngineeringError",
    "MissingInputError",
    "UnsupportedCalculationError",
    "TrajectoryEngine",
    "TrajectoryPoint",
    "BitEngine",
    "BHAEngine",
    "HydraulicsEngine",
    "WellControlEngine",
    "OperationsIntelligenceEngine",
    "MudLedgerEngine",
    "ChemicalLedgerEntry",
    "CalculationResult",
    "CasingEngine",
    "CementEngine",
    "MSEEngine",
    "MudVolumeEngine",
    "TorqueDragEngine",
    "BitPerformanceEngine",
    "CalculatorBridge",
]
