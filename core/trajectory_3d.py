"""3D scene of a composed trajectory (M45) - Qt-free and Matplotlib-free.

The 3D view adds NO engineering calculation.  It re-labels the stations that
``core.well_trajectory.compose_well_trajectory`` computed for the 2D plan and
vertical-section views (the same objects, the same display-unit conversion):

    x = East   (+ towards east)      relative to the tie-on station
    y = North  (+ towards true/grid north as stored by the survey engine)
    z = TVD    (+ downwards; the axis is drawn inverted so depth goes down)

so for every station the plan view shows (x, y) and the vertical section
shows (VS, z).  Units are those of the 2D views (``m`` or international
``ft``); no other scaling is applied.  ``axis_limits`` gives equal spans on
all three axes by default so angles are not distorted (a near-vertical well
looks near-vertical); unequal scaling is available only as an explicit
option.

A scene exists only for a drawable trajectory (>= 2 computed stations, status
READY or REVIEW_REQUIRED).  Excluded or invalid survey rows never become
points: they are not stations of the composed trajectory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.well_trajectory import to_display_units

AXIS_CONVENTION = "x = East, y = North (relative to the tie-on), z = TVD positive down"


@dataclass(frozen=True)
class Scene3D:
    status: str
    unit: str
    east: tuple = ()
    north: tuple = ()
    tvd: tuple = ()
    md: tuple = ()
    station_indices: tuple = ()          # index into WellTrajectory.stations for each point
    message: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def drawable(self) -> bool:
        return len(self.station_indices) >= 2

    def point(self, k: int) -> tuple:
        return self.east[k], self.north[k], self.tvd[k]


def scene_from_trajectory(trajectory, unit: str = "m") -> Scene3D:
    """Points of the composed stations in display units, in MD order."""
    if trajectory is None:
        return Scene3D("NO_DATA", unit, message="No well or survey selected.")
    if not trajectory.drawable:
        reasons = {"NO_DATA": "No survey stations are stored for this scope.",
                   "INSUFFICIENT_DATA": "At least two valid stations are needed to draw a path.",
                   "ERROR": "The trajectory could not be computed."}
        return Scene3D(trajectory.status, unit, message=reasons.get(trajectory.status, "Nothing to plot."))
    stations = list(trajectory.stations)
    order = sorted(range(len(stations)), key=lambda i: stations[i].md)
    if order != list(range(len(stations))):      # the composer returns MD order; never re-order silently
        raise ValueError("composed stations are not in measured-depth order")

    def convert(attribute):
        return tuple(to_display_units(getattr(stations[i], attribute), unit) for i in order)

    return Scene3D(trajectory.status, unit, east=convert("east"), north=convert("north"), tvd=convert("tvd"),
                   md=convert("md"), station_indices=tuple(order))


def axis_limits(scene: Scene3D, equal: bool = True, margin: float = 0.05):
    """((xmin, xmax), (ymin, ymax), (zmin, zmax)) for a drawable scene.

    ``equal`` - one common span for all axes (centred on each axis' data), so
    one unit has the same length on every axis.  A zero span (e.g. East and
    North of a vertical well) gets the common span, never a fake slope.
    """
    if not scene.drawable:
        raise ValueError("no drawable scene")
    columns = (scene.east, scene.north, scene.tvd)
    spans = [max(c) - min(c) for c in columns]
    centres = [(max(c) + min(c)) / 2.0 for c in columns]
    if equal:
        half = max(max(spans) / 2.0, 0.5) * (1.0 + margin)
        return tuple((centre - half, centre + half) for centre in centres)
    limits = []
    for centre, span in zip(centres, spans):
        half = max(span / 2.0, 0.5) * (1.0 + margin)
        limits.append((centre - half, centre + half))
    return tuple(limits)


def nearest_station(scene: Scene3D, projected, x: float, y: float, tolerance: float) -> Optional[int]:
    """Index (into the trajectory stations) of the projected point nearest to
    display position (x, y), or None if none is within ``tolerance`` pixels.
    ``projected`` is the list of display positions of the scene points."""
    best, best_distance = None, None
    for k, (px, py) in enumerate(projected):
        distance = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        if distance <= tolerance and (best_distance is None or distance < best_distance):
            best, best_distance = k, distance
    return None if best is None else scene.station_indices[best]
