# M196 – Owner decision packages

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED

These packages update the M112 packs (`M112_OWNER_DECISION_PACKS.md`) and add the gates found since then.

- **Nothing here is a decision.** The engineering view in field 7 is advice only, and no approval is recorded.
- **Sources.** Licence facts come from `docs/engineering/dependency_audit.json` (installed metadata of the
  pinned packages) and from published PyPI metadata for packages that are not installed.
- **Unchanged until the owner decides.** Every gate keeps the behaviour in field 8.

The nine fields of every package are:

1. Decision
2. Current behaviour
3. Evidence
4. Licence / legal facts
5. Options
6. Consequences
7. Engineering view
8. Until decided
9. Owner must provide

---

## P1 — PyMuPDF (AGPL-3.0)

1. **Decision:** Keep PyMuPDF as the native PDF engine in a distributed build, or replace it.
2. **Current behaviour:** `PyMuPDF==1.24.14` is a mandatory locked dependency. It is used by the PDF import and the PDF split (`core/ddr_pdf_split.py`).
3. **Evidence:**
   - `requirements-lock.txt`;
   - `dependency_audit.json` (classified AGPL, owner-gated);
   - M52 register correction.
4. **Licence:** AGPL-3.0, or a commercial Artifex licence. Running PyMuPDF in a child process does not remove the AGPL obligations; this has never been claimed.
5. **Options:**
   - (a) buy a commercial licence;
   - (b) distribute under AGPL terms;
   - (c) replace it with pypdfium2 (BSD-3 / Apache-2.0) plus pdfminer.six (MIT) after a parity test on the synthetic PDF fixtures.
6. **Consequences:**
   - (b) creates source-offer obligations for the whole distributed application;
   - (c) means re-qualifying the PDF routes (M176 matrix).
7. **Engineering view:** (a) or (c). Option (c) is technically feasible; the native-PDF route tests are its acceptance gate.
8. **Until decided:** unchanged. The installer stays UNSIGNED and not release-approved.
9. **Owner must provide:** the chosen licence path in writing.

## P2 — Qt for Python (PySide6, LGPL-3.0)

1. **Decision:** How the LGPL obligations are met in the Windows installer.
2. **Current behaviour:** PySide6 6.8.1.1 is used through dynamic imports. The installer bundles the Qt DLLs unmodified, and `THIRD_PARTY_NOTICES.md` lists them.
3. **Evidence:** `packaging/DrillMaster.spec`; `dependency_audit.json`; the M137 report.
4. **Licence:** LGPL-3.0 requires the notice and licence text, the ability to replace the Qt libraries, and access to the Qt source of the shipped version.
5. **Options:**
   - (a) LGPL compliance (one-folder build, so the DLLs are replaceable, plus a written source offer);
   - (b) a commercial Qt licence.
6. **Consequences:** (a) needs the replaceability of the libraries to be documented and kept in every build.
7. **Engineering view:** (a). The current one-folder layout already keeps the DLLs replaceable.
8. **Until decided:** the build is distributed only internally, UNSIGNED.
9. **Owner must provide:** confirmation of the path, and the source-offer contact.

## P3 — pwptemp and torque_drag (LGPL-3.0)

1. **Decision:** Whether either package may be used.
2. **Current behaviour:** Neither is imported. T&D is the M127 own soft-string Johancsik implementation, and no temperature model ships.
3. **Evidence:** M52 register entries 15 and 18; the M193 re-audit (unchanged upstream, LGPL); `dependency_audit.json`.
4. **Licence:** LGPL-3.0 (PyPI: pwptemp 0.3.6, torque-drag 0.1.1).
5. **Options:**
   - (a) none;
   - (b) optional dynamic use with the LGPL obligations;
   - (c) own implementation with independent goldens.
6. **Consequences:** (b) needs benchmark evidence before any result is shown.
7. **Engineering view:** (a) for T&D (already covered); (c) if a temperature model is required.
8. **Until decided:** not used.
9. **Owner must provide:** the decision and, for (b) or (c), the benchmark cases.

## P4 — MinerU

1. **Decision:** Whether the optional MinerU route may be used or offered.
2. **Current behaviour:**
   - The route exists as an optional external engine (`core/mineru_engine.py`) that is never installed or bundled.
   - Its output is profile-mapped through the M174 aliases.
   - Real-document acceptance is NOT RUN.
3. **Evidence:** the M176 route parity doc; `tests/test_m174_header_aliases.py`; `tests/test_m176_route_parity.py`.
4. **Licence:** a custom MinerU licence (PyPI mineru 4.1.6, read for M112), and its models carry their own terms. Owner-gated.
5. **Options:**
   - (a) do not offer it;
   - (b) document it as a user-installed tool with the user's own licence acceptance;
   - (c) bundle it (needs a licence review of the code and every model).
6. **Consequences:** (c) adds GPU and model-weight questions (see P7).
7. **Engineering view:** (a) or (b).
8. **Until decided:** the route works only if the user installs MinerU, and it is labelled not accepted.
9. **Owner must provide:** the licence review result.

## P5 — OCR engines

1. **Decision:** Whether scanned DDR pages may be OCR'd, and with which engine.
2. **Current behaviour:** No OCR engine is bundled. Scanned pages are detected and reported as needing a text layer (M54).
3. **Evidence:** `core/import_adapters/pdf_generic_tables.py` scanned-page detection; `dependency_audit.json` (rapidocr Apache-2.0, pytesseract Apache-2.0, onnxruntime MIT, all not installed).
4. **Licence:**
   - The engines above are permissive.
   - Models and language data have their own terms.
   - The Tesseract binary is Apache-2.0.
5. **Options:**
   - (a) none;
   - (b) RapidOCR plus ONNX Runtime as an optional install, CPU only;
   - (c) a Tesseract external binary.
6. **Consequences:** OCR errors in numbers become data errors, so a review gate per OCR field would be mandatory.
7. **Engineering view:** (b) with OCR values always routed to review, never auto-accepted.
8. **Until decided:** none.
9. **Owner must provide:** the decision, and the model licence review.

## P6 — qtribbon

1. **Decision:** Whether the ribbon UI dependency may be shipped.
2. **Current behaviour:** Not installed; not on PyPI (licence UNKNOWN).
3. **Evidence:** `dependency_audit.json` (UNKNOWN); M112 pack.
4. **Licence:** unknown, so it is treated as not usable.
5. **Options:** (a) drop it; (b) find the upstream licence; (c) use plain Qt widgets (current).
6. **Consequences:** none for (a) or (c).
7. **Engineering view:** (a) or (c).
8. **Until decided:** not used.
9. **Owner must provide:** nothing, unless (b).

## P7 — AI / GPU / model weights

1. **Decision:** Whether any local model (embeddings or LLM) may ship, and whether a GPU is ever required.
2. **Current behaviour:** The Knowledge Assistant runs offline with lexical retrieval. No model weights, cloud LLM or API key are used.
3. **Evidence:** M49–M51 reports; `tests/test_m122_assistant_worker_lifecycle.py`.
4. **Licence:** model licences vary (for example, `qwen2.5:3b` is non-commercial, while `1.5b` and BGE-M3 / e5-small are permissive). Each exact weight needs its own review.
5. **Options:** (a) none; (b) a user-installed local runtime (Ollama, MIT) with an owner-approved model list; (c) bundled weights.
6. **Consequences:** (c) adds installer size and per-weight licence obligations.
7. **Engineering view:** (a) or (b), CPU only.
8. **Until decided:** offline, with no models.
9. **Owner must provide:** an approved model list with licences.

## P8 — 7.48 against 7.48052 (pcf ↔ ppg)

1. **Decision:** Which constant is canonical, and whether existing records keep their value.
2. **Current behaviour:** Both are in use. The inventory finds 17 uses of 7.48, 14 of 7.48052 and 2 of 7.4805, in 11 files. The difference is 0.007 % (75 pcf = 10.0267 ppg against 10.0260 ppg).
3. **Evidence:** `tools/quality/density_constant_inventory_m192.py`; `docs/mission-reports/m171-m200-evidence/density_constants_m192.json`; `tests/test_m192_density_constants.py`.
4. **Licence:** none.
5. **Options:**
   - (a) keep both, documented;
   - (b) make 7.48052 canonical through a method-version bump per affected contract (old cases re-run with their old version);
   - (c) make 7.48 canonical.
6. **Consequences:** (b) and (c) change printed values in the 4th–5th significant digit. Stored cases stay reproducible only through versioned methods.
7. **Engineering view:** (b), versioned, never a global replace.
8. **Until decided:** unchanged. The test fails on any silent change.
9. **Owner must provide:** the choice.

## P9 — Currency

1. **Decision:** How costs in different currencies are handled.
2. **Current behaviour:** Costs carry their currency, and mixing currencies is refused (M130: 300.00 / 347.06 USD/m goldens). No exchange rates are used.
3. **Evidence:** the M130 tests.
4. **Licence:** if rates are wanted, the source of the rates must be licensed.
5. **Options:** (a) single currency per well (current); (b) owner-entered dated rates with provenance.
6. **Consequences:** (b) needs a rate table with audit.
7. **Engineering view:** (a) until a rate source is named.
8. **Until decided:** mixing is refused.
9. **Owner must provide:** the rate source and policy.

## P10 — Datum and CRS

1. **Decision:** Whether geodetic CRS transforms are in scope.
2. **Current behaviour:**
   - Explicit vertical datum shifts are implemented.
   - CRS / geodetic is NOT IMPLEMENTED (`SURVEY_REFERENCE_SCOPE.md`).
   - The azimuth reference is declared and never guessed.
3. **Evidence:** `SURVEY_REFERENCE_SCOPE.md`; M105 / M129 tests (D11 PARTIAL).
4. **Licence:** pyproj (MIT) plus the EPSG database (its own terms).
5. **Options:** (a) keep declared references only; (b) add pyproj with an EPSG licence review and benchmark points.
6. **Consequences:** (b) is a new mandatory dependency with grid files.
7. **Engineering view:** (a) unless multi-well grid work is required.
8. **Until decided:** declared references only.
9. **Owner must provide:** the decision and reference coordinates for the benchmark.

## P11 — Kill Sheet

1. **Decision:** Whether the W13 Kill Sheet may leave TRAINING AID status.
2. **Current behaviour:** Classified TRAINING AID. It has no re-runnable contract, and its runs are labelled TRAINING AID in the history. The M184 library button in its pipe dialog changes neither of these.
3. **Evidence:** `core/calculator_contracts.LEAF_CLASSES`; `tests/test_m125_w13_classification.py`.
4. **Licence:** none.
5. **Options:** (a) keep it as a training aid; (b) qualify it against an owner-supplied, signed kill-sheet set.
6. **Consequences:** (b) is a safety-critical qualification.
7. **Engineering view:** (a) until reference sheets exist.
8. **Until decided:** TRAINING AID.
9. **Owner must provide:** signed reference kill sheets.

## P12 — Method approvals

1. **Decision:** Who may approve an engineering method, and how an approval is recorded.
2. **Current behaviour:** Every catalogue entry is "NOT APPROVED — OWNER REVIEW REQUIRED". There is no approval action, and "Approved By" text is not an approval.
3. **Evidence:** the Method Catalogue; M92 and M110.
4. **Licence:** none.
5. **Options:** (a) none; (b) a named-approver workflow with signatures (needs P16).
6. **Consequences:** (b) is a regulated record.
7. **Engineering view:** (b) only after signing (P16) exists.
8. **Until decided:** NOT APPROVED everywhere.
9. **Owner must provide:** the approver roles.

## P13 — Encryption at rest, HMAC, DPAPI, SQLCipher

1. **Decision:** Whether the database and backups are encrypted, and how audit tamper evidence is keyed.
2. **Current behaviour:**
   - NOT PROVIDED.
   - Plain SQLite files with application-level guards (including the new M189 published-tubular-set guards) and an append-only audit trigger.
   - Anyone who can write the file can drop the guards; this is documented in `core/security_posture.NON_CLAIMS`.
3. **Evidence:** `core/security_posture.py`; `tests/test_m136_security_hardening.py`; `tests/test_m184_m189_reference_integration.py` (guard test).
4. **Licence:** SQLCipher community edition is BSD-style, but its Python bindings vary. DPAPI is a Windows API.
5. **Options:**
   - (a) none;
   - (b) DPAPI-protected key plus SQLCipher;
   - (c) HMAC chain over audit records with a key outside the database.
6. **Consequences:**
   - Key custody and recovery: a lost key means lost data.
   - Backups need the key.
7. **Engineering view:** (c) first (tamper evidence), then (b) with a recovery procedure.
8. **Until decided:** NOT PROVIDED, and stated so in Tools › Security status.
9. **Owner must provide:** the key custody and recovery policy.

## P14 — Windows ACL

1. **Decision:** Whether the application sets or verifies ACLs on its data folder.
2. **Current behaviour:** NOT PROVIDED. The folder's inherited ACL applies.
3. **Evidence:** `core/security_posture.NON_CLAIMS`.
4. **Licence:** none.
5. **Options:** (a) none; (b) verify and warn; (c) set restrictive ACLs at install.
6. **Consequences:** (c) can lock out administrators or backups.
7. **Engineering view:** (b).
8. **Until decided:** NOT PROVIDED.
9. **Owner must provide:** the policy.

## P15 — Idle lock

1. **Decision:** The idle-lock policy (minutes).
2. **Current behaviour:** Implemented and OFF by default. `DRILLMASTER_SESSION_IDLE_MINUTES` takes 1…1440. Locking never discards edits, and lock events are audited.
3. **Evidence:** `core/session_lock.py`; `tests/test_m136_security_hardening.py`.
4. **Licence:** none.
5. **Options:** (a) off; (b) a fixed site value; (c) a user setting.
6. **Consequences:** none for data.
7. **Engineering view:** (b), set by the site.
8. **Until decided:** OFF.
9. **Owner must provide:** the value.

## P16 — Code and report signing

1. **Decision:** Whether the installer and reports are signed, and with which certificate.
2. **Current behaviour:** Nothing is signed. Everything is labelled UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.
3. **Evidence:** the Windows CI ("installer built UNSIGNED").
4. **Licence:** a code-signing certificate (purchased).
5. **Options:** (a) none; (b) Authenticode for the installer; (c) also signed report packages.
6. **Consequences:** certificate custody.
7. **Engineering view:** (b), then (c).
8. **Until decided:** UNSIGNED.
9. **Owner must provide:** the certificate and custody.

## P17 — Windows and field acceptance

1. **Decision:** Who performs interactive Windows acceptance and field acceptance, and against what checklist.
2. **Current behaviour:** CI builds and installs on Windows, runs the regression and lifecycle stress, and uninstalls. That is not interactive acceptance. Real-document (DDR) acceptance is NOT RUN.
3. **Evidence:** CI runs (see the M171–M200 report section U); `M117_USER_JOURNEYS.md`.
4. **Licence:** none.
5. **Options:** (a) none; (b) owner-run acceptance on the journeys, with signed results.
6. **Consequences:** this is required for any release.
7. **Engineering view:** (b).
8. **Until decided:** NOT FIELD-ACCEPTED.
9. **Owner must provide:** testers, machines and authorized documents.

## P18 — Tubular reference data source (new, M181)

1. **Decision:** Which licensed source may populate the tubular library.
2. **Current behaviour:** The library ships empty. Users import their own data through the controlled importer.
3. **Evidence:** `M181_TUBULAR_SOURCES.md`; `tests/test_m181_m183_tubular_import.py`; `tests/test_m190_tubular_journey.py`.
4. **Licence:**
   - API 5DP / 5CT / TR 5C3 / RP 7G and ISO tables need a licence from the standards body.
   - Manufacturer data needs written redistribution permission.
   - No public dataset qualified.
5. **Options:** (a) user data only; (b) a licensed manufacturer catalogue; (c) a licensed API / ISO data product.
6. **Consequences:** (b) and (c) add licence terms to the installer and the databases.
7. **Engineering view:** (a) now; (b) when permission exists.
8. **Until decided:** empty library.
9. **Owner must provide:** the M181 source-request package (document, licence, value file, reviewer).

## P19 — ISCWSA error models / welleng (carried over from M112)

1. **Decision:** Whether any wellbore position-uncertainty (ISCWSA error) model may be used, which one, and on
   what benchmark evidence.
2. **Current behaviour:**
   - `core/engineering/adapters/welleng_adapter.py` imports `welleng` inside `try`. welleng is not installed,
     so the adapter reports unavailable.
   - Anti-collision is **SCREENING** (centre-to-centre distance only). No separation factor is computed
     without an uncertainty model, and no ISCWSA error model is shipped.
3. **Evidence:** `M112_OWNER_DECISION_PACKS.md` (pack "ISCWSA / welleng"); M52 adoption register entry 2;
   M193 re-audit (`docs/mission-reports/m171-m200-evidence/oss_reaudit_m193.json`: welleng `d29adf906b`
   UNCHANGED, Apache-2.0); `tests/test_m112_dependency_audit.py` (optional import).
4. **Licence:**
   - welleng 0.30.0 is Apache-2.0 (PyPI metadata).
   - The ISCWSA model tables it carries need their **own** licence review. The code licence does not cover them.
5. **Options:** (a) keep SCREENING only; (b) adopt welleng after the model-table licence review and a benchmark
   against published ISCWSA test wells; (c) an own error-model implementation with independent goldens.
6. **Consequences:** (b) and (c) make separation factors safety-relevant outputs, which then need method approval
   (P12) and signing (P16).
7. **Engineering view:** (a) until a benchmark set and the table licence are confirmed.
8. **Until decided:** SCREENING – NO ISCWSA UNCERTAINTY – NO SEPARATION FACTOR – NOT APPROVED.
9. **Owner must provide:** the decision, the model-table licence position and the benchmark wells.

## M400 status (M385 / M398)

**No decision P1–P19 is recorded as approved.** `core/method_catalogue.OWNER_APPROVALS` is still empty; the
62-entry method catalogue shows "NOT APPROVED — OWNER REVIEW REQUIRED" on every row. What M361–M400 changed in the
evidence for each package:

| Package | State | M361–M400 evidence / consequence |
|---|---|---|
| P1 PyMuPDF | OPEN | unchanged (1.24.14; M386: no published advisory) |
| P2 PySide6 | OPEN — **recommendation updated** | `m378_pyside_decision_record.md`: 6.8.3 recommended, 6.8.2.1 alternative; "6.8.5 commercial-only" wording corrected (LGPL 6.8.4/6.8.5 LTS source tags exist, no wheels). Pin stays 6.8.1.1; a change moves all four packages and runs the M378 checklist |
| P3 pwptemp / torque_drag | OPEN | M379 re-audit unchanged; T&D stays own Johancsik code; stiff string NOT IMPLEMENTED |
| P4 MinerU, P5 OCR, P6 qtribbon, P7 AI | OPEN | unchanged |
| P8 density divisor | OPEN — current behaviour kept | M373 avoids the question: its gradient is pcf/144 (exact), no gallon conversion |
| P9 currency | OPEN | unchanged |
| P10 datum / CRS | OPEN | M368 refuses a datum or azimuth-reference mismatch instead of converting |
| P11 kill sheet | OPEN | M373 volumetric method added as **TRAINING AID** under P11; no operational claim |
| P12 method approvals | OPEN | +8 catalogue entries (M314–M373 services), all NOT APPROVED |
| P13–P15 security | OPEN | encryption at rest NOT PROVIDED (M375 step); M386 lock vulnerability audit added |
| P16 signing | OPEN | product label stays UNSIGNED |
| P17 Windows / field acceptance | OPEN | NOT RUN |
| P18 tubular data | OPEN | M371 takes OD / ID / yield as declared or page values; no rating table shipped |
| P19 ISCWSA | OPEN | M369 closest approach is centreline geometry; never called a separation factor |

Dependency change made without an owner gate: **pillow 12.3.0 → 13.0.0** (M386; 58 published advisories fixed in
13.0.0; same MIT-CMU licence; not a Qt package, so P2 does not apply). It is listed here so the owner can reverse it.

## M460 status (M401–M460)

**No decision P1–P19 is recorded as approved.** `core/method_catalogue.OWNER_APPROVALS` is still empty. The 66-entry method catalogue shows "NOT APPROVED — OWNER REVIEW REQUIRED" on every row.

| Package / decision | State | M401–M460 evidence / consequence |
|---|---|---|
| P2 PySide6 | OPEN | The pin stays at 6.8.1.1. M401–M460 extends the dialog-lifecycle test to the M372, M373 and the four new dialogs. |
| P8 density divisor | OPEN — current behaviour kept | M420 converts EMW with the exact 12/231 psi/ft per ppg. It needs no gallon-to-cubic-foot divisor. |
| P10 datum / CRS | OPEN | The M404 addendum restates the rule. M129 v2 trajectory comparison reduces RKB / RT to MSL through the declared `rte_msl`. M368 checks only that the datums are the same and refuses a mismatch. No CRS transform exists. |
| P11 kill sheet | OPEN | Unchanged. |
| P12 method approvals | OPEN | Four catalogue entries were added (m416, m420, m423, m427), all NOT APPROVED. |
| P19 ISCWSA | OPEN | Benchmark M412 D94 checks the centreline 3D closest approach. It is never called a separation factor. |
| D88 CI 3.12 timeout | **BLOCKED BY OWNER DECISION — active risk** | The 3.12 leg on `e9244e8` attempt 1 hit the TIMEOUT; the re-run passed in 56m19s. M409 (`m409_suite_profile.md`) gives the per-file time shares and a balanced two- or three-way split as decision input. The 60 min limit has not been raised and the workflow has not been split. |
| `BL-BIT-DEFAULTS` | OPEN (backlog) | `d_exponent_corrected` defaults to a normal gradient of 8.6 ppg. `cost_per_foot` without rotating hours returns the trip-only cost. Both are documented, not changed. |
| `BL-SS-CONSOLIDATE` | OPEN (backlog) | Two surge methods coexist: the legacy W13 screening and M420. Consolidating them is an owner and product decision. |
| `BL-M408` | OPEN | The `test_m129` intermittent failure was not reproduced (loaded 396/396 twice, 20/20 repeats). |

