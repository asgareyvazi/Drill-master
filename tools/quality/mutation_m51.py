#!/usr/bin/env python3
"""Repeatable mutation run for the M51 contracts.

Each mutant puts ONE old behaviour back (or removes one guard) in a scratch
copy of the working tree and must be KILLED by the listed tests.  The engine
(copy, exact-once snippet check, baseline run, JSON report, exit status) is the
M46 one: ``tools/quality/mutation_m46.py``.  The repository is never modified.

Usage::

    python tools/quality/mutation_m51.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh).  SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

W12 = "tabs/w12_Analysis.py"
KR = "core/knowledge_retrieval.py"
KA = "core/knowledge_answer.py"
KP = "tabs/knowledge_assistant.py"
GC = "core/qt_gc.py"
T_AN = ["tests/test_m51_analysis_snapshot.py"]
T_KC = ["tests/test_m51_knowledge_corpus.py"]
T_AI = ["tests/test_m51_answer_integrity.py"]
T_QR = ["tests/test_m51_query_refinement.py"]
T_VER = ["tests/test_m51_verifier.py"]
T_GC = ["tests/test_m51_gc_soak.py"]

MUTANTS = [
    # ------------------------------------------------------------ §3 Analysis: every read on a worker
    Mutant("AN-cycle-read-on-gui-thread", W12,
           "        if not self._uses_revision_worker():\n            self._update_all_data_sync()\n            return\n"
           "        worker = self._rev_worker",
           "        if True:\n            self._update_all_data_sync()\n            return\n        worker = self._rev_worker",
           T_AN, "a file database is read synchronously on the GUI thread again (pre-M51 cycle)"),
    Mutant("AN-missing-value-read-on-gui", W12,
           "        elif self._uses_revision_worker():\n"
           "            # File database: never read on the GUI thread; a snapshot paints it.",
           "        elif False:\n"
           "            # File database: never read on the GUI thread; a snapshot paints it.",
           T_AN, "a value the snapshot did not carry is read on the GUI thread instead of by a snapshot"),
    Mutant("AN-snapshot-generation-guard-removed", W12,
           "        if generation != self._generation or not self.current_well_id:",
           "        if not self.current_well_id:",
           T_AN, "a snapshot read for the previous scope is painted for the new one"),
    Mutant("AN-late-worker-after-dispose", W12,
           "        self._cancel_revision(wait_ms=5000)",
           "        self._rev_worker = None",
           T_AN, "closing the page drops the worker without cancel/invalidate: its late result starts work"),
    Mutant("AN-snapshot-uses-gui-engine", W12,
           "            with worker_database(self.db_manager) as isolated:     # own read-only engine (M47)",
           "            with __import__('contextlib').nullcontext(self.db_manager) as isolated:",
           T_AN, "the snapshot worker reads through the GUI's engine instead of its own read-only one"),
    Mutant("AN-read-error-as-no-data", W12,
           "                values[name] = _LoadError(exc)",
           "                values[name] = None",
           T_AN, "a failed read on the worker is painted as No data instead of a read error"),
    # ------------------------------------------------------------ §4 corpus off the GUI thread, never stale
    Mutant("K-stale-source-same-length-edit", KR,
           '        digest.update(hashlib.sha256((text or "").encode("utf-8")).digest())\n',
           "        pass\n",
           T_KC, "a same-length text edit keeps the old signature: the old passage is answered"),
    Mutant("K-review-status-not-in-signature", KR,
           "        digest.update(repr((page_id, doc_id, page_no, location, method, status)).encode(\"utf-8\"))",
           "        digest.update(repr((page_id, doc_id, page_no, location, method)).encode(\"utf-8\"))",
           T_KC, "un-approving a page keeps the old signature: an unapproved page can still be cited"),
    Mutant("K-corpus-read-on-gui-thread", KP,
           "        on_worker = _reads_on_worker(self.db_manager)",
           "        on_worker = False",
           T_KC, "the corpus signature and snapshot are read on the GUI thread again"),
    Mutant("K-signature-change-keeps-index", KP,
           "        if self._index is not None and signature != self._snapshot_signature:\n            self._index = None",
           "        if False:\n            self._index = None",
           T_KC, "a changed library signature keeps the stale index and shown answer"),
    # ------------------------------------------------------------ §5 false answers
    Mutant("K-wrong-well-accepted", KR,
           "            if codes and not self.identity_ok(chunk_id, codes):",
           "            if False:",
           T_AI, "a passage about another well answers a question that names a well"),
    Mutant("K-partial-overlap-answered", KR,
           "            if absent_topic:\n                cov = min(cov, ABSENT_TERM_CAP)",
           "            if False:\n                cov = min(cov, ABSENT_TERM_CAP)",
           T_AI, "a question word found nowhere in scope no longer blocks an answer (partial overlap answered)"),
    Mutant("K-code-only-overlap-sufficient", KR,
           "        topic = [t for t in terms if t not in code_parts] or terms",
           "        topic = terms",
           T_AI, "sharing only the well code counts toward sufficiency again"),
    Mutant("K-persian-ignore-rules-unflagged", KA,
           '    r"(دستور|دستورالعمل|قانون|قوانین|قواعد|راهنمایی|پیام|پرامپت)\\S*\\s+(\\S+\\s+){0,2}(را\\s+)?'
           '(نادیده|فراموش)\\s*(بگیر|کن)",\n',
           "",
           T_AI, "a Persian 'ignore the instructions' sentence is not flagged"),
    Mutant("K-flagged-sentence-quoted", KA,
           "    sentences = [s.strip() for paragraph in _PARAGRAPHS.split(item.text) if not detect_instructions(paragraph)",
           "    sentences = [s.strip() for paragraph in _PARAGRAPHS.split(item.text) if True",
           T_AI, "an instruction-like (e.g. Persian) sentence is quoted in the answer"),
    Mutant("K-procedure-flagged", KA,
           '    r"(دستور(?!العمل)|فرمان|کد|اسکریپت)',
           '    r"(دستور|فرمان|کد|اسکریپت)',
           T_AI, "an ordinary Persian procedure ('دستورالعمل ... اجرا کنید') is flagged as an injection"),
    # ------------------------------------------------------------ §7 refinement never broadens scope
    Mutant("Q-suggestions-from-all-scopes", KR,
           "        allowed = self.candidate_chunks(retrieval.scope, retrieval.target, retrieval.page_filter)\n"
           "        if not allowed:\n            return [], []",
           "        allowed = self.candidate_chunks(SCOPE_ALL, None)\n        if not allowed:\n            return [], []",
           T_QR, "suggestions are taken from documents outside the selected scope"),
    Mutant("Q-refined-search-broadens-scope", KP,
           "        return self._start(effective, scope, target, (terms, list(replaces)))",
           "        return self._start(effective, kr.SCOPE_ALL, None, (terms, list(replaces)))",
           T_QR, "the refined search runs on all documents instead of the selected scope"),
    Mutant("Q-blocking-word-kept", KA,
           "    dropped = {t for t in replaces if t and not any(ch.isdigit() for ch in t)}",
           "    dropped = set()",
           T_QR, "the misspelled word stays in the refined query, so the refinement can never help"),
    Mutant("Q-numbers-replaced", KA,
           "    dropped = {t for t in replaces if t and not any(ch.isdigit() for ch in t)}",
           "    dropped = {t for t in replaces if t}",
           T_QR, "a refinement can drop a number from the question"),
    Mutant("Q-stale-result-kept", KP,
           "        self._last_request = (question, scope, target, refinement)\n"
           "        if self.worker is not None:\n            self._stop_worker()\n        self._clear_results()\n",
           "        self._last_request = (question, scope, target, refinement)\n"
           "        if self.worker is not None:\n            self._stop_worker()\n",
           T_QR, "the previous result stays on screen while the refined search runs"),
    Mutant("Q-retry-drops-refinement", KP,
           "        return self._start(*request)",
           "        return self.ask()",
           T_QR, "Retry silently runs the unrefined question"),
    # ------------------------------------------------------------ §8 verifier dimensions
    Mutant("V-other-well-accepted", KA,
           "            if not any(kr._contains(list(entity), list(code)) for r in valid for entity in labels[r].entities):",
           "            if False:",
           T_VER, "a draft naming another well than the cited source passes the citation checks"),
    Mutant("V-edited-source-accepted", KA,
           "            elif page.text_sha != item.text_version or page.text[item.start:item.end] != item.text:",
           "            elif False:",
           T_VER, "a citation to a passage edited after retrieval passes"),
    Mutant("V-snapshot-not-checked", KA,
           "    extractive_check = validate_citations(extractive, evidence, tuple(retrieval.conflicts), index.snapshot)",
           "    extractive_check = validate_citations(extractive, evidence, tuple(retrieval.conflicts))",
           T_VER, "answers are no longer checked against the stored source text"),
    Mutant("V-code-digits-are-numbers", KA,
           '    folded = _ENTITY_CODE.sub(" ", kr.fold(text))',
           "    folded = kr.fold(text)",
           T_VER, "the digits of a well code are checked as quantities (false citation failures)"),
    # ------------------------------------------------------------ §9 GC policy watchdog
    Mutant("G-collected-on-worker", GC,
           "        gc.callbacks.append(self._watch)\n        gc.disable()\n",
           "        gc.callbacks.append(self._watch)\n",
           T_GC, "automatic collection stays on: cycles are collected on worker threads"),
    Mutant("G-watchdog-blind", GC,
           '        if phase == "start" and threading.current_thread() is not self._gui_thread:',
           "        if False:",
           T_GC, "a collection on a worker thread goes unnoticed"),
    Mutant("G-reenable-not-healed", GC,
           "        if gc.isenabled():\n            self.reenabled += 1",
           "        if False:\n            self.reenabled += 1",
           T_GC, "automatic collection re-enabled by other code stays on"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
