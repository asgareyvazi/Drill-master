# ADR 0001 — Licence: OWNER DECISION PENDING

- **Status:** proposed; no licence chosen. Choosing a binding licence is
  reserved to the repository owner.
- **Date:** 2026-10-19 (M43)

## Context

- The repository is **public** and contains **no `LICENSE` file** and no
  licence metadata in `pyproject.toml`. Absent a licence, copyright law
  reserves all rights: others may view the code on GitHub but have no grant to
  use, modify or redistribute it.
- The Windows build bundles third-party runtime libraries whose licences
  constrain what DrillMaster's licence and distribution can be. Declared
  licences of the direct runtime dependencies (from installed package metadata
  of `requirements-lock.txt`; not legal advice):

| Dependency | Declared licence | Consequence for a distributed build |
|---|---|---|
| **PyMuPDF** (`fitz`; bundled by `packaging/DrillMaster.spec`, imported by `core/document_import.py` and `core/import_adapters/pdf_tables.py`) | **GNU AGPL-3.0**, or a commercial licence from Artifex | distributing a build that includes it requires either AGPL-3.0-compatible terms for the whole application (including source availability) **or** a commercial PyMuPDF licence |
| PySide6 / Qt | LGPL-3.0 (or commercial Qt) | allowed in proprietary software if the user can replace the Qt libraries (dynamic linking, as in a PyInstaller one-folder build), with licence notices and source offer for Qt |
| SQLAlchemy, openpyxl, pyqtgraph | MIT | notice required |
| bcrypt | Apache-2.0 | notice required; patent grant |
| numpy, pandas | BSD-3-Clause | notice required |
| matplotlib | matplotlib licence (PSF-style) | notice required |

Transitive dependencies have not been audited.

## Options

| Option | Fits PyMuPDF as bundled today | Notes |
|---|---|---|
| A. Proprietary / all rights reserved (status quo, made explicit) | **only with a commercial PyMuPDF licence**, or by replacing PyMuPDF | consider making the repository private; add a `LICENSE` stating the terms |
| B. AGPL-3.0-or-later | yes | strongest copyleft; network-use clause; most compatible with the current dependency set |
| C. GPL-3.0-or-later | AGPL-3.0 code may be combined with GPL-3.0 code (GPLv3 §13), but the combined work carries AGPL obligations | |
| D. Permissive (MIT / Apache-2.0) for DrillMaster's own code | the source can be permissive, but **a distributed build containing PyMuPDF is still governed by AGPL-3.0** unless a commercial licence is held | |

## Decision procedure (owner)

1. Decide distribution intent (internal tool, commercial product, open source).
2. Choose an option; if A or D with binary distribution, obtain a commercial
   PyMuPDF licence or replace PDF text extraction with a permissively licensed
   library (an engineering change with its own tests).
3. Add `LICENSE`, `pyproject.toml` `license = "<SPDX>"`, and a
   third-party-notices file shipped with the installer.
4. Record the decision here (status: accepted) with the date.

## Risk while undecided

Contributors and users have no licence grant; redistributing the current
Windows build may conflict with PyMuPDF's AGPL terms. No release should be
distributed externally until this is decided.
