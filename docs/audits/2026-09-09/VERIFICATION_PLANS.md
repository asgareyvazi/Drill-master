# Verification Plans — Windows GUI, Installer/Bundle, MinerU Import

Status of this document: **PLANS ONLY.** Nothing in this file has been executed
on the target platform. The 2026-09-09/10 audit sandbox is Linux headless;
that environment can verify configuration and code paths, but **Linux/offscreen
results never prove Windows behavior and no such claim is made here.**

The plans below are grounded in the repo's actual opt-in mechanisms — each plan
exercises the exact hook that exists in the code today.

---

## 1. Windows GUI verification plan

**Why not yet verified:** all GUI verification in the audit ran via
`QT_QPA_PLATFORM=offscreen` on Linux with the stub libraries built by
`tools/qt_headless_env.sh`. No Windows session, no native `qwindows.dll`
platform plugin, no real window manager, no HiDPI, no native file dialogs.

**Preconditions**
- Windows 10 22H2 and Windows 11 (one machine each, or one VM + one physical
  for DPI/font differences), clean user profile (no prior DrillMaster data in
  `%APPDATA%`).
- Python 3.11 (project lock supports 3.10–3.13; 3.11 is the version the audit
  baseline was measured on), repo checkout, `pip install -r requirements-lock.txt`.

**Steps**
1. `python -m compileall -q core dialogs tabs tests` — must exit 0.
2. `python -m pytest -ra --tb=short` with `DRILLMASTER_ENV=test` and
   **no** `QT_QPA_PLATFORM` set (Windows must use the native platform plugin,
   not offscreen). Record passed/skipped counts; compare against the Linux
   baseline (808 passed / 4 skipped, 2026-09-10). Any delta must be explained
   per-test, not averaged away.
3. Launch `python app.py` on both machines. Verify: main window renders,
   SelectionManager combos populate from the hierarchy, an Excel import
   round-trip completes, the schematic tab renders, and a report PDF opens in
   the OS viewer.
4. Repeat step 3 at 150% display scaling on the Windows 11 machine (Qt
   fractional scaling is a classic Windows-only failure surface).

**PASS criteria:** suite green with explained deltas + manual checklist
observed on both Windows versions. Until then: **NOT VERIFIED.**

## 2. Installer / bundle verification plan

**Why not yet verified:** no bundle was built; `test_packaging_smoke.py` skips
its real-bundle check by design (`DRILLMASTER_BUNDLE_DIR` unset), and the
static configuration test only proves the PyInstaller spec / Inno Setup script
/ smoke script say the right things — not that a built `.exe` works.

**Preconditions**
- Windows 10/11 machine with Python 3.11, PyInstaller, Inno Setup 6 installed.

**Steps**
1. `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1` —
   must complete without errors and produce the bundle directory.
2. Run the repo's own bundle validator against the build output:
   `python packaging\package_smoke.py --bundle <output>\DrillMaster` (or set
   `DRILLMASTER_BUNDLE_DIR` and run `pytest tests/test_packaging_smoke.py -k real`).
   Validator checks: `DrillMaster.exe`, `Qt6Core.dll`, `platforms\qwindows.dll`,
   `config\ai_models.json`, `config\company_templates\oeoc.json` present.
3. Install via the generated Inno Setup installer on a clean profile. Verify
   install dir is `{autopf}\DrillMaster` (the spec asserts Program Files, not
   per-user AppData).
4. Cold-start the installed app from the Start-menu shortcut (first run must
   bootstrap DB/config). Import one known-good OEOC workbook; save; restart the
   app; confirm data persisted (this is the Windows equivalent of the R18
   save/reopen contract).
5. Uninstall — verify DB files and user templates are handled per the
   installer's declared policy (decide the policy first; today it is only
   implicitly "leave user data").

**PASS criteria:** steps 1–4 observed and recorded (step 5 once policy is
decided). Until then: **NOT VERIFIED.**

## 3. MinerU / local-AI PDF import verification plan

**Why not yet verified:** the MinerU integration tests are opt-in
(`MINERU_INTEGRATION_INPUT` must point at a real report PDF) and no MinerU
service/model was available in the audit sandbox. Unit tests cover the
parsing/contract layer only.

**Preconditions**
- A machine able to run the MinerU model per `docs/LOCAL_AI_IMPORT.md`
  (the repo's Ollama/MinerU layout; `packaging` ships `ollama`/`mineru` dirs —
  they are excluded from the Linux audit).
- 3 representative DDR PDFs: one text-based export, one scanned image, one
  mixed. The **same workbooks' XLSX twins** for cross-checking extracted
  values (ground truth).

**Steps**
1. Set `MINERU_INTEGRATION_INPUT` to each PDF in turn; run
   `pytest tests/test_mineru_real_integration.py -ra`. All three must pass.
2. For each PDF, diff the MinerU-extracted values against the XLSX golden
   values for the shared fields (dates, depths, ROP, mud weight, NPT hours).
   Record per-field agreement rate; any field below 100% on the text-based PDF
   is a defect (text-based extraction has no OCR excuse).
3. Verify failure semantics on garbage input: a non-PDF renamed to `.pdf` must
   produce an explicit import error, **never** an empty successful import
   (this mirrors the empty-collection contract tested for the Excel path).
4. Verify the model files are found from the packaged layout (the
   `config/ai_models.json` + `mineru` directory arrangement), not only from a
   dev checkout.

**PASS criteria:** all three PDFs pass integration tests + text-based PDF at
100% field agreement + explicit-failure semantics observed. Until then:
**NOT VERIFIED.**

---

## Standing rule

Any future claim of "Windows verified", "installer verified", or "MinerU
verified" must cite an execution record of the corresponding plan above. The
2026-09-09/10 audit status for all three remains **NOT VERIFIED**, and the
production-gate table in `MASTER_FORENSIC_AUDIT.md` must keep saying so until
those records exist.
