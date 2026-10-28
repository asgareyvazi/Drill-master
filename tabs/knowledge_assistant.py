"""Knowledge Assistant - Ask Your Technical Documents (M49).

A panel of the Documents tab.  It answers questions from the REVIEWED pages
of the document library only, shows every passage it used (document, page,
review status) and opens the cited passage in the library viewer.

Threading (M47 session architecture): the UI thread reads the corpus
snapshot from the database; workers get the snapshot / in-memory index and
never touch a database session.  Every request carries a generation number;
a result whose generation is no longer current (question, scope or library
changed, Clear, Cancel) is dropped, so a stale answer is never shown.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Optional

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextBrowser, QVBoxLayout, QWidget)

from core import knowledge_answer as ka
from core import knowledge_retrieval as kr
from core import local_llm as ll

logger = logging.getLogger(__name__)

SCOPE_CHOICES = ((kr.SCOPE_ALL, "All approved documents"), (kr.SCOPE_WELL, "Documents linked to a well"),
                 (kr.SCOPE_REPORT, "Documents linked to a daily report"), (kr.SCOPE_DOCUMENT, "One document"))

# UI states -> (label, colour)
STATE_STYLE = {
    "idle": ("Ask a question about the reviewed documents.", "#455a64"),
    "searching": ("Searching… (reading the reviewed pages)", "#1565c0"),
    "retrieving": ("Retrieving evidence…", "#1565c0"),
    "generating": ("Generating with the local model…", "#1565c0"),
    "ready": ("Ready", "#2e7d32"),
    "no_evidence": ("No evidence", "#9a5b00"),
    "no_documents": ("No documents", "#9a5b00"),
    "empty_scope": ("Nothing in this scope", "#9a5b00"),
    "no_page": ("Page not stored", "#9a5b00"),
    "invalid_query": ("Question too short", "#9a5b00"),
    "model_unavailable": ("Model unavailable - showing the extractive answer", "#b71c1c"),
    "cancelled": ("Cancelled", "#455a64"),
    "stale": ("Question, scope or library changed - press Ask", "#455a64"),
    "error": ("Error", "#b71c1c"),
}
_CITE = re.compile(r"\[\s*(S\d+(?:\s*[,،]\s*S\d+)*)\s*\]")
_RTL = re.compile(r"[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]")
_LTR = re.compile(r"[A-Za-z]")


def _is_rtl(line: str) -> bool:
    """Direction of a line = its first strong character (Unicode bidi rule P2)."""
    rtl, ltr = _RTL.search(line), _LTR.search(line)
    return bool(rtl) and (not ltr or rtl.start() < ltr.start())


def render_failed_draft_html(draft: str, check) -> str:
    """A model draft that failed the citation checks: shown apart, every failed dimension listed, never as
    the answer.  All document and model text is escaped."""
    rows = []
    for name, meaning in ka.VALIDATION_DIMENSIONS:
        value = check.dimensions.get(name) if check is not None else None
        mark = {True: "✓", False: "✗", None: "–"}[value]
        rows.append(f"<li>{mark} {html.escape(meaning)}</li>")
    problems = "".join(f"<li>{html.escape(p)}</li>" for p in (check.problems if check is not None else []))
    return ('<hr><p style="color:#b71c1c"><b>MODEL DRAFT NOT USED</b> - the local model\'s draft failed the '
            'citation checks, so the answer above is quoted from the documents instead.</p>'
            f'<ul>{problems}</ul><p><small>Checks:</small></p><ul>{"".join(rows)}</ul>'
            f'<p style="color:#757575"><i>Unverified model draft ({html.escape(ka.SEMANTIC_LABEL.lower())}, '
            f'citation checks failed):</i></p><p style="color:#757575">{html.escape(draft)}</p>')


def render_answer_html(text: str) -> str:
    """Escape everything, then turn [S1] / [S1, S2] into citation links."""
    blocks = []
    for line in (text or "").splitlines() or [""]:
        escaped = html.escape(line)
        escaped = _CITE.sub(lambda m: "[" + ", ".join(
            f'<a href="cite:{label.strip()}">{label.strip()}</a>' for label in re.split(r"[,،]", m.group(1))) + "]",
            escaped)
        direction = ' dir="rtl" align="right"' if _is_rtl(line) else ""
        blocks.append(f"<p{direction}>{escaped}</p>")
    return "".join(blocks)


class AskWorker(QThread):
    """Builds the index if needed and answers one question (no DB access)."""

    stage = Signal(int, str)
    done = Signal(int, object, object)          # generation, Answer | exception text, index

    def __init__(self, generation, snapshot, index, question, scope, target, adapter, use_model, cancel, parent=None,
                 store=None):
        super().__init__(parent)
        self.generation, self.snapshot, self.index = generation, snapshot, index
        self.question, self.scope, self.target = question, scope, target
        self.adapter, self.use_model, self.cancel_token, self.store = adapter, use_model, cancel, store

    def run(self):
        try:
            if self.index is None:
                self.index = kr.KnowledgeIndex(self.snapshot, embedding_store=self.store,
                                               embed_model=getattr(self.adapter, "embed_model", None) or None)
            answer = ka.answer_question(self.index, self.question, self.scope, self.target, adapter=self.adapter,
                                        use_model=self.use_model, cancel=self.cancel_token,
                                        stage=lambda s: self.stage.emit(self.generation, s))
            self.done.emit(self.generation, answer, self.index)
        except Exception as exc:  # shown as an explicit error state, never as "no evidence"
            logger.warning("Knowledge Assistant question failed: %s", type(exc).__name__)
            self.done.emit(self.generation, f"{type(exc).__name__}: the question could not be answered", self.index)


class StatusWorker(QThread):
    done = Signal(int, object)

    def __init__(self, generation, adapter, parent=None):
        super().__init__(parent)
        self.generation, self.adapter = generation, adapter

    def run(self):
        self.done.emit(self.generation, self.adapter.status())


class SemanticBuildWorker(QThread):
    progress = Signal(int, int)
    done = Signal(object)

    def __init__(self, index, adapter, store, cancel, parent=None):
        super().__init__(parent)
        self.index, self.adapter, self.store, self.cancel_token = index, adapter, store, cancel

    def run(self):
        try:
            self.done.emit(kr.build_semantic_index(self.index, self.adapter, self.store, cancel=self.cancel_token,
                                                   progress=lambda d, t: self.progress.emit(d, t)))
        except ll.LocalLLMError as exc:
            self.done.emit({"state": exc.state, "message": str(exc)})
        except Exception as exc:
            logger.warning("Semantic index build failed: %s", type(exc).__name__)
            self.done.emit({"state": "error", "message": f"{type(exc).__name__}: semantic index not built"})


class KnowledgeAssistantPanel(QWidget):
    """Question -> cited answer over the reviewed document pages."""

    open_evidence_requested = Signal(int, int, int, int, str)  # document_id, page_no, start, end, text sha256

    def __init__(self, db_manager, library=None, link_service=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.library = library
        self.link_service = link_service
        self._generation = 0
        self._index: Optional[kr.KnowledgeIndex] = None
        self._snapshot_signature = None
        self._store: Optional[kr.EmbeddingStore] = None
        self.worker: Optional[AskWorker] = None
        self.status_worker: Optional[StatusWorker] = None
        self.semantic_worker: Optional[SemanticBuildWorker] = None
        self._cancel: Optional[ll.CancelToken] = None
        self._semantic_cancel: Optional[ll.CancelToken] = None
        self._old_workers = []
        self.model_status: Optional[ll.ModelStatus] = None
        self.last_answer: Optional[ka.Answer] = None
        self.last_error: Optional[str] = None
        self.current_state = "idle"
        self._asked = None                      # (question, scope, target) of the shown answer
        self._build()
        self._fill_targets()
        self._set_state("idle")
        self._connect_selection()

    # ------------------------------------------------------------------ UI
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        intro = QLabel("Ask in Persian or English. Answers come only from reviewed (approved) document pages, quote "
                       "them with page citations, and nothing leaves this computer.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Scope:"))
        self.scope_combo = QComboBox()
        for key, label in SCOPE_CHOICES:
            self.scope_combo.addItem(label, key)
        self.scope_combo.currentIndexChanged.connect(self._scope_changed)
        scope_row.addWidget(self.scope_combo)
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(220)
        self.target_combo.currentIndexChanged.connect(self._target_changed)
        scope_row.addWidget(self.target_combo, 1)
        self.report_combo = QComboBox()
        self.report_combo.setMinimumWidth(200)
        self.report_combo.currentIndexChanged.connect(lambda _i: self._invalidate("scope"))
        scope_row.addWidget(self.report_combo, 1)
        layout.addLayout(scope_row)

        self.question_edit = QPlainTextEdit()
        self.question_edit.setObjectName("knowledgeQuestion")
        self.question_edit.setPlaceholderText("Ask a question…  /  سؤال خود را بنویسید…")
        self.question_edit.setMaximumHeight(72)
        self.question_edit.textChanged.connect(lambda: self._invalidate("question"))
        layout.addWidget(self.question_edit)

        actions = QHBoxLayout()
        self.ask_button = QPushButton("Ask")
        self.ask_button.setObjectName("knowledgeAsk")
        self.ask_button.setStyleSheet(
            "QPushButton#knowledgeAsk { background-color: #1565c0; color: white; padding: 4px 18px; border-radius: 3px; }"
            "QPushButton#knowledgeAsk:disabled { background-color: #b0bec5; color: #eceff1; }")
        self.ask_button.clicked.connect(self.ask)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        self.retry_button = QPushButton("Retry")
        self.retry_button.clicked.connect(self.ask)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear)
        self.use_model_check = QCheckBox("Write the answer with the local model")
        self.use_model_check.setToolTip("Off: the answer is quoted from the documents (no model). On: a local model "
                                        "writes it, and every sentence is checked against the cited passages.")
        for widget in (self.ask_button, self.cancel_button, self.retry_button, self.clear_button):
            actions.addWidget(widget)
        actions.addWidget(self.use_model_check)
        actions.addStretch()
        self.state_label = QLabel("")
        self.state_label.setObjectName("knowledgeState")
        self.state_label.setWordWrap(True)
        actions.addWidget(self.state_label, 1)
        layout.addLayout(actions)

        layout.addWidget(self._build_model_box())

        splitter = QSplitter(Qt.Vertical)
        answer_box = QWidget()
        answer_layout = QVBoxLayout(answer_box)
        answer_layout.setContentsMargins(0, 0, 0, 0)
        answer_layout.addWidget(QLabel("<b>Answer</b>"))
        self.answer_view = QTextBrowser()
        self.answer_view.setObjectName("knowledgeAnswer")
        self.answer_view.setOpenLinks(False)
        self.answer_view.anchorClicked.connect(self._citation_clicked)
        answer_layout.addWidget(self.answer_view, 1)
        self.notes_label = QLabel("")
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextFormat(Qt.PlainText)
        answer_layout.addWidget(self.notes_label)
        splitter.addWidget(answer_box)

        evidence_box = QWidget()
        evidence_layout = QVBoxLayout(evidence_box)
        evidence_layout.setContentsMargins(0, 0, 0, 0)
        evidence_header = QHBoxLayout()
        evidence_header.addWidget(QLabel("<b>Evidence</b> (retrieved passages - the only text the answer may use)"))
        evidence_header.addStretch()
        self.open_source_button = QPushButton("Open source in library")
        self.open_source_button.setEnabled(False)
        self.open_source_button.clicked.connect(lambda: self.open_evidence_row(self.evidence_table.currentRow()))
        evidence_header.addWidget(self.open_source_button)
        evidence_layout.addLayout(evidence_header)
        self.evidence_table = QTableWidget(0, 7)
        self.evidence_table.setHorizontalHeaderLabels(("Source", "Document", "Page", "Review", "Match",
                                                       "Found by", "Passage"))
        self.evidence_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.evidence_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.evidence_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.evidence_table.setWordWrap(False)
        self.evidence_table.verticalHeader().setVisible(False)
        header = self.evidence_table.horizontalHeader()
        for column in range(6):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        self.evidence_table.itemSelectionChanged.connect(
            lambda: self.open_source_button.setEnabled(self.evidence_table.currentRow() >= 0))
        self.evidence_table.cellDoubleClicked.connect(lambda row, _c: self.open_evidence_row(row))
        evidence_layout.addWidget(self.evidence_table, 1)
        splitter.addWidget(evidence_box)
        splitter.setSizes([320, 260])
        layout.addWidget(splitter, 1)

    def _build_model_box(self):
        box = QGroupBox("Local model (optional - answers work without it)")
        box.setObjectName("knowledgeModelBox")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Server:"))
        adapter = ll.OllamaAdapter()
        self.model_url_edit = QLineEdit(adapter.base_url or ll.DEFAULT_BASE_URL)
        self.model_url_edit.setToolTip("Only 127.0.0.1, localhost or [::1] are accepted.")
        self.model_url_edit.setMaximumWidth(220)
        row.addWidget(self.model_url_edit)
        row.addWidget(QLabel("Answer model:"))
        self.chat_model_combo = QComboBox()
        self.chat_model_combo.setEditable(True)
        self.chat_model_combo.setMinimumWidth(160)
        self.chat_model_combo.setEditText(adapter.chat_model)
        row.addWidget(self.chat_model_combo)
        row.addWidget(QLabel("Embedding model:"))
        self.embed_model_combo = QComboBox()
        self.embed_model_combo.setEditable(True)
        self.embed_model_combo.setMinimumWidth(160)
        self.embed_model_combo.setEditText(adapter.embed_model)
        row.addWidget(self.embed_model_combo)
        self.check_model_button = QPushButton("Check model")
        self.check_model_button.clicked.connect(self.check_model)
        row.addWidget(self.check_model_button)
        self.build_semantic_button = QPushButton("Build semantic index")
        self.build_semantic_button.setEnabled(False)
        self.build_semantic_button.clicked.connect(self.build_semantic_index)
        row.addWidget(self.build_semantic_button)
        row.addStretch()
        layout.addLayout(row)
        self.model_label = QLabel("Local model: not checked. Answers are quoted from the documents (no model needed).")
        self.model_label.setObjectName("knowledgeModelState")
        self.model_label.setWordWrap(True)
        layout.addWidget(self.model_label)
        self.semantic_label = QLabel("Semantic retrieval unavailable: no local embedding model configured. "
                                     "Keyword retrieval (FTS5 + Persian/English glossary + character n-grams) works.")
        self.semantic_label.setWordWrap(True)
        layout.addWidget(self.semantic_label)
        self.use_model_check.setEnabled(False)
        return box

    # -------------------------------------------------------------- scope
    def _connect_selection(self):
        try:
            from core.selection_manager import SelectionManager
            manager = SelectionManager()
            manager.well_changed.connect(self._selection_changed)
            manager.report_changed.connect(self._selection_changed)
            manager.selection_cleared.connect(self._selection_changed)
            self._selection = manager
        except Exception as exc:  # silent-ok: panel works without the global selection (tests/tools)
            logger.debug("Selection manager unavailable: %s", type(exc).__name__)
            self._selection = None

    def _selection_changed(self, *_args):
        """A new well/report in the app resets a well/report scope to it."""
        scope = self.scope_combo.currentData()
        if scope in (kr.SCOPE_WELL, kr.SCOPE_REPORT):
            self._fill_targets()
            self._invalidate("scope")

    def _current_selection(self):
        manager = getattr(self, "_selection", None)
        if manager is None:
            return None, None
        return getattr(manager, "current_well_id", None), getattr(manager, "current_report_id", None)

    def _scope_changed(self, _index):
        self._fill_targets()
        self._invalidate("scope")

    def _target_changed(self, _index):
        if self.scope_combo.currentData() == kr.SCOPE_REPORT:
            self._fill_reports()
        self._invalidate("scope")

    def _fill_targets(self):
        scope = self.scope_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        well_id, _report_id = self._current_selection()
        if scope in (kr.SCOPE_WELL, kr.SCOPE_REPORT) and self.link_service is not None:
            try:
                for well in self.link_service.well_choices():
                    code = f" ({well['code']})" if well.get("code") else ""
                    self.target_combo.addItem(f"{well['name']}{code}", well["id"])
            except Exception as exc:
                logger.warning("Well list unavailable: %s", type(exc).__name__)
            index = self.target_combo.findData(well_id) if well_id is not None else -1
            self.target_combo.setCurrentIndex(index if index >= 0 else (0 if self.target_combo.count() else -1))
        elif scope == kr.SCOPE_DOCUMENT and self.library is not None:
            try:
                for doc in self.library.list_documents():
                    self.target_combo.addItem(f"{doc['file_name']}  (#{doc['id']}, {doc['stored_pages']} page(s))",
                                              doc["id"])
            except Exception as exc:
                logger.warning("Document list unavailable: %s", type(exc).__name__)
        self.target_combo.setEnabled(scope != kr.SCOPE_ALL and self.target_combo.count() > 0)
        self.target_combo.setVisible(scope != kr.SCOPE_ALL)
        self.target_combo.blockSignals(False)
        self._fill_reports()

    def _fill_reports(self):
        scope = self.scope_combo.currentData()
        self.report_combo.blockSignals(True)
        self.report_combo.clear()
        if scope == kr.SCOPE_REPORT and self.link_service is not None and self.target_combo.currentData() is not None:
            _well, report_id = self._current_selection()
            try:
                for report in self.link_service.report_choices(self.target_combo.currentData()):
                    when = report["report_date"].isoformat() if report.get("report_date") else "no date"
                    self.report_combo.addItem(f"Report #{report.get('report_number') or '?'} · {when}", report["id"])
            except Exception as exc:
                logger.warning("Report list unavailable: %s", type(exc).__name__)
            index = self.report_combo.findData(report_id) if report_id is not None else -1
            self.report_combo.setCurrentIndex(index if index >= 0 else (0 if self.report_combo.count() else -1))
        self.report_combo.setVisible(scope == kr.SCOPE_REPORT)
        self.report_combo.setEnabled(scope == kr.SCOPE_REPORT and self.report_combo.count() > 0)
        self.report_combo.blockSignals(False)

    def current_scope(self):
        """(scope, target id or None)."""
        scope = self.scope_combo.currentData()
        if scope == kr.SCOPE_ALL:
            return scope, None
        if scope == kr.SCOPE_REPORT:
            return scope, self.report_combo.currentData()
        return scope, self.target_combo.currentData()

    # ------------------------------------------------------------- states
    def _set_state(self, state, detail=""):
        self.current_state = state
        label, colour = STATE_STYLE[state]
        self.state_label.setText(label + (f" - {detail}" if detail else ""))
        self.state_label.setStyleSheet(f"QLabel#knowledgeState {{ color: {colour}; font-weight: bold; }}")
        busy = state in ("searching", "retrieving", "generating")
        self.ask_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.retry_button.setEnabled(not busy and state in ("model_unavailable", "error", "cancelled"))
        self.scope_combo.setEnabled(True)

    def _invalidate(self, reason):
        """Question/scope/library changed: drop any shown or pending answer."""
        if self.worker is not None:
            self._stop_worker()
        shown = self.last_answer is not None or self.last_error is not None or self.answer_view.toPlainText()
        self._generation += 1
        if shown or self.current_state in ("searching", "retrieving", "generating"):
            self._clear_results()
            self._set_state("stale" if reason != "cleared" else "idle")

    def _clear_results(self):
        self.last_answer, self.last_error, self._asked = None, None, None
        self.answer_view.clear()
        self.notes_label.clear()
        self.evidence_table.setRowCount(0)
        self.open_source_button.setEnabled(False)

    def clear(self):
        self.question_edit.blockSignals(True)
        self.question_edit.clear()
        self.question_edit.blockSignals(False)
        self._invalidate("cleared")
        self._clear_results()
        self._set_state("idle")

    def library_changed(self):
        """Called by the Documents tab after import/delete/link changes."""
        self._fill_targets()
        if self._index is not None:
            try:
                changed = kr.corpus_signature(self.db_manager) != self._snapshot_signature
            except Exception as exc:
                logger.warning("Corpus signature unavailable: %s", type(exc).__name__)
                changed = True
            if changed:
                self._index = None
                self._invalidate("library")

    # ---------------------------------------------------------------- ask
    def _adapter(self):
        return ll.OllamaAdapter(self.model_url_edit.text(), self.chat_model_combo.currentText(),
                                self.embed_model_combo.currentText())

    def _embedding_store(self):
        if self._store is None:
            self._store = kr.EmbeddingStore(kr.default_embedding_store_path(self.db_manager))
        return self._store

    def ask(self):
        question = self.question_edit.toPlainText().strip()
        if not question:
            self._set_state("invalid_query", "type a question first")
            return False
        scope, target = self.current_scope()
        if self.worker is not None:
            self._stop_worker()
        self._clear_results()
        self._generation += 1
        generation = self._generation
        self._set_state("searching")
        try:
            signature = kr.corpus_signature(self.db_manager)
            snapshot = None
            if self._index is None or signature != self._snapshot_signature:
                snapshot = kr.read_corpus(self.db_manager)     # UI thread owns the session
                self._index, self._snapshot_signature = None, snapshot.signature
        except Exception as exc:
            logger.warning("Document pages could not be read: %s", type(exc).__name__)
            self.last_error = f"{type(exc).__name__}: the document pages could not be read"
            self._set_state("error", self.last_error)
            return False
        adapter = self._adapter()
        use_model = self.use_model_check.isChecked() and self.use_model_check.isEnabled()
        store = self._embedding_store() if adapter.embed_model else None
        if self._index is not None and adapter.embed_model:
            self._index.embedding_store, self._index.embed_model = store, adapter.embed_model
        self._cancel = ll.CancelToken()
        self.worker = AskWorker(generation, snapshot, self._index, question, scope, target, adapter, use_model,
                                self._cancel, parent=self, store=store)
        self.worker.stage.connect(self._worker_stage)
        self.worker.done.connect(self._worker_done)
        self._asked = (question, scope, target)
        self.worker.start()
        return True

    def _worker_stage(self, generation, stage):
        if generation == self._generation and stage in ("retrieving", "generating"):
            self._set_state(stage)

    def _worker_done(self, generation, outcome, index):
        worker = self.sender()
        if worker is self.worker:
            self.worker = None
        if index is not None and generation == self._generation:
            self._index = index
        if generation != self._generation:
            return                                  # stale: question/scope/library changed meanwhile
        if isinstance(outcome, str):
            self.last_error = outcome
            self._set_state("error", outcome)
            return
        self.show_answer(outcome)

    def cancel(self):
        if self.worker is None:
            return
        self._stop_worker()
        self._generation += 1
        self._set_state("cancelled")

    def _stop_worker(self):
        worker, self.worker = self.worker, None
        if self._cancel is not None:
            self._cancel.cancel()
        if worker is not None:
            try:
                worker.stage.disconnect()
                worker.done.disconnect()
            except (RuntimeError, TypeError):  # silent-ok: signals already disconnected (worker finished or replaced)
                pass
            if worker.isRunning():
                self._old_workers.append(worker)   # keep a reference until the thread ends
                worker.finished.connect(lambda w=worker: self._forget(w))

    def _forget(self, worker):
        if worker in self._old_workers:
            self._old_workers.remove(worker)
        worker.deleteLater()

    # ------------------------------------------------------------ results
    def show_answer(self, answer: ka.Answer):
        self.last_answer = answer
        parts = []
        check_line = ""
        if answer.check is not None and answer.state in ("ready", "model_unavailable"):
            check_line = (f'<p style="color:#555"><small>{html.escape(answer.check.label)} · '
                          f'{html.escape(ka.SEMANTIC_LABEL)}</small></p>')
        if answer.state in ("ready", "model_unavailable"):
            how = ("Written by the local model; every sentence passed the citation checks against the cited "
                   "passages. Read the passages before relying on it." if answer.mode == "generated"
                   else "Quoted from the documents (extractive; no model used).")
            parts.append(f'<p style="color:#2e7d32"><i>{html.escape(how)}</i></p>' + render_answer_html(answer.text)
                         + check_line)
            if answer.state == "model_unavailable":
                parts.insert(0, f'<p style="color:#b71c1c"><b>Local model unavailable:</b> '
                                f'{html.escape(answer.model_message)}</p>')
            if answer.draft:
                parts.append(render_failed_draft_html(answer.draft, answer.draft_check))
        else:
            parts.append(f"<p><b>{html.escape(answer.text)}</b></p>")
            if answer.found:
                parts.append("<p>Closest passages found (not enough to answer):</p><ul>" +
                             "".join(f"<li>{html.escape(f)}</li>" for f in answer.found) + "</ul>")
            if answer.not_found:
                parts.append("<ul>" + "".join(f"<li>{html.escape(f)}</li>" for f in answer.not_found) + "</ul>")
        self.answer_view.setHtml("".join(parts))
        self.notes_label.setText("\n".join(answer.notes))
        self._fill_evidence(answer.evidence)
        detail = ""
        if answer.state == "ready" and answer.check is not None:
            detail = f"{answer.check.label} · {ka.SEMANTIC_LABEL}"
            if answer.draft:
                detail = "extractive answer kept · model draft failed citation checks"
        elif answer.state == "model_unavailable":
            detail = answer.model_state or ""
        self._set_state(answer.state if answer.state in STATE_STYLE else "error", detail)

    def _fill_evidence(self, evidence):
        self.evidence_table.setRowCount(len(evidence))
        for row, item in enumerate(evidence):
            review = item.review_status + (" (OCR)" if item.method == "ocr" else "")
            found_by = ", ".join(f"{k} #{v}" for k, v in sorted(item.ranks.items(), key=lambda kv: kv[1]))
            passage = " ".join(item.text.split())
            flagged = item.instruction_like or item.page_instruction_like
            values = (item.label + (" ⚠" if flagged else ""), item.file_name, f"{item.page_no} ({item.location})",
                      review, f"{item.coverage:.0%}", found_by, passage[:160] + ("…" if len(passage) > 160 else ""))
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column == 6:
                    cell.setToolTip(item.text[:2000])
                if column == 0:
                    cell.setData(Qt.UserRole, row)
                    if flagged:
                        cell.setForeground(QColor("#b71c1c"))
                        cell.setToolTip("Instruction-like text on this page: treated as data only")
                self.evidence_table.setItem(row, column, cell)

    def _citation_clicked(self, url: QUrl):
        label = url.toString().partition(":")[2]
        if self.last_answer is None:
            return
        for row, item in enumerate(self.last_answer.evidence):
            if item.label == label:
                self.evidence_table.selectRow(row)
                self.open_evidence_row(row)
                return

    def open_evidence_row(self, row) -> bool:
        if self.last_answer is None or not 0 <= row < len(self.last_answer.evidence):
            return False
        item = self.last_answer.evidence[row]
        self.open_evidence_requested.emit(item.document_id, item.page_no, item.start, item.end, item.text_version)
        return True

    # -------------------------------------------------------------- model
    def check_model(self):
        self._generation_status = getattr(self, "_generation_status", 0) + 1
        adapter = self._adapter()
        self.model_label.setText("Local model: checking…")
        self.check_model_button.setEnabled(False)
        self.status_worker = StatusWorker(self._generation_status, adapter, self)
        self.status_worker.done.connect(self._status_done)
        self.status_worker.start()

    def _status_done(self, generation, status):
        worker, self.status_worker = self.status_worker, None
        if worker is not None:
            worker.deleteLater()
        self.check_model_button.setEnabled(True)
        if generation != getattr(self, "_generation_status", 0):
            return
        self.apply_model_status(status)

    def apply_model_status(self, status: ll.ModelStatus):
        self.model_status = status
        for combo, current in ((self.chat_model_combo, status.chat_model), (self.embed_model_combo, status.embed_model)):
            text = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(status.local_models)
            combo.setEditText(text if text else (current or ""))
            combo.blockSignals(False)
        lines = []
        if status.state == ll.READY:
            lines.append(f"Local model: {status.message} (Ollama {status.server_version}).")
        else:
            lines.append(f"Local model unavailable: {status.message}.")
            if status.state in (ll.NOT_RUNNING, ll.MODEL_MISSING, ll.NOT_CONFIGURED, ll.REMOTE_REJECTED):
                lines.append(ll.SETUP_GUIDANCE)
        if status.rejected_models:
            lines.append("Refused (would run outside this computer): " + ", ".join(status.rejected_models))
        self.model_label.setText("\n".join(lines))
        self.use_model_check.setEnabled(status.chat_ready)
        if not status.chat_ready:
            self.use_model_check.setChecked(False)
        self.build_semantic_button.setEnabled(status.embed_ready and self.semantic_worker is None)
        if not status.embed_ready:
            self.semantic_label.setText("Semantic retrieval unavailable: " + (
                "no local embedding model configured" if status.embed_state == ll.NOT_CONFIGURED else
                f"embedding model state '{status.embed_state}'") + ". Keyword retrieval works.")

    def build_semantic_index(self):
        if self.semantic_worker is not None:
            self._semantic_cancel.cancel()
            return
        try:
            snapshot = kr.read_corpus(self.db_manager)
        except Exception as exc:
            self.semantic_label.setText(f"Semantic index not built: pages could not be read ({type(exc).__name__})")
            return
        adapter = self._adapter()
        store = self._embedding_store()
        index = kr.KnowledgeIndex(snapshot, embedding_store=store, embed_model=adapter.embed_model)
        self._index, self._snapshot_signature = index, snapshot.signature
        self._semantic_cancel = ll.CancelToken()
        self.semantic_worker = SemanticBuildWorker(index, adapter, store, self._semantic_cancel, self)
        self.semantic_worker.progress.connect(
            lambda d, t: self.semantic_label.setText(f"Building semantic index… {d}/{t} passages (not ready yet)"))
        self.semantic_worker.done.connect(self._semantic_done)
        self.build_semantic_button.setText("Cancel semantic build")
        self.semantic_worker.start()

    def _semantic_done(self, result):
        worker, self.semantic_worker = self.semantic_worker, None
        if worker is not None:
            worker.deleteLater()
        self.build_semantic_button.setText("Build semantic index")
        state = result.get("state")
        if state == "complete":
            self.semantic_label.setText(f"Semantic retrieval ready: {result['total']} passages embedded locally.")
        elif state == "cancelled":
            self.semantic_label.setText(f"Semantic build cancelled at {result['done']}/{result['total']} - "
                                        "not used until complete (Build again to resume).")
        else:
            self.semantic_label.setText(f"Semantic index not built: {result.get('message', state)}. "
                                        "Keyword retrieval works.")

    # ------------------------------------------------------------ cleanup
    def cleanup(self):
        self._stop_worker()
        if self._semantic_cancel is not None:
            self._semantic_cancel.cancel()
        for worker in [self.semantic_worker, self.status_worker, *self._old_workers]:
            if worker is not None:
                worker.wait(5000)
        if self._index is not None:
            self._index.close()
        if self._store is not None:
            self._store.close()
            self._store = None
