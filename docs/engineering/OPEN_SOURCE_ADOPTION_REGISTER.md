# Open-source adoption register (M52)

Status: COMPLETE for the 50 repositories named in the M52 brief. Every repository was downloaded as a source tarball at the SHA below into an isolated temporary directory (`/home/user/m52-work/oss/`, outside the repository) and reviewed read-only. **No upstream code was executed, installed into the application environment or copied into Drill-master.**

Classifications: ADOPT (use as-is) / ADAPT (copy and modify, licence permitting) / REUSE ALGORITHM (independent re-implementation of a documented method) / INSPIRE ONLY (ideas; nothing copied) / REJECT / OWNER REVIEW REQUIRED.

Rules applied: no-licence repositories are ideas only; GPL/LGPL/CC-NC code is owner-gated and not taken; no cloud APIs, model downloads or new mandatory dependencies; any safety-relevant method needs an independent reference before it enters an engine; no ISCWSA claim without reference validation.

## Summary

| Classification | Count |
|---|---|
| ADOPT | 0 |
| ADAPT | 0 |
| REUSE ALGORITHM | 2 |
| INSPIRE ONLY | 39 |
| OWNER REVIEW REQUIRED | 2 |
| REJECT | 7 |

What reached the product: two independent re-implementations, no copied code:

* `core/trajectory_compare.py` (plan vs actual and offset-well centre-to-centre screening, exact minimum-curvature arc, continuous closest approach). Method ideas from **welleng** (Apache-2.0). Labelled `SCREENING - centre-to-centre, no ISCWSA uncertainty, NOT APPROVED`.
* `CementEngine.balanced_plug` (SCREENING). Method from **cement-calc** (MIT), attribution in `THIRD_PARTY_NOTICES.md`.

Dependencies: **M52 adds no runtime or development dependency.** `pyproject.toml` and `requirements-lock.txt` (the dependency inventory) are unchanged; scipy, pyproj, PyMuPDF, OCR engines and embedding models remain absent.

Owner decisions opened by this review: welleng ISCWSA error models (scipy/pyproj, reference validation); LGPL pro-well-plan (pwptemp, torque_drag); any GPL (ejbo2001) or CC BY-NC (nmamzada) code; PyMuPDF (AGPL) and OCR/embedding models used by the DDR/RAG repositories; well-control calculators (kill-sheet).

## Overview

| # | Repository | Group | Licence (file) | Classification |
|---|---|---|---|---|
| 1 | [ShreshthSrivastav/DrillingAdvisor](https://github.com/ShreshthSrivastav/DrillingAdvisor) | C | none detected | INSPIRE ONLY |
| 2 | [jonnymaserati/welleng](https://github.com/jonnymaserati/welleng) | A | Apache-2.0 | REUSE ALGORITHM |
| 3 | [BillyFrcs/DrillingEngineeringOperations](https://github.com/BillyFrcs/DrillingEngineeringOperations) | D | MIT | INSPIRE ONLY |
| 4 | [Kukuruza24110/well-engineer](https://github.com/Kukuruza24110/well-engineer) | D | none detected | INSPIRE ONLY |
| 5 | [dasvan/engineering-calculations](https://github.com/dasvan/engineering-calculations) | D | none detected | INSPIRE ONLY |
| 6 | [manjramkar/Drilling-Engineering](https://github.com/manjramkar/Drilling-Engineering) | A | none detected | INSPIRE ONLY |
| 7 | [Otto-Destiny/3d_well_trajectory_visualization](https://github.com/Otto-Destiny/3d_well_trajectory_visualization) | A | none detected | INSPIRE ONLY |
| 8 | [juangjuang74-eng/drilling-engineer-toolkit](https://github.com/juangjuang74-eng/drilling-engineer-toolkit) | D | MIT | INSPIRE ONLY |
| 9 | [mengyangcup/drilling_engineering_design](https://github.com/mengyangcup/drilling_engineering_design) | D | none detected | INSPIRE ONLY |
| 10 | [johnryan417/python-for-drilling-engineers](https://github.com/johnryan417/python-for-drilling-engineers) | F | none detected | INSPIRE ONLY |
| 11 | [Himageo2006/mud-engineer-pro](https://github.com/Himageo2006/mud-engineer-pro) | D | none detected | INSPIRE ONLY |
| 12 | [f0nzie/volve-drilling](https://github.com/f0nzie/volve-drilling) | F | none detected | INSPIRE ONLY |
| 13 | [jntran08/DataAnalyticsforEngineering](https://github.com/jntran08/DataAnalyticsforEngineering) | F | none detected | INSPIRE ONLY |
| 14 | [ejbo2001/3D-directional-drilling-engine](https://github.com/ejbo2001/3D-directional-drilling-engine) | A | GPL-3.0 | REJECT |
| 15 | [pro-well-plan/pwptemp](https://github.com/pro-well-plan/pwptemp) | E | LGPL-3.0 | OWNER REVIEW REQUIRED |
| 16 | [fraclad/wellArchitectureDesign](https://github.com/fraclad/wellArchitectureDesign) | D | MIT | INSPIRE ONLY |
| 17 | [bpamos/welltrajconvert](https://github.com/bpamos/welltrajconvert) | A | MIT | INSPIRE ONLY |
| 18 | [pro-well-plan/torque_drag](https://github.com/pro-well-plan/torque_drag) | D | LGPL-3.0 | OWNER REVIEW REQUIRED |
| 19 | [almasovAzad/Wellbore_Stability](https://github.com/almasovAzad/Wellbore_Stability) | E | none detected | INSPIRE ONLY |
| 20 | [Atashnezhad/Petroleum_Engineering](https://github.com/Atashnezhad/Petroleum_Engineering) | D | MIT | INSPIRE ONLY |
| 21 | [maribickpostanes/Interactive-Well-Trajectory-Plot](https://github.com/maribickpostanes/Interactive-Well-Trajectory-Plot) | A | none detected | INSPIRE ONLY |
| 22 | [ArokyaMatthew/DrillMind](https://github.com/ArokyaMatthew/DrillMind) | C | MIT | INSPIRE ONLY |
| 23 | [geoharkat/Directional-Well-Planner](https://github.com/geoharkat/Directional-Well-Planner) | A | MIT | INSPIRE ONLY |
| 24 | [FrancisFM/Smart-PAD-Scheduler](https://github.com/FrancisFM/Smart-PAD-Scheduler) | F | MIT | INSPIRE ONLY |
| 25 | [kcabrera-oil-gas/drilling-optimization](https://github.com/kcabrera-oil-gas/drilling-optimization) | F | none detected | REJECT |
| 26 | [poetabdullah/DrillSense](https://github.com/poetabdullah/DrillSense) | C | none detected | REJECT |
| 27 | [wjwhitmire/npt-cost](https://github.com/wjwhitmire/npt-cost) | F | MIT | INSPIRE ONLY |
| 28 | [wjwhitmire/wellpath](https://github.com/wjwhitmire/wellpath) | A | MIT | INSPIRE ONLY |
| 29 | [djimrastephane/DDR_UTAH_FORGE](https://github.com/djimrastephane/DDR_UTAH_FORGE) | B | MIT | INSPIRE ONLY |
| 30 | [wjwhitmire/kill-sheet](https://github.com/wjwhitmire/kill-sheet) | D | MIT | INSPIRE ONLY |
| 31 | [wjwhitmire/cement-calc](https://github.com/wjwhitmire/cement-calc) | D | MIT | REUSE ALGORITHM |
| 32 | [gewazy/DrillingManagementStudio](https://github.com/gewazy/DrillingManagementStudio) | B | MIT | INSPIRE ONLY |
| 33 | [B0yko/wellbrief](https://github.com/B0yko/wellbrief) | C | Apache-2.0 | INSPIRE ONLY |
| 34 | [chinuckb/Drilling-Well-Path-Design](https://github.com/chinuckb/Drilling-Well-Path-Design) | A | none detected | INSPIRE ONLY |
| 35 | [awojinrin/ML-Workflow-for-the-Determination-of-Hole-Cleaning-Conditions](https://github.com/awojinrin/ML-Workflow-for-the-Determination-of-Hole-Cleaning-Conditions) | F | MIT | INSPIRE ONLY |
| 36 | [mhnajafi7/pdf-report-table-extractor](https://github.com/mhnajafi7/pdf-report-table-extractor) | B | Apache-2.0 | INSPIRE ONLY |
| 37 | [nmamzada/drilling-report-database](https://github.com/nmamzada/drilling-report-database) | B | NOASSERTION | REJECT |
| 38 | [aytacbie/drilling-reports-ds-pipeline](https://github.com/aytacbie/drilling-reports-ds-pipeline) | B | none detected | INSPIRE ONLY |
| 39 | [djimrastephane/ddr-rag-book](https://github.com/djimrastephane/ddr-rag-book) | C | NOASSERTION | INSPIRE ONLY |
| 40 | [geoharkat/welltraj](https://github.com/geoharkat/welltraj) | A | MIT | INSPIRE ONLY |
| 41 | [ldocallaghan/BoreTHM](https://github.com/ldocallaghan/BoreTHM) | E | Apache-2.0 | INSPIRE ONLY |
| 42 | [SiliconWit/drillstring-surface-recoverability](https://github.com/SiliconWit/drillstring-surface-recoverability) | F | MIT | INSPIRE ONLY |
| 43 | [imadeddinedjekoune/DrillAR-Sonatrach](https://github.com/imadeddinedjekoune/DrillAR-Sonatrach) | F | none detected | REJECT |
| 44 | [NajafiIB/wellbore-stability-model-selector](https://github.com/NajafiIB/wellbore-stability-model-selector) | E | MIT | INSPIRE ONLY |
| 45 | [Anatoly5ms/drilling_complication_prognostication](https://github.com/Anatoly5ms/drilling_complication_prognostication) | F | MIT | INSPIRE ONLY |
| 46 | [Athori99/RigTrack-Drilling-Dashboard-PHR](https://github.com/Athori99/RigTrack-Drilling-Dashboard-PHR) | F | none detected | INSPIRE ONLY |
| 47 | [DrillerDB/drillerdb-mcp](https://github.com/DrillerDB/drillerdb-mcp) | C | MIT | REJECT |
| 48 | [api-evangelist/national-oilwell-varco](https://github.com/api-evangelist/national-oilwell-varco) | F | none detected | REJECT |
| 49 | [BJZ-BJZ/marine-deepsea-drilling](https://github.com/BJZ-BJZ/marine-deepsea-drilling) | F | none detected | INSPIRE ONLY |
| 50 | [avrangainulloev/DrillingCore](https://github.com/avrangainulloev/DrillingCore) | B | none detected | INSPIRE ONLY |

## Details

Fields: upstream SHA (default-branch HEAD at review), licence evidence, language, declared dependencies, test files, Windows/offline, data and redistribution, numerics, classification, use in Drill-master, copied code / modified files.

### 1. ShreshthSrivastav/DrillingAdvisor

* URL: https://github.com/ShreshthSrivastav/DrillingAdvisor
* Upstream SHA: `ba971ba7295949b3578bd8b9de5a13068f972336` (2024-12-05, branch `main`)
* Licence: none detected; licence files: none
* Language: Python; files: 9
* Dependencies: joblib, langchain-community, llama-index, llama-index-core, llama-index-embeddings-huggingface, llama-index-embeddings-openai, streamlit, transformers
* Test files: 0
* Windows / offline: Needs network (OpenAI embeddings option) and Streamlit; not executed.
* Data / redistribution: Bundles a prebuilt vector store; redistribution terms unknown (no licence).
* Numerics: No numerics.
* Group: C (Offline knowledge assistant)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: LLM advisory demo (LlamaIndex, OpenAI/HuggingFace embeddings, Streamlit). No licence file: ideas only. Cloud embedding path conflicts with the offline rule; the M51 Knowledge Assistant already covers offline retrieval.
* Copied code / modified files: none

### 2. jonnymaserati/welleng

* URL: https://github.com/jonnymaserati/welleng
* Upstream SHA: `d29adf906b38e08e3f8b5a10409305bb1c058992` (2026-10-25, branch `main`)
* Licence: Apache-2.0; licence files: `LICENSE`
* Language: Python; files: 587
* Dependencies: numpy (<3), scipy, openpyxl, pandas, pint, pydantic, pyproj, PyYAML; optional extras include vtk/vedo/trimesh, python-fcl, coolprop, sympy, lasio
* Test files: 167
* Windows / offline: Pure Python + numpy/scipy; would run offline; not installed in the app environment. Cloud API not used.
* Data / redistribution: Ships ISCWSA tool-group spreadsheets (third-party content; redistribution not assessed - not copied).
* Numerics: Upstream has 167 test files; not used as the golden reference for M52 (independent analytical references are used instead).
* Group: A (Trajectory / anti-collision)
* **Classification: REUSE ALGORITHM**
* Use in Drill-master: Minimum-curvature interpolation and closest-approach concepts informed core/trajectory_compare.py (independent implementation, no code copied, not a dependency). ISCWSA error models and separation factor: OWNER REVIEW REQUIRED (needs reference validation against the matching ISCWSA revision; adds scipy/pyproj).
* Pre-existing (not M52): `core/engineering/adapters/welleng_adapter.py` (since M27) imports welleng only if the user installs it; `requirements-optional.txt` lists it as a third-party adapter to install and review. welleng is not installed in the build/test environment and M52 did not change the adapter.
* Copied code / modified files: none

### 3. BillyFrcs/DrillingEngineeringOperations

* URL: https://github.com/BillyFrcs/DrillingEngineeringOperations
* Upstream SHA: `5195e1129d936739950008f86b16b12a5ce1ec68` (2026-05-08, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 77
* Dependencies: click, requests
* Test files: 0
* Windows / offline: Python CLI; not executed.
* Data / redistribution: No data.
* Numerics: No tests; formulas unsourced.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Small drilling-operations calculators without tests; overlaps existing W13 engines.
* Copied code / modified files: none

### 4. Kukuruza24110/well-engineer

* URL: https://github.com/Kukuruza24110/well-engineer
* Upstream SHA: `ebd02d9b26b77aa9121d08e3976dd01fbc8c16a3` (2026-08-09, branch `main`)
* Licence: none detected; licence files: none
* Language: JavaScript; files: 7
* Dependencies: @vitejs/plugin-react, lucide-react, react, react-dom, vite
* Test files: 0
* Windows / offline: Browser app; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: React/Vite web app; no licence file: ideas only. Stack not compatible (PySide6 only).
* Copied code / modified files: none

### 5. dasvan/engineering-calculations

* URL: https://github.com/dasvan/engineering-calculations
* Upstream SHA: `684ba9ef9c131ec69f4d68ef46f6d59bad5cbd39` (2025-11-09, branch `main`)
* Licence: none detected; licence files: none
* Language: CSS; files: 19
* Dependencies: none declared
* Test files: 0
* Windows / offline: Static web page; not executed.
* Data / redistribution: No data.
* Numerics: No tests; formulas unsourced.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Static HTML/CSS/JS field calculators (drilling fluids, directional). No licence file and no licence statement in the README: all rights reserved, ideas only. Formulas are not sourced.
* Copied code / modified files: none

### 6. manjramkar/Drilling-Engineering

* URL: https://github.com/manjramkar/Drilling-Engineering
* Upstream SHA: `3c0418b3f3cde919b57bb20f19504f9bba933447` (2020-09-04, branch `master`)
* Licence: none detected; licence files: none
* Language: Jupyter Notebook; files: 6
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebook; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Trajectory notebook; no licence file. The app already has a tested minimum-curvature engine.
* Copied code / modified files: none

### 7. Otto-Destiny/3d_well_trajectory_visualization

* URL: https://github.com/Otto-Destiny/3d_well_trajectory_visualization
* Upstream SHA: `a66e754ce552918db5792f37ca624602c8c1eb4e` (2025-06-27, branch `main`)
* Licence: none detected; licence files: none
* Language: HTML; files: 10
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebook/HTML; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Plotly 3D trajectory demo; no licence file. The app already has a Matplotlib 3D view (M44-M50).
* Copied code / modified files: none

### 8. juangjuang74-eng/drilling-engineer-toolkit

* URL: https://github.com/juangjuang74-eng/drilling-engineer-toolkit
* Upstream SHA: `8537e1df1dbab24b41e4a0b6eb29d6619f667f01` (2026-04-28, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 8
* Dependencies: black, flake8, ipykernel, jupyterlab, matplotlib, numpy, pandas, petropt, plotly, pytest, pytest-cov, scipy
* Test files: 1
* Windows / offline: Python; not executed.
* Data / redistribution: No data.
* Numerics: 1 test file; no reference cases.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT toolkit with 1 test; depends on petropt/scipy. Nothing adopted: formulas would need independent references first.
* Copied code / modified files: none

### 9. mengyangcup/drilling_engineering_design

* URL: https://github.com/mengyangcup/drilling_engineering_design
* Upstream SHA: `43342279c6e1ce91f92a3f95dbca4002408bc32c` (2021-12-03, branch `main`)
* Licence: none detected; licence files: none
* Language: Jupyter Notebook; files: 14
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebook; not executed.
* Data / redistribution: Bundles a course PDF; no licence.
* Numerics: No tests.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Course design notebooks (Chinese); no licence file.
* Copied code / modified files: none

### 10. johnryan417/python-for-drilling-engineers

* URL: https://github.com/johnryan417/python-for-drilling-engineers
* Upstream SHA: `61e88036e0107f10de0b3f23b3d011db10c1f1cf` (2025-06-26, branch `main`)
* Licence: none detected; licence files: none
* Language: HTML; files: 37
* Dependencies: XlsxWriter, ipykernel, jupyter, matplotlib, numpy, pandas, scikit-learn, seaborn, ydata-profiling
* Test files: 0
* Windows / offline: Notebooks; not executed.
* Data / redistribution: Includes a bit-run CSV with unknown provenance/licence - not copied.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Course notebooks (pandas/sklearn); no licence file.
* Copied code / modified files: none

### 11. Himageo2006/mud-engineer-pro

* URL: https://github.com/Himageo2006/mud-engineer-pro
* Upstream SHA: `e244ce1e2e8d459e5acfecd9e53b51da240b775d` (2026-10-27, branch `main`)
* Licence: none detected; licence files: none
* Language: HTML; files: 33
* Dependencies: @capacitor/android, @capacitor/core, @capacitor/ios, cordova-plugin-purchase
* Test files: 0
* Windows / offline: Mobile/web; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Capacitor mobile app with an in-app purchase plugin; no licence file.
* Copied code / modified files: none

### 12. f0nzie/volve-drilling

* URL: https://github.com/f0nzie/volve-drilling
* Upstream SHA: `3698c43d4adc0ee11ffa8fd5f876fa961c9c846d` (2019-01-31, branch `master`)
* Licence: none detected; licence files: none
* Language: R; files: 406
* Dependencies: none declared
* Test files: 0
* Windows / offline: R; not executed.
* Data / redistribution: Volve data is under the Equinor Open Data Licence; not copied, not used.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: R analysis of the Volve dataset; no code licence file.
* Copied code / modified files: none

### 13. jntran08/DataAnalyticsforEngineering

* URL: https://github.com/jntran08/DataAnalyticsforEngineering
* Upstream SHA: `823e1e53af94d5b53e2806615ef01b55d1d956a7` (2020-10-29, branch `main`)
* Licence: none detected; licence files: none
* Language: Jupyter Notebook; files: 3
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebook; not executed.
* Data / redistribution: Includes a paper PDF; not copied.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Geosteering ML notebook on Volve data; no licence file.
* Copied code / modified files: none

### 14. ejbo2001/3D-directional-drilling-engine

* URL: https://github.com/ejbo2001/3D-directional-drilling-engine
* Upstream SHA: `f96787d7c5c412693d9e7f1424ea10746d013ee2` (2026-04-10, branch `main`)
* Licence: GPL-3.0; licence files: `LICENSE`
* Language: Python; files: 17
* Dependencies: lasio, numpy, pandas, plotly, pytest, scipy, streamlit
* Test files: 2
* Windows / offline: Python/Streamlit; not executed.
* Data / redistribution: Includes a Volve-derived LAS/CSV; not copied.
* Numerics: 2 test files; not used.
* Group: A (Trajectory / anti-collision)
* **Classification: REJECT**
* Use in Drill-master: GPL-3.0 LICENSE file (README shows an MIT badge - conflicting; the LICENSE file governs). GPL code is not taken (owner-gated). Concepts already covered by the existing engine.
* Copied code / modified files: none

### 15. pro-well-plan/pwptemp

* URL: https://github.com/pro-well-plan/pwptemp
* Upstream SHA: `a6d73e24b412623b9831fb71b7be9b9e9ed8ff8b` (2021-03-02, branch `master`)
* Licence: LGPL-3.0; licence files: `LICENSE.md`
* Language: Python; files: 55
* Dependencies: numpy, plotly, scipy, torque_drag, well_profile
* Test files: 9
* Windows / offline: Python + scipy; not executed.
* Data / redistribution: Test trajectory spreadsheet only.
* Numerics: 9 test files; not used.
* Group: E (Thermal / stability (optional))
* **Classification: OWNER REVIEW REQUIRED**
* Use in Drill-master: LGPL-3.0 well-temperature models (group E, optional). Review only; any use needs an owner licence decision and independent validation.
* Copied code / modified files: none

### 16. fraclad/wellArchitectureDesign

* URL: https://github.com/fraclad/wellArchitectureDesign
* Upstream SHA: `0573d473df02ec318b3f6ba807f8c6e8cdd5e3c9` (2024-12-22, branch `main`)
* Licence: MIT; licence files: `LICENSE.md`
* Language: Python; files: 14
* Dependencies: matplotlib, numpy
* Test files: 0
* Windows / offline: Python; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT Matplotlib casing-architecture drawing; the app already renders a schematic from stored objects.
* Copied code / modified files: none

### 17. bpamos/welltrajconvert

* URL: https://github.com/bpamos/welltrajconvert
* Upstream SHA: `86ee684fdb1968218ac17e4b260df80c6c88f475` (2020-10-27, branch `master`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 58
* Dependencies: dataclasses, jupyter, matplotlib, nbsphinx, numpy, pandas, pathlib, pyproj, scipy, sphinx, utm
* Test files: 15
* Windows / offline: Python; not executed.
* Data / redistribution: Example survey files (synthetic/public); not copied.
* Numerics: 15 test files; not used.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT survey metadata/CRS conversion; requires pyproj/utm (not in the app). The CRS idea is reflected by refusing well-to-well comparison until the user confirms one projected CRS.
* Copied code / modified files: none

### 18. pro-well-plan/torque_drag

* URL: https://github.com/pro-well-plan/torque_drag
* Upstream SHA: `701cfff5990e33b495f45e082364d608ee65db87` (2021-07-28, branch `master`)
* Licence: LGPL-3.0; licence files: `LICENSE.md`
* Language: Python; files: 24
* Dependencies: plotly, well_profile
* Test files: 2
* Windows / offline: Python; not executed.
* Data / redistribution: No data.
* Numerics: 2 test files.
* Group: D (Calculators)
* **Classification: OWNER REVIEW REQUIRED**
* Use in Drill-master: LGPL-3.0 torque & drag; review only, owner licence decision needed.
* Copied code / modified files: none

### 19. almasovAzad/Wellbore_Stability

* URL: https://github.com/almasovAzad/Wellbore_Stability
* Upstream SHA: `834e52c5d9e3490a3cbc198a1020572b88394ae1` (2020-11-06, branch `main`)
* Licence: none detected; licence files: none
* Language: MATLAB; files: 6
* Dependencies: none declared
* Test files: 0
* Windows / offline: MATLAB; not executed.
* Data / redistribution: Spreadsheets and a report PDF; not copied.
* Numerics: No tests.
* Group: E (Thermal / stability (optional))
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MATLAB class project (Mohr-Coulomb); no licence file.
* Copied code / modified files: none

### 20. Atashnezhad/Petroleum_Engineering

* URL: https://github.com/Atashnezhad/Petroleum_Engineering
* Upstream SHA: `f074c07a1d18fb60354a9c9aac37daa0c81bed31` (2021-02-25, branch `master`)
* Licence: MIT; licence files: `LICENSE`
* Language: Jupyter Notebook; files: 73
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebooks; not executed.
* Data / redistribution: Datasets of unknown provenance; not copied.
* Numerics: No tests.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT notebooks (drilling simulator etc.) without tests.
* Copied code / modified files: none

### 21. maribickpostanes/Interactive-Well-Trajectory-Plot

* URL: https://github.com/maribickpostanes/Interactive-Well-Trajectory-Plot
* Upstream SHA: `6231dc346f6a6f38be21404005d930d7d3abbc89` (2026-06-06, branch `main`)
* Licence: none detected; licence files: none
* Language: HTML; files: 11
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebook/HTML; not executed.
* Data / redistribution: Mentions Volve licence partners; no data copied.
* Numerics: No tests.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Plotly trajectory plot of Volve wells; no licence file.
* Copied code / modified files: none

### 22. ArokyaMatthew/DrillMind

* URL: https://github.com/ArokyaMatthew/DrillMind
* Upstream SHA: `bcc9e5d5020130f54c84449f4f984e08a0f8ee13` (2026-06-02, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 76
* Dependencies: fastapi, uvicorn, httpx, pydantic, rank_bm25, numpy, pandas, openpyxl, pyyaml, loguru, prometheus_client
* Test files: 7
* Windows / offline: Python web service; not executed.
* Data / redistribution: No data.
* Numerics: 7 test files; not used.
* Group: C (Offline knowledge assistant)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT FastAPI service with hybrid BM25 RAG and anomaly flags. A web service is out of architecture; hybrid lexical retrieval already exists offline in the app (M51).
* Copied code / modified files: none

### 23. geoharkat/Directional-Well-Planner

* URL: https://github.com/geoharkat/Directional-Well-Planner
* Upstream SHA: `5bd74dd1458442ec2c9a24074cbd4e0295a0eff5` (2026-05-04, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: HTML; files: 6
* Dependencies: none declared
* Test files: 0
* Windows / offline: Browser; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT client-side planner (single HTML). Not adopted: browser JS, no tests.
* Copied code / modified files: none

### 24. FrancisFM/Smart-PAD-Scheduler

* URL: https://github.com/FrancisFM/Smart-PAD-Scheduler
* Upstream SHA: `54b1632d9ae0daa9cd7ea6569dacee59264c94f6` (2020-05-23, branch `master`)
* Licence: MIT; licence files: `LICENSE`
* Language: Jupyter Notebook; files: 7
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebook; not executed.
* Data / redistribution: CSV datasets of unknown provenance; not copied.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT pad-scheduling optimiser notebook; outside M52 scope.
* Copied code / modified files: none

### 25. kcabrera-oil-gas/drilling-optimization

* URL: https://github.com/kcabrera-oil-gas/drilling-optimization
* Upstream SHA: `fc9cc87c7a6a161bb6541b41b61c7bd9dadfa137` (2026-07-29, branch `main`)
* Licence: none detected; licence files: none
* Language: Python; files: 47
* Dependencies: flask, joblib, matplotlib, numpy, python-dotenv, scikit-learn, streamlit
* Test files: 4
* Windows / offline: Python web; not executed.
* Data / redistribution: Pickled models - not loaded, not copied.
* Numerics: 4 test files.
* Group: F (Analytics / other)
* **Classification: REJECT**
* Use in Drill-master: No licence file, ships pickled models (unsafe to load) and a Flask/Streamlit stack. Nothing taken; ML risk outputs would need defensible data.
* Copied code / modified files: none

### 26. poetabdullah/DrillSense

* URL: https://github.com/poetabdullah/DrillSense
* Upstream SHA: `4ac25221c6f414fd15790a7175b702f2ff3451fc` (2025-10-12, branch `main`)
* Licence: none detected; licence files: none
* Language: Jupyter Notebook; files: 84
* Dependencies: @testing-library/dom, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, bootstrap, es-toolkit, faiss-cpu, fastapi, framer-motion, google-cloud-aiplatform, google-cloud-storage, gunicorn
* Test files: 0
* Windows / offline: Requires cloud services.
* Data / redistribution: Bundles embeddings pickles - not loaded.
* Numerics: No tests.
* Group: C (Offline knowledge assistant)
* **Classification: REJECT**
* Use in Drill-master: No licence file; depends on Google Cloud AI Platform/Storage - conflicts with the offline, no-cloud rule.
* Copied code / modified files: none

### 27. wjwhitmire/npt-cost

* URL: https://github.com/wjwhitmire/npt-cost
* Upstream SHA: `3ae72097d4e98ac783bbbb10e778844b459bf686` (2026-10-24, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: HTML; files: 21
* Dependencies: none declared
* Test files: 5
* Windows / offline: Browser app; not executed.
* Data / redistribution: Test vectors only.
* Numerics: 5 test files (self-generated vectors).
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT NPT cost (hours x rate) calculator. NOT implemented in M52 (decision recorded: cost rates are owner data; money handling is owner-gated).
* Copied code / modified files: none

### 28. wjwhitmire/wellpath

* URL: https://github.com/wjwhitmire/wellpath
* Upstream SHA: `8e3bb5896feb3bf23dc71e5635b227fb764dde2d` (2026-10-24, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 22
* Dependencies: none declared
* Test files: 6
* Windows / offline: Python + browser; not executed.
* Data / redistribution: Example CSV; not copied.
* Numerics: 6 test files; self-generated vectors.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT minimum-curvature survey calculator. The app already has a tested engine; the upstream vectors are produced by its own library, so they are not an independent golden reference.
* Copied code / modified files: none

### 29. djimrastephane/DDR_UTAH_FORGE

* URL: https://github.com/djimrastephane/DDR_UTAH_FORGE
* Upstream SHA: `092fa7c7890d4a41f34ff8bd2cc7b2b938578edd` (2026-07-24, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 146
* Dependencies: PyYAML, faiss-cpu, fastapi, numpy, pandas, pdf2image, pdfplumber, plotly, pyarrow, pymupdf, pytesseract, pytest
* Test files: 9
* Windows / offline: Python; not executed.
* Data / redistribution: Public FORGE DDRs are not bundled here; none copied.
* Numerics: 9 test files; not used.
* Group: B (DDR ingestion / manual entry)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT DDR pipeline for the public FORGE archive. Profile-based extraction ideas only; no FORGE-specific rules. Depends on PyMuPDF (AGPL, owner-gated), pytesseract, faiss.
* Copied code / modified files: none

### 30. wjwhitmire/kill-sheet

* URL: https://github.com/wjwhitmire/kill-sheet
* Upstream SHA: `5e0c571e769c0b64cb9c8ea6f07699ebdae2b7fa` (2026-10-24, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: HTML; files: 22
* Dependencies: none declared
* Test files: 6
* Windows / offline: Python + browser; not executed.
* Data / redistribution: Example CSV only.
* Numerics: 6 test files; vectors self-generated.
* Group: D (Calculators)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT kill sheet (Driller's / Wait-and-Weight), self-described 'training and cross-check aid'. Not adopted: well-control calculations need owner review and independent references before entering the app.
* Copied code / modified files: none

### 31. wjwhitmire/cement-calc

* URL: https://github.com/wjwhitmire/cement-calc
* Upstream SHA: `2a6145007f32e45e72d33099e1f959896bd7d92c` (2026-10-24, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: HTML; files: 21
* Dependencies: none declared
* Test files: 4
* Windows / offline: Browser + Python; upstream not executed.
* Data / redistribution: Example JSON/CSV only; not copied.
* Numerics: 4 upstream test files; M52 uses its own hand-calculated references (tests/test_m52_balanced_plug.py).
* Group: D (Calculators)
* **Classification: REUSE ALGORITHM**
* Use in Drill-master: MIT balanced-plug method (equal heights inside/outside, spacer behind = ahead x Cp/Ca, under-displacement). Independently re-implemented as CementEngine.balanced_plug (SCREENING) with hand references; no code copied. Attribution in THIRD_PARTY_NOTICES.md.
* Copied code / modified files: none (independent implementation; see THIRD_PARTY_NOTICES.md)

### 32. gewazy/DrillingManagementStudio

* URL: https://github.com/gewazy/DrillingManagementStudio
* Upstream SHA: `7286e70fcf08545c823afbf1dcbb5584b00f5b99` (2024-06-17, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 10
* Dependencies: none declared
* Test files: 0
* Windows / offline: Python; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: B (DDR ingestion / manual entry)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT database course project; schema ideas only.
* Copied code / modified files: none

### 33. B0yko/wellbrief

* URL: https://github.com/B0yko/wellbrief
* Upstream SHA: `100cb4a871392e2322e1e7d3a346df0fc7695a46` (2026-10-26, branch `main`)
* Licence: Apache-2.0; licence files: `LICENSE`
* Language: Python; files: 177
* Dependencies: pypdf (floor excludes advisories); optional extras
* Test files: 58
* Windows / offline: Python (pypdf); not executed.
* Data / redistribution: Example NPT ledger CSV and result JSON; not copied.
* Numerics: 58 test files; not used.
* Group: C (Offline knowledge assistant)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Apache-2.0 offline-first RAG with a benchmark/ablation discipline. Ideas only (the M51 Knowledge Assistant already has BM25/RRF and sentence citations).
* Copied code / modified files: none

### 34. chinuckb/Drilling-Well-Path-Design

* URL: https://github.com/chinuckb/Drilling-Well-Path-Design
* Upstream SHA: `bfcc42ada8142baa9d66c1c8c08213518117f6b1` (2024-10-08, branch `main`)
* Licence: none detected; licence files: none
* Language: Python; files: 8
* Dependencies: none declared
* Test files: 0
* Windows / offline: Python; not executed.
* Data / redistribution: Spreadsheets; not copied.
* Numerics: No tests.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: J-type well path script; no licence file.
* Copied code / modified files: none

### 35. awojinrin/ML-Workflow-for-the-Determination-of-Hole-Cleaning-Conditions

* URL: https://github.com/awojinrin/ML-Workflow-for-the-Determination-of-Hole-Cleaning-Conditions
* Upstream SHA: `027b7e907173c338cf7cbe6d81b854fe39ebcdad` (2022-09-15, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Jupyter Notebook; files: 19
* Dependencies: none declared
* Test files: 0
* Windows / offline: Notebooks; not executed.
* Data / redistribution: Datasets of unknown provenance; not copied.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT ensemble-ML notebooks on a small dataset; not defensible for production risk outputs.
* Copied code / modified files: none

### 36. mhnajafi7/pdf-report-table-extractor

* URL: https://github.com/mhnajafi7/pdf-report-table-extractor
* Upstream SHA: `fb1a0b863cb31f8768bdebdc809c23ff5482a8cf` (2026-08-08, branch `main`)
* Licence: Apache-2.0; licence files: `LICENSE`
* Language: Python; files: 126
* Dependencies: Pillow, pdf2image, pdfplumber, pypdf
* Test files: 0
* Windows / offline: Python; not executed.
* Data / redistribution: Bundles public DDR PDFs whose redistribution terms are not stated - not copied.
* Numerics: No tests.
* Group: B (DDR ingestion / manual entry)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Apache-2.0 DDR pipeline (PDF split, title-guided table detection, crop, validation). Ideas inform the profile-based import design; pdf2image needs Poppler.
* Copied code / modified files: none

### 37. nmamzada/drilling-report-database

* URL: https://github.com/nmamzada/drilling-report-database
* Upstream SHA: `075642a358dc7c2b8ab00c41aa0d7216dfed1f28` (2026-09-09, branch `main`)
* Licence: NOASSERTION; licence files: `LICENSE`
* Language: Python; files: 13
* Dependencies: flask, openpyxl, pdfplumber
* Test files: 0
* Windows / offline: Python/Flask; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: B (DDR ingestion / manual entry)
* **Classification: REJECT**
* Use in Drill-master: LICENSE is CC BY-NC 4.0 (non-commercial) - no code taken (owner-gated).
* Copied code / modified files: none

### 38. aytacbie/drilling-reports-ds-pipeline

* URL: https://github.com/aytacbie/drilling-reports-ds-pipeline
* Upstream SHA: `5a43ad6a64db094996d7510432415e6cdf0fa3a2` (2026-10-27, branch `main`)
* Licence: none detected; licence files: none
* Language: Jupyter Notebook; files: 10
* Dependencies: matplotlib, numpy, openpyxl, pandas, pdfplumber, scikit-learn
* Test files: 0
* Windows / offline: Notebook; not executed.
* Data / redistribution: Result spreadsheets; not copied.
* Numerics: No tests.
* Group: B (DDR ingestion / manual entry)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: DDR PDF parsing + NLP notebook; no licence file.
* Copied code / modified files: none

### 39. djimrastephane/ddr-rag-book

* URL: https://github.com/djimrastephane/ddr-rag-book
* Upstream SHA: `4c94867c3cf1fa0c779e2fb2bdbe2204cf6711f2` (2026-09-15, branch `main`)
* Licence: NOASSERTION; licence files: `LICENSE`, `LICENSE-CONTENT.md`
* Language: Python; files: 273
* Dependencies: faiss-cpu, ipykernel, jupyter, numpy, pandas, pdf2image, pdfplumber, pyarrow, pytesseract, pytest, rank-bm25, sentence-transformers
* Test files: 18
* Windows / offline: Python; not executed.
* Data / redistribution: Bundles public FORGE PDFs; not copied.
* Numerics: 18 test files; not used.
* Group: C (Offline knowledge assistant)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Code MIT, prose CC BY 4.0 (LICENSE-CONTENT.md). Ideas only; depends on sentence-transformers (model download - owner-gated).
* Copied code / modified files: none

### 40. geoharkat/welltraj

* URL: https://github.com/geoharkat/welltraj
* Upstream SHA: `3fa866108688e28a3328424e95f413994129168d` (2026-05-19, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: JavaScript; files: 38
* Dependencies: none declared
* Test files: 5
* Windows / offline: Node/browser; not executed.
* Data / redistribution: Example well JSON; not copied.
* Numerics: 5 test files; not used.
* Group: A (Trajectory / anti-collision)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT JavaScript trajectory library with anti-collision. JS, no ISCWSA reference validation shown; ideas only.
* Copied code / modified files: none

### 41. ldocallaghan/BoreTHM

* URL: https://github.com/ldocallaghan/BoreTHM
* Upstream SHA: `1756c0bb8ac8d709d394029d1441cf8fbd03b539` (2026-10-29, branch `main`)
* Licence: Apache-2.0; licence files: `LICENSE`, `LICENSE-docs`, `NOTICE`
* Language: Python; files: 922
* Dependencies: iapws, matplotlib, mkdocs, mkdocs-material, numpy, pytest, scipy
* Test files: 89
* Windows / offline: Python; not executed.
* Data / redistribution: 580 benchmark/data files; not copied.
* Numerics: 89 test files; not used.
* Group: E (Thermal / stability (optional))
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Apache-2.0 code (with NOTICE) and separately licensed docs. Superhot geothermal thermal/stability models - optional group E, not implemented in M52 (needs iapws/scipy and independent validation).
* Copied code / modified files: none

### 42. SiliconWit/drillstring-surface-recoverability

* URL: https://github.com/SiliconWit/drillstring-surface-recoverability
* Upstream SHA: `fb11ec214348a91d006282afd7dd8c6b58235fe1` (2026-09-22, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 34
* Dependencies: matplotlib, numpy, pytest
* Test files: 5
* Windows / offline: Python; not executed.
* Data / redistribution: No data.
* Numerics: 5 test files.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT drillstring vibration/sensor-rate study; outside M52 scope.
* Copied code / modified files: none

### 43. imadeddinedjekoune/DrillAR-Sonatrach

* URL: https://github.com/imadeddinedjekoune/DrillAR-Sonatrach
* Upstream SHA: `cc71c8399722f42961c0bf81d3b2e0aa98c63402` (2023-09-30, branch `master`)
* Licence: none detected; licence files: none
* Language: Java; files: 94
* Dependencies: none declared
* Test files: 1
* Windows / offline: Android; not executed.
* Data / redistribution: No data.
* Numerics: 1 test file.
* Group: F (Analytics / other)
* **Classification: REJECT**
* Use in Drill-master: Java Android AR app; no licence file; unrelated platform.
* Copied code / modified files: none

### 44. NajafiIB/wellbore-stability-model-selector

* URL: https://github.com/NajafiIB/wellbore-stability-model-selector
* Upstream SHA: `9c2062a568c511d27efd7bacadc666330c43a544` (2026-10-26, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: HTML; files: 24
* Dependencies: none declared
* Test files: 4
* Windows / offline: Browser; not executed.
* Data / redistribution: Rule/evaluation JSON; not copied.
* Numerics: 4 test files.
* Group: E (Thermal / stability (optional))
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT rule-based geomechanics model selector (web). Optional group E; not implemented.
* Copied code / modified files: none

### 45. Anatoly5ms/drilling_complication_prognostication

* URL: https://github.com/Anatoly5ms/drilling_complication_prognostication
* Upstream SHA: `a0e16ed97f64d142ca99eb8e4d73a89c05e82eec` (2026-10-19, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: Python; files: 45
* Dependencies: PyYAML, catboost, huggingface_hub, lightgbm, numpy, pandas, pyarrow, scikit-learn
* Test files: 0
* Windows / offline: Python; not executed.
* Data / redistribution: Volve data under the Equinor Open Data Licence; not copied.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: MIT complication-risk ML on Volve DDRs (leakage control, held-out evaluation). Not adopted: needs huggingface_hub downloads and the Volve licence; any risk output would be an estimate needing defensible local data.
* Copied code / modified files: none

### 46. Athori99/RigTrack-Drilling-Dashboard-PHR

* URL: https://github.com/Athori99/RigTrack-Drilling-Dashboard-PHR
* Upstream SHA: `7807366e88206256655a1c02186c0aa2cd227dfc` (2026-07-01, branch `main`)
* Licence: none detected; licence files: none
* Language: Python; files: 3
* Dependencies: none declared
* Test files: 0
* Windows / offline: Web; not executed.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: Streamlit + PostgreSQL dashboard; no licence file; stack not allowed (PySide6 only).
* Copied code / modified files: none

### 47. DrillerDB/drillerdb-mcp

* URL: https://github.com/DrillerDB/drillerdb-mcp
* Upstream SHA: `4707fb6174034c83ef11a5808a420326cb8aa127` (2026-10-07, branch `main`)
* Licence: MIT; licence files: `LICENSE`
* Language: n/a; files: 16
* Dependencies: none declared
* Test files: 0
* Windows / offline: Requires a remote service.
* Data / redistribution: No data.
* Numerics: No tests.
* Group: C (Offline knowledge assistant)
* **Classification: REJECT**
* Use in Drill-master: MIT, but a remote cloud MCP server for a SaaS - conflicts with the offline, no-cloud rule.
* Copied code / modified files: none

### 48. api-evangelist/national-oilwell-varco

* URL: https://github.com/api-evangelist/national-oilwell-varco
* Upstream SHA: `1ed5ab7f97ff2d104dcc681174f2a516031ca9dc` (2026-09-23, branch `main`)
* Licence: none detected; licence files: none
* Language: n/a; files: 89
* Dependencies: none declared
* Test files: 0
* Windows / offline: Not applicable.
* Data / redistribution: Press/screenshots metadata; not copied.
* Numerics: No tests.
* Group: F (Analytics / other)
* **Classification: REJECT**
* Use in Drill-master: An API-profile catalogue (no engineering code); no licence file.
* Copied code / modified files: none

### 49. BJZ-BJZ/marine-deepsea-drilling

* URL: https://github.com/BJZ-BJZ/marine-deepsea-drilling
* Upstream SHA: `a20b25c1475cfee711bfe250577d3674e074c63b` (2026-10-08, branch `main`)
* Licence: none detected; licence files: none
* Language: Python; files: 27
* Dependencies: numpy
* Test files: 2
* Windows / offline: Python; not executed.
* Data / redistribution: Processed log CSVs (CC BY 4.0 per README); not copied.
* Numerics: 2 test files.
* Group: F (Analytics / other)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: No code licence file (data stated as CC BY 4.0). Research scripts; ideas only.
* Copied code / modified files: none

### 50. avrangainulloev/DrillingCore

* URL: https://github.com/avrangainulloev/DrillingCore
* Upstream SHA: `b874026ec64854f0c14557730d83f775d82c15ed` (2025-07-08, branch `main`)
* Licence: none detected; licence files: none
* Language: C#; files: 520
* Dependencies: bootstrap, pinia, vue, vue-router
* Test files: 1
* Windows / offline: .NET/web; not executed.
* Data / redistribution: No operational data.
* Numerics: 1 test file.
* Group: B (DDR ingestion / manual entry)
* **Classification: INSPIRE ONLY**
* Use in Drill-master: C#/Vue drilling forms and safety system; no licence file. Form ideas only.
* Copied code / modified files: none
