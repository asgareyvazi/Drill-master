# Optional AI mapping boundary

**Audit date:** 2026-09-06

AI is advisory only. It is not a second import architecture, does not replace
`ExcelIntelligence`, does not call MinerU, and never writes SQLite.

## Runtime position

```text
Excel common IR -> deterministic canonical mapping -> unresolved fields only
                                               -> optional AIImportMapper
                                               -> schema/type/confidence checks
                                               -> ReviewItem (REVIEW)
                                               -> user confirmation -> atomic save
```

`SmartTemplateDialog._merge_ai_fallback()` is a legacy/manual UI helper. The
universal import dialog does not invoke Smart Template for an automatic
fallback. The shared canonical review/save boundary remains mandatory.

## Configuration

| Setting | Environment variable | Actual behavior |
| --- | --- | --- |
| Enable | `DRILLMASTER_AI_IMPORT` | disabled unless explicitly enabled |
| Model | `DRILLMASTER_AI_MODEL` | selected local model; no model is bundled |
| Ollama URL | `DRILLMASTER_OLLAMA_URL` | local endpoint, default `http://127.0.0.1:11434` |
| Timeout | `DRILLMASTER_AI_TIMEOUT` | bounded request; failure is review/unavailable |

Capability checks distinguish disabled, service unavailable, model missing,
invalid response, timeout, and worker error. No cloud fallback is assumed.

## Proposal contract

A proposal must identify a canonical field, source sheet/row/column when known,
the original value, a proposed value, and a confidence between 0 and 1. The
field must exist in `FIELD_SPECS`; ambiguous or incomplete proposals are not
accepted. Missing source coordinates remain `None`, not fabricated coordinates.
Every AI proposal is low-authority and remains `REVIEW` until a user confirms
it.

## Deterministic authority

The authoritative path is contextual deterministic mapping:

1. template preferred cell and structural evidence;
2. contextual canonical alias/label lookup;
3. typed `normalize_for_field` and field bounds;
4. explicit `UnitManager` conversion only when a source unit is present;
5. optional AI only for unresolved fields;
6. review, then atomic persistence.

The 523 alias entries are not globally unique: 37 normalized alias keys are
shared by multiple fields. AI must not resolve these by string alone.

## Failure and security rules

AI failure never blocks a deterministic import and never creates defaults or
zeros. Prompt context is bounded and excludes credentials. Requests use the
configured local endpoint; callers must approve any data transfer. The model
output is treated as untrusted text and validated against the canonical schema.

## Review/export

AI source, confidence, proposed/original/normalized values, mapping method,
validation state and user decision are represented in `ReviewItem`. The Qt
preview supports mapping/value/unit editing; edits are synchronized to the
serialized row and applied only after explicit confirmation. There is no claim
that AI has been tested against the user's Windows runtime or Python 3.12.
