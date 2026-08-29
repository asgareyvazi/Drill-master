# DrillMaster — Engineering Architecture Documentation

> **Version:** 1.0 — Audit Baseline (2026-08-24)

---

## 1. Design Principles

1. **Deterministic:** All calculations use published formulas from industry references (Bourgoyne et al., SPE, Applied Drilling Engineering)
2. **No LLM Guessing:** AI never modifies engineering data directly. AI can call engines and receive results.
3. **Explicit Contracts:** Every calculation has documented required inputs, outputs, units, assumptions, and error conditions
4. **Error Propagation:** Missing inputs raise `MissingInputError`, unsupported calculations raise `UnsupportedCalculationError`
5. **Traceable:** Results include assumptions, warnings, and calculation method
6. **Testable:** All engines have comprehensive unit tests

---

## 2. Architecture

```
UI Tabs
    │
    ▼
Application Services (future)
    │
    ▼
Engineering Core (core/engineering/)
    ├── core.py          # All engine implementations
    ├── registry.py      # Capability detection
    ├── engines/         # Specialized engines
    └── adapters/        # External library adapters
    │
    ▼
Repositories (core/repositories/)
    │
    ▼
Database (core/database.py)
```

---

## 3. Engine Catalog

### 3.1 TrajectoryEngine

**File:** `core/engineering/core.py`
**Method:** Minimum Curvature Method (MCM)
**Reference:** Bourgoyne et al., SPE

#### Governing Equations
```
Dogleg = arccos[ cos(I1)·cos(I2) + sin(I1)·sin(I2)·cos(A2-A1) ]
RF = (2/DL) · tan(DL/2)    if DL ≠ 0, else 1
ΔTVD = 0.5 · ΔMD · (cos I1 + cos I2) · RF
ΔNorth = 0.5 · ΔMD · (sin I1·cos A1 + sin I2·cos A2) · RF
ΔEast = 0.5 · ΔMD · (sin I1·sin A1 + sin I2·sin A2) · RF
```

#### Inputs
| Field | Type | Unit | Required | Validation |
|-------|------|------|----------|------------|
| md | float | m | Yes | Monotonic increasing, no duplicates |
| inc | float | deg | Yes | Range [0, 180] |
| azi | float | deg | Yes | Normalized to [0, 360) |

#### Outputs
| Field | Unit | Description |
|-------|------|-------------|
| tvd | m | True Vertical Depth |
| north | m | Northing displacement |
| east | m | Easting displacement |
| vs | m | Vertical Section |
| hd | m | Horizontal Displacement |
| dls | deg/30m | Dogleg Severity |
| build_rate | deg/30m | Build rate |
| turn_rate | deg/30m | Turn rate |

#### Additional Methods
- `project_ahead()` — Project from last point to target MD with constant inc/azi

---

### 3.2 BitEngine

**File:** `core/engineering/core.py`

#### Calculations

**TFA (Total Flow Area):**
```
TFA = Σ (π/4 · (d/32)²)    where d = nozzle size in 32nds of inch
```

**HSI (Hydraulic Horsepower per Square Inch):**
```
HHP = Q · ΔP / 1714         where Q in gpm, ΔP in psi
HSI = HHP / (π/4 · D²)     where D = bit size in inch
```

---

### 3.3 BHAEngine

**File:** `core/engineering/core.py`

#### Calculations
- Cumulative length calculation (bottom-up)
- Cumulative weight calculation
- Component validation

---

### 3.4 HydraulicsEngine

**File:** `core/engineering/core.py`

#### Annular Velocity
```
AV = 24.51 · Q / (Dh² - Dp²)    ft/min
where Q in gpm, Dh = hole ID in inch, Dp = pipe OD in inch
```

#### ECD (Equivalent Circulating Density)
```
ECD = MW + APL / (0.052 · TVD)
where MW in ppg, APL in psi, TVD in ft
```

#### PV/YP from Viscometer
```
PV = θ600 - θ300
YP = θ300 - PV
```

---

### 3.5 WellControlEngine

**File:** `core/engineering/core.py`

#### Kill Mud Weight
```
Kill MW = Original MW + SIDPP / (0.052 · TVD)
```

#### MAASP (Maximum Allowable Annular Surface Pressure)
```
MAASP = (Frac MW - Current MW) · 0.052 · Shoe TVD
where Frac MW = Leak-off / (0.052 · TVD) if leak-off provided
```

---

### 3.6 OperationsIntelligenceEngine

**File:** `core/engineering/core.py`

#### ROP Trend Analysis
Detects ROP degradation over time. Returns insight with evidence if decline exceeds threshold (default 18%).

#### NPT Trend Analysis
Flags when NPT percentage exceeds threshold (default 20%).

---

### 3.7 MudLedgerEngine

**File:** `core/engineering/core.py`

#### Chemical Ledger
```
Closing Stock = Opening + Received + Adjusted - Used - Returned
Next Day Opening = Previous Closing
```

#### Alerts
- Negative stock
- Unusual consumption (>2x opening)
- No movement (stock with no usage)

---

## 4. Calculation Result Contract

Every engine method returns a `CalculationResult`:

```python
@dataclass
class CalculationResult:
    success: bool
    value: Any = None
    values: Dict[str, Any] = None
    unit: str = ""
    assumptions: List[str] = None
    warnings: List[str] = None
    error: str = ""
```

---

## 5. Error Hierarchy

```
EngineeringError (base)
├── MissingInputError(field)     # Required input not provided
└── UnsupportedCalculationError(reason)  # Calculation not implemented
```

---

## 6. Capability Registry

**File:** `core/engineering/registry.py`

Detects optional external packages at runtime without blocking startup:

| Capability | Package | Purpose |
|------------|---------|---------|
| Trajectory / anti-collision | welleng | Survey planning, error models, clearance |
| Torque & drag | torque_drag | Axial load and torque along string |
| Drilling optimization | gekko | ROP and scenario optimization |
| PDF tables | camelot | Text PDF table extraction |
| PDF OCR tables | pytesseract | Scanned PDF OCR fallback |

---

## 7. Testing

All engines have comprehensive tests in `tests/test_p0_engineering_core.py` (20 tests):

- Trajectory: single point, multi-point, validation, projection
- Bit: TFA calculation, HSI calculation
- BHA: cumulative length/weight
- Hydraulics: annular velocity, ECD, PV/YP
- Well Control: kill MW, MAASP
- Operations: ROP trend, NPT trend
- Mud Ledger: closing stock, alerts

---

## 8. Future Engines

| Engine | Priority | Status |
|--------|----------|--------|
| Torque & Drag | High | Stub exists |
| Anti-Collision | High | Stub exists |
| Casing Design | Medium | Not started |
| Cementing | Medium | Not started |
| Kick Tolerance | Medium | Not started |
| Pressure Loss | Medium | Not started |
| ROP Optimization | Low | Not started |
