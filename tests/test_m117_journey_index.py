"""M117: the user-journey index - all 26 journeys A-Z cite tests that walk them through real widgets; the level
of every citation is computed from the test source (tools/quality/journey_index.py), and the table in
docs/engineering/M117_USER_JOURNEYS.md is current.
"""
from __future__ import annotations

import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import journey_index as ji  # noqa: E402


def test_every_journey_a_to_z_is_walked_through_real_widgets():
    result = ji.evaluate(ROOT)
    assert list(result) == list(string.ascii_uppercase)
    not_widget = {k: e["citations"] for k, e in result.items() if e["level"] != "widget"}
    assert not_widget == {}


def test_the_journey_table_is_current():
    assert ji.main(["--check"]) == 0


def test_the_classifier_needs_a_real_widget(tmp_path):
    source = tmp_path / "test_probe.py"
    source.write_text(
        "import pytest\n"
        "from PySide6.QtWidgets import QApplication\n"
        "from core import calculation_history as ch\n"
        "CHILD = dedent('''\nfrom tabs.home_tab import HomeTab\n''')\n"
        "@pytest.fixture\n"
        "def app():\n    return QApplication.instance() or QApplication([])\n"
        "@pytest.fixture\n"
        "def tab(app):\n    from tabs.documents_tab import DocumentsTab\n    return DocumentsTab(None)\n"
        "def _helper():\n    from dialogs.x import Dialog\n    return Dialog\n"
        "def test_app_only(app):\n    assert ch\n"
        "def test_by_fixture(tab):\n    assert tab\n"
        "def test_by_helper():\n    assert _helper()\n"
        "def test_by_child_script():\n    assert CHILD\n"
        "def test_module_attribute():\n    from PySide6 import QtWidgets\n    assert QtWidgets.QLabel\n"
        "def test_module_application():\n    from PySide6 import QtWidgets\n    assert QtWidgets.QApplication\n",
        encoding="utf-8")
    level = {name: ji.classify(source, name) for name in (
        "test_app_only", "test_by_fixture", "test_by_helper", "test_by_child_script", "test_module_attribute",
        "test_module_application", "test_absent")}
    assert level == {"test_app_only": "service", "test_by_fixture": "widget", "test_by_helper": "widget",
                     "test_by_child_script": "widget", "test_module_attribute": "widget",
                     "test_module_application": "service", "test_absent": "missing"}
    assert ji.classify(tmp_path / "test_nowhere.py", "test_x") == "missing"


def test_a_missing_citation_fails_the_index(monkeypatch):
    monkeypatch.setitem(ji.JOURNEYS, "A", ("probe", ["tests/test_m117_journey_index.py::test_does_not_exist"]))
    assert ji.evaluate(ROOT)["A"]["level"] == "missing"
    assert ji.main([]) == 1
