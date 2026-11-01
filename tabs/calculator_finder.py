"""M56: find, favourite and reopen engineering calculators in W13.

The index is built from the live tab tree (top-level tabs, nested tabs and the
group-box titles inside each page), so it can never list a calculator that does
not exist.  Favourites and recents are stored as stable title paths in
``QSettings`` (an injectable mapping in tests); unknown stored paths are ignored.
No calculation is performed here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, MutableMapping, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

FINDER_VERSION = "M56 calculator finder v1"
MAX_RECENTS = 8
SEPARATOR = " › "
_LEADING_SYMBOLS = re.compile(r"^[^0-9A-Za-z\u0600-\u06FF(]+")


def clean_title(text: str) -> str:
    """Tab title without its leading pictogram (emoji and variation selectors)."""
    return _LEADING_SYMBOLS.sub("", (text or "").replace("&", "")).strip()


@dataclass
class CalculatorEntry:
    path: str                                   # "Hydraulics › Bit Hydraulics"
    steps: List[tuple]                          # [(QTabWidget, index), ...] outermost first
    keywords: List[str] = field(default_factory=list)

    def matches(self, terms: List[str]) -> bool:
        haystack = " ".join([self.path, *self.keywords]).casefold()
        return all(term in haystack for term in terms)


def _direct_tab_widgets(page: QWidget) -> List[QTabWidget]:
    """Tab widgets inside ``page`` that are not nested in another tab widget of ``page``."""
    found = []
    for candidate in page.findChildren(QTabWidget):
        parent, nested = candidate.parentWidget(), False
        while parent is not None and parent is not page:
            if isinstance(parent, QTabWidget):
                nested = True
                break
            parent = parent.parentWidget()
        if not nested:
            found.append(candidate)
    return found


def _group_titles(page: QWidget, exclude: List[QWidget]) -> List[str]:
    titles = []
    for box in page.findChildren(QGroupBox):
        if any(other.isAncestorOf(box) for other in exclude):
            continue
        title = clean_title(box.title())
        if title:
            titles.append(title)
    return titles


def build_index(tabs: QTabWidget) -> List[CalculatorEntry]:
    entries: List[CalculatorEntry] = []

    def walk(tab_widget: QTabWidget, prefix: List[str], steps: List[tuple]):
        for index in range(tab_widget.count()):
            title = clean_title(tab_widget.tabText(index))
            page = tab_widget.widget(index)
            path_parts, path_steps = [*prefix, title], [*steps, (tab_widget, index)]
            inner = _direct_tab_widgets(page) if page is not None else []
            keywords = _group_titles(page, inner) if page is not None else []
            tip = tab_widget.tabToolTip(index)
            if tip:
                keywords.append(tip)
            entries.append(CalculatorEntry(SEPARATOR.join(path_parts), path_steps, keywords))
            for nested in inner:
                walk(nested, path_parts, path_steps)

    walk(tabs, [], [])
    return entries


class _DictStore:
    """Minimal QSettings-like store used when no settings object is supplied (tests)."""

    def __init__(self, data: Optional[MutableMapping] = None):
        self.data = data if data is not None else {}

    def value(self, key, default=None):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value


def _as_list(value) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


class CalculatorFinder(QWidget):
    """Search box + favourites + recents for a calculator tab tree."""

    opened = Signal(str)

    def __init__(self, tabs: QTabWidget, store=None, parent: Optional[QWidget] = None,
                 settings_factory: Optional[Callable[[], object]] = None):
        super().__init__(parent)
        self.tabs = tabs
        if store is None:
            if settings_factory is None:
                from PySide6.QtCore import QSettings
                settings_factory = lambda: QSettings("DrillMaster", "EngineeringCalculatorFinder")  # noqa: E731
            store = settings_factory()
        self.store = store
        self.entries: List[CalculatorEntry] = []
        self.by_path: Dict[str, CalculatorEntry] = {}
        self._watched: set = set()
        self._build_ui()
        self.reindex()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setLayoutDirection(Qt.LeftToRight)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Find a calculator (e.g. kill sheet, ECD, casing, nozzle)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.search)
        self.search_edit.returnPressed.connect(self.open_first_result)
        self.favorite_btn = QPushButton("☆ Favourite")
        self.favorite_btn.setCheckable(True)
        self.favorite_btn.setToolTip("Add or remove the calculator that is open now")
        self.favorite_btn.clicked.connect(self.toggle_current_favorite)
        row.addWidget(self.search_edit, 1)
        row.addWidget(self.favorite_btn)
        layout.addLayout(row)

        lists = QHBoxLayout()
        self.results_list = self._list("Search results")
        self.favorites_list = self._list("Favourites")
        self.recents_list = self._list("Recently opened")
        for title, widget in (("Results", self.results_list), ("Favourites", self.favorites_list),
                              ("Recent", self.recents_list)):
            box = QVBoxLayout()
            label = QLabel(title)
            label.setStyleSheet("font-weight: bold;")
            box.addWidget(label)
            box.addWidget(widget)
            lists.addLayout(box, 1)
        layout.addLayout(lists)
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _list(self, accessible: str) -> QListWidget:
        widget = QListWidget()
        widget.setAccessibleName(accessible)
        widget.setMaximumHeight(110)
        widget.itemActivated.connect(self._item_chosen)     # bound slots: no reference cycle
        widget.itemClicked.connect(self._item_chosen)
        return widget

    def _item_chosen(self, item: QListWidgetItem):
        self.open_path(item.data(Qt.UserRole))

    @staticmethod
    def _fill(widget: QListWidget, paths: List[str]):
        widget.clear()
        for path in paths:
            item = QListWidgetItem(path)
            item.setData(Qt.UserRole, path)
            widget.addItem(item)

    # --------------------------------------------------------------- model
    def reindex(self):
        self.entries = build_index(self.tabs)
        self.by_path = {entry.path: entry for entry in self.entries}
        for entry in self.entries:
            for tab_widget, _index in entry.steps:
                if id(tab_widget) not in self._watched:
                    self._watched.add(id(tab_widget))
                    tab_widget.currentChanged.connect(self._sync_favorite_button)
        self._refresh_lists()
        self.search(self.search_edit.text())

    def favorites(self) -> List[str]:
        return [p for p in _as_list(self.store.value("favorites")) if p in self.by_path]

    def recents(self) -> List[str]:
        return [p for p in _as_list(self.store.value("recents")) if p in self.by_path]

    def _refresh_lists(self):
        self._fill(self.favorites_list, self.favorites())
        self._fill(self.recents_list, self.recents())
        self._sync_favorite_button()

    def search(self, text: str = "") -> List[str]:
        terms = [t for t in (text or "").casefold().split() if t]
        if not terms:
            self._fill(self.results_list, [])
            self.status_label.setText(f"{len(self.entries)} calculators and pages indexed.")
            return []
        hits = [entry.path for entry in self.entries if entry.matches(terms)]
        self._fill(self.results_list, hits)
        self.status_label.setText(f"{len(hits)} match(es)." if hits else "No calculator matches that search.")
        return hits

    def current_path(self) -> Optional[str]:
        """Deepest indexed page that is open now."""
        best = None
        for entry in self.entries:
            if all(tab_widget.currentIndex() == index for tab_widget, index in entry.steps):
                if best is None or len(entry.steps) > len(best.steps):
                    best = entry
        return best.path if best else None

    def open_path(self, path: Optional[str]) -> bool:
        entry = self.by_path.get(path or "")
        if entry is None:
            self.status_label.setText("That calculator is no longer available.")
            return False
        for tab_widget, index in entry.steps:
            tab_widget.setCurrentIndex(index)
        recents = [entry.path, *[p for p in self.recents() if p != entry.path]][:MAX_RECENTS]
        self.store.setValue("recents", recents)
        self._refresh_lists()
        self.opened.emit(entry.path)
        return True

    def open_first_result(self) -> bool:
        return self.results_list.count() > 0 and self.open_path(self.results_list.item(0).data(Qt.UserRole))

    def toggle_current_favorite(self) -> Optional[bool]:
        """Returns True if added, False if removed, None if nothing is open."""
        path = self.current_path()
        if path is None:
            return None
        favorites = self.favorites()
        added = path not in favorites
        favorites = [*favorites, path] if added else [p for p in favorites if p != path]
        self.store.setValue("favorites", favorites)
        self._refresh_lists()
        return added

    def _sync_favorite_button(self, *_):
        path = self.current_path()
        is_favorite = path in self.favorites() if path else False
        self.favorite_btn.blockSignals(True)
        self.favorite_btn.setChecked(is_favorite)
        self.favorite_btn.setText("★ Favourite" if is_favorite else "☆ Favourite")
        self.favorite_btn.blockSignals(False)
