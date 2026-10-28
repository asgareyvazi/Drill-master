#!/usr/bin/env python3
"""Repeatable mutation run for the M50 contracts.

Each mutant puts ONE old behaviour (or removes one guard) in a scratch copy of
the working tree and must be KILLED by the listed tests. The engine (copy,
exact-once snippet check, baseline run, JSON report, exit status) is the M46
one: ``tools/quality/mutation_m46.py``. The repository is never modified.

Usage::

    python tools/quality/mutation_m50.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh). SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

W12 = "tabs/w12_Analysis.py"
EV = "core/analysis_evidence.py"
GC = "core/qt_gc.py"
APP = "app.py"
T_ASYNC = ["tests/test_m50_analysis_async.py"]
KR = "core/knowledge_retrieval.py"
KA = "core/knowledge_answer.py"
T_RET = ["tests/test_m50_knowledge_retrieval.py", "tests/test_m50_knowledge_gold.py"]
T_VER = ["tests/test_m50_verifier.py", "tests/test_m50_citation_navigation.py", "tests/test_m49_knowledge_answer.py"]
DT = "tabs/documents_tab.py"
V3D = "tabs/trajectory_3d_view.py"
AIM = "core/ai_import_mapper.py"
T_LEG = ["tests/test_m50_legacy_ai_importer.py", "tests/test_release_smoke.py"]
T_3D = ["tests/test_m50_trajectory_3d_disposal.py", "tests/test_trajectory_3d.py",
        "tests/test_trajectory_3d_lifecycle_m46.py"]

MUTANTS = [
    # ------------------------------------------------------------ P0: Analysis revision off the GUI thread
    Mutant("N-synchronous-fingerprint", W12,
           "        if not self._uses_revision_worker():\n            self._update_all_data_sync()",
           "        if True:\n            self._update_all_data_sync()",
           T_ASYNC, "the data revision is computed on the GUI thread again (M49 behaviour)"),
    Mutant("N-sequence-guard-removed", W12,
           "        if seq != self._rev_seq:\n            return                                  # superseded",
           "        if False:\n            return                                  # superseded",
           T_ASYNC, "a superseded (late) revision result is accepted and painted"),
    Mutant("N-generation-guard-removed", W12,
           "        if generation != self._generation or not self.current_well_id:",
           "        if not self.current_well_id:",
           T_ASYNC, "a revision requested before a scope change is painted for the new scope"),
    Mutant("N-verify-skipped", W12,
           '            self._start_revision("verify", painted=revision, reloads=reloads)\n            return',
           "            self._finish_status([])\n            return",
           T_ASYNC, "no second revision: a write committed during the load is shown as Updated"),
    Mutant("N-verify-mismatch-accepted", W12,
           "        if revision == painted:",
           "        if True:",
           T_ASYNC, "a changed revision after the load is accepted (concurrent edit ignored)"),
    Mutant("N-reload-limit-removed", W12,
           "        if reloads >= self._MAX_RELOADS:",
           "        if False:",
           T_ASYNC, "continuous edits are retried without bound and then reported as Updated"),
    Mutant("N-cleanup-leaves-worker", W12,
           "        self._cancel_revision(wait_ms=5000)",
           "        pass",
           T_ASYNC, "closing the page leaves the revision thread running"),
    Mutant("N-cancel-not-polled", EV,
           "        if cancelled is not None and count % _CANCEL_CHECK_ROWS == 0 and cancelled():",
           "        if False:",
           T_ASYNC, "a cancelled revision scan runs to the end"),
    Mutant("N-old-values-while-loading", W12,
           "            self._show_loading_values()\n",
           "            pass\n",
           T_ASYNC, "the previous well's numbers stay on screen while the new well loads"),
    Mutant("N-worker-not-retained", W12,
           "        _LIVE_REVISION_WORKERS.add(worker)\n",
           "",
           T_ASYNC, "unsafe Qt order: a running QThread can be destroyed when its page drops it"),
    Mutant("N-worker-uses-gui-engine", W12,
           "            with worker_database(self.db_manager) as reader:",
           "            with __import__('contextlib').nullcontext(self.db_manager) as reader:",
           T_ASYNC, "the worker reads through the GUI's engine instead of its own read-only one"),
    Mutant("N-error-shown-as-updated", W12,
           '            if error:\n                failed.append(f"read data revision ({error})")',
           "            if error:\n                pass",
           T_ASYNC, "a failed revision read is reported as Updated"),
    # ------------------------------------------------------------ GC only on the GUI thread
    Mutant("G-automatic-gc-left-on", GC,
           "        gc.disable()\n",
           "",
           T_ASYNC, "cyclic GC can run on worker threads (captured deadlock)"),
    Mutant("G-app-does-not-install", APP,
           "        qt_gc.install(self)\n",
           "",
           T_ASYNC, "the application never installs the GUI-thread GC policy"),
    Mutant("G-collect-never-runs", GC,
           "        if count0 > self.threshold[0]:",
           "        if False:",
           T_ASYNC, "with automatic GC off, reference cycles are never reclaimed"),
    # ------------------------------------------------------------ P0: retrieval v3 (each general rule)
    Mutant("R-context-ignored", KR,
           "            hit = term in context or any(phrase_in(toks, form) for form in forms)",
           "            hit = any(phrase_in(toks, form) for form in forms)",
           T_RET, "a well code named in the page header / file name no longer covers the page's chunks"),
    Mutant("R-context-loose-parts", KR,
           "            if _contains(self._page_tokens.get(page_id, []), list(code)) or \\",
           "            if all(part in self._page_tokens.get(page_id, []) for part in code) or \\",
           T_RET, "code parts scattered on the page (a date '05', a crew 'KE') count as the well code"),
    Mutant("R-file-name-context-dropped", KR,
           "                    _contains(self._name_tokens.get(page_id, []), list(code)):",
           "                    False:",
           T_RET, "a well code that only the file name states is ignored (Q19)"),
    Mutant("R-absent-ignores-context", KR,
           "            context = self.context_covered(self.chunks[cid].page_id, codes) if codes else frozenset()",
           "            context = frozenset()",
           T_RET, "the insufficient-evidence message claims a well code is missing that the file name states"),
    Mutant("R-answer-type-cap-removed", KR,
           "            if kinds and self.answer_type_missing(kinds, chunk_id):",
           "            if False:",
           T_RET, "a passage without the asked quantity (no time / temperature) can be sufficient"),
    Mutant("R-frame-words-kept", KR,
           "    kept = [t for t in terms if t not in frame_words]",
           "    kept = list(terms)",
           T_RET, "'how long ... take' keeps 'long'/'take' as required content words (Q09)"),
    Mutant("R-named-quantity-not-required", KR,
           "        if framed or any(phrase_in(terms, list(noun)) for noun in kind.nouns):",
           "        if framed:",
           T_RET, "'mud temperature in X' can be answered by a mud-weight passage"),
    Mutant("R-sufficiency-rerank-removed", KR,
           "        candidates.sort(key=lambda c: c[3] < SUFFICIENT_COVERAGE)",
           "        candidates.sort(key=lambda c: 0)",
           T_RET, "header-only passages push the answering passage out of the top k"),
    Mutant("R-designation-read-as-value", KR,
           '                if match.group(2) == "in" and _DESIGNATED.match(tail, match.end()):',
           "                if False:",
           T_RET, "'the 16 in section' is read as the quantity: real conflicts are missed"),
    Mutant("R-glossary-m50-entries-removed", KR,
           "mud pump | پمپ گل\nrepair | تعمیر\nduration | مدت | طول کشید\n",
           "",
           T_RET, "the M50 glossary entries are dropped: English pump-repair questions miss Persian reports"),
    Mutant("R-glossary-daily-report-removed", KR,
           "daily report | گزارش روزانه\n",
           "",
           T_RET, "'daily report' no longer reaches Persian daily reports"),
    Mutant("R-version-not-bumped", KR,
           "RETRIEVAL_VERSION = 3 ",
           "RETRIEVAL_VERSION = 2 ",
           T_RET, "retrieval rules changed but cached indexes keyed on the version are not invalidated"),
    Mutant("A-sentence-inherits-any-size", KA,
           "                                   context | (size_tokens if not kr.size_designations(s) else frozenset()))[0], i, s)",
           "                                   context | size_tokens)[0], i, s)",
           T_RET, "a sentence about another size (13-3/8 in LOT) is quoted for the asked size"),
    Mutant("A-instruction-paragraph-leaks", KA,
           "    sentences = [s.strip() for paragraph in _PARAGRAPHS.split(item.text) if not detect_instructions(paragraph)",
           "    sentences = [s.strip() for paragraph in _PARAGRAPHS.split(item.text)",
           T_RET, "the follow-on sentence of a detected instruction paragraph is quoted as an answer"),
    # ------------------------------------------------------------ P0: verifier dimensions + citation navigation
    Mutant("V-units-unchecked", KA,
           "        if not occurrences:\n            other = sorted(",
           "        if False:\n            other = sorted(",
           T_VER, "1.42 ppg passes against a source that says 1.42 sg"),
    Mutant("V-relationship-unchecked", KA,
           "        if not any(_links(words, kr.words(_qualifying_span(src_folded[k], src_values[k], j)))",
           "        if False and not any(_links(words, kr.words(_qualifying_span(src_folded[k], src_values[k], j)))",
           T_VER, "'the flow rate is 3200 psi' passes because 3200 psi is the standpipe pressure"),
    Mutant("V-generic-qualifier-links", KA,
           "    return [w for w in kr.words(segment) if w not in kr.STOPWORDS and w not in _GENERIC_QUALIFIERS",
           "    return [w for w in kr.words(segment) if w not in kr.STOPWORDS",
           T_VER, "a shared 'planned' links the flow rate to the mud weight's value"),
    Mutant("V-sizes-unchecked", KA,
           "        for size in sorted(sizes - available):",
           "        for size in []:",
           T_VER, "an 8-1/2 in statement passes against a 12-1/4 in source"),
    Mutant("V-conflict-undisclosed-accepted", KA,
           "        if missing:\n            check.fail(\"conflicts_disclosed\"",
           "        if False:\n            check.fail(\"conflicts_disclosed\"",
           T_VER, "a draft stating one side of a conflict passes"),
    Mutant("V-failed-draft-replaces-answer", KA,
           "    if not check.citation_checks_passed:\n        # A failed draft never becomes the answer",
           "    if False:\n        # A failed draft never becomes the answer",
           T_VER, "a draft that failed the citation checks is returned as the answer (M49 behaviour)"),
    Mutant("V-semantic-claimed", KA,
           "    semantic_verified: bool = False                 # always False: there is no entailment check",
           "    semantic_verified: bool = True                  # always False: there is no entailment check",
           T_VER, "an answer claims semantic verification that does not exist"),
    Mutant("V-conflict-sides-capped", KA,
           "    usable = sorted(conflicting + strongest[:max(0, max_sources - len(conflicting))],",
           "    usable = sorted((conflicting + strongest)[:max_sources],",
           T_VER, "the source cap hides one side of a conflict (contradicts the M49 docstring)"),
    Mutant("V-conflicts-across-sizes", KR,
           "            by_key[(phrase, unit, sizes)].append((value, hit.chunk.chunk_id, hit.page.document_id))",
           "            by_key[(phrase, unit, frozenset())].append((value, hit.chunk.chunk_id, hit.page.document_id))",
           T_VER, "1.08 sg for 16 in and 1.25 sg for 12-1/4 in are reported as a conflict"),
    Mutant("V-changed-page-highlighted", DT,
           '        if text_sha and hashlib.sha256((page["text"] or "").encode("utf-8")).hexdigest() != text_sha:',
           "        if False:",
           T_VER, "a page edited after the answer is highlighted as if it were the cited text"),
    Mutant("V-panel-drops-text-version", "tabs/knowledge_assistant.py",
           "item.start, item.end, item.text_version)",
           'item.start, item.end, "")',
           T_VER, "the panel stops sending the cited text version, so changed pages are highlighted"),
    # ------------------------------------------------------------ P1: Windows 3D lifecycle (§8)
    Mutant("W-destroyed-release-dropped", V3D,
           "            self.destroyed.connect(functools.partial(",
           "            (functools.partial(",
           T_3D, "a destroyed view leaves its Qt canvas and widgets to a later garbage collection"),
    Mutant("W-figure-keeps-qt-canvas", V3D,
           "    base_canvas_class(figure)        # the figure now points at a plain, Qt-free canvas",
           "    pass",
           T_3D, "the figure <-> Qt canvas cycle survives the view"),
    Mutant("W-canvas-attributes-kept", V3D,
           "    vars(canvas).clear()             # drops draw_idle -> view",
           "    pass  # drops draw_idle -> view",
           T_3D, "canvas.draw_idle keeps the destroyed view alive for the garbage collector"),
    Mutant("W-import-garbage-kept", V3D,
           "        _import_garbage_collected = True\n        gc.collect()\n",
           "        _import_garbage_collected = True\n",
           T_3D, "Matplotlib's first-import cycles keep the first view for a later collection"),
    # ------------------------------------------------------------ P1: legacy AI importer stays local (§7)
    Mutant("L-remote-endpoint-accepted", AIM,
           "            self.endpoint = validate_loopback_url(raw_endpoint)",
           "            self.endpoint = raw_endpoint",
           T_LEG, "workbook cells are posted to a remote DRILLMASTER_OLLAMA_URL"),
    Mutant("L-cloud-model-listed", AIM,
           "                (rejected if is_remote_model(item) else local).append(name)",
           "                local.append(name)",
           T_LEG, "an installed Ollama cloud model is listed as a local model"),
    Mutant("L-cloud-selection-unchecked", AIM,
           '        if is_remote_model({"name": self.model}):\n            self.last_status = "remote-rejected"',
           '        if False:\n            self.last_status = "remote-rejected"',
           T_LEG, "a ':cloud' selection reaches the server instead of being refused up front"),
    Mutant("L-remote-flag-ignored", AIM,
           "        if self.model in self.rejected_models:",
           "        if False:",
           T_LEG, "a model Ollama reports as remote is used when its name looks local"),
    Mutant("L-redirect-and-proxy-followed", AIM,
           "        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())",
           "        self._opener = urllib.request.build_opener()",
           T_LEG, "a redirect or an environment proxy carries the request off this computer"),
    # ------------------------------------------------------------ P0: model / index states (§6)
    Mutant("S-semantic-stale-shown-ready", "tabs/knowledge_assistant.py",
           "        if self._semantic_signature is not None and signature != self._semantic_signature:",
           "        if False:",
           ["tests/test_m50_assistant_states.py"], "a semantic index built for other documents stays labelled ready"),
    Mutant("S-embed-reason-misreported", "tabs/knowledge_assistant.py",
           "            elif status.state not in (ll.READY, ll.NOT_CONFIGURED, ll.MODEL_MISSING, ll.REMOTE_REJECTED):",
           "            elif False:",
           ["tests/test_m50_assistant_states.py"], "a configured embedding model is reported by state when the server could not be asked"),
    # ------------------------------------------------------------ §9 diagnostics
    Mutant("D-number-fragments-listed", "core/knowledge_answer.py",
           "    return [t for t in terms if not (t.isdigit() and any(t != o and t in o for o in terms))]",
           "    return terms",
           ["tests/test_m50_assistant_states.py"], "a refusal lists '8, 2' beside '8-1/2 in' as missing terms"),
    Mutant("D-diagnostics-kept-when-stale", "tabs/knowledge_assistant.py",
           "        self.diagnostics_view.clear()\n",
           "        pass\n",
           ["tests/test_m50_assistant_states.py"], "the diagnostics of an invalidated answer stay on screen"),
    Mutant("D-semantic-claimed-used", "tabs/knowledge_assistant.py",
           '        row("Semantic retrieval", esc("used" if "semantic" in retrieval.lists_used else',
           '        row("Semantic retrieval", esc("used" if True else',
           ["tests/test_m50_assistant_states.py"], "diagnostics say semantic retrieval was used when it did not run"),
    Mutant("D-diagnostics-unescaped", "tabs/knowledge_assistant.py",
           "    esc = html.escape\n",
           "    esc = str\n",
           ["tests/test_m50_assistant_states.py"], "document or model text is rendered as HTML in the diagnostics"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
