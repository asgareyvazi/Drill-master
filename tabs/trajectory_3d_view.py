"""Interactive 3D survey view (M45) - Matplotlib mplot3d inside Qt.

Renders a ``core.trajectory_3d.Scene3D`` (the composed stations the plan and
vertical-section views already show) as a 3D path with station markers.

* Rotate: left-drag.  Zoom: mouse wheel / the +/- buttons (only the axis
  limits change, never the data).  Preset view angles and a reset button.
* Clicking a station selects that real station (``station_picked`` emits the
  index into ``WellTrajectory.stations``); the viewer then updates the info
  panel, the table and the 2D highlights.
* Drawing goes through a single-shot timer owned by this widget and only
  while the canvas is visible (a hidden view draws when it is shown).
  Matplotlib's own ``draw_idle`` (called by its resize and mouse-rotation
  handlers) queues an unowned timer that can fire after the canvas was
  destroyed ("Internal C++ object already deleted"), so this canvas's
  ``draw_idle`` is routed to the owned timer as well.
* Interactive 3D needs the Qt Matplotlib canvas.  When only the static Agg
  fallback (or no Matplotlib) is available the tab says so and draws nothing:
  a static picture is never presented as an interactive 3D view.

Matplotlib (PSF-style Matplotlib licence) is already a locked core
dependency; mplot3d ships with it, so no dependency is added.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.trajectory_3d import AXIS_CONVENTION, Scene3D, axis_limits, nearest_station

logger = logging.getLogger(__name__)

# (label, elevation, azimuth) - Matplotlib's 3D camera angles in degrees.
VIEW_PRESETS = (
    ("Isometric", 25.0, -60.0),
    ("Top (plan, north up)", 90.0, -90.0),
    ("Looking north (East vs TVD)", 0.0, -90.0),
    ("Looking west (North vs TVD)", 0.0, 0.0),
)
PICK_TOLERANCE_PX = 8.0
CLICK_MOVE_PX = 4.0


def _load_canvas():
    """(canvas class, interactive?, reason).  Separate for tests."""
    try:
        from matplotlib.figure import Figure  # noqa: F401
        import mpl_toolkits.mplot3d  # noqa: F401  (registers the '3d' projection)
    except ImportError as exc:  # pragma: no cover  # silent-ok: reported in the tab as 'Matplotlib unavailable'
        return None, False, f"Matplotlib 3D is not available ({type(exc).__name__})."
    from core.matplotlib_widgets import select_figure_canvas
    canvas_class, interactive = select_figure_canvas()
    if canvas_class is None or not interactive:
        return None, False, "Interactive 3D needs the Qt Matplotlib canvas, which could not be loaded."
    return canvas_class, True, ""


class Trajectory3DView(QWidget):
    """3D path + stations; emits ``station_picked(index)`` on a station click."""

    station_picked = Signal(int)

    def __init__(self, parent=None, canvas_loader=_load_canvas):
        super().__init__(parent)
        self.scene: Optional[Scene3D] = None
        self.equal_scale = True
        self.highlighted: Optional[int] = None
        self._press = None
        self._zoom = 1.0
        self._dirty = False
        self._draw_timer = QTimer(self)                 # owned: destroyed with the view
        self._draw_timer.setSingleShot(True)
        self._draw_timer.setInterval(0)
        self._draw_timer.timeout.connect(self._draw_now)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        self.preset_combo = QComboBox()
        for label, elevation, azimuth in VIEW_PRESETS:
            self.preset_combo.addItem(label, (elevation, azimuth))
        self.reset_button = QPushButton("Reset view")
        self.zoom_in_button = QPushButton("Zoom +")
        self.zoom_out_button = QPushButton("Zoom −")
        self.stations_check = QCheckBox("Stations")
        self.stations_check.setChecked(True)
        controls.addWidget(QLabel("View:"))
        controls.addWidget(self.preset_combo)
        for widget in (self.reset_button, self.zoom_in_button, self.zoom_out_button, self.stations_check):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #4a5560;")
        layout.addWidget(self.hint)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("QLabel { color: #4a5560; padding: 8px; }")
        layout.addWidget(self.message)

        canvas_class, self.interactive, reason = canvas_loader()
        self.figure = self.axes = self.canvas = None
        if self.interactive:
            from matplotlib.figure import Figure
            self.figure = Figure(figsize=(6, 5), facecolor="white")
            self.canvas = canvas_class(self.figure)
            self.canvas.draw_idle = self._request_draw   # every redraw request uses the owned timer
            self.axes = self.figure.add_subplot(111, projection="3d")
            self.figure.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=1.0)
            layout.addWidget(self.canvas, 1)
            self.canvas.mpl_connect("button_press_event", self._mouse_press)
            self.canvas.mpl_connect("button_release_event", self._mouse_release)
            self.canvas.mpl_connect("scroll_event", self._scroll)
        else:
            self.unavailable_reason = reason
            layout.addStretch(1)
        for widget in (self.preset_combo, self.reset_button, self.zoom_in_button, self.zoom_out_button,
                       self.stations_check):
            widget.setEnabled(self.interactive)
        self.preset_combo.currentIndexChanged.connect(self.apply_preset)
        self.reset_button.clicked.connect(self.reset_view)
        self.zoom_in_button.clicked.connect(lambda: self.zoom(1.25))
        self.zoom_out_button.clicked.connect(lambda: self.zoom(0.8))
        self.stations_check.toggled.connect(self._redraw)
        self.clear("Select a well to view its trajectory.")

    # ---------------------------------------------------------------- state
    def clear(self, message: str = ""):
        self.scene, self.highlighted = None, None
        if not self.interactive:
            self.message.setText("3D view unavailable — " + self.unavailable_reason)
            self.hint.setText("")
            return
        self.axes.clear()
        self.axes.set_axis_off()
        self.message.setText(message or "Nothing to plot.")
        self.message.setVisible(True)
        self.hint.setText("")
        self._request_draw()

    def render(self, scene: Scene3D, equal_scale: bool = True):
        """Draw a scene; a non-drawable scene shows its reason and no path."""
        if not self.interactive:
            self.clear()
            return
        if scene is None or not scene.drawable:
            self.clear(scene.message if scene is not None else "")
            return
        self.scene, self.equal_scale, self.highlighted = scene, equal_scale, None
        self._zoom = 1.0
        self._redraw(keep_camera=False)

    def _redraw(self, *_args, keep_camera=True):
        if self.scene is None or not self.interactive:
            return
        ax, scene, unit = self.axes, self.scene, self.scene.unit
        elevation, azimuth = (ax.elev, ax.azim) if keep_camera else self.preset_combo.currentData()
        ax.clear()
        ax.set_axis_on()
        ax.set_proj_type("ortho")                         # no perspective distortion of lengths
        ax.plot(scene.east, scene.north, scene.tvd, color="#1f6fb2", linewidth=2, label="Composed path")
        if self.stations_check.isChecked():
            ax.scatter(scene.east, scene.north, scene.tvd, color="#1f6fb2", s=10, depthshade=False)
        ax.scatter([scene.east[0]], [scene.north[0]], [scene.tvd[0]], marker="s", s=40, color="#27ae60",
                   depthshade=False, label="Tie-on (first station)")
        ax.scatter([scene.east[-1]], [scene.north[-1]], [scene.tvd[-1]], marker="^", s=50, color="#c0392b",
                   depthshade=False, label="Last station")
        ax.set_xlabel(f"East ({unit})")
        ax.set_ylabel(f"North ({unit})")
        ax.set_zlabel(f"TVD ({unit}, down)")
        ax.legend(loc="upper left", fontsize=8)
        self._apply_limits()
        ax.view_init(elev=elevation, azim=azimuth)
        self.message.setVisible(False)
        scale = "equal scale on all axes" if self.equal_scale else "axes scaled independently (angles distorted)"
        self.hint.setText(f"{AXIS_CONVENTION}; units {unit}; {scale}. Drag to rotate, wheel or ± to zoom, "
                          "click a station to inspect it.")
        if self.highlighted is not None:
            self._draw_highlight(self.highlighted)
        self._request_draw()

    def _apply_limits(self):
        (x0, x1), (y0, y1), (z0, z1) = axis_limits(self.scene, equal=self.equal_scale)

        def shrink(lo, hi):
            centre, half = (lo + hi) / 2.0, (hi - lo) / 2.0 / self._zoom
            return centre - half, centre + half

        self.axes.set_xlim(*shrink(x0, x1))
        self.axes.set_ylim(*shrink(y0, y1))
        z0, z1 = shrink(z0, z1)
        self.axes.set_zlim(z1, z0)                        # inverted: TVD increases downwards
        self.axes.set_box_aspect((1.0, 1.0, 1.0))

    # -------------------------------------------------------------- drawing
    def _request_draw(self):
        if self.canvas is not None:
            self._dirty = True
            self._draw_timer.start()

    def _draw_now(self):
        if self.canvas is None or not self._dirty:
            return
        if not self.canvas.isVisible():                  # drawn by showEvent instead
            return
        self._dirty = False
        self.canvas.draw()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._draw_timer.start()

    # --------------------------------------------------------------- camera
    def camera(self) -> tuple:
        return (self.axes.elev, self.axes.azim) if self.interactive else (None, None)

    def apply_preset(self, *_args):
        if self.interactive and self.scene is not None:
            elevation, azimuth = self.preset_combo.currentData()
            self.axes.view_init(elev=elevation, azim=azimuth)
            self._request_draw()

    def reset_view(self):
        if not self.interactive or self.scene is None:
            return
        self._zoom = 1.0
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentIndex(0)
        self.preset_combo.blockSignals(False)
        self._redraw(keep_camera=False)

    def zoom(self, factor: float):
        if not self.interactive or self.scene is None:
            return
        self._zoom = min(max(self._zoom * factor, 0.2), 20.0)
        self._apply_limits()
        self._request_draw()

    def _scroll(self, event):
        self.zoom(1.25 if event.button == "up" else 0.8)

    # -------------------------------------------------------------- picking
    def projected_points(self) -> list:
        """Display (pixel) positions of the scene points for the current camera."""
        if self.scene is None or not self.interactive:
            return []
        from mpl_toolkits.mplot3d import proj3d
        self.canvas.draw()                               # make sure the projection matrix is current
        xs, ys, _zs = proj3d.proj_transform(list(self.scene.east), list(self.scene.north), list(self.scene.tvd),
                                            self.axes.get_proj())
        return [tuple(p) for p in self.axes.transData.transform(list(zip(xs, ys)))]

    def pick_at(self, x: float, y: float) -> Optional[int]:
        """Select the station nearest to display position (x, y), if any."""
        if self.scene is None:
            return None
        index = nearest_station(self.scene, self.projected_points(), x, y, PICK_TOLERANCE_PX)
        if index is not None:
            self.station_picked.emit(index)
        return index

    def _mouse_press(self, event):
        self._press = (event.x, event.y) if event.button == 1 else None

    def _mouse_release(self, event):
        if self._press is None or event.button != 1 or event.x is None:
            return
        moved = ((event.x - self._press[0]) ** 2 + (event.y - self._press[1]) ** 2) ** 0.5
        self._press = None
        if moved <= CLICK_MOVE_PX:                       # a click, not a rotation drag
            self.pick_at(event.x, event.y)

    def highlight(self, index: Optional[int]):
        """Mark the selected station (index into the trajectory stations)."""
        if not self.interactive or self.scene is None or index is None or index not in self.scene.station_indices:
            return
        self.highlighted = index
        self._draw_highlight(index)
        self._request_draw()

    def _draw_highlight(self, index):
        for artist in list(self.axes.collections) + list(self.axes.texts):
            if getattr(artist, "_m45_highlight", False):
                artist.remove()
        k = self.scene.station_indices.index(index)
        x, y, z = self.scene.point(k)
        marker = self.axes.scatter([x], [y], [z], s=120, facecolors="none", edgecolors="#e67e22", linewidths=2.5,
                                   depthshade=False)
        marker._m45_highlight = True
        label = self.axes.text(x, y, z, f"  MD {self.scene.md[k]:,.1f} {self.scene.unit}", color="#a04000",
                               fontsize=8)
        label._m45_highlight = True

    def highlighted_point(self) -> Optional[tuple]:
        """Data coordinates of the highlight marker actually drawn (for tests)."""
        for artist in self.axes.collections if self.interactive else ():
            if getattr(artist, "_m45_highlight", False):
                xs, ys, zs = artist._offsets3d
                return float(xs[0]), float(ys[0]), float(zs[0])
        return None
