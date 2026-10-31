#!/usr/bin/env python3
"""Repeatable mutation run for the M52 contracts.

Each mutant puts ONE old behaviour back (or removes one guard) in a scratch
copy of the working tree and must be KILLED by the listed tests.  The engine
(copy, exact-once snippet check, baseline run, JSON report, exit status) is the
M46 one: ``tools/quality/mutation_m46.py``.  The repository is never modified.

The two M50 survivors (``R-file-name-context-dropped``,
``R-absent-ignores-context``) are re-run here with the M52 test that pins the
behaviour they change (a code-only question on a file-name identity), with the
exact snippets of ``tools/quality/mutation_m50.py``.

Usage::

    python tools/quality/mutation_m52.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh).  SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

KR = "core/knowledge_retrieval.py"
KA = "core/knowledge_answer.py"
KP = "tabs/knowledge_assistant.py"
AW = "core/async_workers.py"
T_SC = ["tests/test_m52_scope_choices.py"]
T_TR = ["tests/test_m52_thread_release.py"]
T_SS = ["tests/test_m52_sentence_support.py"]
T_SS_GOLD = T_SS + ["tests/test_m50_knowledge_gold.py"]

MUTANTS = [
    # ------------------------------------------------------------ §2.4 the M50 survivors, re-run
    Mutant("R-file-name-context-dropped", KR,
           "                    _contains(self._name_tokens.get(page_id, []), list(code)):",
           "                    False:",
           T_SS, "a well code that only the file name states is ignored (M50 survivor)"),
    Mutant("R-absent-ignores-context", KR,
           "        covered = set(self.context_covered(page_id, codes)) if codes else set()",
           "        covered = set()",
           T_SS, "the insufficient-evidence message claims a well code is missing that the file name states"),
    # ------------------------------------------------------------ §2.2 scope lists on a worker
    Mutant("KP-scope-list-read-on-gui", KP,
           "        token = self._choices_token[slot]\n        if _reads_on_worker(self.db_manager):",
           "        token = self._choices_token[slot]\n        if False:",
           T_SC, "the well / report / document lists are read on the GUI thread again (pre-M52)"),
    Mutant("KP-late-list-accepted", KP,
           "        if token != self._choices_token[slot]:\n            return",
           "        if False:\n            return",
           T_SC, "a late well list overwrites the picker of a newer scope"),
    Mutant("KP-error-shown-as-empty", KP,
           "        if error is not None:\n            combo.setPlaceholderText",
           "        if error is not None:\n            rows, error = [], None\n        if False:\n            combo.setPlaceholderText",
           T_SC, "an unreadable well list looks like 'no wells' (pre-M52)"),
    Mutant("KP-ask-not-blocked-while-loading", KP,
           "        blocked = self._scope_choices_block()",
           "        blocked = None",
           T_SC, "a question is asked for a scope whose list is loading or unreadable"),
    Mutant("KP-refresh-drops-chosen-well", KP,
           "        self._targets_previous = (current if keep_current and current is not None",
           "        self._targets_previous = (current if False and current is not None",
           T_SC, "a library refresh moves the question to another well silently"),
    # ------------------------------------------------------------ §2.5 QThread release
    Mutant("TR-release-while-running", AW,
           "    worker.finished.connect(release)\n    if not worker.isRunning():",
           "    release()\n    if False:",
           T_TR, "a result slot deletes a QThread still inside run() (Qt aborts the process)"),
    # ------------------------------------------------------------ §2.3 sentence-level support
    Mutant("SS-identity-alone-supports", KA,
           "        if index.text_coverage(topical, by_term, toks, retrieval.strict_terms, shown(sentence))[0] <= 0:\n"
           "            return 0.0                           # an inherited size alone is not support",
           "        if False:\n            return 0.0",
           T_SS, "a sentence with no topical word of its own is quoted (N16/N19)"),
    Mutant("SS-topical-terms-include-identity", KA,
           "    topical = [t for t in retrieval.terms if t not in identity]",
           "    topical = list(retrieval.terms)",
           T_SS, "the inherited well code counts as a sentence's own support"),
    Mutant("SS-similar-well-sentence-quoted", KA,
           "    found = kr.entity_codes(sentence)\n    if not found or not codes",
           "    found = ()\n    if not found or not codes",
           T_SS, "a sentence about SYN-QA-12 is quoted for a SYN-QA-21 question"),
    Mutant("SS-bare-heading-quoted", KA,
           "        if kr.fold(sentence) == kr.fold(heading_text) and not _numbers(sentence):",
           "        if False:",
           T_SS, "a page heading without a value is quoted as the answer"),
    Mutant("SS-heading-support-without-value", KA,
           "if own > 0 and _numbers(x[2])]",
           "if own > 0]",
           T_SS, "every sentence under a heading counts as supported (crew change under 'Kick tolerance')"),
    Mutant("SS-partial-sentence-kept", KA,
           "    scored = [x for x, own in supported if own >= 0.6 * best_own]",
           "    scored = [x for x, own in supported if own > 0]",
           T_SS, "a sentence stating only part of the question is quoted next to the full answer"),
    Mutant("SS-own-support-ignores-paragraph-size", KA,
           "        sizes_here = size_tokens if not kr.size_designations(sentence) else frozenset()",
           "        sizes_here = frozenset()",
           T_SS_GOLD, "the ECD sentence under the 12-1/4 in text loses to a size-only sentence (N30)"),
    Mutant("SS-identity-only-uses-fallback", KA,
           "        if sentences is None and not item.instruction_like:",
           "        if not sentences and not item.instruction_like:",
           T_SS, "an identity-only passage is quoted through the n-gram first-sentence fallback"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
