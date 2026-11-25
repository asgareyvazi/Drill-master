# M469–M472: Open a `.citations.json` passage from the Documents tab (U2 closed for SYNTHETIC scope)

## Before

M334 (A-8) added navigation from a verified citation record, but only inside the **Knowledge Assistant** panel. The
Documents tab's **Library & Search** page had no way to open a saved record.

The record reader was `citation_record.load` → `verify_record`. A user-picked file had these weaknesses:

- **No size bound.** Any file size was read in full.
- **Duplicate keys.** Duplicate JSON keys were accepted, so the last one won (a second `"start"`).
- **Non-JSON constants.** `NaN` and `Infinity` were accepted.
- **Type errors crashed verification.** `int("abc")` raised `ValueError` inside `verify_record`.
- **Booleans as offsets.** A JSON `true` became offset 1.
- **No identity check.** A record from another library opened whatever local document had the same id. A
  PAGE_CHANGED result then showed an unrelated page as "the cited page, changed".
- **Rich text in the status label.** The Knowledge Assistant status `QLabel` used Qt's automatic rich-text detection.
  A crafted label such as `<img src=…>` could render as rich text.

## After

### M469: schema

The schema is `docs/engineering/schemas/citation_record_v1.schema.json` (JSON Schema 2020-12). A test pins the
schema to the service constants.

| Field | Constraint |
|---|---|
| `record_version` | constant `M320-E citation record v1` |
| `citations` | 1 to 500 entries |
| ids, page and span | integers in 0 … 2³¹−1 |
| `text_version` | 64 lower-case hex digits |
| `label` | short plain token |
| `quote` | at most 20 000 characters |
| `file_name` | single line, at most 260 characters (the `documents.file_name` column width) |
| file | at most 4 MiB |

### M470: secure passage service

The service is `core/citation_passage.py` (`M469 citation passage service v1`). It is the only read path for both UI
entry points.

**Whole-file refusal.** The whole file is refused with a reason (`PassageError`, a `CitationRecordError`) when:
- it is not a regular file;
- it is larger than 4 MiB (checked by `stat` and again on a bounded read);
- it is not UTF-8;
- it is not valid JSON;
- it contains a duplicate key;
- it contains `NaN` or `Infinity`;
- it is nested too deeply (`RecursionError`);
- the record version is wrong;
- it has no citations or too many;
- a top-level text field is not text.

**Per-entry check.** Each citation is checked on its own. A malformed entry is `UNREADABLE`, with the field named. It
is never passed to `verify_record` or to navigation. The other entries are still verified.

**Identity check.** When the record names a file and the library document with that id has another file name, the
status is `IDENTITY_MISMATCH`. That status is not openable.

**Preserved behaviour.** A quote that the span does not hold stays `SPAN_MISMATCH`, which is the M334 behaviour. The
existing test is unchanged.

The service is read-only and offline. It never repairs, re-anchors, writes or fetches anything.

### M471: Documents tab UI

On the Library & Search page:

- **Open citation file…** verifies the record and lists its citations, with their status, in a combo box.
- **Open passage** opens the chosen citation in the library viewer:
  - EXACT: the quote is highlighted.
  - PAGE_CHANGED: the page opens with no highlight, and the change is stated (the M50 viewer check).
  - Anything else: nothing opens, and the tooltip and status give the reason.

A refused file clears the previous record's passages. Both status labels (library page and Knowledge Assistant) are
`Qt.PlainText`.

The Knowledge Assistant "Verify citation file…" uses the same service.

### M472: tests

| File | Tests | Scope |
|---|---|---|
| `tests/test_m469_citation_passage_service.py` | 30 | Real `DocumentsTab` (M50 SYNTHETIC corpus): EXACT open with highlight, PAGE_CHANGED without highlight, refused file clears targets, `<img>` label stays plain text and UNREADABLE, foreign record → IDENTITY_MISMATCH, assistant uses the service (boolean offset → UNREADABLE). Service: 7 hostile files, size/directory/encoding/missing/too-many limits, 14 entry-schema cases, valid Unicode names, schema ↔ constants |
| `tests/test_m472_citation_mainwindow_journey.py` | 2 | Real `MainWindow` → Documents tab → file dialog → EXACT passage highlighted in `syn_alpha_daily.txt`. A record edited to another file name is refused |

The existing tests `test_m320e_citation_record.py`, `test_m334_citation_record_navigation.py` and
`test_m50_citation_navigation.py` pass unchanged. The historical CR-* and KA-* mutants (15) are all KILLED.

### Mutation

14 new mutants (CP-*, DT-*, KA-*) were added to `tools/quality/mutation_m461_m520.py`. All 14 are KILLED.

## Limits

- Identity is checked by file name, because that is the only identity field in a v1 record. Two different documents
  with the same file name and the same id are not told apart. A record v2 with a document content hash would be
  needed for that, and v2 is not implemented.
- The citation checks are exact text checks. They are **not semantic verification**.
