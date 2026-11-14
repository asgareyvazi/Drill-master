# M181–M183 Tubular reference sources, controlled importer and data population

Status: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

## 1. Outcome

- **No permitted tubular dataset was found.** The library ships empty: no DP, HWDP, DC, tool-joint, casing,
  tubing or liner rows are committed or bundled.
- A controlled importer (`core/engineering/tubular_import.py`, contract `tubular-import-v1`) lets the owner load
  a file they are licensed to use into a DRAFT set. It previews the file, requires confirmation, writes an audit
  record and then publishes.
- Tests use **synthetic** fixtures only (`SYN-*` designations, deliberately non-catalogue numbers):
  `tests/test_m181_m183_tubular_import.py` (35 tests) and `tests/test_m184_m189_reference_integration.py`.
- An owner source-request package (section 4) lists what is needed to populate the library.

## 2. Sources evaluated (M181)

Rules applied: a public PDF or web page is not a redistribution right. API 5DP / 5CT / RP 7G / TR 5C3 and
ISO 11960 / 11961 / 10400 tables are owner-gated. CC-BY needs attribution and a database-rights check. NOASSERTION
or unlicensed sources are owner-gated.

| Source | Publisher / licence | Content | Decision |
|---|---|---|---|
| `github.com/openwashdata/drillingdata` | openwashdata, CC BY 4.0 | Malawi water-borehole records 2018–2024, casing ID/OD in mm | **Rejected**: water-well casing per borehole, not an oilfield tubular specification |
| `gdr.openei.org/files/1776/casing_v2.csv` (DOE GDR "Supercritical Drilling Materials Analysis", via catalog.data.gov) | US DOE GDR, CC BY 4.0 | Per-well case histories: nominal casing ODs per well, materials, failure notes, literature references | **Rejected**: nominal OD per well only (no ID, weight or ratings per item); it is a failure-history dataset, not a specification catalogue |
| `github.com/Open-Source-Drilling-Community/DrillString` (HEAD `f241de5d99e736d1821ae00d06fdf9e8b78165fb`) | MIT | Drill-string microservice: C# model, JSON schemas, no data rows | **Rejected as data** (no tubular rows). Code not adopted (C#/.NET service, outside the product stack) |
| Other `Open-Source-Drilling-Community` repositories (34 listed via the GitHub API, e.g. `Drillstring-Test-Cases` with no licence, `Dixit-Drillstring-Model-2023` Apache-2.0) | mixed | numerical models and test cases | **Rejected**: no licensed tubular catalogue; `Drillstring-Test-Cases` has no licence |
| `github.com/bubinbei/open-drill` | MIT | acquisition software | **Rejected**: no tubular data |
| OSDU reference values (`TubularComponentType`, `TubularComponentGrade`) | The Open Group OSDU, Apache-2.0 | code lists (names), no dimensions | **Not used**: vocabulary only, no values |
| Manufacturer / service-company data books and spec sheets found by search (e.g. well-control data books, coating-company spec booklets, rental-tool spec sheets) | proprietary; many reprint API tables | dimensions and ratings | **Rejected**: public PDFs without a redistribution licence, and several reprint API RP 7G / Spec 7 tables |

Nothing was downloaded into the repository. The rejected PDFs were not opened beyond the search-result excerpts.

## 3. Importer controls (M182)

`core/engineering/tubular_import.py`, UI `dialogs/tubular_import_dialog.py` (opened from
**Tools › Tubular Reference Library › Import / publish…**):

- **Formats:** XLSX/XLSM (the sheet must be chosen when there are several), CSV (UTF-8) and JSON (a list of
  objects or `{"items": [...]}`). Limits: 20 MB, 5000 rows.
- **Headers:** canonical only. Use the field name (`nominal_od_in`) or the label with its canonical unit
  (`Nominal OD (in)`). A known label without a unit, or with another unit (`Nominal OD (mm)`), blocks the file.
  Nothing is converted. Unknown columns are listed as ignored. Template:
  `docs/engineering/tubular_import_template.csv` (headers only).
- **Cells:**
  - A blank cell stays unavailable, never 0.
  - These make the row INVALID: non-numbers (`5-1/2`), booleans, NaN / ±inf, 0 or negative values, and Excel
    formulas. A formula is a derived value; its cached result is ignored.
  - The M157 geometry checks also apply: ID < OD, drift ≤ ID, and wall = (OD − ID)/2 within 0.001 in.
- **Provenance:**
  - Stated once for the file. Origin is `user`, or `manufacturer`, which needs manufacturer, document and an
    explicit licence. `derived` cannot be imported from a file.
  - A file whose provenance cites API 5DP / 5CT / RP 7G / TR 5C3 / Spec 7-2 or ISO 11960 / 11961 / 10400 is
    refused.
  - Every row also records the file SHA-256, its page (`Page` column) and `source row N`.
- **Row classes:**
  - NEW.
  - ALREADY_PRESENT: same values and source statement already in the set.
  - DUPLICATE_IN_FILE.
  - CONFLICT: same type, designation, grade and connection with different values, in the file or in the set.
    It is never overwritten.
  - INVALID.
- **Apply:**
  - Requires an explicit confirmation, a reason and a non-blocked preview.
  - INVALID or CONFLICT rows block the import unless a partial import is explicitly accepted.
  - The file must be byte-identical to the previewed one (SHA-256), and the set must still be a DRAFT. A row that
    was added to the set meanwhile refuses the whole import.
  - One transaction writes the NEW rows and the audit record `tubular_reference_import`. If the audit fails,
    nothing is written.
- **Raw file:** not stored. Only the values, the file name and the SHA-256 are kept.

## 4. Owner source-request package (M183)

To populate the library, the owner supplies for each source:

1. **The document**: manufacturer, title, document number, revision/date, URL. It is kept outside the
   repository.
2. **Written permission or licence text** that allows storing and redistributing the values inside DrillMaster
   databases, and in the installer if bundling is wanted. A public PDF is not enough.
3. **Confirmation that the values are not copied from API / ISO standards tables.** Otherwise a separate licence
   from the standards body is needed.
4. **The values in the template** (`docs/engineering/tubular_import_template.csv`), in canonical units, with
   blanks where the document does not state a value. Nothing is derived. Yield is never inferred from the grade.
5. **A named reviewer** who confirms the import preview and publishes the set.

Until then, users build their own libraries with origin `user`. Calculations cite only PUBLISHED sets through
immutable snapshots (M157, M189).

## 5. Not claimed

- No real tubular data populated. No licence was obtained or assumed.
- No API / ISO table content, no manufacturer data, no derived values.
- The DOE GDR and openwashdata datasets were evaluated, not adopted.
