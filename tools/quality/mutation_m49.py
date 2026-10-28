#!/usr/bin/env python3
"""Repeatable mutation run for the M49 Knowledge Assistant and cache contracts.

Each mutant puts ONE old behaviour (or removes one guard) in a scratch copy of
the working tree and must be KILLED by the listed tests. The engine (copy,
exact-once snippet check, baseline run, JSON report, exit status) is the M46
one: ``tools/quality/mutation_m46.py``. The repository is never modified.

Usage::

    python tools/quality/mutation_m49.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh). SYNTHETIC test data only; the "model" in the tests
is a fake loopback server - it isolates the external dependency, never
product logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

KR = "core/knowledge_retrieval.py"
KA = "core/knowledge_answer.py"
LLM = "core/local_llm.py"
LIB = "core/document_library.py"
EV = "core/analysis_evidence.py"
PANEL = "tabs/knowledge_assistant.py"
DOCS = "tabs/documents_tab.py"
T_LLM = ["tests/test_m49_local_llm.py"]
T_RET = ["tests/test_m49_knowledge_retrieval.py"]
T_ANS = ["tests/test_m49_knowledge_answer.py"]
T_GOLD = ["tests/test_m49_knowledge_gold.py"]
T_UI = ["tests/test_m49_knowledge_ui.py"]
T_CACHE = ["tests/test_m49_cache_integrity.py"]
T_CORE = T_RET + T_ANS + T_GOLD

MUTANTS = [
    # ------------------------------------------------------------ scope / approval / provenance
    Mutant("K-scope-filter-dropped", KR,
           "            if page.document_id in documents and (page_no is None or page.page_no == page_no):",
           "            if (page_no is None or page.page_no == page_no):",
           T_CORE, "the scope filter is dropped: every document is searchable from a well/report scope"),
    Mutant("K-approval-ignored", KR,
           "        if status not in APPROVED_STATUSES:",
           "        if False:",
           T_RET + T_GOLD, "pages rejected at review (not approved) become answerable"),
    Mutant("K-wrong-page-id", KA,
           "page.document_id, page.file_name, page.page_id, page.page_no, page.location,",
           "page.document_id, page.file_name, page.page_id, page.page_no + 1, page.location,",
           T_ANS + T_GOLD + T_UI, "evidence cites the wrong page number"),
    Mutant("K-stale-corpus-signature", KR,
           "        return (NORMALIZATION_VERSION, CHUNKER_VERSION, RETRIEVAL_VERSION) + pages + (audit, link_digest)",
           "        return (NORMALIZATION_VERSION, CHUNKER_VERSION, RETRIEVAL_VERSION) + pages + (link_digest,)",
           T_RET + T_UI, "a delete + same-size re-import keeps the stale knowledge index (document changed)"),
    Mutant("K-library-signature-m44", LIB,
           "                func.sum(func.length(DocumentPage.text))).one()) + (audit,)",
           "                func.sum(func.length(DocumentPage.text))).one())",
           T_RET, "the M44 library search keeps a stale FTS index after delete + same-size re-import"),
    # ------------------------------------------------------------ loopback-only adapter
    Mutant("L-remote-host-allowed", LLM,
           "    if host not in LOOPBACK_NAMES:",
           "    if False:",
           T_LLM, "a remote model host is accepted"),
    Mutant("L-remote-model-accepted", LLM,
           '    if entry.get("remote_host") or entry.get("remote_model"):\n        return True',
           '    if False:\n        return True',
           T_LLM, "a cloud/remote model listed by the local server is offered as local"),
    Mutant("L-remote-stream-accepted", LLM,
           '                if chunk.get("remote_host") or chunk.get("remote_model"):',
           "                if False:",
           T_LLM, "an answer streamed from a remote (cloud) model is accepted"),
    Mutant("L-tool-calls-accepted", LLM,
           '                if message.get("tool_calls"):',
           "                if False:",
           T_LLM, "a model tool-call request is not refused"),
    Mutant("L-proxy-honoured", LLM,
           "urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())",
           "urllib.request.build_opener(_NoRedirect())",
           T_LLM, "HTTP(S)_PROXY environment variables route loopback traffic through a proxy"),
    Mutant("L-abort-closes-response", LLM,
           "    try:\n        handle = sock.detach()",
           "    response.close()\n    try:\n        handle = sock.detach()",
           T_LLM, "cancel closes the http.client response from the UI thread (waits for the reader's lock)"),
    Mutant("L-abort-handle-left-open", LLM,
           "            socket.close(handle)",
           "            pass",
           T_LLM, "cancel only shuts the socket down (does not wake a blocked Windows read)"),
    Mutant("L-connect-timeout-is-timeout", LLM,
           'raise LocalLLMError(NOT_RUNNING, f"No local model server accepted a connection',
           'raise LocalLLMError(TIMEOUT, f"No local model server accepted a connection',
           T_LLM, "a loopback connection that is never accepted is reported as a hung server"),
    # ------------------------------------------------------------ answers / citations
    Mutant("A-fake-citation-accepted", KA,
           "        unknown = [r for r in refs if r not in labels]",
           "        unknown = []",
           T_ANS, "an invented source [S9] is not reported"),
    Mutant("A-uncited-sentence-accepted", KA,
           "        if not refs:\n            check.fail(\"claims_cited\"",
           "        if False:\n            check.fail(\"claims_cited\"",
           T_ANS, "a sentence without any citation passes validation"),
    Mutant("A-number-unchecked", KA,
           "            if number not in source_numbers:",
           "            if False:",
           T_ANS, "a number absent from the cited source passes validation"),
    Mutant("A-error-becomes-no-evidence", KA,
           "        # The evidence and the extractive answer stay available; the failure is explicit.\n",
           '        return Answer("no_evidence", "none", NO_EVIDENCE_TEXT["no_evidence"], evidence, retrieval,'
           " notes=notes)\n",
           T_ANS + T_UI, "a model error is shown as 'insufficient evidence'"),
    Mutant("A-injection-ignored", KA,
           "    return any(p.search(text) or p.search(folded) for p in INJECTION_PATTERNS)",
           "    return False",
           T_ANS + T_GOLD, "instruction-like document text is not detected"),
    Mutant("A-injection-quoted", KA,
           "_PARAGRAPHS.split(item.text) if not detect_instructions(paragraph)\n",
           "_PARAGRAPHS.split(item.text) if True\n",
           T_ANS + T_GOLD, "an instruction-like sentence is quoted as the answer"),
    Mutant("A-flag-note-dropped", KA,
           "    if flagged:\n        notes.append(",
           "    if False:\n        notes.append(",
           T_ANS + T_UI, "the user is not told a source contains instruction-like text"),
    Mutant("A-absence-unchecked", KR,
           "            result.absent_terms = self.absent_terms(terms, expansions_by_term, allowed, codes)",
           "            result.absent_terms = list(terms)",
           T_ANS + T_UI, "insufficient evidence claims stored words are missing (screenshot-review defect)"),
    # ------------------------------------------------------------ retrieval guards
    Mutant("R-identifier-weight-removed", KR,
           "        if df == 0 and term not in strict and not term.isdigit():",
           "        if df == 0:",
           T_CORE, "an unknown identifier/number weighs like an ordinary word (loose false answers)"),
    Mutant("R-size-rule-removed", KR,
           "            if sizes and not sizes <= self._sizes(chunk_id):",
           "            if False:",
           T_ANS + T_GOLD, "a question about a 17-1/2 in section is answered with the 12-1/4 in value"),
    Mutant("R-size-absence-unreported", KR,
           '                [f"{s} in" for s in sorted(sizes) if not any(s in self._sizes(cid) for cid in allowed)]',
           "                []",
           T_ANS, "insufficient evidence does not say that the asked size occurs in no passage"),
    Mutant("R-coverage-threshold-removed", KR,
           "        if not hits or result.best_coverage < SUFFICIENT_COVERAGE:",
           "        if not hits:",
           T_CORE, "weakly related passages are presented as an answer"),
    Mutant("R-dedupe-removed", KR,
           "            if seen_pages[chunk.page_id] >= 2:",
           "            if False:",
           T_RET, "one page floods the evidence list"),
    Mutant("R-partial-semantic-ready", KR,
           "        return self.build_dims(model, signature) is not None",
           "        return True",
           T_RET, "a partial/cancelled semantic index is reported ready"),
    Mutant("R-dimension-mismatch-used", KR,
           "            if built != len(query_vector):",
           "            if False:",
           T_RET, "vectors of another dimension are compared after a model change"),
    Mutant("R-store-writes-foreign-db", KR,
           "        if foreign:",
           "        if False:",
           T_RET, "the embedding cache creates tables inside the application database"),
    Mutant("R-rrf-constant", KR,
           "\nRRF_K = 60\n",
           "\nRRF_K = 1\n",
           T_RET, "the documented RRF constant k=60 is changed"),
    # ------------------------------------------------------------ UI: stale answers / citations
    Mutant("U-generation-guard-removed", PANEL,
           "        if generation != self._generation:\n            return                                  # stale",
           "        if False:\n            return                                  # stale",
           T_UI, "an answer that finished after a scope/question change is shown"),
    Mutant("U-invalidate-noop", PANEL,
           '        """Question/scope/library changed: drop any shown or pending answer."""\n',
           '        """Question/scope/library changed: drop any shown or pending answer."""\n        return\n',
           T_UI, "changing scope/question/library keeps the old answer on screen"),
    Mutant("U-scope-change-keeps-answer", PANEL,
           '    def _scope_changed(self, _index):\n        self._fill_targets()\n        self._invalidate("scope")',
           '    def _scope_changed(self, _index):\n        self._fill_targets()',
           T_UI, "a scope change alone does not clear the answer"),
    Mutant("U-open-wrong-span", DOCS,
           '        fmt.setBackground(QColor("#b3e5fc"))\n        cursor = QTextCursor(self.viewer.document())\n'
           "        cursor.setPosition(utf16_offset(text, start))",
           '        fmt.setBackground(QColor("#b3e5fc"))\n        cursor = QTextCursor(self.viewer.document())\n'
           "        cursor.setPosition(utf16_offset(text, 0))",
           T_UI, "opening a citation highlights from the page start, not the cited passage"),
    Mutant("U-disabled-looks-enabled", PANEL,
           '            "QPushButton#knowledgeAsk:disabled { background-color: #b0bec5; color: #eceff1; }")',
           '            "")',
           T_UI, "the busy (disabled) Ask button looks enabled"),
    # ------------------------------------------------------------ M48 cache P0
    Mutant("P-revision-ids-only", EV,
           "        return [model.__table__.c[name] for name in model.__table__.c.keys()]",
           '        return [model.__table__.c["id"]]',
           T_CACHE, "the analysis cache key ignores edited values (M48-style summary)"),
    Mutant("P-cost-not-fingerprinted", EV,
           "(Wellbore, Section, DailyReport, DrillingParameters, MudReport, CostRecord, SafetyReport)",
           "(Wellbore, Section, DailyReport, DrillingParameters, MudReport, SafetyReport)",
           T_CACHE, "a currency-only cost change is not detected"),
    Mutant("P-npt-not-fingerprinted", EV,
           "    parts.append(_rows_digest(\n",
           "    0 and parts.append(_rows_digest(\n",
           T_CACHE, "an NPT code/category-only change is not detected"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
