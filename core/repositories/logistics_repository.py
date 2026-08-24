"""Logistics, Equipment, Bulk, Fuel repositories."""

from .base import BaseRepository
from core.database import BulkMaterials, FuelWaterInventory, EquipmentLog, ServiceCompanyPOB, TransportLog
from typing import List, Dict
from core.engineering.core import MudLedgerEngine, ChemicalLedgerEntry
import logging

logger = logging.getLogger(__name__)


class BulkRepository(BaseRepository):
    def validate_ledger(self, entries: List[Dict]) -> List[str]:
        ledger_entries = []
        for e in entries:
            ledger_entries.append(
                ChemicalLedgerEntry(
                    product=e.get("material_name", ""),
                    opening_stock=float(e.get("initial_stock", 0) or 0),
                    received=float(e.get("received", 0) or 0),
                    used=float(e.get("used", 0) or 0),
                    returned=float(e.get("returned", 0) or 0),
                    adjusted=float(e.get("adjusted", 0) or 0),
                    unit=e.get("unit", ""),
                )
            )
        return MudLedgerEngine.validate_ledger(ledger_entries)


class EquipmentRepository(BaseRepository):
    pass


class LogisticsRepository(BaseRepository):
    pass


class FuelRepository(BaseRepository):
    pass
