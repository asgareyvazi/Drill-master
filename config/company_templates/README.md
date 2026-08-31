# Company mapping templates

Add a JSON file here for each source company. **Do not add per-company Python.**

Required keys:

- `company` — lookup key (case-insensitive)
- `field_map` — source label → canonical field path
- `activity_map` — source activity code → `{canonical_code, canonical_description, confidence}`
- `sheet_map` — optional source sheet name → canonical sheet

The importer and `CompanyMappingService` load these files. Existing DrillMaster tabs consume the canonical result.
