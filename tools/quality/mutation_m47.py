#!/usr/bin/env python3
"""Repeatable mutation run for the M47 fixes (pool isolation, maintenance gate,
in-memory policy, P3-A spans, P3-B fold, P3-C notes).

Each mutant puts ONE old behaviour (or one removed guard) back into a scratch
copy of the working tree and must be KILLED by the listed tests.  The engine
(copy, exact-once snippet check, baseline run, JSON report, exit status) is the
M46 one: ``tools/quality/mutation_m46.py``.  The repository is never modified.

Usage::

    python tools/quality/mutation_m47.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh).  SYNTHETIC test data only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_m46 as engine  # noqa: E402
from mutation_m46 import Mutant  # noqa: E402

POOL = ["tests/test_sqlite_pool_isolation_m47.py"]
SEARCH = ["tests/test_search_closure_m47.py"]
SEARCH_ALL = SEARCH + ["tests/test_search_parity_m46.py", "tests/test_search_normalization.py"]
NOTES = ["tests/test_search_closure_m47.py"]

MUTANTS = [
    # ---------------------------------------------------------------- pool: one connection per session
    Mutant("P-staticpool", "core/database.py",
           "poolclass=QueuePool,\n                               **sqlite_connection.pool_settings(), **common)",
           "poolclass=StaticPool, **common)",
           POOL, "file database back on StaticPool: every session shares one DB-API connection (M46)"),
    Mutant("P-fk-checkout", "core/database.py",
           "            if dbapi_connection.execute(\"PRAGMA foreign_keys\").fetchone()[0] != 1:",
           "            if False:",
           POOL, "a pooled connection without foreign-key enforcement is reused"),
    Mutant("P-settings-bounds", "core/sqlite_connection.py",
           "    if not low <= value <= high:", "    if False:",
           POOL, "out-of-range pool settings accepted"),
    # ---------------------------------------------------------------- maintenance gate
    Mutant("G-unmatched-checkin", "core/db_maintenance.py",
           "            if count <= 0:\n                return  # a refused checkout: it was never counted",
           "            if count <= 0:\n                if self._held:\n"
           "                    self._held.pop(next(iter(self._held)))\n                return",
           POOL, "a refused checkout's checkin releases another holder (G1, old max(0, n-1))"),
    Mutant("G-install-reset", "core/db_maintenance.py",
           "    gate = gate_for(manager)\n    watch_engine(gate, manager.engine)\n",
           "    gate = gate_for(manager)\n    gate._held.clear()\n    gate.closed = False\n"
           "    watch_engine(gate, manager.engine)\n",
           POOL, "initialize resets and reopens the gate (old install_gate)"),
    Mutant("G-connect-guard", "core/database.py",
           "            with gate.connecting():\n                return sqlite_connection.connect(",
           "            if True:\n                return sqlite_connection.connect(",
           POOL, "new DB-API connections are opened (and configured) while maintenance holds the file"),
    Mutant("G-reentrant-close", "core/db_maintenance.py",
           "            if self.closed:\n                raise MaintenanceBusy(\"another database maintenance operation is in progress\")\n"
           "            self.closed = True\n",
           "            self.closed = True\n",
           POOL, "a second maintenance stacks on the first instead of being refused"),
    Mutant("G-no-dispose", "core/db_maintenance.py",
           "        gate.close(self.drain_timeout)\n        self.manager.engine.dispose()\n",
           "        gate.close(self.drain_timeout)\n",
           POOL, "restore keeps idle pooled connections open on the file it replaces"),
    # ---------------------------------------------------------------- in-memory policy
    Mutant("M-worker-thread", "core/export_jobs.py",
           "        if shares_single_connection(db_manager) and threading.current_thread() is not threading.main_thread():",
           "        if False:",
           POOL, "a worker thread may query the shared in-memory connection"),
    Mutant("M-hierarchy-thread", "main_window.py",
           "        if shares_single_connection(self.db_manager):", "        if False:",
           POOL, "in-memory hierarchy read moved to a QThread"),
    Mutant("M-export-thread", "tabs/w11_Export.py",
           "        if shares_single_connection(self.db):", "        if False:",
           POOL, "in-memory export moved to a QThread"),
    Mutant("M-detect", "core/export_jobs.py",
           "    return isinstance(pool, (StaticPool, SingletonThreadPool))", "    return False",
           POOL, "the shared in-memory connection is not recognised"),
    # ---------------------------------------------------------------- P3-A span contract
    Mutant("A-library-flat", "core/document_library.py",
           "            spans = find_spans(original, groups)",
           "            spans = find_spans(original, [t for g in groups for t in g])",
           SEARCH, "search results highlight every token of an identifier separately (old flat terms)"),
    Mutant("A-ui-flat", "tabs/documents_tab.py",
           "(result.get(\"groups\") or self.library._groups(query)))",
           "[t for g in (result.get(\"groups\") or self.library._groups(query)) for t in g])",
           SEARCH, "the viewer highlights every token of an identifier separately (old flat terms)"),
    Mutant("A-phrase-prefix", "core/search_normalization.py",
           "                    if page_tokens[i:i + n] == group:",
           "                    if all(page_tokens[i + k].startswith(group[k]) for k in range(n)):",
           SEARCH_ALL, "a multi-token group matches token prefixes (SYN-DEV-012 for SYN-DEV-01)"),
    Mutant("A-no-merge", "core/search_normalization.py",
           "        if merged and start <= merged[-1][1]:", "        if False:",
           SEARCH_ALL, "overlapping spans are not merged (order-dependent highlight)"),
    Mutant("A-utf16", "core/search_normalization.py",
           "    return position + sum(1 for char in prefix if ord(char) > 0xFFFF)", "    return position",
           SEARCH, "Qt positions taken as code points: highlight shifts after a non-BMP character"),
    # ---------------------------------------------------------------- P3-B fold
    Mutant("B-full-casefold", "core/search_normalization.py",
           "    folded = char.casefold()\n    if len(folded) == 1:\n        return folded\n",
           "    return char.casefold()[:1] or char\n",
           SEARCH, "full case folding truncated to one character (old _fold: 'ß' -> 's')"),
    Mutant("B-fold-order", "core/search_normalization.py",
           "        out.append(_CHAR_MAP.get(folded, folded))", "        out.append(folded)",
           SEARCH, "diacritic fold not applied after case folding (U+1E9B -> U+1E61 kept)"),
    Mutant("B-keeps", "core/search_normalization.py",
           "_FTS5_KEEPS = frozenset((\"\\u01e0\", \"\\u01e1\"))", "_FTS5_KEEPS = frozenset()",
           SEARCH, "U+01E0/U+01E1 folded although FTS5 unicode61 keeps them"),
    Mutant("B-version", "core/search_normalization.py",
           "NORMALIZATION_VERSION = 3\n", "NORMALIZATION_VERSION = 2\n",
           SEARCH_ALL, "fold rules changed without an index signature bump"),
    # ---------------------------------------------------------------- P3-C notes
    Mutant("C-old-normalize", "core/document_links.py",
           "    text = str(note).strip()[:NOTE_MAX_LENGTH].strip()\n",
           "    return (note or None) and str(note).strip()[:NOTE_MAX_LENGTH]\n    text = ''\n",
           NOTES, "old note expression: whitespace-only notes stored as ''"),
    Mutant("C-read-raw", "core/document_links.py",
           "\"note\": normalize_note(link.note), \"linked_at\"", "\"note\": link.note, \"linked_at\"",
           NOTES, "legacy '' notes read back as '' instead of None"),
    Mutant("C-unchanged-ignores-note", "core/document_links.py",
           "            if (link.well_id, link.report_id, link.page_no, old_note) == (well_id, report_id, page_no, new_note):",
           "            if (link.well_id, link.report_id, link.page_no) == (well_id, report_id, page_no):",
           NOTES, "a note-only change is refused as unchanged"),
    Mutant("C-note-dropped", "core/document_links.py",
           "            new_note = old_note if note is _UNSET else normalize_note(note)",
           "            new_note = old_note",
           NOTES, "update_link ignores the note argument"),
]


def main(argv=None) -> int:
    engine.MUTANTS = MUTANTS
    return engine.main(argv)


if __name__ == "__main__":
    sys.exit(main())
