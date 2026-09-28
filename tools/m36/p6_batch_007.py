#!/usr/bin/env python3
"""M36 / P6 - adjudication records for p6-batch-007 (45 HIGH records, classes E/D).

Class-E/D batch: optional-resource loaders, narrow parser guards and the section-data dialog
loaders across core modules.  Same contract as p6_batch_005/006: read each site, quote the
deciding contract, adjudicate one construct once.  One new finding is recorded (a comment that
promises a stderr warning the branch does not emit) and deliberately NOT patched here.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
BATCH = "p6-batch-007"

VC, INT, DUP, DDD, DEF = ("VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE",
                          "DOMAIN_DECISION_REQUIRED", "GENUINE_DEFECT")

RECHECK_AGAINST: dict[str, str] = {}


def dup(sibling: str, where: str, summary: str) -> tuple[str, str, None]:
    return (DUP,
            f"Second register record for {where}, already adjudicated under {sibling}: "
            f"{summary}",
            None)


def cosmos(what: str) -> tuple[str, str, None]:
    """A rule mis-fire where the subject is not a number at all."""
    return (DUP,
            f"Rule mis-fire, not a behaviour to adjudicate: {what}",
            None)


W2 = "tabs/w2_Daily_Report.py"
ROW_PAINT = ("Row-height/completer/suggestion maintenance around the daily-report table. The guard "
             "wraps purely visual work whose failure mode is 'the convenience did not apply', "
             "never a wrong number: the row keeps its default height, the completer stays unset and "
             "the suggestion list simply lacks an entry (the method then adds its static fallbacks "
             "and returns the sorted set - `contractors.update([...])`, `return sorted(list("
             "contractors))`).")
TIME_LOG = ("`_extract_time_log_row` reads a table row into a time-log record and every swallow is "
            "compensated by the code that follows it: the duration cell is re-derived from the "
            "from/to times right after ('compute duration if it was zero', 1432-1440), and the "
            "widgets' own `get_time()` contract defines midnight as this module's encoding of "
            "'24:00' (`if is_2400: from_python_time = time(0, 0)`, 1413-1416). The `hasattr` guard "
            "on the line before each try means a non-TimeLineEdit cell never reaches the parse.")

NEW_FINDINGS = [
    {
        "id": "NEW-P6-002",
        "file": "app.py",
        "line": 57,
        "severity": "LOW-MEDIUM",
        "class": "E (comment/behaviour mismatch, diagnostics)",
        "trigger": ("`_setup_logging` cannot create the rotating file handler (read-only profile) "
                    "and hits `except OSError`"),
        "observed": ("The handler body is `pass`. The surrounding comment and the module docstring "
                     "promise the opposite: 'A read-only profile must not prevent the UI from "
                     "starting. The warning is visible on stderr, without including configuration "
                     "values.' (58-59) and 'Configure a rotating user-data log with a safe stderr "
                     "fallback.' (39) - but nothing is written at that moment; only the console "
                     "handler attached afterwards (62-65, WARNING level) will show later log "
                     "output."),
        "deciding_contract": ("The start-up requirement itself is documented and satisfied - the UI "
                              "must start with a read-only profile - and console logging still "
                              "works, so no data or computation is affected. What is not "
                              "implemented is the *stderr warning* the comment claims."),
        "reachable": ("yes - any read-only/locked user-data directory (the OSError path this "
                      "handler exists for)."),
        "status": "recorded, not patched",
        "not_patched_because": ("the fix direction is a product choice: emit the promised warning "
                                "(one `print(..., file=sys.stderr)` with no configuration values) or "
                                "correct the comment. Patching either way changes user-visible "
                                "behaviour or documentation, so it is recorded as the batch's next "
                                "action rather than decided inside an audit batch."),
        "next_action": ("decide warn-vs-reword; if 'warn', add the stderr line plus a regression that "
                        "captures stderr for a read-only log directory, then commit separately."),
    }
]

R: dict[str, tuple[str, str, str | None]] = {
    # ------------------------------------------------------------------ app.py
    "INV34-000039": (INT,
        "Start-up robustness with a documented reason ('A read-only profile must not prevent the UI "
        "from starting', 58) - the app must start even when the rotating log file cannot be created, "
        "and logging still reaches stderr through the console handler attached a few lines later "
        "(62-65, WARNING level, added to the root logger at 69-71). Residual recorded separately as "
        "NEW-P6-002: the comment also claims a warning is printed at that moment, which this branch "
        "does not do.", None),
    "INV34-006770": dup("INV34-000039", "app.py:57/60 - the `pass` line of INV34-000039's handler",
                        "start-up robustness; logged as NEW-P6-002 in this batch"),

    # ------------------------------------------------------------------ core/ai_import_mapper.py
    "INV34-000078": (INT,
        "Optional AI resource: the module's contract is 'Optional offline-safe local AI assistant "
        "... AI is opt-in and advisory only. Deterministic import validation remains the source of "
        "truth; an unavailable Ollama service produces a clear capability status and never blocks "
        "non-AI imports.' (1-5). A missing/unreadable model catalog therefore yields an empty "
        "catalog, and the capability status - not an exception - is how the caller learns AI is "
        "unavailable. No import path depends on it.", None),
    "INV34-000077": dup("INV34-000078", "core/ai_import_mapper.py:38 - the identical reader "
                                        "construct in `configured_model` (settings file instead of "
                                        "catalog; same documented opt-in contract)",
                        "an absent settings file means 'no model configured' (\"\")"),

    # ------------------------------------------------------------------ core/base_tab.py
    "INV34-000102": (INT,
        "Display fallback chain for a tab header: in-memory name, then one DB look-up, then the "
        "neutral label `\"No well selected\"` (401). A DB failure yields the neutral label rather "
        "than a fabricated well name, and nothing is written.", None),
    "INV34-006804": dup("INV34-000102", "core/base_tab.py:398/399 - the `pass` line of "
                                        "INV34-000102's handler", "the neutral fallback is returned"),

    # ------------------------------------------------------------------ mapping certainty
    "INV34-000161": (VC,
        "`mapping_certainty(confidence or 0, mapping_method)` (core/canonical_mapper.py:203): the "
        "callee's documented ladder (core/canonical_schema.py:565-587) maps *any* confidence below "
        "0.50 (deterministic) or below 0.85 (fuzzy) to LOW, so 0 - the value used for an absent or "
        "unparseable confidence - and an explicit 0 produce the same tier. 'Confidence is never "
        "inflated' (570-572): the coalesce cannot raise a tier, and it cannot lower one either "
        "(there is no tier below LOW for a known confidence).", None),
    "INV34-000175": (VC,
        "`except (TypeError, ValueError): return \"LOW\"` inside `mapping_certainty`: an unparseable "
        "confidence takes the lowest certainty tier, i.e. the conservative end of the documented "
        "ladder (565-587) under the module's own 'Confidence is never inflated' rule (570-572). "
        "Returning nothing or raising would be worse; returning HIGH/MEDIUM would be a fabrication.",
        None),

    # ------------------------------------------------------------------ core/data_quality.py
    "INV34-000276": (VC,
        "`report = self.db.get_daily_report_by_id(report_id) if report_id else None` - the subject "
        "is a DailyReport primary key (positive); the None fallback means 'no report selected' and "
        "the metrics list is simply empty for it (no DB call with an invalid id).", None),
    "INV34-000280": (VC,
        "The register's line carries the statement start (`total_reports = len(reports)`, 181) "
        "whose *guard* sits inside the expression on 183; the guarded quantity is provably "
        "non-zero: the method returns early when the query yields no reports (`if not reports: "
        "return [QualityMetric(\"Well completeness\", 0, \"critical\", \"No reports\")]`, 178-179), so "
        "`len(reports) >= 1` and the truthiness test cannot take a division-by-zero path. No "
        "fabricated rate is produced for an empty well.", None),

    # ------------------------------------------------------------------ core/database_reset.py
    "INV34-001134": (VC,
        "`except FileNotFoundError: pass` around `Path(f\"{candidate_path}{suffix}\").unlink()` - "
        "the canonical idempotent-delete guard: the goal is 'the file must not exist afterwards', "
        "and it does not, whether it was removed now or was already gone. Any other OSError "
        "propagates.", None),

    # ------------------------------------------------------------------ core/document_import.py
    "INV34-001402": (INT,
        "Tier-3 OCR *metrics* collection around an optional external engine (pytesseract): the "
        "block appends diagnostic metrics (page, engine, confident word count, mean confidence), "
        "and its failure only means those metrics are not reported. The actual tier-3 result is "
        "produced from `tier3_rows` afterwards (181-184) - the swallow cannot change extracted "
        "data.", None),
    "INV34-007396": dup("INV34-001402", "core/document_import.py:178/179 - the `pass` line of "
                                        "INV34-001402's handler",
                        "OCR diagnostics only; the tier-3 result comes from `tier3_rows` (181-184)"),

    # ------------------------------------------------------------------ core/domain_records.py
    "INV34-001427": (INT,
        "A *probe*, not a decision: `ast.literal_eval(value)` tries to recognise an embedded "
        "literal and the swallow falls through to the explicit type/filename checks that follow "
        "(`return isinstance(value, (dict, list, tuple, set)) or (...)` , 58-59). The fallback path "
        "is the method's normal 'not a literal' answer, so the exception is an expected probe "
        "outcome rather than a hidden failure.", None),
    "INV34-007397": dup("INV34-001427", "core/domain_records.py:56/57 - the `pass` line of "
                                        "INV34-001427's probe",
                        "the fall-through answers 'not a literal'"),

    # ------------------------------------------------------------------ core/excel_intelligence.py
    "INV34-001896": (VC,
        "`except (ValueError, TypeError): return \"invalid_type\"` (833-834): the failure is "
        "reported as a *named classification* rather than a silent value - the caller receives "
        "`\"invalid_type\"` and can act on it. Nothing numeric is fabricated for an unparseable "
        "cell.", None),
    "INV34-001895": (INT,
        "`except (ValueError, TypeError): return value` (914-915): this helper's contract is 'the "
        "numeric value when it parses, otherwise the original text', which is what the caller "
        "needs in order to keep non-numeric content (dates, names) intact while normalising "
        "numbers. Returning the input unchanged cannot invent a measurement.", None),
    "INV34-001786": (INT,
        "Optional workbook metadata: `workbook.filename = str(source_file)` is an attribution "
        "field on the in-memory workbook object (openpyxl) and a failure only leaves it unset - it "
        "is not part of any extraction or persistence contract.", None),
    "INV34-007551": dup("INV34-001786", "core/excel_intelligence.py:1236/1237 - the `pass` line of "
                                        "INV34-001786's handler",
                        "optional workbook attribution metadata"),

    # ------------------------------------------------------------------ core/functions.py
    "INV34-001906": (VC,
        "The guard cannot hide an unflagged problem: the loop just above already validates every "
        "numeric field, including `depth_in`/`depth_out` (`float(value)` with "
        "`errors[field] = \"... must be a number\"`, 59-67), so by the time this comparison runs a "
        "parse failure has a user-visible error attached to the field. The swallow exists only so "
        "the comparison itself does not raise a second, duplicate error for the same input.", None),
    "INV34-007569": dup("INV34-001906", "core/functions.py:75/76 - the `pass` line of "
                                        "INV34-001906's guard",
                        "the numeric-field loop above already reported 'must be a number'"),

    # ------------------------------------------------------------------ core/mapping_store.py
    "INV34-002108": (INT,
        "Optional persisted mapping file: an unreadable/corrupt store yields the documented empty "
        "store `{\"mappings\": {}}` (19-20) - the same value a first run produces - so the caller "
        "sees 'nothing remembered yet' instead of an exception. Nothing is written back by this "
        "read path.", None),

    # ------------------------------------------------------------------ core/mineru_engine.py
    "INV34-002201": (INT,
        "`except subprocess.TimeoutExpired as exc: return self._failure(source_display, ...)` "
        "(602-604): the failure is *returned as an explicit failure result* carrying the reason - "
        "not swallowed. MinerU is the documented external-optional engine, so a timeout becomes a "
        "reported capability/parse failure and the non-MinerU paths stay available.", None),
    "INV34-002199": (INT,
        "`except MinerUOutputError as exc: return self._failure(...)` (646-647): same shape as "
        "INV34-002201 - a typed error is converted into the module's failure result (with method "
        "and reason) rather than a silent fallback.", None),
    "INV34-002203": (INT,
        "`_parse_html_table` returns `([], [])` both on a parser error and when the document "
        "contains no table at all (`if not parser.rows: return [], []`, 1050-1051) - i.e. the "
        "failure mode is the function's documented 'no table found' answer, and the caller treats "
        "it as 'nothing to import' rather than as data. TypeError/ValueError cover the stdlib "
        "parser's documented non-string/malformed-input errors.", None),

    # ------------------------------------------------------------------ core/performance.py
    "INV34-002269": (INT,
        "A size *metric* for progress display: an unreadable file reports 0.0 MB. The value is "
        "used for the progress/indicator text, not for any decision about the file's contents, and "
        "the subsequent processing of that file reports its own errors. Residual (recorded, not a "
        "defect claim): 'unknown size' is displayed as 0.0 MB rather than as 'unknown'.", None),
    "INV34-002258": (INT,
        "A progress callback must not be able to abort the operation it reports on: "
        "`cb(pct, self.current, self.total)` is a UI hook, and letting its exception propagate "
        "would turn a cosmetic failure into a failed operation. No stored or computed value "
        "depends on the callback.", None),
    "INV34-007660": dup("INV34-002258", "core/performance.py:113/114 - the `pass` line of "
                                        "INV34-002258's handler",
                        "a UI progress hook must not abort the operation"),

    # ------------------------------------------------------------------ core/runtime_config.py
    "INV34-002767": (INT,
        "Optional MinerU settings file: an unreadable or non-dict payload yields `{}` (102-103), "
        "the same 'no settings' value the module uses when the file is absent (`value if "
        "isinstance(value, dict) else {}`, 101). MinerU is the documented external-optional engine; "
        "callers fall back to their defaults.", None),

    # ------------------------------------------------------------------ core/selection_manager.py
    "INV34-002795": (VC,
        "`select_all`'s documented contract makes each id optional: 'Select well + wellbore + "
        "section + report in one call. Useful after import to set everything at once. Emits signals "
        "in correct order: well -> wellbore -> section -> report' (294-300). The subjects are "
        "primary keys (positive), so the truthiness test is exactly the 'this id is not part of the "
        "selection' test - a not-provided id must not be selected.", None),
    "INV34-002794": dup("INV34-002795", "core/selection_manager.py:307 - the same optional-id "
                                        "truthiness test two lines below (report id)",
                        "same documented optional-id contract"),

    # ------------------------------------------------------------------ core/standards.py
    "INV34-002813": (VC,
        "A configuration value with a documented fallback: `max(1, int(cfg[\"bop_test_interval_days\"]))` "
        "inside a try whose `except (TypeError, ValueError): return default` (42-43) returns the "
        "caller's default when the configured value is unusable, and the `max(1, ...)` already "
        "guards the lower bound for a parseable value. No hard-coded number is invented: `default` "
        "comes from the call site.", None),

    # ------------------------------------------------------------------ core/survey_records.py
    "INV34-002818": (VC,
        "Fail-closed *exclusion*: the predicate asks whether every coordinate of a record is a "
        "finite number, and an unparseable value raises out of `float(...)`/`math.isfinite` into "
        "`return False` (64-65) - the record is then filtered out of `usable` (66). The swallow "
        "makes the record unusable, not usable; a survey with unreadable numbers can never reach "
        "the trajectory maths through this path.", None),

    # ------------------------------------------------------------------ core/text_utils.py
    "INV34-002851": (VC,
        "`safe_float(value, default=0.0)` is *defined* to return the caller's `default` when the "
        "value is absent or unparseable (`float(value) if value is not None else default` plus "
        "`except (ValueError, TypeError): return default`, 24-28). The default is an explicit "
        "parameter at every call site, so the helper cannot invent a number the caller did not "
        "choose.", None),
    "INV34-002852": dup("INV34-002851", "core/text_utils.py:34 - the identical construct in "
                                        "`safe_int` (int-of-float with the caller's default)",
                        "same documented default-parameter contract (31-35)"),

    # ------------------------------------------------------------------ core/universal_import.py
    "INV34-002895": (INT,
        "Optional metadata on an import result: `result[\"file_size\"] = "
        "Path(file_path).stat().st_size` inside an `except Exception: pass` (107-110) means the key "
        "is simply absent when the size cannot be read. The import itself continues and reports its "
        "own status; no extracted value depends on the file size.", None),
    "INV34-007853": dup("INV34-002895", "core/universal_import.py:109/110 - the `pass` line of "
                                        "INV34-002895's handler",
                        "optional file-size metadata key"),

    # ------------------------------------------------------------------ tabs/w3c_section_data.py
    "INV34-005747": (VC,
        "The dialog loaders' `sv(key, d)` helper returns the field's documented default `d` when the "
        "stored value is absent or unparseable (`float(v) if v is not None else d` plus "
        "`except (TypeError, ValueError): return d`, 200-203) - the same loader pattern already "
        "adjudicated in p6-batch-005 for w3 (`safe_val` vs `safe_opt`): the spin box is an operator "
        "entry field whose domain includes a legal zero, and the default comes from the call site "
        "(`sv(\"compressive_strength\",2500)`, ...).", None),
    "INV34-005743": dup("INV34-005747", "tabs/w3c_section_data.py:369/370 - the identical `sv` "
                                        "helper of the second dialog class in the same file",
                        "same caller-supplied-default loader contract"),
    "INV34-005745": (INT,
        "Legacy thickening-time text is parsed into two spin boxes; on an unparseable/partial value "
        "the boxes keep their current (default) contents - no time is invented, and the operator "
        "sees the field as it was rather than a fabricated schedule entry.", None),
    "INV34-008331": dup("INV34-005745", "tabs/w3c_section_data.py:212/213 - the `pass` line of "
                                        "INV34-005745's handler",
                        "the spin boxes keep their defaults"),
    "INV34-005746": (INT,
        "The handler's own comment is the contract: 'malformed legacy materials JSON - leave table "
        "empty' (225). The table was reset before parsing, no rows are invented from a corrupt blob, "
        "and the typed guard names the expected failure modes (JSONDecodeError/TypeError/ValueError/"
        "KeyError).", None),
    "INV34-005735": (VC,
        "`if company_id: self._load()` - a Company primary key tested for truthiness before the "
        "dialog loads its data; with no company selected the dialog stays empty instead of querying "
        "with an invalid id.", None),
    "INV34-005748": (INT,
        "`QDate.fromString(...)`/`setDate(...)` do not raise for a bad date string (they yield an "
        "invalid/blank date), so this guard is defensive; its consequence if it ever fires is that "
        "the date field keeps its previous state - it can never fabricate a date for a report.",
        None),
    "INV34-008347": dup("INV34-005748", "tabs/w3c_section_data.py:1221 - the second rule on the "
                                        "same defensive date handler",
                        "an unparseable date leaves the field's previous state"),
}
def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def git_show(rev: str, path: str) -> list[str]:
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"git show {rev}:{path} failed")
    return out.stdout.decode("utf-8", "replace").splitlines()


def symbol_body(source: str, symbol: str) -> tuple[int, int]:
    import ast

    parts = [p for p in (symbol or "").split(".") if p]
    name = parts[-1] if parts else ""
    tree = ast.parse(source)
    candidates = [n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if not candidates:
        raise SystemExit(f"symbol {symbol!r} not found")
    node = min(candidates, key=lambda n: n.lineno)
    return node.lineno, node.end_lineno


def line_map(commit: str, path: str, current: list[str]) -> dict[int, int]:
    previous = git_show(f"{commit}^", path)
    matcher = difflib.SequenceMatcher(None, previous, current, autojunk=False)
    mapping: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
    return mapping


def check(batch: list[dict]) -> list[tuple[str, str, int, int]]:
    problems: list[str] = []
    reanchored: list[tuple[str, str, int, int]] = []
    cache: dict[str, list[str]] = {}
    sources: dict[str, str] = {}
    maps: dict[str, dict[int, int]] = {}
    for record in batch:
        path, line, expected = record["file"], record["line"], record.get("current_source_line")
        if path not in cache:
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            sources[path] = text
            cache[path] = text.splitlines()
        lines = cache[path]

        if 0 < line <= len(lines) and _norm(lines[line - 1]) == _norm(expected):
            continue

        commit = RECHECK_AGAINST.get(path)
        if commit is None:
            actual = lines[line - 1].strip() if 0 < line <= len(lines) else "<beyond EOF>"
            problems.append(f"{record['id']}: {path}:{line} is {actual!r}, register recorded "
                            f"{expected!r}")
            continue

        previous = git_show(f"{commit}^", path)
        if _norm(previous[line - 1]) != _norm(expected):
            problems.append(f"{record['id']}: {commit}^ has {previous[line - 1].strip()!r} at "
                            f"{path}:{line}, register recorded {expected!r}")
            continue

        if path not in maps:
            maps[path] = line_map(commit, path, lines)
        new_line = maps[path].get(line)
        start, end = symbol_body(sources[path], record.get("symbol", ""))
        if new_line is None or _norm(lines[new_line - 1]) != _norm(expected) \
                or not (start <= new_line <= end):
            problems.append(f"{record['id']}: re-anchor {path}:{line} -> {new_line} failed")
            continue
        reanchored.append((record["id"], path, line, new_line))
    if problems:
        print("STALE / UNVERIFIED EVIDENCE - not applying:")
        for problem in problems:
            print("  ", problem)
        raise SystemExit(2)
    return reanchored


def record_head() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, check=True).stdout.decode().strip()


def main() -> int:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    batch = [r for r in register["records"] if r.get("p6_batch") == BATCH]
    if len(batch) != len(R):
        print(f"batch has {len(batch)} records, adjudications: {len(R)}")
        print("missing:", sorted({r["id"] for r in batch} - set(R)))
        print("extra:", sorted(set(R) - {r["id"] for r in batch}))
        return 1

    reanchored = check(batch)

    counts: dict[str, int] = {}
    for record in batch:
        classification = R[record["id"]][0]
        counts[classification] = counts.get(classification, 0) + 1
    classes: dict[str, int] = {}
    for record in batch:
        classes[record["p6_class"]] = classes.get(record["p6_class"], 0) + 1

    items = [{
        "id": record["id"], "file": record["file"], "line": record["line"],
        "classification": R[record["id"]][0], "evidence": R[record["id"]][1],
        "remaining_question": R[record["id"]][2],
        "defect": R[record["id"]][0] == DEF,
        "test": None, "commit": None,
    } for record in batch]

    payload = {
        "schema": "m36-p6-batch", "batch": BATCH,
        "class": ("class E 37 / class D 8 (optional-resource loaders, narrow parser guards, "
                  "dialog loaders): " + ", ".join(f"{k}:{v}" for k, v in sorted(classes.items()))),
        "records": len(items),
        "sites": len({(i["file"], i["line"]) for i in items}),
        "by_classification": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "defects_fixed": [],
        "new_findings": NEW_FINDINGS,
        "tests": ("no production change in this batch; the full suite evidence recorded in "
                  "P6_PROGRESS.md (1 831 tests / 0 failures / 0 errors / 4 skipped on the 3f0cf3e "
                  "tree) stands for this batch too - every site read here is untracked by this "
                  "session's changes"),
        "head": record_head(),
        "commit": None,
        "evidence_commit": None,
        "evidence_files": [f"docs/audits/m36-evidence/{BATCH}.json",
                           f"docs/audits/m36-evidence/{BATCH}.md",
                           "docs/audits/m36-evidence/m36-open-item-register.json",
                           "docs/audits/m36-evidence/m36-master-ledger.json",
                           "docs/audits/m36-evidence/P6_PROGRESS.md",
                           "tools/m36/p6_batch_006.py"],
        "staleness": {"checked": len(batch), "stale": 0, "re_anchored": len(reanchored),
                      "method": ("every record's recorded text must match the current line exactly; "
                                 "no file in this batch was changed by this session (verified: the "
                                 "batch touches only files untouched since the register was built), "
                                 "so no record needed re-anchoring"),
                      "re_anchored_items": []},
        "method": ("each record read at its own site in the current tree, with the fallback path "
                   "traced to its consumer (e.g. the section-data loaders through the spin-box "
                   "defaults, the import-mapper loaders through the module's opt-in/advisory "
                   "contract, `mapping_certainty` through its documented LOW/MEDIUM/HIGH ladder) and "
                   "the deciding contract quoted in `evidence`"),
        "items": items,
    }
    (EVIDENCE / f"{BATCH}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"{BATCH}: {len(items)} records, {payload['sites']} sites, staleness 0, "
          f"re-anchored {len(reanchored)}, defects fixed 0")
    print("by classification:", payload["by_classification"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
