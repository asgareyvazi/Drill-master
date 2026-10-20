"""The built-in procedure templates survived their extraction from core.database unchanged."""
import hashlib
import json

from core.database import DatabaseManager
from core.default_procedure_templates import default_procedure_templates

# SHA-256 of the canonical JSON of DatabaseManager._get_default_templates() measured
# at ba08ff0, before the data moved out of core/database.py (M43).
PRE_EXTRACTION_SHA256 = "1102885c05c6fed154e1eccaf95933836c0a4e224c9ad0e030c4215058d3ed3a"


def _digest(templates):
    return hashlib.sha256(json.dumps(templates, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def test_templates_are_byte_identical_to_the_pre_extraction_data():
    templates = default_procedure_templates()
    assert len(templates) == 6
    assert _digest(templates) == PRE_EXTRACTION_SHA256


def test_manager_method_still_delegates_and_each_call_returns_a_fresh_list():
    first = DatabaseManager()._get_default_templates()
    second = default_procedure_templates()
    assert first == second
    assert first is not second and first[0] is not second[0]
