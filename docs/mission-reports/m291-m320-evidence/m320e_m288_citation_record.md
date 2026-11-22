# M320 E (M288) — Knowledge Assistant answers exported with exact citations

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

* `core/citation_record.py` (`RECORD_VERSION` "M320-E citation record v1").
* **Building a record:** `build_record(answer, question)` freezes the question, the answer text, the mode, the
  citation-check label and **"Not semantically verified"**, plus any problems and notes. For every cited passage it
  stores:
  * the document id and file name;
  * the page id and number;
  * the span `[start, end)`;
  * the page SHA-256;
  * the exact quote.
  Only a *ready* answer can be recorded; a no-answer state is refused.
* **Saving:** `save` writes `<name>.citations.json` and a readable `<name>.citations.md`. `load` refuses a file with
  the wrong version, a non-record or a missing file.
* **Verifying:** `verify_record(db, record)` is read-only and exact. Each citation gets one status:
  * **EXACT**;
  * **PAGE_CHANGED** (the SHA-256 differs; the quote is "not trusted");
  * **SPAN_MISMATCH**;
  * **PAGE_MISSING**;
  * **DOCUMENT_MISSING**;
  * **UNREADABLE**.
  Nothing is re-anchored, searched for or repaired. The summary reads "ALL EXACT" or "NOT ALL EXACT".
* **UI:** Knowledge Assistant evidence header › **Export with citations…** (enabled only for a ready answer) and
  **Verify citation file…**. The result appears in a status line.

**Windows layout (found by CI on `2273aa4`).** The two buttons first sat on the evidence header and widened the
panel past the M49 limit of 1,300 px on Windows. They now sit on their own row with the status line. With enlarged
fonts the width is 1,275 px, identical to the layout before M320 E; on the header row it was 1,487 px. The UI test
asserts that the citation row is no wider than the header row.

**Tests:** `tests/test_m320e_citation_record.py` has 7 tests, 0 failures. They cover:
* the exact slice and SHA-256;
* a changed page;
* a corrupted span, missing page, missing document and unreadable record;
* a deleted document;
* the JSON and md round-trip and the refusals;
* the no-answer refusal;
* the UI buttons end to end, including PAGE_CHANGED after an edit.
They use the SYNTHETIC M49 corpus. Ruff is clean.

**Status:** COMPLETE for the synthetic scope. A citation proves that the text is present; it does not prove the
answer is correct.
