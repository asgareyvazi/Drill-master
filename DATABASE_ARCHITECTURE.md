# DrillMaster — Database Architecture Documentation

> **Version:** 1.1 — Release-candidate deployment audit (2026-09-05)

---

## 1. Overview

The database layer uses SQLAlchemy ORM with SQLite as the storage engine. All models and database operations are currently in a single file (`core/database.py`, approximately 7,952 lines).

---

## 2. Engine Configuration

The SQLite filename is resolved by `core/runtime_config.py`, normally under
the OS user-data directory. `DRILLMASTER_DB_PATH` can override it; the
application does not write beside the installed source package.

```python
engine = create_engine(
    f"sqlite:///{configured_database_path()}",
    connect_args={"check_same_thread": False, "timeout": 30},
    poolclass=StaticPool,
    echo=False,
    pool_pre_ping=True,
)
```

### SQLite Pragmas
- `journal_mode=WAL` — Write-Ahead Logging for concurrent reads
- `synchronous=NORMAL` — Balanced durability/performance
- `cache_size=10000` — 10MB page cache
- `foreign_keys=ON` — Enforce FK constraints

---

## 3. Model Inventory

### 3.1 Identity & Access Control

| Model | Table | Purpose |
|-------|-------|---------|
| User | users | User accounts with RBAC |
| Company | companies | Operating companies |
| Project | projects | Drilling projects |
| Well | wells | Individual wellbores |
| Section | sections | Well sections (hole intervals) |

### 3.2 Daily Reporting

| Model | Table | Purpose |
|-------|-------|---------|
| DailyReport | daily_reports | Daily drilling reports |
| ReportRevision | report_revisions | Immutable **complete** report snapshots (header + all report-owned child records) |
| ApprovalAction | approval_actions | Workflow approval history (action, actor, comment) |
| TimeLog24H | time_logs_24h | 24-hour time logs |
| TimeLogMorning | time_logs_morning | Morning tour time logs |

### 3.3 Drilling Parameters

| Model | Table | Purpose |
|-------|-------|---------|
| DrillingParameters | drilling_parameters | WOB, RPM, torque, ROP, pump data |
| MudReport | mud_reports | Mud properties (MW, PV, YP, etc.) |

### 3.4 Well Construction

| Model | Table | Purpose |
|-------|-------|---------|
| CementReport | cement_reports | Cementing job data |
| CasingReport | casing_reports | Casing running data |
| WellboreSchematic | wellbore_schematics | Wellbore schematic images |

### 3.5 Downhole & Bits

| Model | Table | Purpose |
|-------|-------|---------|
| DownholeEquipment | downhole_equipment | MWD/LWD/NM data |
| BHAReport | bha_reports | Bottom Hole Assembly records |
| BitReport | bit_reports | Bit run records |
| FormationReport | formation_reports | Formation tops |

### 3.6 Survey & Trajectory

| Model | Table | Purpose |
|-------|-------|---------|
| SurveyPoint | survey_points | MD, Inc, Azi, TVD, North, East |
| TrajectoryCalculation | trajectory_calculations | MCM calculation results |
| TrajectoryPlot | trajectory_plots | Plot data and images |
| TripSheetEntry | trip_sheet_entries | Trip sheet records |

### 3.7 Logistics

| Model | Table | Purpose |
|-------|-------|---------|
| LogisticsPersonnel | logistics_personnel | Personnel on location |
| ServiceCompanyPOB | service_company_pob | Service company POB |
| FuelWaterInventory | fuel_water_inventory | Fuel and water tracking |
| BulkMaterials | bulk_materials | Mud/drilling bulk-material ledger (feeds MudChemicalLedger) |
| InventoryItem | inventory_items | General consumable/materials inventory (W5 Inventory tab) |
| TransportLog | transport_logs | Vehicle/boat/helicopter logs |
| TransportNotes | transport_notes | Transport notes |
| MaterialRequest | material_requests | Material procurement requests |

#### Inventory domains (distinct — never merged)

The product persists inventory through THREE distinct, non-interchangeable
authoritative models. They are separate domains and must not be summed together
(kg of Barite, litres of Diesel and bbl of water are not one quantity):

| Domain | Model | Owner UI | Notes |
|--------|-------|----------|-------|
| Mud/drilling bulk material | `BulkMaterials` | W7 Logistics, W10 Planning | Consumed wholesale by `MudChemicalLedger`; no item category / reorder levels |
| Fuel & water | `FuelWaterInventory` | W7 Logistics | Fixed fuel/water schema |
| General consumables/materials | `InventoryItem` | W5 Equipment → Inventory tab | Item `category`, reorder `min_level`/`max_level`; report-scoped |

`InventoryItem` is the authoritative store for the W5 Inventory tab. W5 used to
encode inventory into an `EquipmentLog.notes` string
(`Stock:..|Recv:..|Used:..|Rem:..|Unit:..`), which lost Min/Max levels and
collapsed missing into 0. That path is retired for new writes; legacy rows are
read once via `get_legacy_inventory_notes` (read-only) and migrated by
re-saving.

Three-state numeric semantics (shared with `BulkMaterials`, enforced in
`core/inventory_semantics.py`): `None` = not reported (unknown), `0.0` =
explicitly reported zero, value = reported quantity. `current_stock` (closing)
= opening + received − used only when opening is known, else NULL — never a
fabricated 0. Carry-forward fills only a MISSING opening from the previous
report's closing; it never overwrites an explicit opening (including 0). One
worksheet save is one atomic transaction; clearing then saving yields an empty
persisted collection for that report while older reports remain intact.

### 3.8 Safety

| Model | Table | Purpose |
|-------|-------|---------|
| SafetyReport | safety_reports | Daily safety reports |
| SafetyIncident | safety_incidents | Incident records |
| BOPComponent | bop_components | BOP stack components |
| WasteRecord | waste_records | Waste disposal records |

### 3.9 Services & Equipment

| Model | Table | Purpose |
|-------|-------|---------|
| ServiceCompany | service_companies | Service company records |
| ServiceNote | service_notes | Service notes |
| EquipmentLog | equipment_logs | Equipment maintenance logs |

### 3.10 Planning & Analysis

| Model | Table | Purpose |
|-------|-------|---------|
| WellPlan | well_plans | Well drilling plans |
| PlannedActivity | planned_activities | Planned activities |
| SevenDaysLookahead | seven_days_lookahead | 7-day lookahead |
| NPTReport | npt_reports | Non-Productive Time records |
| ActivityCode | activity_codes | Activity code dictionary |
| TimeDepthData | time_depth_data | Time-depth curve data |
| ROPAnalysis | rop_analysis | ROP analysis results |

### 3.11 Procedures

| Model | Table | Purpose |
|-------|-------|---------|
| OperationalProcedure | operational_procedures | DWI procedures |
| ProcedureStep | procedure_steps | Procedure steps |
| ProcedureChecklist | procedure_checklists | Pre-job checklists |
| ProcedureApproval | procedure_approvals | Approval signatures |
| PJSMRecord | pjsm_records | Pre-Job Safety Meetings |
| ProcedureTemplate | procedure_templates | Procedure templates |

### 3.12 Cost & Export

| Model | Table | Purpose |
|-------|-------|---------|
| CostRecord | cost_records | Cost tracking (AFE) |
| ExportTemplate | export_templates | Export templates |

#### Cost truth boundary (single source of truth)

`CostRecord` (well-scoped) is the **only** persisted cost truth. There is no
parallel cost table. The canonical semantics live in `core/cost_semantics.py`
and are shared by every consumer:

* **Variance sign** is `planned - actual` everywhere (positive = under budget).
  It is recomputed on save (`save_afe_worksheet`) so the stored `variance`
  column can never contradict `get_cost_summary` / `get_actual_vs_plan` /
  report engine.
* **Total actual cost** is `Σ CostRecord.actual_cost`. This is what the report
  engine, `OperationsIntelligenceService.analyze_well`, W16 Summary, and W12
  Analysis all report. Rig/spread day-rates entered in W16/W12 are UI
  **planning assumptions/projections**, never persisted as actual cost.
* **NPT cost** is an *allocation* of stored actual cost by NPT time fraction
  (`actual_cost * npt_hours / total_hours`); it is `None` (unknown) when actual
  cost or recorded time is absent — never a synthetic rig-rate product.
* **Currency** has no model default: an unspecified currency stays `NULL`
  (unknown), never silently `USD`.
* **W16 AFE worksheet** persists via `DatabaseManager.save_afe_worksheet`,
  which atomically replaces the well's `cost_type="AFE"` budget lines in one
  transaction (idempotent re-save; OPEX lines untouched). `save_data` used to
  be a no-op `return True`.

### 3.13 Audit

| Model | Table | Purpose |
|-------|-------|---------|
| AuditLog | audit_logs | User action audit trail |

---

## 4. DatabaseManager API

### 4.1 Core Operations

| Method | Purpose |
|--------|---------|
| `initialize()` | Create engine, tables, default data |
| `create_session()` | Create new SQLAlchemy session |
| `session_scope()` | Context manager with auto-commit/rollback |
| `generic_save(model, data)` | Generic upsert for any model |
| `generic_get_list(model, filters)` | Generic query with filters |
| `generic_delete(model, id)` | Generic delete by ID |

### 4.2 Hierarchy Operations

| Method | Purpose |
|--------|---------|
| `get_hierarchy()` | Full company→project→well tree |
| `get_full_hierarchy()` | Eager-loaded hierarchy with sections and reports |
| `get_all_projects()` | List all projects |

### 4.3 Well Operations

| Method | Purpose |
|--------|---------|
| `save_well(data)` | Create or update well |
| `get_well_by_id(id)` | Get well by ID |
| `delete_well(id)` | Delete well and all children |
| `get_sections_by_well(id)` | Get sections for a well |

### 4.4 Report Operations

| Method | Purpose |
|--------|---------|
| `save_daily_report(data)` | Create or update daily report |
| `get_daily_report_by_id(id)` | Get report by ID |
| `get_daily_reports_by_well(id)` | Get reports for a well |
| `get_daily_reports_by_section(id)` | Get reports for a section |
| `delete_daily_report(id)` | Delete report and all children |
| `transition_report(id, action, has_permission, user_id, comment, ...)` | **Authoritative** lifecycle path: validates transition + permission + actor + content + ownership, then writes status, a COMPLETE immutable revision snapshot, and the approval action in ONE atomic transaction |
| `create_report_revision(id)` | Header-only snapshot — COMPATIBILITY/TEST ONLY, not a production path |
| `set_report_status(id, status)` | Raw status writer — COMPATIBILITY/TEST ONLY, does not enforce the state machine |

### 4.5 Import Operations

| Method | Purpose |
|--------|---------|
| `save_imported_multi_tab_data_atomic()` | Atomic multi-table import |
| `snapshot_import_target()` | Capture pre-import state |
| `restore_import_snapshot()` | Rollback to pre-import state |

### 4.6 Domain-Specific Operations

Each domain (drilling, mud, safety, logistics, etc.) has dedicated save/get methods. See the source code for complete API.

Cost-specific:

| Method | Purpose |
|--------|---------|
| `save_afe_worksheet(well_id, rows, afe_number, currency, user_id)` | Atomically replace the well's `cost_type="AFE"` budget lines in ONE transaction; recomputes canonical variance; leaves OPEX lines untouched (idempotent re-save) |
| `save_cost_record(data)` | Upsert a single cost line (OPEX or AFE) |
| `get_cost_records(well_id, category)` | All cost lines for a well |
| `get_cost_summary(well_id)` | Per-category `planned`/`actual`/`variance` (variance = planned − actual) |
| `get_planned_total_days(well_id)` | Read-only mirror of the active `WellPlan.planned_total_days` (Planning owns it; W16 only displays it) |

Note: AFE and OPEX `actual_cost` lines are distinct cost records; total actual
cost is their sum. There is no code path that writes the same spend to both an
AFE and an OPEX record, so summing them does not double-count.

Inventory-specific (general consumables — `InventoryItem`):

| Method | Purpose |
|--------|---------|
| `save_inventory_items(well_id, report_id, rows, report_date, section_id, user_id)` | Atomically replace a report's inventory worksheet; three-state + carry-forward; identity = (well, report, item_name) |
| `get_inventory_items(well_id, report_id, report_date)` | Structured inventory rows (unknown preserved as None) |
| `get_legacy_inventory_notes(well_id, report_id)` | Read-only decode of legacy `EquipmentLog` "Inventory" notes rows (migration compatibility) |

KPI canonical source:

`tabs/w12_Analysis.py::calculate_kpis` sources its shared metrics
(current depth = MAX recorded depth, average ROP, NPT hours, NPT %, rig days)
from `OperationsIntelligenceService.analyze_well` so W12, the report engine and
the intelligence dashboard cannot silently disagree. W12-specific reductions
(best ROP, mean WOB/RPM/torque, daily depth gain) remain local and keep the
unknown≠zero contract. The `CostReportEngine` always reports stored actual cost
as "Total Actual Cost"; a supplied day-rate produces a separately-labelled
"Projected Total", never actual cost.

---

## 5. Session Management

### 5.1 Pattern

```python
# Preferred: context manager
with db.session_scope() as session:
    session.query(Well).all()
    # Auto-commit on success, auto-rollback on exception

# Legacy: manual session
session = db.create_session()
try:
    # ... operations
    session.commit()
except:
    session.rollback()
finally:
    session.close()
```

### 5.2 Thread Safety

SQLite with `check_same_thread=False` and `StaticPool` ensures single-connection access. The `session_scope()` context manager handles cleanup.

---

## 6. Backup Strategy

- **Auto-backup:** Every 30 minutes via `auto_backup()`
- **Location:** configured `DRILLMASTER_BACKUP_DIR`, normally `<data>/backups/`
- **Retention:** Max 10 backups
- **Method:** SQLite backup API, including WAL state
- **Recovery:** stop the application, restore a verified backup, and restart;
  deployments must perform and record a restore drill
- **Schema:** startup migrations are recorded in `schema_version` (current
  version `2`).  Additive upgrades are followed by an idempotent SQLite
  nullability-contract audit/rebuild for legacy `NOT NULL` columns where the
  ORM explicitly allows `NULL`; migration errors fail initialization.

## 6.1 Import transaction boundary

The universal Excel/PDF import opens one outer SQLAlchemy session in
`ExcelImportDialog._do_import()`. Well, section, daily report, mud, drilling
parameters, time logs, morning logs, and every report-scoped collection receive
that session. Save helpers `flush()` only when an identifier is needed; they do
not commit or swallow exceptions when a caller-owned import session is passed.
There is exactly one successful commit, or the outer rollback removes all
objects created/updated by that report import. Ordinary CRUD calls omit the
session and retain their own commit behavior.

Import results expose `ACCEPT`, `REVIEW_REQUIRED`, `VALIDATION_ERROR`, and
`PERSISTENCE_ERROR` separately. Structured diagnostics include stage,
entity/field, row/source, original and normalized values, expected type,
operation, exception type/message, traceback, and available provenance.
Reviewable input is never counted as a persistence failure; morning
continuation rows remain review items with their source cells and text rather
than receiving invented time values. Final status precedence is deterministic:
`PERSISTENCE_ERROR` > `VALIDATION_ERROR` > `REVIEW_REQUIRED` > `ACCEPT`.

All source formats first become the lossless IR in `core/import_ir.py`. Excel
uses `ExcelIntelligence.extract()` for matched templates and the same module's
`extract_generic()` for unknown `.xlsx` files; it never routes XLSX through
MinerU. PDF/MinerU and Excel both use `core/canonical_mapper.py` for canonical
alias resolution, contextual `Hrs`/`Report Date` disambiguation, typed
normalization, and the `ReviewItem` contract. Unknown or ambiguous labels are
reviewable with document/page/sheet/table/cell provenance rather than guessed.

Schema v2 migration uses the live SQLite `CREATE TABLE` SQL as the rebuild
source. It copies every live column, preserves defaults, embedded constraints,
foreign keys, external indexes, triggers, and unknown data, verifies the
result, checks `PRAGMA foreign_key_check`, records the version, and rolls back
as one migration transaction. Future versions are rejected before any table
creation or import write.

---

## 7. Refactoring Roadmap

### Phase 1: Extract Models
Split `database.py` into model files while maintaining backward compatibility:

```python
# core/database/__init__.py
from .models.identity import User, Company, Project, Well, Section
from .models.reporting import DailyReport, ReportRevision
# ... etc
from .manager import DatabaseManager
```

### Phase 2: Extract Services
Move business logic from DatabaseManager into service classes:

```python
# core/database/services/well_service.py
class WellService:
    def __init__(self, session_factory):
        self.session_factory = session_factory
    
    def save_well(self, data):
        # ... extracted logic
```

### Phase 3: Expand Repositories
The `core/repositories/` directory already exists with base classes. Expand to cover all domains.

### Rules
1. **Never break existing API** — re-export everything from `core/database.py`
2. **Test after each extraction** — run full test suite
3. **No data loss** — schema migrations must preserve all existing data
