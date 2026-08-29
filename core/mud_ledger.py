"""
Mud Chemical Ledger - Professional Inventory Management

P0/P1 Requirements:
- Ledger: Opening Stock, Received, Used, Returned, Adjusted, Closing Stock
- Formula: Closing = Opening + Received + Adjusted - Used - Returned
- Next day: Opening(day+1) = Closing(day)
- Alerts: Negative Stock, Low Stock, Unusual Consumption, No Movement, Duplicate Material, Unit Mismatch
- History: Daily Usage Chart, Stock Trend, Consumption Rate, Days Remaining, Received vs Used
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    date: date
    material_name: str
    opening_stock: float = 0.0
    received: float = 0.0
    used: float = 0.0
    returned: float = 0.0
    adjusted: float = 0.0
    unit: str = "kg"
    well_id: Optional[int] = None
    report_id: Optional[int] = None

    @property
    def closing_stock(self) -> float:
        return self.opening_stock + self.received + self.adjusted - self.used - self.returned

    def to_dict(self):
        return {
            "date": self.date,
            "material_name": self.material_name,
            "opening_stock": self.opening_stock,
            "received": self.received,
            "used": self.used,
            "returned": self.returned,
            "adjusted": self.adjusted,
            "closing_stock": self.closing_stock,
            "unit": self.unit,
            "well_id": self.well_id,
            "report_id": self.report_id,
        }


class MudChemicalLedger:
    """Professional ledger with day-to-day continuity."""

    def __init__(self, db_manager):
        self.db = db_manager

    def get_ledger_for_well(self, well_id: int, material_name: str = None) -> List[LedgerEntry]:
        """Get ledger entries for a well, with opening calculated from previous closing."""
        from core.database import BulkMaterials

        with self.db.session_scope() as session:
            query = session.query(BulkMaterials).filter(BulkMaterials.well_id == well_id).order_by(BulkMaterials.report_date)
            if material_name:
                query = query.filter(BulkMaterials.material_name == material_name)
            rows = query.all()

            entries = []
            last_closing_by_material: Dict[str, float] = {}

            for r in rows:
                mat = r.material_name
                # Opening should be previous closing if not explicitly stored
                opening = r.initial_stock
                if mat in last_closing_by_material and opening == 0:
                    # If opening is 0 but previous closing exists, use it (carry_forward)
                    # But only if no received/used - indicates missing opening
                    if r.received == 0 and r.used == 0:
                        opening = last_closing_by_material[mat]

                entry = LedgerEntry(
                    date=r.report_date,
                    material_name=mat,
                    opening_stock=float(opening or 0),
                    received=float(r.received or 0),
                    used=float(r.used or 0),
                    returned=0.0,  # Not yet in BulkMaterials model, future
                    adjusted=0.0,
                    unit=r.unit or "kg",
                    well_id=r.well_id,
                    report_id=r.report_id,
                )
                entries.append(entry)
                last_closing_by_material[mat] = entry.closing_stock

            return entries

    def validate(self, entries: List[LedgerEntry]) -> List[Dict]:
        """Generate alerts as per spec."""
        alerts = []
        material_totals: Dict[str, List[LedgerEntry]] = {}

        for e in entries:
            material_totals.setdefault(e.material_name, []).append(e)

        for material, mats in material_totals.items():
            mats_sorted = sorted(mats, key=lambda x: x.date)

            # Check duplicate material same date
            seen_dates = set()
            for entry in mats_sorted:
                if entry.date in seen_dates:
                    alerts.append(
                        {
                            "level": "warning",
                            "material": material,
                            "date": entry.date,
                            "message": f"Duplicate Material: {material} on {entry.date}",
                            "type": "Duplicate Material",
                        }
                    )
                seen_dates.add(entry.date)

            for entry in mats_sorted:
                closing = entry.closing_stock

                # Negative Stock
                if closing < 0:
                    alerts.append(
                        {
                            "level": "error",
                            "material": material,
                            "date": entry.date,
                            "message": f"Negative Stock: {material} closing {closing:.2f} {entry.unit} on {entry.date}",
                            "type": "Negative Stock",
                            "value": closing,
                        }
                    )

                # Low Stock (e.g. <10% of opening)
                if entry.opening_stock > 0 and closing < entry.opening_stock * 0.1 and closing > 0:
                    alerts.append(
                        {
                            "level": "warning",
                            "material": material,
                            "date": entry.date,
                            "message": f"Low Stock: {material} {closing:.2f} {entry.unit} (<10% of opening)",
                            "type": "Low Stock",
                            "value": closing,
                        }
                    )

                # Unusual Consumption (used > 2 * opening)
                if entry.opening_stock > 0 and entry.used > entry.opening_stock * 2:
                    alerts.append(
                        {
                            "level": "warning",
                            "material": material,
                            "date": entry.date,
                            "message": f"Unusual Consumption: {material} used {entry.used:.2f} vs opening {entry.opening_stock:.2f} on {entry.date}",
                            "type": "Unusual Consumption",
                            "value": entry.used,
                        }
                    )

                # No Movement
                if entry.opening_stock > 0 and entry.received == 0 and entry.used == 0 and entry.returned == 0 and entry.adjusted == 0:
                    alerts.append(
                        {
                            "level": "info",
                            "material": material,
                            "date": entry.date,
                            "message": f"No Movement: {material} stock {entry.opening_stock:.2f} {entry.unit} with no usage on {entry.date}",
                            "type": "No Movement",
                        }
                    )

        return alerts

    def get_history(self, well_id: int) -> Dict[str, Dict]:
        """History per material: Daily Usage Chart, Stock Trend, Consumption Rate, Days Remaining, Received vs Used."""
        entries = self.get_ledger_for_well(well_id)
        history: Dict[str, List[LedgerEntry]] = {}
        for e in entries:
            history.setdefault(e.material_name, []).append(e)

        result = {}
        for material, mats in history.items():
            mats_sorted = sorted(mats, key=lambda x: x.date)
            usages = [float(m.used or 0) for m in mats_sorted]
            stocks = [float(m.closing_stock) for m in mats_sorted]
            received = [float(m.received or 0) for m in mats_sorted]
            dates = [m.date.isoformat() if hasattr(m.date, "isoformat") else str(m.date) for m in mats_sorted]

            avg_consumption = sum(usages) / len(usages) if usages else 0
            last_stock = stocks[-1] if stocks else 0
            days_remaining = last_stock / avg_consumption if avg_consumption > 0 else 0

            result[material] = {
                "dates": dates,
                "daily_usage_chart": usages,
                "stock_trend": stocks,
                "received_trend": received,
                "consumption_rate": round(avg_consumption, 2),
                "days_remaining": round(days_remaining, 2),
                "received_vs_used": {
                    "total_received": round(sum(received), 2),
                    "total_used": round(sum(usages), 2),
                },
                "opening_stock": mats_sorted[0].opening_stock if mats_sorted else 0,
                "closing_stock": last_stock,
                "unit": mats_sorted[0].unit if mats_sorted else "kg",
            }

        return result

    def check_continuity(self, well_id: int) -> List[Dict]:
        """Check Opening(day+1) = Closing(day) continuity."""
        entries = self.get_ledger_for_well(well_id)
        history: Dict[str, List[LedgerEntry]] = {}
        for e in entries:
            history.setdefault(e.material_name, []).append(e)

        issues = []
        for material, mats in history.items():
            mats_sorted = sorted(mats, key=lambda x: x.date)
            for i in range(1, len(mats_sorted)):
                prev = mats_sorted[i - 1]
                curr = mats_sorted[i]
                expected_opening = prev.closing_stock
                if abs(curr.opening_stock - expected_opening) > 0.01 and curr.opening_stock != 0:
                    issues.append(
                        {
                            "material": material,
                            "date": curr.date,
                            "message": f"Continuity break: {material} opening {curr.opening_stock:.2f} != previous closing {expected_opening:.2f} on {curr.date}",
                            "expected": expected_opening,
                            "actual": curr.opening_stock,
                        }
                    )
        return issues
