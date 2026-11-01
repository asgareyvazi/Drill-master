"""M56 calculator finder: search, favourites and recents over the real W13 tab tree.

Offscreen Qt on Linux. Settings use an in-memory store (no QSettings files are
written). This is not Windows desktop testing.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QGroupBox, QTabWidget, QVBoxLayout, QWidget  # noqa: E402

from tabs.calculator_finder import CalculatorFinder, _DictStore, build_index, clean_title  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _page(*groups):
    page = QWidget()
    layout = QVBoxLayout(page)
    for title in groups:
        layout.addWidget(QGroupBox(title))
    return page


@pytest.fixture
def tree(app):
    tabs = QTabWidget()
    tabs.addTab(_page("Pipe capacity"), "📊 Volume")
    hydraulics = QWidget()
    inner = QTabWidget(hydraulics)
    QVBoxLayout(hydraulics).addWidget(inner)
    inner.addTab(_page("ECD at bit"), "🌀 Annular")
    inner.addTab(_page("Jet velocity"), "🔵 Bit Hydraulics")
    tabs.addTab(hydraulics, "💧 Hydraulics")
    tabs.addTab(_page("Kill mud weight"), "🛡️ Well Control")
    yield tabs
    tabs.deleteLater()


def test_titles_lose_their_pictograms_but_keep_words():
    assert clean_title("⬆️⬇️ Weight/Dilution/Mix") == "Weight/Dilution/Mix"
    assert clean_title("🛢️ CSG/CMT") == "CSG/CMT"
    assert clean_title("📈 Pore Press & FG") == "Pore Press  FG"      # Qt mnemonic '&' is dropped


def test_the_index_follows_the_live_tab_tree_with_group_keywords(tree):
    paths = {entry.path: entry for entry in build_index(tree)}
    assert list(paths) == ["Volume", "Hydraulics", "Hydraulics › Annular", "Hydraulics › Bit Hydraulics",
                           "Well Control"]
    assert paths["Hydraulics › Annular"].keywords == ["ECD at bit"]
    assert paths["Hydraulics"].keywords == []          # nested pages' groups belong to the nested entry


def test_search_matches_titles_and_group_keywords_with_all_terms(tree):
    finder = CalculatorFinder(tree, store=_DictStore())
    assert finder.search("ecd") == ["Hydraulics › Annular"]
    assert finder.search("bit") == ["Hydraulics › Annular", "Hydraulics › Bit Hydraulics"]
    assert finder.search("bit jet") == ["Hydraulics › Bit Hydraulics"]
    assert finder.search("torque") == [] and finder.status_label.text() == "No calculator matches that search."
    assert finder.search("") == [] and finder.status_label.text() == "5 calculators and pages indexed."


def test_opening_a_result_navigates_and_records_a_bounded_recent_list(tree):
    store = _DictStore()
    finder = CalculatorFinder(tree, store=store)
    finder.search_edit.setText("jet")
    assert finder.open_first_result()
    assert tree.currentIndex() == 1 and tree.widget(1).findChild(QTabWidget).currentIndex() == 1
    assert finder.current_path() == "Hydraulics › Bit Hydraulics"
    finder.open_path("Volume")
    finder.open_path("Hydraulics › Bit Hydraulics")
    assert store.data["recents"] == ["Hydraulics › Bit Hydraulics", "Volume"]
    for title in [f"Extra {n}" for n in range(10)]:        # more distinct calculators than the bound
        tree.addTab(_page(), title)
    finder.reindex()
    assert len(finder.entries) == 15
    for entry in finder.entries:
        finder.open_path(entry.path)
    assert store.data["recents"] == [e.path for e in reversed(finder.entries)][:8]   # newest first, bounded
    assert not finder.open_path("Retired calculator") and "no longer available" in finder.status_label.text()


def test_favourites_toggle_on_the_open_page_and_survive_a_restart(tree):
    store = _DictStore({"favorites": ["Removed calculator"], "recents": "Volume"})
    finder = CalculatorFinder(tree, store=store)
    assert finder.favorites() == [] and finder.recents() == ["Volume"]        # stale paths are ignored
    finder.open_path("Well Control")
    assert finder.toggle_current_favorite() is True and finder.favorite_btn.text() == "★ Favourite"
    finder.open_path("Volume")
    assert finder.favorite_btn.text() == "☆ Favourite"
    restarted = CalculatorFinder(tree, store=store)
    assert restarted.favorites() == ["Well Control"] and restarted.favorites_list.count() == 1
    restarted.open_path("Well Control")
    assert restarted.toggle_current_favorite() is False and restarted.favorites() == []


def test_the_engineering_calculator_tab_offers_the_finder(app):
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    tab = EngineeringCalculatorTab(None)
    try:
        finder = tab.calculator_finder
        finder.store = _DictStore()
        hits = finder.search("kill sheet")
        assert hits == ["Well Control › Kill Sheet"]
        assert finder.open_path(hits[0]) and tab.tabs.tabText(tab.tabs.currentIndex()).endswith("Well Control")
        assert finder.search("casing strength") == ["CSG/CMT › Casing Strength"]
        assert finder.layoutDirection().name == "LeftToRight"
    finally:
        tab.deleteLater()
        app.processEvents()
