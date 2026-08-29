# DrillMaster - Audit کامل و نقشه فازبندی به Intelligence Platform

**تاریخ:** 2026-08-24
**شاخه:** arena/01a03299-drill-master
**هدف:** تبدیل از Drilling Operations Data Platform به Drilling Operations Intelligence Platform (Overall 9/10)

---

## 1. FULL PROJECT AUDIT

### 1.1 ساختار فعلی

```
core/
  database.py (6717 خط) - God Object
  canonical_schema.py (45 فیلد)
  unit_manager.py (58 خط - فقط 7 quantity)
  universal_import.py (WorkbookScanner ساده)
  profile_import_engine.py (869 خط - OEOC محور اما با fallback)
  ai_import_mapper.py (Ollama local, JSON-only)
  table_record_mapper.py (Generic header mapping)
  import_quality.py (Review Matrix + Validator)
  hydraulics_engine.py (Advanced Hydraulics)
  engineering/
    registry.py (Capability registry)
    adapters/welleng_adapter.py, torque_drag_adapter.py
  operations_intelligence.py (KPIs ساده)
  validators.py, time_utils.py, etc.

tabs/ - 16 تب (w1..w16 + w3b,w3c)
  همه از DrillTabBase ارث می‌برند
  بعضی business logic داخل widget دارند

dialogs/
  excel_import_dialog.py - Universal Import entry
  smart_template_dialog.py - 3757 خط (FieldDetector + CodeResolver + LearningManager)
  hierarchy_dialogs.py, daily_report_dialogs.py etc.

main_window.py - 2836 خط (Hierarchy + Ribbon + TabRegistry + ImportCoordinator مخلوط)

tests/ - 7 فایل, dependency-light, بدون golden files
```

### 1.2 مشکلات معماری (Architecture Score: 5/10)

| مشکل | شدت | توضیح |
|------|-----|-------|
| DatabaseManager God Object | Critical | 6000+ خط, همه مدل‌ها + save/get + business logic (fuel carry_forward, bulk totals). باید به Repository تقسیم شود |
| MainWindow God Object | Critical | Navigation, TabRegistry, ContextManager, MenuManager, ExportCoordinator, ImportCoordinator همه داخل یک کلاس |
| UI/Business Logic Coupling | High | Widgetها مستقیم session می‌سازند, منطق محاسباتی داخل UI |
| No Domain Service Layer | High | HydraulicsEngine وجود دارد ولی به تب‌ها متصل نیست, Trajectory محاسبات داخل adapter فقط |
| No Unit of Work | High | هر save یک session جدا, امکان atomic transaction برای 16 جدول نیست |
| Missing Engineering Core Contracts | High | هر محاسبه باید contract مشخص داشته باشد: inputs, outputs, units, assumptions, validation |
| Hard-coded values | Medium | بعضی مقادیر مثل build_rate default, surge/swab gap default 8.5", cost daily_rate 60000 |

### 1.3 Excel Importer (Score: 6/10)

**موجود:**
- WorkbookScanner: sheet info (name, rows, columns, hidden, merged_ranges, used_range, density) + detect_tables via row bands
- SheetRouter: امتیازدهی بر اساس keyword + content
- FieldDetector: multi-strategy (exact, fuzzy, synonym, context-group proximity, radius search)
- CodeResolver: catalog پویا از workbook (نه hard-coded شرکت)
- LearningManager: یادگیری از تصحیح کاربر
- AIImportMapper: فقط 80 context entry + workbook structure compact, JSON-only, confidence scoring
- ImportReviewMatrix: Sheet/Page, Table, Source Cell, Original/Normalized, Unit, Target Field, Confidence, Decision
- ImportValidator + find_duplicates + decision_for_confidence

**ناقص / شکسته:**
- Workbook Scanner حرفه‌ای ناقص: Hidden Rows/Columns, Border/Style, Formula Count, Empty Cell Ratio, Table Count دقیق نیست, چند جدول عمودی/افقی/تو در تو, Header دو/سه ردیفی, Merge بدون Border را کامل نمی‌فهمد
- Sheet Classifier: فقط keyword, نه بر اساس Data Types, Table Shape, AI Semantic کامل
- Table Detector پیشرفته: Row Density, Column Density, Blank Row/Column, Border, Style, Header Pattern, Data Type Consistency, Repeated Header را کامل ندارد
- استخراج ردیفی: TimeLog کامل (From/To/Duration/Main Phase/Main Code/Sub Code/NPT/Contractor/Description) موجود است ولی Survey, BHA, Bit, Mud Chemicals, Equipment, Logistics, Services ناقص
- Import Transaction واقعی: snapshot_import_target / restore موجود ولی save_imported_multi_tab_data هر جدول را جدا commit می‌کند - atomic نیست
- Import Preview قبل از ذخیره: در SmartTemplateDialog وجود دارد ولی در ExcelImportDialog._unified_import مستقیماً import می‌کند بدون Preview
- Universal Import: FIELD_PATTERNS گسترده (60+ فیلد) ولی هنوز به OEOC_PROFILE وابسته است برای fallback, و aliasهای universal مثل Well/Well Name/Well Number/Well ID → well.name باید تقویت شود
- Batch گزارش: موفق/ناموفق جدا گزارش نمی‌شود

**Performance Bottlenecks:**
- _unmerge: برای هر شیت تا 500*150=75k سلول می‌خواند (قابل قبول ولی برای 20 شیت 1.5M)
- compact_context: فقط 80 entry - خوب
- AI calls: یک call برای هر فایل, timeout 45s, FunctionWorker در background thread - خوب ولی باید confidence-based escalation باشد

### 1.4 Engineering Knowledge Core (Score: 4/10)

**موجود:**
- hydraulics_engine.py: AdvancedHydraulicsEngine با PipeSegment, CasingSection, MudProperties (Bingham, Power Law, Herschel-Bulkley), ECD Profile, Surge/Swab, Surface Losses
- welleng_adapter.py: optional, fallback None
- torque_drag_adapter.py: optional, version-neutral boundary
- operations_intelligence.py: KPIs ساده (npt%, ROP decline)
- actual_vs_plan.py: Variance calculation
- trajectory_calculation model وجود دارد ولی محاسبات Minimum Curvature داخلی نیست

**ناقص:**
- Well trajectory: Minimum Curvature, DLS, Build/Turn Rate, TVD/North/East/VS/HD, Projection, Survey QC, Duplicate MD, Non-monotonic MD - هیچ کدام deterministic engine ندارند, فقط welleng adapter
- Anti-Collision: Clearance Factor, Error Ellipse, ISCWSA - نیست
- Torque & Drag: Hookload, Tension, Torque profile - فقط adapter خالی
- BHA: Cumulative Length, Weight, Service Life - JSON ذخیره می‌شود بدون محاسبه
- Bit: Run History, Life, ROP per Bit, TFA - ناقص
- Hydraulics: PV/YP/Gel, ECD, Annular velocity - موجود ولی به mud_report متصل نیست
- Well Control: MAASP, Kick Tolerance - نیست
- Casing/Cement: Burst/Collapse, Tensile - فیلدها وجود دارند ولی calculation نیست
- ROP/MSE/NPT KPIs: فقط basic

**قانون طلایی نقض شده در بعضی جاها:**
- بعضی جاها missing input با 0.0 جایگزین می‌شود (fake default) به جای MISSING_INPUT

### 1.5 Units (Score: 5/10)

**موجود:**
- _UNITS: length (m, ft, in), pressure (psi, bar, kpa), flow (gpm, lpm), volume (bbl, m3), temperature (c, f), density (ppg, sg, kg_m3), torque (ft_lbf, kn_m)
- convert + normalize_row

**ناقص:**
- Missing: Diameter, Depth (جدا از length), Force, Weight, ROP (m/hr, ft/hr), RPM, Viscosity (cp), Yield Point (lb/100ft2), ECD, DLS (deg/100ft), Azimuth, Inclination, Gel, Solid %, Oil %, etc.
- No metadata: باید ذخیره شود Original: 1.50 SG, Normalized: 12.52, Canonical Unit: ppg
- No Quantity field: Field → Quantity → Source Unit → Canonical Unit → Original → Normalized → Conversion Rule

### 1.6 Daily Report (Score: 6/10)

**موجود:**
- TimeLog24H + TimeLogMorning models
- TimeLineEdit با پشتیبانی 24:00 + day_offset
- DrillTime با forward elapsed
- TimeLogValidator: total ~24h check

**ناقص:**
- No overlap detection
- No gap detection
- No duration validation per row vs From/To
- No total must equal 24h enforcement
- No midnight crossing handling (00:00-06:00, 06:00-12:30, 12:30-18:30, 18:30-24:00)
- No continuation rows handling (در profile_import_engine وجود دارد ولی در validator نیست)
- No duplicate time range detection
- Contractor autocomplete: در w2_Daily_Report فقط LineEdit ساده, نه recent contractors, نه company master data

### 1.7 Mud & Chemical (Score: 5/10)

**موجود:**
- MudReport model + BulkMaterials model
- carry_forward logic: opening از closing روز قبل

**ناقص:**
- No Ledger: Opening Stock, Received, Used, Returned, Adjusted, Closing Stock با فرمول Closing = Opening + Received + Adjusted - Used - Returned و Opening(day+1)=Closing(day)
- No alerts: Negative Stock, Low Stock, Unusual Consumption, No Movement, Duplicate Material, Unit Mismatch
- No history: Daily Usage Chart, Stock Trend, Consumption Rate, Days Remaining, Received vs Used

### 1.8 Bit & BHA (Score: 4/10)

**ناقص موارد لیست شده در spec:** Bit Run History, Bit Life, Total Drilled, Hours on Bit, ROP per Bit, Nozzle Config, TFA, Cost, BHA Assembly, Cumulative Length, Weight, Service Life, و هشدارهای Missing Bit Size/IADC/Nozzle, Duplicate Bit Run, Invalid BHA Length

### 1.9 Trajectory & Survey (Score: 4/10)

**موجود:** SurveyPoint model, TrajectoryCalculation, TrajectoryPlot, WellengAdapter (optional)

**ناقص:** Minimum Curvature implementation داخلی, DLS, Build/Turn Rate, TVD/North/East/VS/HD, Projection, Project Ahead, Survey QC, Duplicate/Non-monotonic MD, Anti-Collision, Clearance, Error Ellipse, ISCWSA, welleng Adapter فقط بعد از Benchmark

**خروجی:** 2D Plan/Section, 3D Well, Multi-well, Tooltip, Depth Slider, Export HTML/PNG/PDF - در w6_Trajectory_Widget باید بررسی شود (هنوز نخوانده)

### 1.10 Safety & BOP (Score: 5/10)

**موجود:** SafetyReport, BOPComponent, WasteRecord, SafetyIncident models

**ناقص:** BOP Component Register, Pressure Test History, Test Due Date, Test Interval Configuration (باید configurable باشد: Operator Standard, Well Type, Region, Company Policy نه hard-coded), Safety Drill History, LTI, Near Miss, Incident, H2S, Fire Drill, BOP Drill, Waste, Corrective Action

### 1.11 Logistics & Services (Score: 5/10)

**موجود:** LogisticsPersonnel, ServiceCompanyPOB, FuelWaterInventory, BulkMaterials, TransportLog, TransportNotes, ServiceCompany, ServiceNote, MaterialRequest, EquipmentLog

**ناقص:** POB Day/Night/Total دقیق, Fuel/Water/Bulk Transport, Boat/Helicopter, Crew Change, Delivery/Backload, و رابطه کامل Well→Section→Report→Service Company→Service Event→Cost→Document

### 1.12 Analysis & Monitoring (Score: 5/10)

**موجود:** Analysis tab, OperationsIntelligenceService (KPIs ساده)

**ناقص:** Dashboard کامل با Current Depth, Daily Progress, Avg ROP, NPT%, Productive Time, Rig Days, Cost per Meter, Plan Variance, Mud/Torque/RPM/WOB/ECD/DLS Trends, Safety KPI, Data Quality Score, و قابلیت‌های Date/Well/Section/Report Filter, Multi-well Comparison, Drill-down, Tooltip, Zoom, Export Chart/Dataset

### 1.13 Operations Intelligence (Score: 4/10)

**موجود:** ROP degradation ساده (20% decline)

**ناقص:** AI باید بر اساس validated data تحلیل کند: ROP Degradation, NPT Increase, Mud Property Change, Torque Increase, Hole Condition Pattern, Plan Delay, Cost Overrun, Safety Pattern با evidence (Source Reports, Date Range, Metrics, Confidence, Reason)

### 1.14 Export (Score: 6/10)

**موجود:** DDRReportEngine, EOWR, NPT, Cost, Plan, ExportWidget

**ناقص:** Metadata حرفه‌ای (Company, Project, Field, Well, Section, Report Number, Date, Revision, Status, Prepared By, Checked By, Approved By, Generated At UTC, Timezone, Units, Data Quality, Audit ID), Excel sheets کامل (Executive Summary, Daily Report, Time Logs, Mud, Drilling Params, Bit, BHA, Survey, Safety, Logistics, Services, Cost, Data Quality, Validation, Audit, Raw Data), PDF با Header/Logo/Footer/Page Number/Watermark/Revision/Approval/Tables/Charts/Signature/Data Quality

### 1.15 Security & Permission (Score: 6/10)

**موجود:** PermissionManager با ROLE_PERMISSIONS (admin:*, supervisor, engineer, manager, viewer: can_export), require_permission decorator, apply_viewer_mode

**ناقص:** همه عملیات حساس باید protected باشند: Create, Edit, Save, Delete, Import, Export, Approve, Reject, Finalize. Viewer واقعاً read-only: No Save, No Delete, No Import, No Approve, No Edit. در حال حاضر بعضی تب‌ها check نمی‌کنند, delete_well در MainWindow check ندارد.

### 1.16 Database (Score: 6/10)

**مشکلات:**
- Missing fields: بعضی فیلدهای engineering مثل MAASP, Kick Tolerance, DLS, Build Rate, etc. نیست
- No Ledger tables for Mud Chemicals
- No welleng cache
- No data lineage
- No soft delete
- Hierarchy cache TTL 30s ولی invalidation دستی

### 1.17 Testing (Score: 3/10)

**موجود:** 7 تست dependency-light, compile pass

**ناقص:** Import Tests, Excel Tests (OEOC, Company A/B/C, Simple, Merged, Multi-table, CSV فارسی), PDF Tests (Text, Scanned), Mapping Tests, AI JSON Tests, Unit Tests, Database Tests, Delete Tests, Rollback Tests, Inventory Tests, Time Log Tests, Well Resolution Tests, Trajectory Tests, DLS Tests, Hydraulics Tests, Export Tests, Permission Tests, Security Tests

### 1.18 External Repositories Knowledge

بر اساس بررسی سریع (بدون کپی کد):

1. **welleng** (jonnymaserati/welleng): مهم‌ترین - Trajectory, Survey, Minimum Curvature, ISCWSA, Uncertainty, Anti-Collision, Clearance, Torque & Drag, Kick Tolerance, Well Planning, BHA. باید اولین باشد. دارای SurveyHeader, Survey, error models, clearance calculations.

2. **DrillingEngineeringOperations** (BillyFrcs): محاسبات عملیات حفاری - hydraulics, bit, mud, casing.

3. **mud-engineer-pro** (Himageo2006): Mud Engineering, Rheology, PV/YP/Gel, ECD, Hydraulics.

4. **drilling_engineering_design** (mengyangcup): Well/Drilling Design, ارتباط با Program.

5. **drilling-engineer-toolkit** (juangjuang74): محاسبات عمومی حفاری.

6. **well-engineer** (Kukuruza24110): مقایسه Engineها.

7. **3D Well Trajectory Visualization** (Otto-Destiny): Visualization, Trajectory UI.

8. **3D Directional Drilling Engine** (ejbo2001): Directional Drilling, 3D.

9. **engineering-calculations** (dasvan.github.io): مقایسه Formulaها.

10. **volve-drilling** (f0nzie): داده واقعی برای تست.

11. **python-for-drilling-engineers** (johnryan417): الگوریتم‌ها و مثال‌ها.

12. **DataAnalyticsforEngineering** (jntran08): Analytics.

13. **Drilling-Engineering** (manjramkar): منبع مقایسه Formula.

**قانون:** هیچ کدام را کپی نکن, فقط governing equation/algorithm, inputs/outputs, assumptions, units, source/reference, validation cases را استخراج کن, duplicateها را مقایسه کن, بهترین را انتخاب کن, با معماری NNNNN بازطراحی کن.

---

## 2. فازبندی پیشنهادی (بر اساس P0/P1/P2)

### فاز 0: Audit & Foundation (این سند) - ✅ انجام شد
- Audit کامل
- این سند
- CI gates تعریف

### فاز 1: P0 - Import Integrity & Security (اولویت فوری)
**هدف:** زنجیره Data→Normalization→Validation→Database→Tabs بدون نقص

1. **Atomic Import Transaction**
   - `DatabaseManager.session_scope()` را به عنوان Unit of Work برای کل import استفاده کن
   - `save_imported_multi_tab_data` باید یک transaction واحد باشد, نه 16 commit جدا
   - اگر هر مرحله شکست: Rollback All
   - Batch: فایل‌های موفق/ناموفق جدا گزارش
   - Test: Rollback Tests

2. **Import Preview قبل از ذخیره (Complete Review Matrix)**
   - در ExcelImportDialog._unified_import: ابتدا SmartTemplateDialog را به صورت preview modal باز کن
   - دکمه‌ها: Accept All High Confidence, Review Medium, Reject Low Confidence, Edit Mapping/Value/Unit, Ignore Column, Confirm Import, Cancel Import
   - هیچ داده‌ای قبل از Confirm ذخیره نشود
   - Review Matrix شامل: File, Sheet/Page, Detected Table, Source Cell, Original Value, Normalized Value, Unit, Target Field, Confidence, Decision

3. **No Fake Defaults**
   - همه جا missing → None, نه 0.0
   - depth_0000/0600/2400: اگر missing باشد NULL بماند
   - TimeLog duration: اگر missing باشد از From/To محاسبه شود, نه 0
   - Generic validators: اگر critical field missing باشد MISSING_INPUT برگردان, نه guess

4. **Time Log 24h Validation حرفه‌ای**
   - Total must equal 24h (tolerance 0.5h)
   - Overlap detection: دو بازه نباید همپوشانی داشته باشند
   - Gap detection: نباید gap باشد (مگر توضیح)
   - Duration validation: duration باید با From/To بخواند
   - Midnight crossing: 24:00 با day_offset
   - Continuation rows: ردیف ادامه‌دار به قبلی بچسبد
   - Duplicate time range detection

5. **Well/Section/Report Identity (Universal Import)**
   - Well: Well, Well Name, Well Number, Well ID, نام چاه → well.name
   - MD: MD, Measured Depth, Bit Depth, Current Depth, Depth → drilling_params.depth
   - WOB: WOB, Wt. on Bit, Bit Load, Weight on Bit → drilling_params.wob
   - Section: نام سکشن + depth_from/to برای identity, نه فقط نام
   - Report: well_id + section_id + report_date یکتا

6. **Permission Enforcement**
   - همه عملیات حساس: Create, Edit, Save, Delete, Import, Export, Approve, Reject, Finalize
   - Decorator روی متدهای MainWindow و DrillTabBase
   - Viewer: واقعاً read-only (No Save, No Delete, No Import, No Approve, No Edit)
   - Test: Permission Tests

7. **Unit Preservation**
   - UnitManager: اضافه کردن Length, Diameter, Depth, Pressure, Flow Rate, Volume, Density, Temperature, Torque, Force, Weight, ROP, RPM, Viscosity, Yield Point, ECD, DLS, Azimuth, Inclination, Gel, etc.
   - ذخیره Original Value + Normalized Value + Canonical Unit + Conversion Rule
   - مثال: 1.50 SG → Original: 1.50 SG, Normalized: 12.52, Canonical: ppg

**Deliverables فاز 1:**
- `core/repositories/` با WellRepository, ReportRepository, etc.
- `core/import_quality.py` تقویت شده با TimeLog 24h validator کامل
- `core/unit_manager.py` کامل
- `dialogs/excel_import_dialog.py` با Preview
- `core/database.py` با atomic transaction
- `core/permissions.py` تقویت شده
- Tests: rollback, time_log, well_resolution, permission

### فاز 2: P1 - Import کامل و Engineering Core

8. **Workbook Scanner حرفه‌ای**
   - File Name, Size, Type, Workbook Version, Sheet Count, Hidden Sheets, Merged Ranges, Hidden Rows/Columns, Used Range, Formula Count, Empty Cell Ratio, Table Count

9. **Sheet Classifier**
   - بر اساس Sheet Name, Headers, Content, Data Types, Nearby Titles, Table Shape, AI Semantic Mapping
   - طبقه‌بندی به Daily Report, Mud, Drilling, BHA, Bit, Survey, Trajectory, Safety, BOP, Logistics, Services, Cost, Planning, Reference, Unknown

10. **Table Detector پیشرفته**
    - Row/Column Density, Blank Row/Column, Border, Style, Merged Cells, Header Pattern, Data Type Consistency, Title, Repeated Header
    - حالت‌ها: چند جدول عمودی/افقی, تو در تو, Header دو/سه ردیفی, Merge, بدون Border, ادامه‌دار

11. **استخراج ردیفی کامل**
    - برای هر Table یک Row مستقل با فیلدهای مشخص (TimeLog, Survey, BHA, Bit, Mud Chemicals, Equipment, Logistics)

12. **Engineering Core (Deterministic)**
    - ایجاد `core/engineering/core.py` با:
      - TrajectoryEngine: Minimum Curvature, DLS, Build/Turn Rate, TVD/North/East/VS/HD, Projection, Survey QC
      - Units: ft/m, psi/bar/kPa, ppg/sg, etc. با conversion در boundary
      - Contracts: هر calculation با Required inputs, Outputs, Units, Assumptions, Validation, Error conditions
      - هرگز silent guess نکند: MISSING_INPUT یا UNSUPPORTED_CALCULATION
    - اتصال به welleng_adapter فقط بعد از Benchmark

13. **Mud/Hydraulics کامل**
    - Mud Chemical Ledger: Opening, Received, Used, Returned, Adjusted, Closing با فرمول و Opening(day+1)=Closing(day)
    - کنترل موجودی: Negative/Low Stock, Unusual Consumption, No Movement, Duplicate, Unit Mismatch
    - تاریخچه: Usage Chart, Stock Trend, Consumption Rate, Days Remaining, Received vs Used
    - اتصال hydraulics_engine به mud_report

14. **AI Architecture**
    - AI نباید مستقیم DB را تغییر دهد: Excel → AI Proposal → Validation → Review → User Confirmation → Database
    - AI Context محدود: Table Title, Header Row, Sample Values, Neighbor Headers, Source Coordinates, Unit Candidates, Canonical Fields
    - Tool interface: AI می‌تواند Engineering Engine را call کند, نه اینکه خودش فرمول بسازد

15. **Export QA**
    - Metadata کامل, Excel sheets پیشنهادی, PDF حرفه‌ای

**Deliverables فاز 2:**
- `core/engineering/engines/` با trajectory, hydraulics, bit, bha
- `core/mud_ledger.py`
- `core/import_profiler.py` تقویت شده
- Tests: trajectory, hydraulics, inventory, export

### فاز 3: P2 - Intelligence & Advanced

16. **Welleng Integration**
    - Trajectory, Survey, Anti-Collision, Clearance, Torque & Drag, ISCWSA, Uncertainty
    - Benchmark با Engine داخلی
    - خروجی‌ها: 2D Plan/Section, 3D Well, Multi-well, Tooltip, Depth Slider, Export HTML/PNG/PDF

17. **Well Control**
    - MAASP, Kick Tolerance

18. **Operations Intelligence**
    - ROP Degradation, NPT Increase, Mud Property Change, Torque Increase, Hole Condition Pattern, Plan Delay, Cost Overrun, Safety Pattern با evidence

19. **WITSML, Real-time, APIs**
    - WITSML Import, Landmark WBP, EDM, LAS, MQTT, OPC-UA, REST API, GraphQL, Offline Mode, Cloud Sync, etc.

20. **RAG Historical DDR Search**
    - Search بر اساس داده‌های تاریخی

**Deliverables فاز 3:**
- `core/engineering/adapters/welleng_adapter.py` کامل
- `core/operations_intelligence.py` کامل با evidence
- Analysis dashboards حرفه‌ای
- REST API

---

## 3. اولویت‌بندی نهایی (از دیدگاه Production Readiness)

**P0 (باید قبل از هر Feature جدید):**
- Atomic Import
- Complete Review Matrix (Preview)
- No Fake Defaults
- Time Log 24h Validation
- Well/Section/Report Identity
- Permission Enforcement
- Unit Preservation

**P1 (بعد از P0):**
- Async Import (FunctionWorker موجود ولی باید برای همه)
- PDF OCR
- Generic Table Mapping
- Full Validators
- Complete Tests
- Export QA
- Inventory Ledger

**P2 (بعد از P1):**
- Welleng Integration
- Anti-Collision
- WITSML
- Torque & Drag
- Operations Intelligence
- RAG
- Real-time Data

**نمره هدف:**
| بخش | هدف |
|-----|-----|
| Architecture | 9 |
| Import | 9 |
| AI | 8.5 |
| Database | 9 |
| UI/UX | 8.5 |
| Analysis | 9 |
| Engineering | 9 |
| Export | 9 |
| Security | 9 |
| Testing | 9 |
| Production Readiness | 9 |
| **Overall** | **9/10** |

**زنجیره طلایی که باید بدون نقص کار کند:**
```
Data
  ↓
Normalization
  ↓
Validation
  ↓
Database
  ↓
Tabs
  ↓
Analysis
  ↓
Engineering
  ↓
AI Interpretation
  ↓
Recommendation
  ↓
Professional Export
```

---

## 4. Implementation Strategy (Incremental)

1. Audit current architecture (این سند)
2. Identify existing functionality (انجام شد)
3. Identify duplicated functionality (انجام شد)
4. Identify missing functionality (انجام شد)
5. Produce implementation plan (این سند)
6. Implement one module at a time (شروع از P0)
7. Run tests
8. Verify existing features
9. Only then continue

**قوانین:**
- Do NOT rewrite from scratch
- Do NOT remove existing functionality
- Do NOT blindly copy external repositories
- Preserve backward compatibility
- Never silently invent formulas, constants, limits, missing inputs, units, assumptions → return MISSING_INPUT یا UNSUPPORTED_CALCULATION

---

## 5. External Repo Integration Rules

برای هر قابلیت مهندسی از 13 repository:

1. Identify algorithm
2. Identify governing equation
3. Required inputs/outputs
4. Assumptions
5. Units
6. Validation/test cases
7. References
8. Edge cases
9. Compare duplicate implementations
10. Select most reliable
11. Reimplement using NNNNN's architecture
12. Check License
13. Check tests

**Do NOT keep multiple redundant implementations**

---

## 6. فاز 1 - جزئیات پیاده‌سازی (در حال اجرا روی branch)

### 6.1 Atomic Import
- `core/database.py`: `save_imported_multi_tab_data` به `session_scope` با single transaction
- `dialogs/excel_import_dialog.py`: `_do_import` با snapshot + rollback
- Batch: گزارش موفق/ناموفق جدا

### 6.2 Review Matrix Preview
- `ExcelImportDialog._unified_import`: قبل از `_do_import`, نمایش `SmartTemplateDialog` به عنوان preview
- دکمه‌های Accept All High Confidence, Review Medium, Reject Low, Edit Mapping/Value/Unit, Ignore Column, Confirm, Cancel
- هیچ داده‌ای قبل از Confirm ذخیره نشود

### 6.3 No Fake Defaults
- `excel_normalizer.py`: نرمال‌سازی بدون جایگزینی 0
- `profile_import_engine.py`: depth fields → None اگر missing
- `validators.py`: MISSING_INPUT برای critical fields

### 6.4 Time Log 24h Validation
- `import_quality.py`: TimeLogValidator کامل با overlap, gap, duration, midnight, duplicate

### 6.5 Unit Preservation
- `unit_manager.py`: 20+ quantity, ذخیره Original/Normalized/Canonical

### 6.6 Permission
- `base_tab.py`: save_data باید permission check کند
- `main_window.py`: delete actions با require_permission

### 6.7 Repository Refactor (شروع)
- `core/repositories/base.py`
- `core/repositories/well_repository.py`
- `core/repositories/report_repository.py`
- `core/repositories/mud_repository.py`
- `core/repositories/trajectory_repository.py`
- `core/repositories/bha_repository.py`
- `core/repositories/logistics_repository.py`
- `core/repositories/safety_repository.py`
- `core/repositories/service_repository.py`
- `core/repositories/cost_repository.py`
- `core/repositories/audit_repository.py`

---

## 7. تست‌های لازم برای فاز 1

- `tests/test_atomic_import.py`: transaction rollback
- `tests/test_time_log_validation.py`: 24h, overlap, gap, duplicate
- `tests/test_unit_preservation.py`: original/normalized preservation
- `tests/test_well_identity.py`: universal aliases
- `tests/test_permission_enforcement.py`: viewer read-only
- `tests/test_review_matrix.py`: accept/reject/edit flow

---

## 8. نتیجه‌گیری

پروژه ساختار نسبتاً خوبی دارد (QA foundation 90%, Import integrity 70%, Review Matrix 65%). اما برای رسیدن به Intelligence Platform باید:

1. ابتدا P0 را بدون نقص کنیم (Atomic Import, Review Preview, No Fake Defaults, 24h Validation, Identity, Permission, Units)
2. سپس Engineering Core deterministic را بسازیم (نه وابسته به LLM)
3. سپس welleng را به عنوان اولین external repo با Benchmark ادغام کنیم
4. سپس Mud/Hydraulics و Well Control
5. سپس AI را به Engineering Tools وصل کنیم (AI → call Engine → receive result → explain)
6. در تمام مراحل تست‌های واقعی با فایل‌های OEOC, Company A/B/C, Excel Merge, CSV فارسی, PDF متنی/اسکن‌شده

**این Audit + Plan مبنای PRهای کوچک بعدی است.**

