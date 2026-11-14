"""M174: profile-driven aliases for the free-text column of DDR time-log tables.

Contract ``ddr-header-aliases-v1``. Bare words such as "Activity", "Description", "Operation" or "Details"
are too generic for the shared canonical index: they would wrongly map in a mud or BHA table. They are
therefore resolved here, for MinerU and native PDF tables only, under four strict conditions:

* the table is a time log: it has both a ``time_from`` and a ``time_to`` column of the same section
  (``time_log`` or ``time_log_morning``), resolved by an explicit alias;
* no column of the table already maps to that section's ``activity_description``;
* the header matches a listed label exactly after case/space/Arabic-Persian letter normalisation.
  Nothing is fuzzy or partial, so "Activity Code" or "Operation Hours" never match;
* exactly one column matches. Two or more matches are AMBIGUOUS. None of them is mapped, and the operator
  decides by adding an explicit profile alias for one header. That alias takes precedence in the
  normal profile lookup, and saving it creates a new immutable profile version.

A profile can replace the label list with ``table_rules["description_headers"]``; an empty list turns the
rule off. Each decision keeps the original header text, its column number and the table provenance,
including the page and bounding box.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Iterable, Optional, Sequence

CONTRACT = "ddr-header-aliases-v1"
HEADER_RULES_VERSION = 1
RULE_KEY = "description_headers"

DEFAULT_DESCRIPTION_HEADERS: tuple[str, ...] = (
    # English
    "Activity", "Activities", "Description", "Operation", "Operations", "Details",
    "Operation Details", "Operation Description", "Activity Details", "Description of Operations",
    # Persian
    "شرح", "شرح عملیات", "عملیات", "فعالیت", "توضیحات", "جزئیات", "شرح فعالیت",
)

_SECTIONS = ("time_log", "time_log_morning")
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "\u200c": " ", "\u200f": "", "\u200e": ""})


def normalize_header(text: Any) -> str:
    """Return the exact-match key: NFKC, Persian letter forms, lower case, single spaces, no trailing colon."""
    value = unicodedata.normalize("NFKC", str(text or "")).translate(_LETTERS)
    return " ".join(value.strip().rstrip(":：").lower().split())


def description_labels(table_rules: Optional[dict] = None) -> tuple[str, ...]:
    """Return the active label list: the profile's override when present (it may be empty), else the defaults."""
    rules = table_rules or {}
    if RULE_KEY in rules:
        return tuple(str(label) for label in (rules.get(RULE_KEY) or []))
    return DEFAULT_DESCRIPTION_HEADERS


def validate_rule(value: Any) -> list[str]:
    """Return human-readable errors in a profile's ``description_headers`` value."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return [f"Table rule '{RULE_KEY}' must be a list of text values."]
    keys = [normalize_header(item) for item in value]
    errors = [f"Table rule '{RULE_KEY}' has an empty label." for key in keys if not key][:1]
    if len(set(filter(None, keys))) != len([key for key in keys if key]):
        errors.append(f"Table rule '{RULE_KEY}' lists the same label twice.")
    return errors


def time_log_section(fields: Sequence[Optional[str]]) -> Optional[str]:
    """Return the time-log section anchored by explicit from/to columns, else ``None`` (also when mixed)."""
    anchored = [section for section in _SECTIONS
                if f"{section}.time_from" in fields and f"{section}.time_to" in fields]
    return anchored[0] if len(anchored) == 1 else None


def resolve_description_headers(headers: Sequence[Any], fields: Sequence[Optional[str]], *,
                                table_rules: Optional[dict] = None, profile_key: str = "",
                                profile_version: Optional[int] = None) -> tuple[list[Optional[str]], dict]:
    """Return ``(fields, outcome)``. ``fields`` is a copy of the input with at most one new mapping.

    ``outcome["state"]`` is NOT_TIME_LOG, ALREADY_MAPPED, NO_MATCH, MAPPED, AMBIGUOUS or DISABLED.
    """
    fields = list(fields)
    labels = description_labels(table_rules)
    overridden = RULE_KEY in (table_rules or {})
    outcome: dict[str, Any] = {
        "contract": CONTRACT, "rules_version": HEADER_RULES_VERSION,
        "label_source": f"profile {profile_key} v{profile_version}" if overridden else "default list",
        "candidates": [],
    }
    section = time_log_section(fields)
    if section is None:
        return fields, dict(outcome, state="NOT_TIME_LOG")
    target = f"{section}.activity_description"
    outcome["field"] = target
    if target in fields:
        return fields, dict(outcome, state="ALREADY_MAPPED")
    if not labels:
        return fields, dict(outcome, state="DISABLED")
    keys = {normalize_header(label) for label in labels}
    candidates = [{"column": index + 1, "header": str(header)}
                  for index, header in enumerate(headers)
                  if index < len(fields) and fields[index] is None and normalize_header(header) in keys]
    outcome["candidates"] = candidates
    if not candidates:
        return fields, dict(outcome, state="NO_MATCH")
    if len(candidates) > 1:
        names = ", ".join(f"'{c['header']}' (column {c['column']})" for c in candidates)
        return fields, dict(outcome, state="AMBIGUOUS", message=(
            f"Operator decision required: {names} could each be the activity description of this time log. "
            "None was mapped. Add a profile alias for exactly one of these headers."))
    (chosen,) = candidates
    fields[chosen["column"] - 1] = target
    method = (f"profile {profile_key} v{profile_version} description header" if overridden
              else "default description header")
    return fields, dict(outcome, state="MAPPED", column=chosen["column"], header=chosen["header"], method=method)


def describe(outcomes: Iterable[dict]) -> list[str]:
    """Return short lines for review screens."""
    lines = []
    for item in outcomes:
        if item.get("state") == "MAPPED":
            lines.append(f"'{item['header']}' → {item['field']} ({item['method']}, rules v{item['rules_version']})")
        elif item.get("state") == "AMBIGUOUS":
            lines.append(item["message"])
    return lines
