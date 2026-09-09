"""Preservation policy for the historical name -> component-list JSON schema.

Current list-based editors cannot round-trip configuration identities. No
migration or normalization is performed here: retain the original document.
"""

import json


class LegacyBHAReadOnlyError(NotImplementedError):
    pass


def is_legacy_bha(value):
    if isinstance(value, str):
        value = json.loads(value)
    return isinstance(value, dict) and bool(value)


def require_editable_bha(value):
    if is_legacy_bha(value):
        raise LegacyBHAReadOnlyError(
            "Legacy named BHA configurations are read-only. Select and inspect "
            "each configuration or export the report archive. Replacement, rename "
            "and deletion require an explicit lossless migration, not this editor."
        )


def protect_bha_record(record):
    if getattr(record, "__tablename__", None) == "bha_reports":
        require_editable_bha(record.bha_data_json)


def protect_bha_insert(session, model, values):
    """A generic insert must not hide a protected record behind a newer row."""
    if getattr(model, "__tablename__", None) != "bha_reports":
        return
    query = session.query(model)
    if values.get("report_id") is not None:
        query = query.filter(model.report_id == values["report_id"])
    else:
        query = query.filter(model.well_id == values.get("well_id"), model.bha_name == values.get("bha_name"))
    for existing in query.all():
        protect_bha_record(existing)
