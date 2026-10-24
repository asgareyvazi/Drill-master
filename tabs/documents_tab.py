"""Documents tab: reviewed document import and local full-text search (M44).

Import is three explicit steps: extraction in a worker thread (no database
access), a review dialog where the user approves/edits/rejects each page (OCR
pages start unapproved), then an atomic per-document import with an audit
record.  Search runs over stored, reviewed page text only and every result
names its file and page/location; opening a result shows that stored text.
"""
from __future__ import annotations

import logging
import re
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

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.library = DocumentLibrary(db_manager)
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
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        layout.addLayout(search_row)
        self.search_info = QLabel("")
        self.search_info.setWordWrap(True)
        layout.addWidget(self.search_info)

        splitter = QSplitter(Qt.Horizontal)
        left = QSplitter(Qt.Vertical)
        library_box = QWidget()
        library_layout = QVBoxLayout(library_box)
        library_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("File", "Type", "Pages stored / source", "Extraction", "Imported (UTC)",
                                              "By"))
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

    # --------------------------------------------------------------- library
    def refresh(self):
        try:
            documents = self.library.list_documents()
        except Exception as exc:
            logger.warning("Document library could not be read: %s", type(exc).__name__)
            self.library_info.setText(f"Library could not be read ({type(exc).__name__})")
            return
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(documents))
        for row, doc in enumerate(documents):
            values = (doc["file_name"], doc["kind"], f"{doc['stored_pages']} / {doc['page_count']}",
                      STATUS_TEXT.get(doc["status"], doc["status"]),
                      doc["imported_at"].strftime("%Y-%m-%d %H:%M") if doc["imported_at"] else "—",
                      doc["imported_by"] or "—")
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.UserRole, doc["id"])
                self.table.setItem(row, column, item)
        self.library_info.setText(f"{len(documents)} document(s)" if documents else
                                  "No documents yet. Use “Import documents…” to add PDFs, text files or images.")
        try:
            from core.permissions import permissions
            allowed = permissions.can_import()
        except Exception:  # silent-ok: no session principal (tests/tools); the data layer still enforces
            allowed = True
        self.import_button.setEnabled(allowed)
        self.import_button.setToolTip("" if allowed else "Your role cannot import documents")

    def _selected_document_id(self):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        return item.data(Qt.UserRole) if item else None

    def _document_selected(self):
        document_id = self._selected_document_id()
        self.delete_button.setEnabled(document_id is not None)
        if document_id is not None:
            self.show_document(document_id)

    def show_document(self, document_id, page_no=None, terms=()):
        self._viewer_pages = self.library.pages(document_id)
        name = next((self.table.item(r, 0).text() for r in range(self.table.rowCount())
                     if self.table.item(r, 0).data(Qt.UserRole) == document_id), f"document {document_id}")
        self._viewer_name, self._viewer_terms = name, tuple(terms)
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for page in self._viewer_pages:
            self.page_combo.addItem(page["location"], page["page_no"])
        index = next((i for i, p in enumerate(self._viewer_pages) if p["page_no"] == page_no), 0)
        self.page_combo.setCurrentIndex(index if self._viewer_pages else -1)
        self.page_combo.blockSignals(False)
        self._show_viewer_page(index)

    def _page_chosen(self, index):
        self._show_viewer_page(index)

    def _show_viewer_page(self, index):
        if not 0 <= index < len(self._viewer_pages):
            self.viewer_title.setText(f"{getattr(self, '_viewer_name', '')}: no stored pages")
            self.viewer.clear()
            return
        page = self._viewer_pages[index]
        score = "" if page["confidence"] is None else f", OCR score {page['confidence']:.2f}"
        self.viewer_title.setText(f"<b>{self._viewer_name}</b> — {page['location']} "
                                  f"({page['method']}, {page['review_status']}{score})")
        self.viewer.setPlainText(page["text"])
        self._highlight(self._viewer_terms)

    def _highlight(self, terms):
        selections = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#ffe58f"))
        text = self.viewer.toPlainText()
        for term in terms:
            for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
                cursor = QTextCursor(self.viewer.document())
                cursor.setPosition(match.start())
                cursor.setPosition(match.end(), QTextCursor.KeepAnchor)
                selection = QTextEdit.ExtraSelection()
                selection.cursor, selection.format = cursor, fmt
                selections.append(selection)
        self.viewer.setExtraSelections(selections)
        if selections:
            self.viewer.setTextCursor(selections[0].cursor)

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
        self.refresh()

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
        self._search_terms = tuple(self.library._terms(query))
        for hit in result["hits"]:
            item = QListWidgetItem(f"{hit['file_name']} — {hit['location']}  [{hit['review_status']}]\n"
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
            self.show_document(hit["document_id"], hit["page_no"], getattr(self, "_search_terms", ()))

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
