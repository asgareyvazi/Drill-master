# DrillMaster — AI Mapping Documentation

> **Version:** 1.0 — Audit Baseline (2026-08-24)

---

## 1. Overview

The AI mapping system assists in mapping Excel column headers to canonical drilling fields. It uses a local LLM (via Ollama) to provide semantic understanding of ambiguous or non-standard column names.

---

## 2. Architecture

```
Excel Headers
    │
    ▼
Deterministic Keyword Matching (SheetClassifier)
    │
    ▼ (if ambiguous)
AIImportMapper
    ├── Build compact context (title, headers, samples)
    ├── Send to Ollama LLM
    ├── Parse JSON response
    ├── Validate against canonical schema
    └── Return proposals with confidence scores
    │
    ▼
Human Review (future)
    │
    ▼
Canonical Schema → Unit Normalization → Database
```

---

## 3. AIImportMapper

**File:** `core/ai_import_mapper.py`

### 3.1 Configuration

| Setting | Env Variable | Default |
|---------|-------------|---------|
| Ollama URL | `DRILLMASTER_OLLAMA_URL` | `http://127.0.0.1:11434` |
| Model | `DRILLMASTER_AI_MODEL` | `qwen2.5-local` |
| Timeout | `DRILLMASTER_AI_TIMEOUT` | 30-45 seconds |
| Enable | `DRILLMASTER_AI_IMPORT` | `1` (enabled) |

### 3.2 Prompt Structure

```json
{
  "task": "Map workbook cells to canonical drilling fields.",
  "rules": [
    "Return JSON only: {proposals: []}.",
    "Never invent values.",
    "Keep source_sheet, source_row and source_column.",
    "Return confidence between 0 and 1.",
    "Use null when ambiguous."
  ],
  "allowed_fields": ["well_info.name", "mud_report.mw", ...],
  "context": {
    "sheets": [...],
    "tables": [...]
  }
}
```

### 3.3 Proposal Format

```json
{
  "field": "mud_report.mw",
  "source_sheet": "Daily Report",
  "source_row": 17,
  "source_column": 8,
  "value": 10.2,
  "confidence": 0.96
}
```

### 3.4 Validation Rules

A proposal is valid if:
1. `field` is in the canonical schema
2. `source_sheet` is not empty
3. `source_row` is not null
4. `value` is not null
5. `confidence` is between 0 and 1

---

## 4. Deterministic Fallback

When AI is unavailable, the system falls back to keyword-based matching:

| Header Pattern | Mapped Field |
|----------------|-------------|
| MW, Mud Wt., Mud Weight, Density | mud_report.mw |
| PV, Plastic Viscosity | mud_report.pv |
| YP, Yield Point | mud_report.yp |
| WOB, Weight on Bit | drilling_params.wob |
| RPM, Rotary Speed | drilling_params.rpm |
| ROP, Rate of Penetration | drilling_params.avg_rop |
| MD, Measured Depth | survey.md |
| Inc, Inclination | survey.inc |
| Azi, Azimuth | survey.azi |
| TVD, True Vertical Depth | survey.tvd |

---

## 5. Current Limitations

1. **No persistent mapping learning:** Each import starts fresh
2. **No human review UI:** Low-confidence mappings are not presented for manual correction
3. **No cloud AI fallback:** Only local Ollama is supported
4. **Limited context window:** Large workbooks are truncated for the prompt
5. **No multi-language support:** Headers must be in English

---

## 6. Future Improvements

### 6.1 Mapping Store
**File:** `core/mapping_store.py` (exists, needs integration)

Persist successful mappings so the same header pattern is automatically mapped in future imports.

### 6.2 Confidence-Based Review
- High confidence (>0.9): Auto-accept
- Medium confidence (0.7-0.9): Present for review
- Low confidence (<0.7): Require manual mapping

### 6.3 Data Lineage
Every imported value should store:
- Source file name
- Source sheet name
- Source cell coordinates
- Original header text
- Mapping method (deterministic/AI)
- Confidence score
- Validation status
