"""Engineering Core - deterministic calculations + optional adapters."""

from .registry import capability_registry
from .core import (
    TrajectoryEngine,
    BitEngine,
    BHAEngine,
    HydraulicsEngine,
    WellControlEngine,
    OperationsIntelligenceEngine,
    MudLedgerEngine,
    ChemicalLedgerEntry,
    MissingInputError,
    UnsupportedCalculationError,
)
from .extended import (
    MudEngineering,
    HydraulicsExtended,
    WellControlExtended,
    CasingDesign,
    DirectionalExtended,
    CementingEngine,
    ROPModels,
)

__all__ = [
    "capability_registry",
    "TrajectoryEngine",
    "BitEngine",
    "BHAEngine",
    "HydraulicsEngine",
    "WellControlEngine",
    "OperationsIntelligenceEngine",
    "MudLedgerEngine",
    "ChemicalLedgerEntry",
    "MissingInputError",
    "UnsupportedCalculationError",
    "MudEngineering",
    "HydraulicsExtended",
    "WellControlExtended",
    "CasingDesign",
    "DirectionalExtended",
    "CementingEngine",
    "ROPModels",
]
