"""Capability registry: optional packages never prevent application startup."""
from dataclasses import dataclass
import importlib.util


@dataclass(frozen=True)
class Capability:
    name: str
    package: str
    installed: bool
    purpose: str


class CapabilityRegistry:
    def __init__(self):
        self._items = (
            Capability("Trajectory / anti-collision", "welleng", self._installed("welleng"), "survey planning, error models and clearance"),
            Capability("Torque & drag", "torque_drag", self._installed("torque_drag"), "axial load and torque along the string"),
            Capability("Drilling optimization", "gekko", self._installed("gekko"), "optional ROP and scenario optimization"),
            Capability("PDF tables", "camelot", self._installed("camelot"), "text PDF table extraction"),
            Capability("PDF OCR tables", "pytesseract", self._installed("pytesseract"), "scanned PDF OCR fallback"),
        )

    @staticmethod
    def _installed(package):
        return importlib.util.find_spec(package) is not None

    def all(self):
        return list(self._items)

    def missing(self):
        return [item for item in self._items if not item.installed]

    def as_dict(self):
        return [item.__dict__.copy() for item in self._items]


capability_registry = CapabilityRegistry()
