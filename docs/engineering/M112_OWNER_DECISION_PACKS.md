# M112 – Owner decision packs

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED

Each pack states what the code does today, the evidence, the options and the decision the owner has to take.
No approval is recorded by this document, and the product has no approval action (the Method Catalogue shows
every entry as "NOT APPROVED — OWNER REVIEW REQUIRED"). Nothing gated was installed, downloaded or bundled
to write these packs. Licence facts come from `docs/engineering/dependency_audit.json`
(`tools/quality/dependency_audit.py`): installed metadata for pinned packages, published PyPI metadata
(read 2026-11-03) for optional packages that are not installed.

## Pack — ISCWSA / welleng

* **Today:** `core/engineering/adapters/welleng_adapter.py` imports `welleng` inside `try`; welleng is not
  installed, so the adapter reports unavailable. Anti-collision is SCREENING (no separation factor without an
  uncertainty model); no ISCWSA error model is shipped.
* **Evidence:** welleng 0.30.0 is Apache-2.0 (PyPI); the ISCWSA model tables it carries need their own
  licence review (M52 adoption register, entry 2). Catalogue: welleng entry OWNER REVIEW REQUIRED.
* **Options:** (a) keep SCREENING only; (b) adopt welleng after licence review of the model tables and a
  benchmark against published ISCWSA test wells; (c) own implementation of an error model with independent
  goldens.
* **Decision needed:** whether any error model may be used, which one, and on what benchmark evidence.

## Pack — pwptemp

* **Today:** not imported anywhere in the product; the catalogue lists it as OWNER REVIEW REQUIRED
  ("pwptemp is LGPL-3.0: owner decision required"). No temperature model is shipped.
* **Evidence:** pwptemp 0.3.6, LGPL v3 (PyPI); M52 register entry 15.
* **Options:** (a) none; (b) optional dynamic use with LGPL obligations (notice, relinkable, source offer);
  (c) own implementation with a benchmark.
* **Decision needed:** whether an LGPL package may be used, and how it would be distributed.

## Pack — torque_drag

* **Today:** `core/engineering/adapters/torque_drag_adapter.py` imports `torque_drag` only inside `try`
  (M112 made the second import guarded too); not installed, so `calculate` returns `None`. The product's
  own soft-string T&D engine is used; the stiff-string entry `tnd.stiff_string` is NOT IMPLEMENTED.
* **Evidence:** torque-drag 0.1.1, LGPL v3 (PyPI).
* **Options:** as for pwptemp.
* **Decision needed:** LGPL use or an own stiff-string implementation with a benchmark.

## Pack — PyMuPDF

* **Today:** a pre-existing **mandatory** dependency (`requirements.txt`, `requirements-lock.txt` 1.24.14,
  `pyproject.toml`); `fitz` is imported by `core/ddr_pdf_split.py`, `core/document_import.py`,
  `core/document_library.py` (text layer, page split, document index). Report PDF *generation* does not use it
  (Qt `QTextDocument`; AST test in M110).
* **Evidence:** installed metadata "GNU AFFERO GPL 3.0" (AGPL). Not removed or replaced (owner directive).
* **Options:** (a) commercial Artifex licence; (b) keep AGPL and meet its obligations for the distribution
  model; (c) replace with a permissively licensed parser (behaviour change; needs a parity benchmark).
* **Decision needed:** licence route before any distribution.

## Pack — OCR (RapidOCR, Tesseract, camelot, onnxruntime, MinerU, torch)

* **Today:** every OCR import is guarded (audit: `guarded: true`); none of the packages is installed;
  `requirements-optional.txt` is never installed here. A scanned page stops at "OCR unavailable" and nothing is
  guessed. MinerU runs only as an external, configured process; `torch` is only probed for a device.
* **Evidence:** camelot-py 2.0.0 MIT; pytesseract 0.3.13 Apache-2.0; pdf2image 1.17.0 MIT; rapidocr 3.10.0
  Apache-2.0; onnxruntime 1.31.1 MIT; torch 2.15.0 Apache-2.0 AND BSD/MIT family; MinerU 4.1.6
  "LicenseRef-MinerU-Open-Source-License" (custom: needs legal reading). OCR models/weights carry their own
  licences (not assessed: not downloaded).
* **Options:** (a) no OCR; (b) Tesseract (system binary) only; (c) RapidOCR with reviewed model licences;
  (d) MinerU after legal review of its licence.
* **Decision needed:** whether OCR is in scope, which engine and models, and GPU use.

## Pack — Kill sheet

* **Today:** label TRAINING AID; W13 Kill Sheet is NOT_SUPPORTED as a contract (TRAINING AID and the
  drill-string table); records are reproducible from their snapshot.
* **Options:** (a) stay TRAINING AID; (b) qualify against an independent, owner-supplied kill sheet set
  (driller's and wait-and-weight methods) and leave TRAINING AID only after sign-off.
* **Decision needed:** whether the kill sheet may leave TRAINING AID and on which evidence.

## Pack — Cost / currency

* **Today:** per-currency totals; no conversion; an empty currency is unknown, never USD
  (`core/cost_semantics.py`). No money migration has been made.
* **Options:** (a) keep per currency; (b) owner-supplied rates with date and source, stored per conversion;
  (c) a reporting currency per project.
* **Decision needed:** whether conversions are allowed and where rates come from.

## Pack — Hydraulics and method approvals

* **Today:** hydraulics engines are IMPLEMENTED with independent goldens (M90), W13 Hydraulics is
  NOT_SUPPORTED as a contract (M107 reason recorded); all 54 catalogue entries are NOT APPROVED.
* **Decision needed:** which methods the owner approves for which use, with which evidence — recorded outside
  the product, since the product has no approval action.

## Pack — 7.48 vs 7.48052 (gal/ft³)

* **Today:** pcf→ppg uses **7.48** in the kill sheet (`PCF_PER_PPG`), the T&D engine and the W13 formation
  pressure contract; **7.48052** in hydraulics (`hydraulics_engine.py`, `calculator_contracts.py` bit
  hydraulics, `extended.py`); `mud_volume.py` uses 42/7.4805 ft³/bbl. Difference 0.007 % (ppg
  values differ by ~7 × 10⁻⁵ relative). Documented deviation since M90; full inventory in M113.
* **Options:** (a) keep, documented; (b) adopt 7.48052 everywhere as a new method version (old records keep
  their version; never relabelled).
* **Decision needed:** which constant is authoritative.

## Pack — Datum / CRS

* **Today:** survey references and datum per `docs/engineering/SURVEY_REFERENCE_SCOPE.md`; a datum offset only
  with explicit parameters as a new revision; no CRS transformation, no GIS, no network (no online declination).
* **Decision needed:** whether CRS transformations enter scope, with which library (licence) and geodetic
  reference data.

## Pack — Qt for Python (LGPL-3.0) distribution

* **Today:** PySide6 / shiboken6 6.8.1.1 are LGPL ("GNU Library or Lesser General Public License (LGPL);
  Other/Proprietary License"). The product imports only PySide6. M112 removed a PyQt5 import (GPL-3.0) that had
  been inside W13 (D30).
* **Decision needed:** distribution model for the frozen Windows build (dynamic linking, relinkability,
  notices) — part of release authorization.

## Pack — qtribbon (unknown licence)

* **Today:** `main_window.py` imports `qtribbon` inside `try` and falls back to the built-in toolbar; it is not
  on PyPI and not installed; its licence is UNKNOWN.
* **Decision needed:** none while it is absent; it must not be bundled without a licence review.
