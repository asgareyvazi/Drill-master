# M546–M550 (U4) — citation record v2

Code: `core/citation_record_v2.py`, read path `core/citation_passage.py` (M469 service, extended), UI
`tabs/documents_tab.py` ("Save as v2…"), schema `docs/engineering/schemas/citation_record_v2.schema.json`.

## Fields added per citation

| Field | Meaning | Source of the value |
|---|---|---|
| `document_sha256` | SHA-256 of the imported source file bytes | copied from `Document.sha256` (computed at import from the real bytes) **only** when the citation verified EXACT at upgrade; otherwise `null`. Never invented. |
| `page_text_sha256` | SHA-256 of the stored page text | equals v1 `text_version` |
| `quote_sha256` | SHA-256 of the quote (UTF-8) | computed from the quote |
| `offset_unit` | span unit | constant "unicode code points of the stored page text" |
| `passage_id` | SHA-256 of `[document_sha256 or "", page_no, start, end, quote_sha256]` | computed |
| `verification_state` | `VERIFIED_EXACT` / `NOT_VERIFIED` (+ `state_reason`, `verified_at`) | the M469 verification at upgrade |

## Read rules (v2)

v1 rules, plus: hex hashes; bare `file_name` (no `/`, `\`, `:`, `.`/`..`); `passage_id`, `quote_sha256`,
`page_text_sha256` consistent with the citation's own fields, else **UNREADABLE**; `VERIFIED_EXACT` requires a
hash; a recorded content hash different from the library's → **DOCUMENT_CHANGED** (not openable). Any record path
that is a symbolic link is refused (v1 and v2). v1 records are verified exactly as before and are never rewritten.

## Not claimed

No signature or encryption (P13/P16/P17); the content hash proves identity with the library's imported bytes, not
authorship or semantic correctness ("Not semantically verified" stays). The Knowledge Assistant still writes v1
records; v2 is produced from a verified v1 record in the Documents tab.

## Evidence

`tests/test_m546_citation_record_v2.py` (upgrade, changed page, changed library file, 10 tamper cases, symlinks,
v1 compatibility, UI save/open, schema-vs-code), `tests/test_m550_citation_v2_mainwindow_journey.py` (real
MainWindow), mutants CP-*/CR2-*/DT-* in `tools/quality/mutation_m521_m600.py` (11/11 killed).
