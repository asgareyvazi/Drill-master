"""M115: every chart axis states its unit or is a reviewed categorical axis, and the W12 performance chart's axes
say what is plotted (D34).  Static audit of the axis-label calls in tabs/ and core/, plus the real W12 tab on a
SYNTHETIC temporary database (offscreen Qt; not a Windows desktop test).
"""
from __future__ import annotations

import ast
import os
import re
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
CALLS = {"set_xlabel", "set_ylabel", "set_zlabel", "setLabel"}
UNIT = re.compile(r"\([^()]*[^\s()][^()]*\)")
#: axes whose title is itself the unit, or a category / neutral placeholder (reviewed in M115)
UNITLESS = {
    "Hours": "the title is the unit", "Days": "the title is the unit", "Cumulative Days": "the title is the unit",
    "Rig Day": "the title is the unit", "Calendar day": "the title is the unit",
    "Section": "category", "Sections": "category", "Material": "category", "Bit Number": "category",
    "Cost line": "category",
    "Value": "neutral axis of the empty analytics chart, replaced by every analysis",
    "Parameter": "neutral axis of the empty analytics chart, replaced by every analysis",
}
#: labels computed at run time, each read and verified to carry its unit (M115 review)
DYNAMIC = {
    ("tabs/w10_Planning_Widget.py", "group_data['ylabel']"): "each group's ylabel names its units",
    ("tabs/w10_Planning_Widget.py", "label"): "the mud parameter map; checked below",
    ("tabs/w12_Analysis.py", "unit"): "the projection's unit from the caller",
    ("tabs/parameter_trend_panel.py", "self.result.axis_label"): "parameter_trends.AXIS_LABELS; checked below",
}


def _axis_labels():
    for base in ("tabs", "core"):
        for path in sorted((ROOT / base).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            constants = {t.id: [e.value for e in n.value.elts] for n in tree.body if isinstance(n, ast.Assign)
                         and isinstance(n.value, ast.Tuple)
                         and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in n.value.elts)
                         for t in n.targets if isinstance(t, ast.Name)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in CALLS:
                    args = node.args[1:] if node.func.attr == "setLabel" else node.args
                    if args:
                        yield path.relative_to(ROOT).as_posix(), node.lineno, args[0], constants


def _text(node, constants):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id in constants
            and isinstance(node.slice, ast.Constant)):              # a module-level tuple of labels
        return constants[node.value.id][node.slice.value]
    return None


def test_every_axis_states_its_unit_or_is_a_reviewed_category():
    missing, dynamic = [], set()
    for rel, line, node, constants in _axis_labels():
        text = _text(node, constants)
        if text is None:
            dynamic.add((rel, ast.unparse(node).replace('"', "'")))
        elif "(unit)" in text or not (UNIT.search(text) or text in UNITLESS):
            missing.append(f"{rel}:{line} {text!r}")
    assert missing == []
    assert dynamic == set(DYNAMIC)                                  # a new computed label must be reviewed


def test_the_trend_axis_labels_say_what_is_plotted():
    from core.parameter_trends import AXIS_LABELS     # M131: the computed bottom label of the trend panel

    assert AXIS_LABELS == {"time": "Report date (DDR)", "depth": "Depth out (m MD, DDR)"}


def test_the_mud_parameter_axis_labels_carry_their_units():
    tree = ast.parse((ROOT / "tabs/w10_Planning_Widget.py").read_text(encoding="utf-8"))
    maps = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "param_map" for t in n.targets) and isinstance(n.value, ast.Dict)]
    labels = [ast.literal_eval(v)[1] for m in maps for v in m.values if isinstance(v, ast.Tuple)]
    assert labels and all(UNIT.search(label) or label == "pH" for label in labels), labels   # pH is dimensionless
    assert "Gel 10s (lb/100ft²)" in labels and "Gel 10m (lb/100ft²)" in labels      # canonical schema: lb/100ft2


def test_d34_the_w12_performance_chart_axes_say_what_is_plotted(tmp_path, monkeypatch):
    from PySide6 import QtWidgets

    from core.database import DailyReport, DrillingParameters
    from tabs.w12_Analysis import AnalysisWidget
    from tests.test_m70_integrity import _open, _seed

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "m115-axes.sqlite", tmp_path, monkeypatch)
    well, _bore = _seed(manager)["A"]
    with manager.session_scope() as session:
        for number, day, rop in ((1, date(2026, 1, 2), 12.0), (2, date(2026, 1, 4), 18.0)):
            report = DailyReport(well_id=well, report_date=day, report_number=number)
            session.add(report)
            session.flush()
            session.add(DrillingParameters(well_id=well, report_id=report.id, report_date=day, bit_no="1",
                                           avg_rop=rop, wob_min=10.0, wob_max=20.0))
    tab = AnalysisWidget(db_manager=manager)
    try:
        tab.current_well_id, tab.current_well_name = well, "SYN-A"
        monkeypatch.setattr(tab, "_uses_revision_worker", lambda: False)   # the synchronous (in-memory) read path
        tab.update_performance_data()
        axis = tab.performance_plot.getPlotItem().getAxis
        assert tab.chart_data["performance"] and len(tab.chart_data["performance"]) == 2
        assert axis("left").labelText == "Percent of scope maximum (%)"
        assert axis("bottom").labelText == "Calendar day (day 1 = first dated record)"
        assert "normalised to its scope maximum" in tab.performance_plot.getPlotItem().titleLabel.text
    finally:
        tab.deleteLater()
        app.processEvents()
        manager.close()
