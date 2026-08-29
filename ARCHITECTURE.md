# DrillMaster — Architecture Documentation

> **Version:** 1.0 — Audit Baseline (2026-08-24)
> **Branch:** `arena/01a032f0-drill-master`

---

## 1. High-Level Architecture

```
Drill-master/
├── app.py                    # Application entry point (PySide6 QApplication)
├── main_window.py            # Main window orchestrator (2,958 lines)
├── run.py                    # CLI launcher
├── reset_database.py         # Database reset utility
├── verify_release.py         # Release verification
│
├── core/                     # Business logic, data, engineering
│   ├── database.py           # ORM models + DatabaseManager (7,094 lines)
│   ├── canonical_schema.py   # Single Source of Truth for field registry
│   ├── universal_import.py   # Workbook scanner, table detector, sheet classifier
│   ├── ai_import_mapper.py   # AI-assisted field mapping (Ollama)
│   ├── unit_manager.py       # Central unit conversion engine
│   ├── excel_normalizer.py   # Excel data normalization
│   ├── profile_import_engine.py  # Import profile management
│   ├── mapping_store.py      # Persistent mapping store
│   ├── import_quality.py     # Import quality validation
│   ├── import_profiler.py    # Import bottleneck detection
│   ├── validators.py         # Data validation rules
│   ├── data_quality.py       # Data quality checks
│   ├── error_handler.py      # Structured error handling
│   ├── permissions.py        # RBAC permission system
│   ├── managers.py           # StatusBar, AutoSave, Shortcut managers
│   ├── selection_manager.py  # Global selection state (well/section/report)
│   ├── cache_manager.py      # In-memory cache with TTL
│   ├── functions.py          # Central utility functions
│   ├── base_tab.py           # Base class for all tabs
│   ├── common_widgets.py     # Shared UI widgets
│   ├── text_utils.py         # Text processing utilities
│   ├── time_utils.py         # Time/date utilities
│   ├── standards.py          # Industry standards reference
│   ├── table_record_mapper.py # Table-to-record mapping
│   ├── hydraulics_engine.py  # Hydraulics calculations
│   ├── operations_intelligence.py # Operations analysis
│   ├── rag_search.py         # RAG-based historical search
│   ├── ai_tools.py           # AI tool integrations
│   ├── report_engine.py      # Report generation engine
│   ├── professional_export.py # Professional export (16 sheets + PDF)
│   ├── ddr_pdf_export.py     # DDR PDF export
│   ├── document_import.py    # Document import utilities
│   ├── actual_vs_plan.py     # Actual vs planned analysis
│   ├── wellbore_schematic_engine.py # Wellbore schematic generation
│   ├── mud_ledger.py         # Mud chemical ledger
│   ├── health_check.py       # System health checks
│   │
│   ├── engineering/          # Deterministic engineering calculations
│   │   ├── __init__.py       # Public API exports
│   │   ├── core.py           # TrajectoryEngine, BitEngine, BHAEngine,
│   │   │                     # HydraulicsEngine, WellControlEngine,
│   │   │                     # OperationsIntelligenceEngine, MudLedgerEngine
│   │   ├── registry.py       # Capability registry (optional packages)
│   │   ├── engines/          # Specialized engines
│   │   │   ├── trajectory.py
│   │   │   ├── torque_drag.py
│   │   │   └── anti_collision.py
│   │   └── adapters/         # External library adapters
│   │       ├── welleng_adapter.py
│   │       └── torque_drag_adapter.py
│   │
│   ├── repositories/         # Data access layer
│   │   ├── base.py
│   │   ├── well_repository.py
│   │   ├── report_repository.py
│   │   ├── cost_repository.py
│   │   ├── logistics_repository.py
│   │   ├── safety_repository.py
│   │   ├── service_repository.py
│   │   └── audit_repository.py
│   │
│   ├── import_adapters/      # Import format adapters
│   │   └── pdf_tables.py     # PDF table extraction
│   │
│   └── api/                  # REST API (FastAPI skeleton)
│       └── rest_api.py
│
├── tabs/                     # UI Tab widgets (PySide6)
│   ├── home_tab.py           # Dashboard/home
│   ├── w1_well_info.py       # Well information
│   ├── w2_Daily_Report.py    # Daily drilling report
│   ├── w3_drilling_report.py # Drilling parameters & mud
│   ├── w3b_wellbore_schematic_tab.py # Wellbore schematic
│   ├── w3c_section_data.py   # Section data (casing, cement, services)
│   ├── w4_Downhole_Widget.py # Downhole equipment
│   ├── w5_Equipment_Widget.py # Surface equipment
│   ├── w6_Trajectory_Widget.py # Survey & trajectory
│   ├── w7_logistics_Widget.py # Logistics (POB, fuel, bulk, transport)
│   ├── w8_Safety_Widget.py   # Safety (HSE, BOP, waste)
│   ├── w9_Services_Widget.py # Service companies & materials
│   ├── w10_Planning_Widget.py # 7-day lookahead & well plans
│   ├── w11_Export.py         # Export (Excel, PDF)
│   ├── w12_Analysis.py       # Analysis & charts
│   ├── w13_Engineering_Calculator.py # Engineering calculator
│   ├── w14_Procedure_Widget.py # Operational procedures (DWI)
│   ├── w15_Reference_Tables.py # Reference tables
│   └── w16_Cost_Management.py # Cost management (AFE)
│
├── dialogs/                  # Modal dialogs
│   ├── excel_import_dialog.py
│   ├── hierarchy_dialogs.py
│   ├── daily_report_dialogs.py
│   ├── drilling_report_dialogs.py
│   ├── engineering_dialogs.py
│   ├── calculator_dialog.py
│   ├── login_dialog.py
│   ├── planning_dialog.py
│   ├── settings_dialog.py
│   ├── smart_template_dialog.py
│   └── startup_dialog.py
│
├── config/                   # Configuration files
├── ui/                       # Custom UI components (ribbon)
├── tools/                    # Utility scripts
├── tests/                    # Test suite (64 tests, all passing)
└── docs/                     # Documentation
```

---

## 2. Data Flow Architecture

```
Excel/PDF File
    │
    ▼
┌─────────────────────────────────┐
│  WorkbookScanner                │  universal_import.py
│  - File metadata                │
│  - Sheet scanning               │
│  - Merged cell analysis         │
│  - Hidden row/column detection  │
│  - Formula detection            │
│  - Table detection              │
│  - Column profiling             │
│  - Sheet classification         │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  SheetClassifier                │  universal_import.py
│  - Name-based classification    │
│  - Header keyword matching      │
│  - Content analysis             │
│  - Data type inference          │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  AIImportMapper                 │  ai_import_mapper.py
│  - Ollama local LLM             │
│  - Semantic field mapping       │
│  - Confidence scoring           │
│  - Canonical field validation   │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  Canonical Schema               │  canonical_schema.py
│  - Field registry (50 fields)   │
│  - Quantity types               │
│  - Canonical units              │
│  - Critical field flags         │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  UnitManager                    │  unit_manager.py
│  - 20+ quantity types           │
│  - Original value preservation  │
│  - Canonical normalization      │
│  - Conversion audit trail       │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  Validators                     │  validators.py
│  - Range checks                 │
│  - Type validation              │
│  - Cross-field consistency      │
│  - Duplicate detection          │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  DatabaseManager                │  database.py
│  - Atomic import transaction    │
│  - Snapshot/rollback support    │
│  - Audit logging                │
│  - 55 ORM models                │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│  UI Tabs                        │  tabs/
│  - 19 tab widgets               │
│  - SelectionManager signals     │
│  - Auto-save support            │
└─────────────────────────────────┘
```

---

## 3. Database Architecture

### 3.1 ORM Models (55 classes in database.py)

| Domain | Models |
|--------|--------|
| **Identity** | User, Company, Project, Well, Section |
| **Reporting** | DailyReport, ReportRevision, ApprovalAction |
| **Time Logging** | TimeLog24H, TimeLogMorning |
| **Drilling** | DrillingParameters, MudReport |
| **Well Construction** | CementReport, CasingReport, WellboreSchematic |
| **Downhole** | DownholeEquipment, BHAReport, BitReport, FormationReport |
| **Survey** | SurveyPoint, TrajectoryCalculation, TrajectoryPlot |
| **Trip** | TripSheetEntry |
| **Logistics** | LogisticsPersonnel, ServiceCompanyPOB, FuelWaterInventory, BulkMaterials, TransportLog, TransportNotes, MaterialRequest |
| **Safety** | SafetyReport, SafetyIncident, BOPComponent, WasteRecord |
| **Services** | ServiceCompany, ServiceNote |
| **Equipment** | EquipmentLog |
| **Planning** | SevenDaysLookahead, NPTReport, ActivityCode, TimeDepthData, ROPAnalysis, PlannedActivity, WellPlan |
| **Procedures** | OperationalProcedure, ProcedureStep, ProcedureChecklist, ProcedureApproval, PJSMRecord, ProcedureTemplate |
| **Cost** | CostRecord, ExportTemplate |
| **Audit** | AuditLog |

### 3.2 Key Relationships

```
Company ──1:N──► Project ──1:N──► Well ──1:N──► Section ──1:N──► DailyReport
                                    │                                  │
                                    ├──1:N──► DrillingParameters       ├──1:N──► TimeLog24H
                                    ├──1:N──► MudReport                ├──1:N──► TimeLogMorning
                                    ├──1:N──► SurveyPoint              ├──1:N──► SurveyPoint
                                    ├──1:N──► SafetyReport             ├──1:N──► SafetyReport
                                    ├──1:N──► EquipmentLog             ├──1:N──► EquipmentLog
                                    ├──1:N──► ServiceCompanyPOB        ├──1:N──► ServiceCompanyPOB
                                    ├──1:N──► BulkMaterials            ├──1:N──► BulkMaterials
                                    ├──1:N──► FuelWaterInventory       ├──1:N──► FuelWaterInventory
                                    ├──1:N──► CostRecord
                                    ├──1:N──► WellPlan
                                    └──1:N──► OperationalProcedure
```

### 3.3 Database Configuration

- **Engine:** SQLite with WAL mode
- **Pool:** StaticPool (single connection for SQLite compatibility)
- **Pragmas:** WAL journal, NORMAL synchronous, 10000 cache size, foreign keys ON
- **Session:** Manual session management with `session_scope()` context manager
- **Backup:** Auto-backup every 30 minutes, max 10 backups retained

---

## 4. Engineering Architecture

### 4.1 Design Principles

1. **Deterministic:** All calculations use published formulas (Bourgoyne et al., SPE)
2. **No LLM Guessing:** AI never modifies engineering data directly
3. **Explicit Contracts:** Every calculation has required inputs, outputs, units, assumptions
4. **Error Propagation:** Missing inputs raise `MissingInputError`, not silent defaults
5. **Traceable:** Results include assumptions, warnings, and calculation method

### 4.2 Engine Inventory

| Engine | File | Status | Key Calculations |
|--------|------|--------|-----------------|
| **TrajectoryEngine** | core.py | ✅ Complete | Minimum Curvature Method, DLS, build/turn rates, VS, projection |
| **BitEngine** | core.py | ✅ Complete | TFA from nozzles, HSI |
| **BHAEngine** | core.py | ✅ Complete | Cumulative length/weight, component validation |
| **HydraulicsEngine** | core.py | ✅ Complete | Annular velocity, ECD, PV/YP from viscometer |
| **WellControlEngine** | core.py | ✅ Complete | Kill MW, MAASP |
| **OperationsIntelligenceEngine** | core.py | ✅ Complete | ROP trend analysis, NPT trend analysis |
| **MudLedgerEngine** | core.py | ✅ Complete | Chemical ledger, stock tracking, consumption analysis |
| **TorqueDragEngine** | engines/torque_drag.py | 🔶 Stub | Placeholder for torque & drag |
| **AntiCollisionEngine** | engines/anti_collision.py | 🔶 Stub | Placeholder for anti-collision |

### 4.3 Capability Registry

Optional external packages detected at runtime:
- `welleng` — Survey planning, error models, clearance
- `torque_drag` — Axial load and torque along string
- `gekko` — ROP and scenario optimization
- `camelot` — PDF table extraction
- `pytesseract` — Scanned PDF OCR fallback

---

## 5. Import Pipeline Architecture

### 5.1 Current Pipeline

```
Excel File (.xlsx)
    │
    ▼
WorkbookScanner.scan()
    ├── File metadata (name, size, type)
    ├── Per-sheet scan (rows, cols, hidden, merged, formulas, density)
    └── Table detection (bands, column gaps, headers, titles, profiles)
    │
    ▼
SheetClassifier.classify_all()
    ├── Keyword matching (14 categories)
    ├── Header analysis
    └── Content heuristics
    │
    ▼
AIImportMapper.map_context() [optional]
    ├── Ollama local LLM
    ├── Semantic field mapping
    └── Confidence scoring
    │
    ▼
Mapping + Validation
    ├── Canonical schema lookup
    ├── Unit normalization
    └── Data validation
    │
    ▼
DatabaseManager.save_imported_multi_tab_data_atomic()
    ├── Begin transaction
    ├── Save all child tables
    ├── Commit or rollback all
    └── No partial imports
```

### 5.2 Supported Table Types

- Vertical tables (headers in row, data below)
- Horizontal tables (headers in column)
- Nested tables (BHA, bit records)
- Multi-row headers (1-3 rows)
- Merged cell tables
- Continuation tables
- Side-by-side tables (column gap detection)
- Borderless tables

### 5.3 Sheet Classification Categories

Daily Report, Mud, Drilling, BHA, Bit, Survey, Trajectory, Safety, BOP, Logistics, Services, Cost, Planning, Reference, Unknown

---

## 6. Canonical Schema

### 6.1 Design

The canonical schema (`core/canonical_schema.py`) is the **Single Source of Truth** for all field definitions. Every importer, mapper, validator, unit converter, and UI component references this schema.

### 6.2 Field Specification

Each field has:
- **path:** Hierarchical identifier (e.g., `mud_report.mw`)
- **quantity:** Data type for unit conversion (e.g., `density`)
- **unit:** Canonical storage unit (e.g., `ppg`)
- **critical:** Whether the field is required for valid import

### 6.3 Current Coverage (50 fields)

| Domain | Fields |
|--------|--------|
| well_info | name, report_date |
| daily_report | report_date, report_number, depth_0000, depth_0600, depth_2400 |
| mud_report | mw, pv, yp, ph, temperature |
| drilling_params | bit_no, bit_size, bit_type, depth_in, depth_out, avg_rop |
| time_log | main_code, sub_code, contractor |
| survey | md, inc, azi, tvd |
| bulk_material | material_name, received, used, current_stock |
| bha | component_name, od, length |
| downhole | equipment_name, serial_number |
| formation | name, md_top |
| casing | size, depth_from, depth_to, grade |
| cement | material, used |
| bop | component_name, working_pressure |
| safety | days_without_lti |
| equipment | equipment_name |
| logistics | company_name |
| service | company_name, service_type |
| cost | description, amount |

---

## 7. Unit Management

### 7.1 Supported Quantities (20+)

Length, Depth, Diameter, Pressure, Flow Rate, Volume, Density, Temperature, Torque, Force, Weight, ROP, RPM, Viscosity, Yield Point, ECD, DLS, Angle, Azimuth, Inclination

### 7.2 Key Design Decisions

1. **Original value preservation:** Every conversion stores original + normalized + canonical
2. **No silent defaults:** If conversion fails, original is kept and flagged
3. **Explicit conversion rules:** Each conversion records the formula used
4. **Alias support:** `MW` → `density`, `WOB` → `force`, `PV` → `viscosity`

---

## 8. Permission System

### 8.1 Roles

| Role | Capabilities |
|------|-------------|
| **admin** | Full access (create, delete, edit, approve, manage users, export, import) |
| **engineer** | Create wells, edit reports, export, import (no delete, no user management) |
| **viewer** | Read-only (export only) |

### 8.2 Permission Fields

- `can_create_well`
- `can_delete_well`
- `can_edit_reports`
- `can_approve_reports`
- `can_manage_users`
- `can_export`
- `can_import`

---

## 9. Testing Strategy

### 9.1 Current Test Suite (64 tests, all passing)

| Test File | Focus | Tests |
|-----------|-------|-------|
| test_canonical_schema.py | Schema integrity | 1 |
| test_config_and_mapping.py | Config and mapping store | 2 |
| test_core_import.py | Core import pipeline | 4 |
| test_health_check.py | System health | 1 |
| test_import_quality_extra.py | Import quality validation | 3 |
| test_operations.py | Operations intelligence | 3 |
| test_p0_atomic_import.py | Atomic import transactions | 3 |
| test_p0_engineering_core.py | Engineering calculations | 20 |
| test_p0_permissions.py | Permission enforcement | 5 |
| test_p0_time_log_validation.py | Time log validation | 10 |
| test_p0_unit_preservation.py | Unit conversion preservation | 8 |
| test_p0_well_identity.py | Well identity management | 3 |
| test_table_mapper.py | Table-to-record mapping | 1 |

### 9.2 Test Categories

- **P0 Critical:** Atomic import, engineering core, permissions, unit preservation, well identity, time log validation
- **Integration:** Core import pipeline, import quality
- **Unit:** Canonical schema, config, health check, operations, table mapper

---

## 10. Known Architectural Risks

### 10.1 🔴 database.py (7,094 lines, 55 classes, 154 functions)

**Risk:** Single file contains all ORM models AND all database operations.

**Impact:**
- Difficult to navigate and maintain
- Merge conflicts in team development
- Testing individual model groups is harder
- Circular import risk when other modules reference specific models

**Recommended Refactor Path:**
```
core/database/
├── __init__.py          # Re-exports for backward compatibility
├── engine.py            # Engine creation, session factory
├── session.py           # Session management, context managers
├── models/
│   ├── __init__.py      # All model imports
│   ├── identity.py      # User, Company, Project, Well, Section
│   ├── reporting.py     # DailyReport, ReportRevision, ApprovalAction
│   ├── drilling.py      # DrillingParameters, MudReport
│   ├── survey.py        # SurveyPoint, TrajectoryCalculation
│   ├── safety.py        # SafetyReport, BOPComponent, WasteRecord
│   ├── logistics.py     # Logistics, POB, Fuel, Bulk, Transport
│   ├── equipment.py     # EquipmentLog, DownholeEquipment
│   ├── planning.py      # WellPlan, PlannedActivity, Lookahead, NPT
│   ├── procedures.py    # OperationalProcedure, Steps, Checklist
│   ├── cost.py          # CostRecord, ExportTemplate
│   └── audit.py         # AuditLog
├── repositories/        # Already exists, needs expansion
└── services/            # Business logic extracted from DatabaseManager
```

### 10.2 🔴 main_window.py (2,958 lines, 3 classes, 108 functions)

**Risk:** MainWindow handles too many responsibilities.

**Impact:**
- Hard to test individual features
- Difficult to add new functionality without touching the main file
- Signal/slot connections become tangled

**Recommended Refactor Path:**
```
main_window.py (orchestrator only)
├── managers/
│   ├── navigation_manager.py    # Tree navigation, item selection
│   ├── tab_manager.py           # Tab creation, switching, refresh
│   ├── toolbar_manager.py       # Toolbar creation and actions
│   ├── hierarchy_manager.py     # Hierarchy tree building, filtering
│   ├── shortcut_manager.py      # Already exists in core/managers.py
│   └── window_state_manager.py  # Dock state, settings, theme
└── controllers/
    └── import_controller.py     # Import workflow orchestration
```

### 10.3 🟡 Missing Integration Tests

**Risk:** No end-to-end test covering the full import pipeline.

**Impact:**
- Regressions in the import → validate → save → display flow may go undetected
- Real-world Excel structures are not tested

### 10.4 🟡 No Data Lineage

**Risk:** Imported values cannot be traced back to their source.

**Impact:**
- Engineers cannot verify where a value came from
- Debugging import issues is harder
- Audit trail is incomplete for engineering data

---

## 11. Implementation Priority

### Phase 1: Foundation (Current)
- ✅ Architecture audit
- ✅ Test baseline (64 tests passing)
- ✅ Architecture documentation

### Phase 2: Critical Fixes
- Fix any import/runtime bugs discovered during audit
- Stabilize canonical schema

### Phase 3: Database Refactor (Incremental)
- Extract models into separate files
- Extract services from DatabaseManager
- Maintain backward compatibility via re-exports
- Tests after each extraction

### Phase 4: MainWindow Refactor (Incremental)
- Extract managers/controllers
- Maintain all existing signals and functionality
- Tests after each extraction

### Phase 5: Import Pipeline Hardening
- Add data lineage tracking
- Improve confidence scoring
- Add human review mechanism
- Integration tests with real Excel fixtures

### Phase 6: Engineering Expansion
- Implement torque & drag engine
- Implement anti-collision engine
- Add calculation traceability

### Phase 7: Production Hardening
- Performance optimization
- Error handling standardization
- Documentation completion
- Release preparation
