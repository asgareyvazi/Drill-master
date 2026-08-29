"""Central unit conversion used by import, UI and reports.

Professional Unit Management:
- Every field has metadata: Field, Quantity, Source Unit, Canonical Unit, Original Value, Normalized Value, Conversion Rule
- Supports: Length, Diameter, Depth, Pressure, Flow Rate, Volume, Density, Temperature, Torque, Force, Weight, ROP, RPM, Viscosity, Yield Point, ECD, DLS, Azimuth, Inclination, etc.
- Preserves Original + Normalized + Canonical Unit (no silent fake defaults)
- Example: 1.50 SG → Original: 1.50 SG, Normalized: 12.52, Canonical: ppg
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Tuple
import math


@dataclass(frozen=True)
class UnitDefinition:
    quantity: str
    unit: str
    to_base: float
    offset: float = 0.0
    description: str = ""


@dataclass
class UnitRecord:
    """Complete unit preservation record for one field value."""
    field: str
    quantity: str
    source_unit: str
    canonical_unit: str
    original_value: Any
    normalized_value: Optional[float]
    conversion_rule: str
    confidence: float = 1.0

    def as_dict(self):
        return asdict(self)


# Base unit for each quantity is the canonical internal unit
# to_base: multiplier to convert FROM unit TO base (canonical)
# offset: additive offset before scaling (for temperature)
# For most: base = value * to_base + offset
# To target: (base - target_offset) / target_factor

_UNITS: Dict[str, Dict[str, Tuple[float, float]]] = {
    # Length / Depth / Diameter - base: m
    "length": {
        "m": (1.0, 0.0),
        "meter": (1.0, 0.0),
        "meters": (1.0, 0.0),
        "ft": (0.3048, 0.0),
        "feet": (0.3048, 0.0),
        "in": (0.0254, 0.0),
        "inch": (0.0254, 0.0),
        "inches": (0.0254, 0.0),
        "cm": (0.01, 0.0),
        "mm": (0.001, 0.0),
        "km": (1000.0, 0.0),
    },
    "depth": {
        "m": (1.0, 0.0),
        "ft": (0.3048, 0.0),
        "in": (0.0254, 0.0),
    },
    "diameter": {
        "m": (1.0, 0.0),
        "in": (0.0254, 0.0),
        "ft": (0.3048, 0.0),
        "mm": (0.001, 0.0),
    },
    # Pressure - base: psi
    "pressure": {
        "psi": (1.0, 0.0),
        "bar": (14.5037738, 0.0),
        "kpa": (0.145037738, 0.0),
        "kPa": (0.145037738, 0.0),
        "mpa": (145.037738, 0.0),
        "atm": (14.6959488, 0.0),
        "psf": (0.00694444, 0.0),
    },
    # Flow Rate - base: gpm
    "flow_rate": {
        "gpm": (1.0, 0.0),
        "gal/min": (1.0, 0.0),
        "lpm": (0.264172052, 0.0),
        "l/min": (0.264172052, 0.0),
        "bbl/min": (42.0, 0.0),
        "m3/min": (264.172052, 0.0),
        "m3/hr": (4.40286753, 0.0),
        "l/s": (15.8503231, 0.0),
    },
    "flow": {  # backward compat alias
        "gpm": (1.0, 0.0),
        "lpm": (0.264172052, 0.0),
    },
    # Volume - base: bbl
    "volume": {
        "bbl": (1.0, 0.0),
        "m3": (6.28981077, 0.0),
        "gal": (0.0238095, 0.0),
        "l": (0.00628981, 0.0),
        "liter": (0.00628981, 0.0),
        "ft3": (0.178107606, 0.0),
        "m3": (6.28981077, 0.0),
    },
    # Density / MW - base: ppg
    "density": {
        "ppg": (1.0, 0.0),
        "sg": (8.34540445, 0.0),
        "g/cm3": (8.34540445, 0.0),
        "kg/m3": (0.00834540445, 0.0),
        "kg_m3": (0.00834540445, 0.0),
        "pcf": (0.133680556, 0.0),
        "lb/ft3": (0.133680556, 0.0),
        "lb/gal": (1.0, 0.0),
    },
    # Temperature - base: C (special handling with offset)
    "temperature": {
        "c": (1.0, 0.0),
        "°c": (1.0, 0.0),
        "degc": (1.0, 0.0),
        "f": (5 / 9, -32 * 5 / 9),
        "°f": (5 / 9, -32 * 5 / 9),
        "degf": (5 / 9, -32 * 5 / 9),
        "k": (1.0, -273.15),
    },
    # Torque - base: ft_lbf
    "torque": {
        "ft_lbf": (1.0, 0.0),
        "ft-lbf": (1.0, 0.0),
        "lbf_ft": (1.0, 0.0),
        "kn_m": (737.562149, 0.0),
        "kn-m": (737.562149, 0.0),
        "nm": (0.737562149, 0.0),
        "n_m": (0.737562149, 0.0),
        "klbf_ft": (1000.0, 0.0),
    },
    # Force / Weight / WOB - base: klbf (1000 lbf)
    "force": {
        "klbf": (1.0, 0.0),
        "lbf": (0.001, 0.0),
        "kn": (0.224808943, 0.0),
        "n": (0.000224808943, 0.0),
        "kgf": (0.00220462, 0.0),
        "ton": (2.20462, 0.0),
        "lb": (0.001, 0.0),
        "klb": (1.0, 0.0),
    },
    "weight": {
        "klbf": (1.0, 0.0),
        "kg": (0.00220462, 0.0),
        "lb": (0.001, 0.0),
        "ton": (2.20462, 0.0),
        "ppf": (0.001, 0.0),  # lb/ft as weight per foot - keep numeric
    },
    # ROP - base: m/hr
    "rop": {
        "m/hr": (1.0, 0.0),
        "m/h": (1.0, 0.0),
        "ft/hr": (0.3048, 0.0),
        "ft/h": (0.3048, 0.0),
        "m/min": (60.0, 0.0),
        "ft/min": (18.288, 0.0),
    },
    "rate": {  # backward compat
        "m/hr": (1.0, 0.0),
        "ft/hr": (0.3048, 0.0),
    },
    # RPM - base: rpm (no conversion, just canonical)
    "rpm": {
        "rpm": (1.0, 0.0),
        "1/min": (1.0, 0.0),
        "rev/min": (1.0, 0.0),
    },
    # Viscosity - base: cp
    "viscosity": {
        "cp": (1.0, 0.0),
        "cP": (1.0, 0.0),
        "pa_s": (1000.0, 0.0),
        "pas": (1000.0, 0.0),
        "sec": (1.0, 0.0),  # funnel vis - keep as is, no conversion
    },
    # Yield Point / Stress - base: lb/100ft2
    "yield_point": {
        "lb/100ft2": (1.0, 0.0),
        "lb/100ft²": (1.0, 0.0),
        "pa": (0.0208854, 0.0),
        "lb/ft2": (1.0, 0.0),
    },
    "stress": {
        "lb/100ft2": (1.0, 0.0),
        "pa": (0.0208854, 0.0),
    },
    # ECD - base: ppg (same as density)
    "ecd": {
        "ppg": (1.0, 0.0),
        "sg": (8.34540445, 0.0),
        "pcf": (0.133680556, 0.0),
    },
    # DLS - base: deg/100ft (or deg/30m) - keep numeric, conversion via factor
    "dls": {
        "deg/100ft": (1.0, 0.0),
        "deg/30m": (0.98425197, 0.0),  # approx
        "deg/10m": (3.048, 0.0),
        "deg/m": (30.48, 0.0),
        "deg/ft": (0.01, 0.0),
    },
    # Angle - base: deg
    "angle": {
        "deg": (1.0, 0.0),
        "degree": (1.0, 0.0),
        "rad": (57.2957795, 0.0),
        "radian": (57.2957795, 0.0),
    },
    "azimuth": {
        "deg": (1.0, 0.0),
        "rad": (57.2957795, 0.0),
    },
    "inclination": {
        "deg": (1.0, 0.0),
        "rad": (57.2957795, 0.0),
    },
    # Generic text/number
    "text": {"": (1.0, 0.0)},
    "integer": {"": (1.0, 0.0)},
    "number": {"": (1.0, 0.0)},
    "code": {"": (1.0, 0.0)},
    "date": {"": (1.0, 0.0)},
    "currency": {"": (1.0, 0.0)},
    "volume_generic": {"": (1.0, 0.0)},
}

# Canonical units for each quantity (internal storage)
CANONICAL_UNITS = {
    "length": "m",
    "depth": "m",
    "diameter": "in",
    "pressure": "psi",
    "flow_rate": "gpm",
    "flow": "gpm",
    "volume": "bbl",
    "density": "ppg",
    "temperature": "C",
    "torque": "ft_lbf",
    "force": "klbf",
    "weight": "klbf",
    "rop": "m/hr",
    "rate": "m/hr",
    "rpm": "rpm",
    "viscosity": "cp",
    "yield_point": "lb/100ft2",
    "stress": "lb/100ft2",
    "ecd": "ppg",
    "dls": "deg/100ft",
    "angle": "deg",
    "azimuth": "deg",
    "inclination": "deg",
    "text": "",
    "integer": "",
    "number": "",
    "code": "",
    "date": "",
    "currency": "",
    "volume_generic": "",
}


class UnitManager:
    """Professional unit manager with preservation of original values."""

    @staticmethod
    def normalize(unit: str) -> str:
        """Normalize unit string for lookup."""
        if unit is None:
            return ""
        # Lowercase, strip, remove degree symbols, normalize separators
        u = str(unit).strip().lower()
        u = u.replace("°", "").replace("º", "")
        u = u.replace(" ", "").replace("_", "")
        # Common aliases normalization
        u = u.replace("ppg", "ppg").replace("lb/gal", "ppg")
        return u

    @classmethod
    def _lookup_units(cls, quantity: str):
        q = cls.normalize(quantity)
        # Try exact, then aliases
        if q in _UNITS:
            return _UNITS[q], q
        # Alias mapping for quantity names
        alias_map = {
            "md": "depth",
            "tvd": "depth",
            "measureddepth": "depth",
            "bitdepth": "depth",
            "currentdepth": "depth",
            "holedepth": "depth",
            "wob": "force",
            "weightonbit": "force",
            "bitload": "force",
            "torque": "torque",
            "rpm": "rpm",
            "rop": "rop",
            "rateofpenetration": "rop",
            "flowrate": "flow_rate",
            "pumpoutput": "flow_rate",
            "mudweight": "density",
            "mw": "density",
            "ecd": "ecd",
            "dls": "dls",
            "dogleg": "dls",
            "buildrate": "dls",
            "turnrate": "dls",
            "inclination": "inclination",
            "azimuth": "azimuth",
            "viscosity": "viscosity",
            "pv": "viscosity",
            "yieldpoint": "yield_point",
            "yp": "yield_point",
        }
        mapped = alias_map.get(q)
        if mapped and mapped in _UNITS:
            return _UNITS[mapped], mapped
        return None, q

    @classmethod
    def convert(cls, value, quantity, from_unit, to_unit):
        """Convert value from one unit to another within same quantity.

        Returns None if value is None.
        Raises ValueError if conversion not supported.
        Never returns fake defaults - preserves None.
        """
        if value is None or value == "":
            return None
        try:
            quantity_norm = cls.normalize(quantity)
            from_norm = cls.normalize(from_unit)
            to_norm = cls.normalize(to_unit)

            if from_norm == to_norm:
                return float(value)

            units, _ = cls._lookup_units(quantity_norm)
            if not units:
                raise ValueError(f"Unsupported quantity: {quantity}")

            # Handle empty unit (no conversion)
            if from_norm == "" and to_norm == "":
                return float(value)

            # For empty from/to, try to find original
            if from_norm not in units:
                # Try to find with original case-insensitive search
                for k in units.keys():
                    if cls.normalize(k) == from_norm:
                        from_norm = cls.normalize(k)
                        break
                else:
                    raise ValueError(f"Unsupported from_unit: {from_unit} for {quantity}")

            if to_norm not in units:
                for k in units.keys():
                    if cls.normalize(k) == to_norm:
                        to_norm = cls.normalize(k)
                        break
                else:
                    raise ValueError(f"Unsupported to_unit: {to_unit} for {quantity}")

            factor_from, offset_from = units[from_norm]
            base = float(value) * factor_from + offset_from
            factor_to, offset_to = units[to_norm]
            return (base - offset_to) / factor_to

        except (TypeError, ValueError) as exc:
            # Do not invent - propagate as unsupported
            raise ValueError(f"Unit conversion failed: {quantity} {from_unit}->{to_unit}: {exc}") from exc

    @classmethod
    def normalize_row(cls, row, unit_map):
        """Return a copy converted to canonical units.

        unit_map: {field: (quantity, source_unit, canonical_unit)}
        Preserves None - no fake defaults.
        """
        result = dict(row or {})
        for field, spec in (unit_map or {}).items():
            if field not in result or result[field] in (None, ""):
                continue
            try:
                quantity, source, target = spec
                converted = cls.convert(result[field], quantity, source, target)
                if converted is not None:
                    result[field] = converted
            except ValueError:
                # Keep original if conversion fails, will be flagged in validation
                continue
        return result

    @classmethod
    def create_record(cls, field: str, quantity: str, source_unit: str, original_value: Any, target_unit: Optional[str] = None) -> UnitRecord:
        """Create a full preservation record: Original + Normalized + Canonical.

        Example:
            1.50 SG → UnitRecord(field="mud_report.mw", quantity="density", source="sg", canonical="ppg", original=1.5, normalized=12.52, rule="sg->ppg *8.3454")

        Never invents missing values - if original is None, normalized is None.
        """
        quantity_norm = cls.normalize(quantity) or "text"
        canonical = CANONICAL_UNITS.get(quantity_norm, target_unit or source_unit or "")
        target = target_unit or canonical

        if original_value in (None, ""):
            return UnitRecord(
                field=field,
                quantity=quantity_norm,
                source_unit=source_unit or "",
                canonical_unit=canonical or "",
                original_value=original_value,
                normalized_value=None,
                conversion_rule=f"{source_unit}->{canonical} (missing original)",
                confidence=0.0,
            )

        try:
            normalized = cls.convert(original_value, quantity_norm, source_unit, target)
            rule = f"{source_unit}->{target} factor"
            # Build descriptive rule for common conversions
            if quantity_norm == "density" and cls.normalize(source_unit) == "sg" and cls.normalize(target) == "ppg":
                rule = f"{original_value} SG * 8.3454 = {normalized:.2f} ppg"
            elif quantity_norm in ("length", "depth") and cls.normalize(source_unit) == "ft" and cls.normalize(target) == "m":
                rule = f"{original_value} ft * 0.3048 = {normalized:.4f} m"
            elif quantity_norm == "pressure" and cls.normalize(source_unit) == "bar" and cls.normalize(target) == "psi":
                rule = f"{original_value} bar * 14.5038 = {normalized:.2f} psi"
            return UnitRecord(
                field=field,
                quantity=quantity_norm,
                source_unit=source_unit or "",
                canonical_unit=target or "",
                original_value=original_value,
                normalized_value=normalized,
                conversion_rule=rule,
                confidence=1.0,
            )
        except ValueError as exc:
            return UnitRecord(
                field=field,
                quantity=quantity_norm,
                source_unit=source_unit or "",
                canonical_unit=target or "",
                original_value=original_value,
                normalized_value=None,
                conversion_rule=f"FAILED: {exc}",
                confidence=0.0,
            )

    @classmethod
    def detect_unit(cls, text_value: str) -> Tuple[Optional[float], str]:
        """Detect unit from a string like '1.50 SG' or '12.5 ppg' or '3500 m'.

        Returns (numeric_value, unit) or (None, "") if not detected.
        """
        if not text_value or not isinstance(text_value, str):
            return None, ""
        import re
        # Pattern: number + optional space + unit
        # Supports: 1.50 SG, 12.5 ppg, 3500m, 100 ft, 2000 psi, 150 gpm
        match = re.match(r"^\s*([+-]?[\d,]*\.?\d+(?:[eE][+-]?\d+)?)\s*([a-zA-Z/%°²³0-9\-_\.]+)?\s*$", text_value.strip())
        if match:
            num_str = match.group(1).replace(",", "")
            unit = (match.group(2) or "").strip()
            try:
                val = float(num_str)
                return val, unit
            except ValueError:
                return None, ""
        return None, ""

    @classmethod
    def canonical_for(cls, quantity: str) -> str:
        """Get canonical unit for a quantity."""
        return CANONICAL_UNITS.get(cls.normalize(quantity), "")

    @classmethod
    def all_quantities(cls):
        return list(_UNITS.keys())

    @classmethod
    def units_for(cls, quantity: str):
        units, _ = cls._lookup_units(quantity)
        return list(units.keys()) if units else []
