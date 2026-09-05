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
| ReportRevision | report_revisions | Immutable report snapshots |
| ApprovalAction | approval_actions | Workflow approval history |
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
| BulkMaterials | bulk_materials | Bulk material inventory |
| TransportLog | transport_logs | Vehicle/boat/helicopter logs |
| TransportNotes | transport_notes | Transport notes |
| MaterialRequest | material_requests | Material requests |

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
| `create_report_revision(id)` | Create immutable snapshot |
| `set_report_status(id, status)` | Change workflow state |

### 4.5 Import Operations

| Method | Purpose |
|--------|---------|
| `save_imported_multi_tab_data_atomic()` | Atomic multi-table import |
| `snapshot_import_target()` | Capture pre-import state |
| `restore_import_snapshot()` | Rollback to pre-import state |

### 4.6 Domain-Specific Operations

Each domain (drilling, mud, safety, logistics, etc.) has dedicated save/get methods. See the source code for complete API.

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
- **Schema:** additive startup migrations are recorded in `schema_version`
  (current version `1`); migration errors fail initialization

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
