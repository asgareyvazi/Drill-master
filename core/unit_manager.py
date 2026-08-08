"""Central unit conversion used by import, UI and reports."""
from dataclasses import dataclass


@dataclass(frozen=True)
class UnitDefinition:
    quantity: str
    unit: str
    to_base: float
    offset: float = 0.0


_UNITS = {
    "length": {"m": (1.0, 0.0), "ft": (0.3048, 0.0), "in": (0.0254, 0.0)},
    "pressure": {"psi": (1.0, 0.0), "bar": (14.5037738, 0.0), "kpa": (0.145037738, 0.0)},
    "flow": {"gpm": (1.0, 0.0), "lpm": (0.264172052, 0.0)},
    "volume": {"bbl": (1.0, 0.0), "m3": (6.28981077, 0.0)},
    "temperature": {"c": (1.0, 0.0), "f": (5 / 9, -32 * 5 / 9)},
    "density": {"ppg": (1.0, 0.0), "sg": (8.34540445, 0.0), "kg_m3": (0.00834540445, 0.0)},
    "torque": {"ft_lbf": (1.0, 0.0), "kn_m": (737.562149, 0.0)},
}


class UnitManager:
    @staticmethod
    def normalize(unit):
        return str(unit or "").strip().lower().replace("°", "")

    @classmethod
    def convert(cls, value, quantity, from_unit, to_unit):
        if value is None:
            return None
        quantity = cls.normalize(quantity)
        from_unit, to_unit = cls.normalize(from_unit), cls.normalize(to_unit)
        if from_unit == to_unit:
            return float(value)
        units = _UNITS.get(quantity)
        if not units or from_unit not in units or to_unit not in units:
            raise ValueError(f"Unsupported conversion: {quantity} {from_unit}->{to_unit}")
        factor, offset = units[from_unit]
        base = float(value) * factor + offset
        target_factor, target_offset = units[to_unit]
        return (base - target_offset) / target_factor

    @classmethod
    def normalize_row(cls, row, unit_map):
        """Return a copy converted to canonical units.

        unit_map: {field: (quantity, source_unit, canonical_unit)}
        """
        result = dict(row or {})
        for field, spec in (unit_map or {}).items():
            if field not in result or result[field] in (None, ""):
                continue
            quantity, source, target = spec
            result[field] = cls.convert(result[field], quantity, source, target)
        return result
