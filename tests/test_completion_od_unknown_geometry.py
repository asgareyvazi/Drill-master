"""Real Qt rendering must not turn missing completion OD into a size claim."""
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_unknown_od_completions_render_as_labeled_non_scale_symbols():
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
    except ImportError as exc:  # pragma: no cover - host Qt runtime dependent
        pytest.skip(f"Qt runtime unavailable: {exc}")
    repo_root = str(Path(__file__).resolve().parent.parent)
    script = r'''
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPainter, QPixmap
from core.wellbore_schematic_engine import (
    CompletionItem, ElementType, SchematicConfig,
    WellboreSchematic, WellboreSchematicRenderer,
)
from tabs.w3b_wellbore_schematic_tab import CompletionItemDialog

QApplication([])
dialog = CompletionItemDialog(ElementType.PACKER, 1000)
assert dialog.od_spin.value() == 0
assert dialog.od_spin.specialValueText() == "Not recorded"
dialog._on_ok()
assert dialog.get_item().od_inch == 0
items = [
    CompletionItem(ElementType.PACKER, 100, od_inch=0),
    CompletionItem(ElementType.PERFORATIONS, 200, od_inch=None),
    CompletionItem(ElementType.BRIDGE_PLUG, 300, od_inch=float("nan")),
    CompletionItem(ElementType.SAND_SCREEN, 400, od_inch=-1),
]
schematic = WellboreSchematic(
    well_name="Test", total_depth_m=1000, completion=items,
    show_tubing=False, show_wellhead=False, show_xmas_tree=False,
)
config = SchematicConfig(
    show_formations=False, show_grid=False, show_depth_scale=False,
    show_legend=False, show_cement=False, show_labels=True,
)
renderer = WellboreSchematicRenderer(schematic, config)
recorded = []
original = renderer._draw_unknown_od_marker
def record(painter, item):
    recorded.append(item.element_type)
    original(painter, item)
renderer._draw_unknown_od_marker = record
pixmap = QPixmap(config.total_width, config.total_height)
pixmap.fill(QColor("#000000"))
painter = QPainter(pixmap)
try:
    renderer.render(painter)
finally:
    painter.end()
assert recorded == [item.element_type for item in items]
assert not pixmap.isNull()

# Known, valid dimensions still use the engineering-scale drawing paths.
known = WellboreSchematic(
    total_depth_m=1000,
    completion=[CompletionItem(kind, depth, od_inch=4.5)
                for kind, depth in zip(
                    (ElementType.PACKER, ElementType.PERFORATIONS,
                     ElementType.BRIDGE_PLUG, ElementType.SAND_SCREEN),
                    (100, 200, 300, 400))],
    show_tubing=False, show_wellhead=False, show_xmas_tree=False,
)
known_renderer = WellboreSchematicRenderer(known, config)
known_markers = []
known_renderer._draw_unknown_od_marker = lambda _painter, item: known_markers.append(item)
known_pixmap = QPixmap(config.total_width, config.total_height)
known_pixmap.fill(QColor("#000000"))
known_painter = QPainter(known_pixmap)
try:
    known_renderer.render(known_painter)
finally:
    known_painter.end()
assert known_markers == []
print("UNKNOWN_OD_RENDER_OK")
'''
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc = subprocess.run(
        [sys.executable, "-c", script, repo_root],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert proc.returncode == 0, f"renderer subprocess failed:\n{proc.stderr[-3000:]}"
    assert "UNKNOWN_OD_RENDER_OK" in proc.stdout
