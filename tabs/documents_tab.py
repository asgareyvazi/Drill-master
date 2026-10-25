"""Documents tab: reviewed document import and local full-text search (M44).

Import is three explicit steps: extraction in a worker thread (no database
access), a review dialog where the user approves/edits/rejects each page (OCR
pages start unapproved), then an atomic per-document import with an audit
record.  Search runs over stored, reviewed page text only and every result
names its file and page/location; opening a result shows that stored text.

M45: documents can be linked to a well and, optionally, one of its daily
reports (``core.document_links``).  Links are made only through the link
dialog after the user confirms; text matches of well names are offered as
suggestions.  The library can be filtered to unlinked documents, and
``open_document`` opens any document at a page (used by the Well Info and
Daily Report "Related documents" panels).  Search is Persian/Arabic
normalised; highlights are mapped onto the stored original text.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressDialog, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from core.document_library import (
    FILE_DIALOG_FILTER, PAGE_OK, PAGE_REVIEW, DocumentLibrary, PageDecision, default_decisions, default_ocr_engine,
    extract_batch, ocr_status,
)
from core.document_links import DocumentLinkError, DocumentLinkService
from core.search_normalization import find_spans, line_of
from tabs.document_link_dialog import LinkDocumentDialog
from tabs.related_documents import link_target_text

logger = logging.getLogger(__name__)

STATUS_TEXT = {
    "ready": "Ready", "partial": "Partial (some pages without text)", "needs_review": "Needs review (OCR)",
    "no_text": "No text found", "unsupported": "Unsupported format", "corrupt": "Corrupt file",
    "encrypted": "Password protected", "empty": "Empty file", "too_large": "Too large", "error": "Failed",
    "cancelled": "Cancelled",
}
PAGE_STATUS_COLOR = {"ok": "#1e7b34", "needs_review": "#9a5b00", "no_text": "#667085", "error": "#b42318"}
OUTCOME_TEXT = {"imported": "Imported", "duplicate": "Duplicate - not imported", "nothing_approved":
                "Nothing approved", "not_importable": "Not importable", "denied": "Permission denied",
                "failed": "Failed (rolled back)", "skipped": "Skipped by reviewer"}
LIBRARY_FILTERS = (("all", "All documents"), ("unlinked", "Unlinked documents only"),
                   ("linked", "Linked documents only"))


class ExtractionWorker(QThread):
    """Extract files off the UI thread.  Touches no database."""
    progress = Signal(int, int)
    extracted = Signal(list)

    def __init__(self, paths, use_ocr=True, parent=None):
        super().__init__(parent)
        self.paths = list(paths)
        self.use_ocr = use_ocr
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        engine = default_ocr_engine() if self.use_ocr else None
        results = extract_batch(self.paths, ocr_engine=engine, cancel=lambda: self._cancelled,
                                progress=lambda done, total: self.progress.emit(done, total))
        self.extracted.emit(results)


class DocumentReviewDialog(QDialog):
    """Approve, edit or reject each extracted page before anything is stored."""

    def __init__(self, extracts, library: DocumentLibrary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review extracted documents")
        self.resize(1100, 680)
        self.extracts = list(extracts)
        self.decisions = {}            # index -> {page_no: [approved, text-or-None]}
        self.skipped = set()
        self.blocked = {}              # index -> reason (duplicate / not importable)
        for index, extract in enumerate(self.extracts):
            self.decisions[index] = {n: [d.approved, None] for n, d in default_decisions(extract).items()}
            duplicate = library.duplicate_of(extract.sha256) if extract.sha256 else None
            if duplicate:
                self.blocked[index] = f"Duplicate of '{duplicate[1]}' already in the library"
            elif not extract.importable:
                self.blocked[index] = "; ".join(extract.messages) or STATUS_TEXT.get(extract.status, extract.status)
        self.current_file: Optional[int] = None
        self.current_page: Optional[int] = None
        self._build()
        if self.extracts:
            self.file_list.setCurrentRow(0)

    def _build(self):
        layout = QVBoxLayout(self)
        note = QLabel("Text-layer pages are pre-approved. OCR pages are unapproved until you check them against "
                      "the source; OCR scores are engine scores, not probabilities. Edited text is stored as "
                      "edited and audited.")
        note.setWordWrap(True)
        layout.addWidget(note)
        splitter = QSplitter(Qt.Horizontal)
        self.file_list = QListWidget()
        for index, extract in enumerate(self.extracts):
            text = f"{extract.file_name}\n{STATUS_TEXT.get(extract.status, extract.status)}"
            if index in self.blocked:
                text += f"\n{self.blocked[index]}"
            item = QListWidgetItem(text)
            if index in self.blocked:
                item.setForeground(QColor("#b42318"))
            self.file_list.addItem(item)
        self.file_list.currentRowChanged.connect(self._show_file)
        splitter.addWidget(self.file_list)

        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        self.skip_check = QCheckBox("Skip this file")
        self.skip_check.toggled.connect(self._skip_toggled)
        middle_layout.addWidget(self.skip_check)
        self.page_table = QTableWidget(0, 5)
        self.page_table.setHorizontalHeaderLabels(("Approve", "Location", "Status", "Method / score", "Note"))
        self.page_table.verticalHeader().setVisible(False)
        self.page_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.page_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.page_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.page_table.horizontalHeader().setStretchLastSection(True)
        self.page_table.itemChanged.connect(self._approve_changed)
        self.page_table.currentCellChanged.connect(lambda row, *_: self._show_page(row))
        middle_layout.addWidget(self.page_table)
        self.file_messages = QLabel()
        self.file_messages.setWordWrap(True)
        middle_layout.addWidget(self.file_messages)
        splitter.addWidget(middle)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.page_title = QLabel("Select a page")
        right_layout.addWidget(self.page_title)
        self.editor = QPlainTextEdit()
        self.editor.textChanged.connect(self._text_edited)
        right_layout.addWidget(self.editor)
        splitter.addWidget(right)
        splitter.setSizes([260, 420, 420])
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.import_button = buttons.addButton("Import approved pages", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_file(self, index):
        self.current_file = index if 0 <= index < len(self.extracts) else None
        self.current_page = None
        self.page_table.blockSignals(True)
        self.page_table.setRowCount(0)
        self.editor.blockSignals(True)
        self.editor.clear()
        self.editor.blockSignals(False)
        if self.current_file is None:
            self.page_table.blockSignals(False)
            return
        extract = self.extracts[index]
        blocked = index in self.blocked
        self.skip_check.blockSignals(True)
        self.skip_check.setChecked(index in self.skipped or blocked)
        self.skip_check.setEnabled(not blocked)
        self.skip_check.blockSignals(False)
        self.file_messages.setText("\n".join([self.blocked.get(index, "")] + extract.messages).strip())
        self.page_table.setRowCount(len(extract.pages))
        for row, page in enumerate(extract.pages):
            check = QTableWidgetItem()
            selectable = page.status in (PAGE_OK, PAGE_REVIEW) and not blocked
            flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
            if selectable:
                flags |= Qt.ItemIsUserCheckable
            check.setFlags(flags)
            check.setCheckState(Qt.Checked if self.decisions[index][page.page_no][0] and selectable else Qt.Unchecked)
            self.page_table.setItem(row, 0, check)
            self.page_table.setItem(row, 1, QTableWidgetItem(page.location))
            status = QTableWidgetItem(page.status.replace("_", " "))
            status.setForeground(QColor(PAGE_STATUS_COLOR.get(page.status, "#344054")))
            self.page_table.setItem(row, 2, status)
            score = "" if page.confidence is None else f" · {page.confidence:.2f}"
            self.page_table.setItem(row, 3, QTableWidgetItem(page.method + score))
            self.page_table.setItem(row, 4, QTableWidgetItem(page.note))
        self.page_table.blockSignals(False)
        if extract.pages:
            self.page_table.setCurrentCell(0, 1)
            self._show_page(0)

    def _show_page(self, row):
        if self.current_file is None:
            return
        pages = self.extracts[self.current_file].pages
        if not 0 <= row < len(pages):
            return
        page = pages[row]
        self.current_page = page.page_no
        edited = self.decisions[self.current_file][page.page_no][1]
        self.page_title.setText(f"{self.extracts[self.current_file].file_name} — {page.location} ({page.method})")
        self.editor.blockSignals(True)
        self.editor.setPlainText(page.text if edited is None else edited)
        self.editor.setReadOnly(page.status not in (PAGE_OK, PAGE_REVIEW) or self.current_file in self.blocked)
        self.editor.blockSignals(False)

    def _approve_changed(self, item):
        if item.column() != 0 or self.current_file is None:
            return
        page = self.extracts[self.current_file].pages[item.row()]
        self.decisions[self.current_file][page.page_no][0] = item.checkState() == Qt.Checked

    def _text_edited(self):
        if self.current_file is None or self.current_page is None:
            return
        self.decisions[self.current_file][self.current_page][1] = self.editor.toPlainText()

    def _skip_toggled(self, checked):
        if self.current_file is None:
            return
        (self.skipped.add if checked else self.skipped.discard)(self.current_file)

    # test/automation helpers -------------------------------------------
    def set_page_approved(self, file_index, page_no, approved=True, text=None):
        self.decisions[file_index][page_no][0] = approved
        if text is not None:
            self.decisions[file_index][page_no][1] = text
        if file_index == self.current_file:
            self._show_file(file_index)

    def results(self):
        """[(extract, decisions)] for files to import; [(extract, reason)] for the rest."""
        selected, excluded = [], []
        for index, extract in enumerate(self.extracts):
            if index in self.blocked:
                excluded.append((extract, self.blocked[index]))
            elif index in self.skipped:
                excluded.append((extract, "skipped"))
            else:
                selected.append((extract, {n: PageDecision(approved=a, text=t)
                                           for n, (a, t) in self.decisions[index].items()}))
        return selected, excluded


class DocumentsTab(QWidget):
    """Document library with reviewed import and offline search."""

    links_changed = Signal()

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.library = DocumentLibrary(db_manager)
        self.link_service = DocumentLinkService(db_manager)
        self.current_document_id = None
        self.current_links = []
        self.pending_link_dialog = None
        self.last_link_error = None
        self.current_match_line = None
        self._result_anchor = None
        self.worker: Optional[ExtractionWorker] = None
        self.progress_dialog = None
        self.last_outcomes = []
        self.last_search = None
        self.show_dialogs = True
        self._viewer_pages = []
        self._build()
        self.refresh()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        title = QLabel("Document Library")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header.addWidget(title)
        header.addStretch()
        status = ocr_status()
        self.ocr_label = QLabel(f"OCR: {status['engine']} {status['version']} (results need review)"
                                if status["available"] else f"OCR: not available — {status['reason']}")
        self.ocr_label.setWordWrap(True)
        self.ocr_label.setMaximumWidth(620)
        header.addWidget(self.ocr_label)
        self.import_button = QPushButton("Import documents…")
        self.import_button.clicked.connect(lambda: self.start_import())
        header.addWidget(self.import_button)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search reviewed document text (offline, local index)")
        self.search_edit.returnPressed.connect(self.run_search)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.run_search)
        self.rebuild_button = QPushButton("Rebuild index")
        self.rebuild_button.setToolTip("Rebuild the local search index from the stored text "
                                       "(Persian/Arabic letter forms, digits and half-spaces are normalised "
                                       "for matching only; the stored text is never changed).")
        self.rebuild_button.clicked.connect(self.rebuild_index)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.rebuild_button)
        layout.addLayout(search_row)
        self.search_info = QLabel("")
        self.search_info.setWordWrap(True)
        layout.addWidget(self.search_info)

        splitter = QSplitter(Qt.Horizontal)
        left = QSplitter(Qt.Vertical)
        library_box = QWidget()
        library_layout = QVBoxLayout(library_box)
        library_layout.setContentsMargins(0, 0, 0, 0)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show:"))
        self.filter_combo = QComboBox()
        for key, label in LIBRARY_FILTERS:
            self.filter_combo.addItem(label, key)
        self.filter_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        filter_row.addWidget(self.filter_combo)
        filter_row.addStretch()
        library_layout.addLayout(filter_row)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("File", "Type", "Pages stored / source", "Extraction", "Imported (UTC)",
                                              "By", "Well links"))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._document_selected)
        library_layout.addWidget(self.table)
        library_actions = QHBoxLayout()
        self.delete_button = QPushButton("Remove from library")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected)
        library_actions.addWidget(self.delete_button)
        library_actions.addStretch()
        self.library_info = QLabel("")
        library_actions.addWidget(self.library_info)
        library_layout.addLayout(library_actions)
        left.addWidget(library_box)
        left.addWidget(self._build_links_box())
        self.results = QListWidget()
        self.results.setWordWrap(True)
        self.results.currentRowChanged.connect(self._result_selected)
        left.addWidget(self.results)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.viewer_title = QLabel("Select a document or a search result")
        self.viewer_title.setWordWrap(True)
        nav.addWidget(self.viewer_title, 1)
        self.page_combo = QComboBox()
        self.page_combo.currentIndexChanged.connect(self._page_chosen)
        nav.addWidget(self.page_combo)
        right_layout.addLayout(nav)
        self.viewer = QPlainTextEdit()
        self.viewer.setReadOnly(True)
        right_layout.addWidget(self.viewer)
        splitter.addWidget(right)
        splitter.setSizes([620, 620])
        layout.addWidget(splitter, 1)

    def _build_links_box(self):
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self.link_status = QLabel("Select a document to see its well/report links.")
        self.link_status.setWordWrap(True)
        layout.addWidget(self.link_status)
        self.links_table = QTableWidget(0, 4)
        self.links_table.setHorizontalHeaderLabels(("Well", "Linked to", "Anchor page", "Linked by / at (UTC)"))
        self.links_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.links_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.links_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.links_table.verticalHeader().setVisible(False)
        self.links_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.links_table.horizontalHeader().setStretchLastSection(True)
        self.links_table.setMaximumHeight(150)
        self.links_table.itemSelectionChanged.connect(self._update_link_buttons)
        self.links_table.cellDoubleClicked.connect(lambda row, _c: self._open_link_anchor(row))
        layout.addWidget(self.links_table)
        actions = QHBoxLayout()
        self.link_button = QPushButton("Link to well / report…")
        self.link_button.clicked.connect(lambda: self.link_selected())
        self.change_link_button = QPushButton("Change link…")
        self.change_link_button.clicked.connect(lambda: self.change_selected_link())
        self.remove_link_button = QPushButton("Remove link")
        self.remove_link_button.clicked.connect(lambda: self.remove_selected_link())
        for button in (self.link_button, self.change_link_button, self.remove_link_button):
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.link_info = QLabel("")
        self.link_info.setWordWrap(True)
        layout.addWidget(self.link_info)
        return box

    @staticmethod
    def _can_curate() -> bool:
        try:
            from core.permissions import permissions
            return bool(permissions.can_import())
        except Exception:  # silent-ok: no session principal (tests/tools); the data layer still enforces
            return True

    # --------------------------------------------------------------- library
    def refresh(self):
        try:
            documents = self.library.list_documents()
        except Exception as exc:
            logger.warning("Document library could not be read: %s", type(exc).__name__)
            self.library_info.setText(f"Library could not be read ({type(exc).__name__})")
            return
        total, unlinked = len(documents), sum(1 for d in documents if not d["links"])
        mode = self.filter_combo.currentData()
        if mode == "unlinked":
            documents = [d for d in documents if not d["links"]]
        elif mode == "linked":
            documents = [d for d in documents if d["links"]]
        selected = self.current_document_id
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(documents))
        for row, doc in enumerate(documents):
            values = (doc["file_name"], doc["kind"], f"{doc['stored_pages']} / {doc['page_count']}",
                      STATUS_TEXT.get(doc["status"], doc["status"]),
                      doc["imported_at"].strftime("%Y-%m-%d %H:%M") if doc["imported_at"] else "—",
                      doc["imported_by"] or "—", f"{doc['links']} link(s)" if doc["links"] else "Unlinked")
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, doc["id"])
                if column == 6 and not doc["links"]:
                    item.setForeground(QColor("#9a5b00"))
                self.table.setItem(row, column, item)
            if doc["id"] == selected:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        if total:
            shown = f"{len(documents)} of {total} document(s) shown" if mode != "all" else f"{total} document(s)"
            self.library_info.setText(f"{shown} · {unlinked} not linked to a well")
        else:
            self.library_info.setText("No documents yet. Use “Import documents…” to add PDFs, text files or images.")
        allowed = self._can_curate()
        self.import_button.setEnabled(allowed and self.worker is None)
        self.import_button.setToolTip("" if allowed else "Your role cannot import documents")
        self._refresh_links()

    def _selected_document_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _document_selected(self):
        document_id = self._selected_document_id()
        self.delete_button.setEnabled(document_id is not None)
        if document_id is not None:
            self._result_anchor = None
            self.show_document(document_id)

    def open_document(self, document_id, page_no=None, terms=()) -> bool:
        """Show a document (from a related-documents panel or a link) at a page.

        Clears a library filter that would hide it, selects its row and opens
        the stored text at ``page_no`` (first stored page when None)."""
        document = self.library.document(document_id)
        if document is None:
            self.viewer_title.setText(f"Document {document_id} is no longer in the library.")
            self.viewer.clear()
            return False
        if not any(self.table.item(r, 0).data(Qt.UserRole) == document_id for r in range(self.table.rowCount())):
            self.filter_combo.setCurrentIndex(0)          # 'All documents' (refresh() runs)
        self.current_document_id = document_id
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.UserRole) == document_id:
                self.table.selectRow(row)
        self.table.blockSignals(False)
        self.delete_button.setEnabled(True)
        self.show_document(document_id, page_no, terms)
        return True

    def show_document(self, document_id, page_no=None, terms=()):
        self._viewer_pages = self.library.pages(document_id)
        document = self.library.document(document_id)
        name = document["file_name"] if document else f"document {document_id}"
        self.current_document_id = document_id if document else None
        self._viewer_name, self._viewer_terms = name, tuple(terms)
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for page in self._viewer_pages:
            self.page_combo.addItem(page["location"], page["page_no"])
        index = next((i for i, p in enumerate(self._viewer_pages) if p["page_no"] == page_no), 0)
        self.page_combo.setCurrentIndex(index if self._viewer_pages else -1)
        self.page_combo.blockSignals(False)
        self._show_viewer_page(index)
        self._refresh_links()

    def _page_chosen(self, index):
        self._show_viewer_page(index)

    def _show_viewer_page(self, index):
        if not 0 <= index < len(self._viewer_pages):
            self.viewer_title.setText(f"{getattr(self, '_viewer_name', '')}: no stored pages")
            self.viewer.clear()
            return
        page = self._viewer_pages[index]
        score = "" if page["confidence"] is None else f", OCR score {page['confidence']:.2f}"
        self.viewer.setPlainText(page["text"])           # the stored original, never the normalised copy
        self._highlight(self._viewer_terms)
        where = f", first match on line {self.current_match_line}" if self.current_match_line else ""
        self.viewer_title.setText(f"<b>{self._viewer_name}</b> — {page['location']} "
                                  f"({page['method']}, {page['review_status']}{score}){where}")

    def _highlight(self, terms):
        """Highlight query matches in the original text (normalisation-aware)."""
        selections = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#ffe58f"))
        text = self.viewer.toPlainText()
        spans = find_spans(text, terms)
        for start, end in spans:
            cursor = QTextCursor(self.viewer.document())
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor, selection.format = cursor, fmt
            selections.append(selection)
        self.viewer.setExtraSelections(selections)
        self.current_match_line = line_of(text, spans[0][0]) if spans else None
        if selections:
            self.viewer.setTextCursor(selections[0].cursor)
            self.viewer.ensureCursorVisible()

    def delete_selected(self):
        document_id = self._selected_document_id()
        if document_id is None:
            return
        if self.show_dialogs and QMessageBox.question(
                self, "Remove document", "Remove this document and its stored text from the library?") \
                != QMessageBox.Yes:
            return
        try:
            self.library.delete_document(document_id)
        except Exception as exc:
            logger.warning("Document delete failed: %s", type(exc).__name__)
            self.library_info.setText(f"Remove failed ({type(exc).__name__})")
            return
        self.viewer.clear()
        self.current_document_id = None
        self.refresh()
        self.links_changed.emit()

    # ----------------------------------------------------------------- links
    def _refresh_links(self):
        document_id = self.current_document_id
        if document_id != getattr(self, "_link_info_document_id", None):
            self.link_info.setText("")                    # a message about another document is stale
            self._link_info_document_id = document_id
        self.current_links = []
        self.links_table.setRowCount(0)
        if document_id is None:
            self.link_status.setText("Select a document to see its well/report links.")
            self._update_link_buttons()
            return
        try:
            self.current_links = self.link_service.links_for_document(document_id)
        except Exception as exc:
            logger.warning("Document links could not be read: %s", type(exc).__name__)
            self.link_status.setText(f"Links could not be read ({type(exc).__name__}).")
            self._update_link_buttons()
            return
        self.links_table.setRowCount(len(self.current_links))
        for row, link in enumerate(self.current_links):
            code = f" ({link['well_code']})" if link["well_code"] else ""
            when = link["linked_at"].strftime("%Y-%m-%d %H:%M") if link["linked_at"] else "—"
            values = (f"{link['well_name']}{code}", link_target_text(link),
                      f"page {link['page_no']}" if link["page_no"] else "—", f"{link['linked_by'] or '—'} · {when}")
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, link["id"])
                self.links_table.setItem(row, column, item)
        if self.current_links:
            wells = len({link["well_id"] for link in self.current_links})
            self.link_status.setText(f"<b>Linked</b> to {wells} well(s) through {len(self.current_links)} link(s).")
        else:
            self.link_status.setText("<b>Not linked</b> to any well or report yet. "
                                     "Use “Link to well / report…” to link it.")
        self._update_link_buttons()

    def _selected_link(self):
        row = self.links_table.currentRow()
        return self.current_links[row] if 0 <= row < len(self.current_links) else None

    def _update_link_buttons(self):
        allowed = self._can_curate()
        has_document = self.current_document_id is not None
        has_link = self._selected_link() is not None
        self.link_button.setEnabled(allowed and has_document)
        self.change_link_button.setEnabled(allowed and has_link)
        self.remove_link_button.setEnabled(allowed and has_link)
        tip = "" if allowed else "Your role cannot change document links"
        for button in (self.link_button, self.change_link_button, self.remove_link_button):
            button.setToolTip(tip)

    def _open_link_anchor(self, row):
        if 0 <= row < len(self.current_links):
            link = self.current_links[row]
            self.show_document(link["document_id"], link["page_no"])

    def _make_link_dialog(self, current=None, anchor_page=None):
        document = self.library.document(self.current_document_id) if self.current_document_id else None
        if document is None:
            self.link_info.setText("Select a document first.")
            return None
        try:
            suggestions = self.link_service.suggest_wells(document["id"])
        except Exception as exc:
            logger.warning("Well suggestions unavailable: %s", type(exc).__name__)
            suggestions = []
        return LinkDocumentDialog(self.db_manager, document, self.library.pages(document["id"]),
                                  suggestions=suggestions, current=current, anchor_page=anchor_page, parent=self)

    def _run_link_dialog(self, dialog):
        if dialog is None:
            return None
        if not self.show_dialogs:
            self.pending_link_dialog = dialog          # tests drive the dialog, then apply_link_dialog()
            return dialog
        return self.apply_link_dialog(dialog, dialog.exec() == QDialog.Accepted)

    def link_selected(self, anchor_page=None):
        """Open the link dialog for the shown document (a selected search
        result supplies its page as the default anchor page)."""
        if anchor_page is None and self._result_anchor and self._result_anchor[0] == self.current_document_id:
            anchor_page = self._result_anchor[1]
        return self._run_link_dialog(self._make_link_dialog(anchor_page=anchor_page))

    def change_selected_link(self):
        link = self._selected_link()
        if link is None:
            self.link_info.setText("Select a link to change.")
            return None
        return self._run_link_dialog(self._make_link_dialog(current=link))

    def apply_link_dialog(self, dialog, accepted: bool):
        """Save the dialog's choice after the user confirmed (``accepted``)."""
        self.pending_link_dialog = None
        self.last_link_error = None
        if not accepted:
            self.link_info.setText("Link cancelled; nothing was changed.")
            return None
        choice = dialog.selection()
        if choice["well_id"] is None:
            self.link_info.setText("No well selected; nothing was changed.")
            return None
        try:
            if dialog.current:
                self.link_service.update_link(dialog.current["id"], choice["well_id"], choice["report_id"],
                                              choice["page_no"])
                result, message = dialog.current["id"], "Link changed."
            else:
                result = self.link_service.create_link(self.current_document_id, choice["well_id"],
                                                       choice["report_id"], choice["page_no"])
                message = "Document linked."
        except DocumentLinkError as exc:
            self.last_link_error = exc.code
            self.link_info.setText(str(exc))
            self._refresh_links()
            return None
        self.link_info.setText(message)
        self.refresh()
        self.links_changed.emit()
        return result

    def remove_selected_link(self):
        link = self._selected_link()
        if link is None:
            self.link_info.setText("Select a link to remove.")
            return False
        if self.show_dialogs and QMessageBox.question(
                self, "Remove link", f"Remove the link to {link_target_text(link)}? "
                                     "The document stays in the library.") != QMessageBox.Yes:
            return False
        self.last_link_error = None
        try:
            self.link_service.remove_link(link["id"])
        except DocumentLinkError as exc:
            self.last_link_error = exc.code
            self.link_info.setText(str(exc))
            self._refresh_links()
            return False
        self.link_info.setText("Link removed; the document stays in the library.")
        self.refresh()
        self.links_changed.emit()
        return True

    # ---------------------------------------------------------------- search
    def run_search(self):
        query = self.search_edit.text()
        try:
            result = self.library.search(query)
        except Exception as exc:
            logger.warning("Document search failed: %s", type(exc).__name__)
            self.search_info.setText(f"Search failed ({type(exc).__name__})")
            return
        self.last_search = result
        self.results.clear()
        self._search_terms = tuple(result.get("terms") or self.library._terms(query))
        for hit in result["hits"]:
            line = f", line {hit['line_no']}" if hit.get("line_no") else ""
            item = QListWidgetItem(f"{hit['file_name']} — {hit['location']}{line}  [{hit['review_status']}]\n"
                                   f"{hit['snippet']}")
            item.setData(Qt.UserRole, hit)
            item.setToolTip("Select to open the stored text of this page")
            self.results.addItem(item)
        method = f" · {result['method']}" if result["method"] else ""
        self.search_info.setText(result["message"] + method)

    def _result_selected(self, row):
        item = self.results.item(row) if row >= 0 else None
        hit = item.data(Qt.UserRole) if item else None
        if hit:
            self.open_document(hit["document_id"], hit["page_no"], getattr(self, "_search_terms", ()))
            self._result_anchor = (hit["document_id"], hit["page_no"])

    def rebuild_index(self):
        try:
            info = self.library.rebuild_index()
        except Exception as exc:
            logger.warning("Search index rebuild failed: %s", type(exc).__name__)
            self.search_info.setText(f"Index rebuild failed ({type(exc).__name__})")
            return None
        engine = "FTS5" if info["fts"] else "substring scan (FTS5 unavailable)"
        pages = "" if info["pages"] is None else f"{info['pages']} page(s) indexed, "
        self.search_info.setText(f"Search index rebuilt from the stored text: {pages}"
                                 f"normalisation v{info['normalization_version']}, {engine}.")
        return info

    # ---------------------------------------------------------------- import
    def start_import(self, paths=None):
        if paths is None:
            paths, _ = QFileDialog.getOpenFileNames(self, "Import documents", "", FILE_DIALOG_FILTER)
        if not paths or self.worker is not None:
            return
        self.worker = ExtractionWorker(paths, parent=self)
        self.worker.extracted.connect(self._extracted)
        self.worker.finished.connect(self._worker_finished)
        if self.show_dialogs:
            self.progress_dialog = QProgressDialog("Extracting text…", "Cancel", 0, len(paths), self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.canceled.connect(self.worker.cancel)
            self.worker.progress.connect(lambda done, _total: self.progress_dialog.setValue(done))
        self.import_button.setEnabled(False)
        self.worker.start()

    def _worker_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        if self.progress_dialog is not None:
            self.progress_dialog.close()
            self.progress_dialog = None
        self.refresh()

    def _extracted(self, extracts):
        if not self.show_dialogs:
            self.pending_extracts = extracts
            return
        dialog = DocumentReviewDialog(extracts, self.library, self)
        if dialog.exec() != QDialog.Accepted:
            self.search_info.setText("Import cancelled; nothing was stored.")
            return
        selected, excluded = dialog.results()
        outcomes = self.import_reviewed(selected, excluded)
        QMessageBox.information(self, "Document import", "\n".join(
            f"{o.file_name}: {OUTCOME_TEXT.get(o.status, o.status)} — {o.message}" for o in outcomes))

    def import_reviewed(self, selected, excluded=()):
        """Import each reviewed file in its own transaction; one failure never stops the rest."""
        outcomes = []
        for extract, decisions in selected:
            outcomes.append(self.library.import_reviewed(extract, decisions))
        from core.document_library import ImportOutcome
        for extract, reason in excluded:
            outcomes.append(ImportOutcome(extract.file_name, "skipped" if reason == "skipped" else "not_importable",
                                          message=reason))
        self.last_outcomes = outcomes
        self.refresh()
        imported = sum(1 for o in outcomes if o.status == "imported")
        self.search_info.setText(f"Import finished: {imported} of {len(outcomes)} file(s) imported.")
        return outcomes

    def cleanup(self):
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(5000)
        self.library.close()
