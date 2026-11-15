"""M160: open a user's workbook for reading without a misleading warning, and never modify it.

openpyxl emits ``UserWarning: Data Validation extension is not supported and will be removed`` when a workbook
carries Excel data-validation *extensions* (``x14`` dropdown lists defined on another sheet). It means openpyxl
does not keep those dropdown definitions in its in-memory model - it would drop them **if that model were saved
back**. DrillMaster never saves a user's source workbook (import routes read values only; normalisation writes a
separate ``*_clean.xlsx`` copy), so cell values are imported unchanged and the source file stays untouched.

This helper turns exactly that one warning into a single INFO notice per file and keeps it on the workbook as
``drillmaster_notices`` for diagnostics. Every other warning is re-emitted unchanged.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_VALIDATION_EXTENSION = "Data Validation extension is not supported"
DATA_VALIDATION_NOTICE = ("Excel data-validation dropdown definitions are not read (openpyxl does not support the "
                          "extension); cell values are imported unchanged and the workbook is not modified.")


def load_workbook_readonly_safe(path, **kwargs):
    """``openpyxl.load_workbook`` with the data-validation-extension warning made explicit and harmless."""
    from openpyxl import load_workbook

    notices = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        workbook = load_workbook(path, **kwargs)
    for item in caught:
        if issubclass(item.category, UserWarning) and DATA_VALIDATION_EXTENSION in str(item.message):
            if DATA_VALIDATION_NOTICE not in notices:
                notices.append(DATA_VALIDATION_NOTICE)
            continue
        warnings.warn_explicit(item.message, item.category, item.filename, item.lineno)
    if notices:
        logger.info("%s: %s", Path(str(path)).name, DATA_VALIDATION_NOTICE)
    try:
        workbook.drillmaster_notices = notices
    except AttributeError:            # a read-only workbook class without __dict__: the log line stays the record
        logger.debug("workbook notices not attachable for %s", Path(str(path)).name)
    return workbook


# ---------------------------------------------------------------- M213 generic workbook limits
# A generic (no template) DDR workbook is read cell by cell into memory. These limits refuse a file before it can
# exhaust memory: the size on disk, the uncompressed size of the XLSX zip (a "zip bomb" is small on disk), the number
# of sheets and the used range (rows x columns) of each sheet and of the whole workbook. They are generous for daily
# drilling reports (a DDR workbook with one sheet per day and a few thousand rows stays far below them) and a report
# profile may only TIGHTEN them (``table_rules["excel_limits"]``), never raise them.
LIMITS_RULE_KEY = "excel_limits"


class WorkbookLimitError(ValueError):
    """The workbook exceeds a generic import limit; nothing was read."""


@dataclass(frozen=True)
class WorkbookLimits:
    max_bytes: int = 50 * 1024 * 1024
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    max_sheets: int = 1000
    max_cells_per_sheet: int = 5_000_000
    max_cells_total: int = 30_000_000
    source: str = "built-in"

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in LIMIT_FIELDS} | {"source": self.source}


HARD_LIMITS = WorkbookLimits()
LIMIT_FIELDS = ("max_bytes", "max_uncompressed_bytes", "max_sheets", "max_cells_per_sheet", "max_cells_total")


def validate_limits_rule(rule) -> list:
    """Errors of a profile's ``excel_limits`` rule (positive integers, never above the built-in limit)."""
    if not isinstance(rule, dict):
        return ["Table rule 'excel_limits' must be a mapping of limit name to a whole number."]
    errors = []
    for name, value in rule.items():
        if name not in LIMIT_FIELDS:
            errors.append(f"Unknown Excel limit '{name}' (use {', '.join(LIMIT_FIELDS)}).")
        elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"Excel limit '{name}' must be a positive whole number.")
        elif value > getattr(HARD_LIMITS, name):
            errors.append(f"Excel limit '{name}' = {value} is above the built-in limit {getattr(HARD_LIMITS, name)}; "
                          "a profile may only tighten it.")
    return errors


def limits_from_profile(profile) -> WorkbookLimits:
    """The built-in limits, tightened by the profile's valid ``excel_limits`` rule (an invalid rule is ignored)."""
    rule = (getattr(profile, "table_rules", None) or {}).get(LIMITS_RULE_KEY) if profile is not None else None
    if not rule or validate_limits_rule(rule):
        return HARD_LIMITS
    values = {name: min(int(rule.get(name, getattr(HARD_LIMITS, name))), getattr(HARD_LIMITS, name))
              for name in LIMIT_FIELDS}
    return WorkbookLimits(**values, source=f"profile {profile.key} v{profile.version}")


def check_workbook_file(path, limits: WorkbookLimits = HARD_LIMITS) -> dict:
    """Refuse a file whose size or uncompressed XLSX content exceeds ``limits`` - before openpyxl reads it."""
    import zipfile

    size = Path(str(path)).stat().st_size
    if size > limits.max_bytes:
        raise WorkbookLimitError(f"{Path(str(path)).name}: {size} bytes exceeds the Excel import limit of "
                                 f"{limits.max_bytes} bytes ({limits.source}); nothing was read.")
    uncompressed = None
    if zipfile.is_zipfile(str(path)):
        with zipfile.ZipFile(str(path)) as archive:
            uncompressed = sum(info.file_size for info in archive.infolist())
        if uncompressed > limits.max_uncompressed_bytes:
            raise WorkbookLimitError(f"{Path(str(path)).name}: {uncompressed} bytes uncompressed exceeds the Excel "
                                     f"import limit of {limits.max_uncompressed_bytes} bytes ({limits.source}); "
                                     "nothing was read.")
    return {"bytes": size, "uncompressed_bytes": uncompressed}


def check_workbook_shape(workbook, limits: WorkbookLimits = HARD_LIMITS) -> dict:
    """Refuse a loaded workbook with too many sheets or too large a used range (before any cell is cached)."""
    sheets = list(workbook.worksheets)
    if len(sheets) > limits.max_sheets:
        raise WorkbookLimitError(f"{len(sheets)} sheets exceed the Excel import limit of {limits.max_sheets} "
                                 f"({limits.source}).")
    total = 0
    for sheet in sheets:
        cells = int(sheet.max_row or 0) * int(sheet.max_column or 0)
        if cells > limits.max_cells_per_sheet:
            raise WorkbookLimitError(f"Sheet '{sheet.title}' uses {sheet.max_row} rows x {sheet.max_column} columns "
                                     f"({cells} cells), above the limit of {limits.max_cells_per_sheet} "
                                     f"({limits.source}).")
        total += cells
    if total > limits.max_cells_total:
        raise WorkbookLimitError(f"The workbook uses {total} cells, above the limit of {limits.max_cells_total} "
                                 f"({limits.source}).")
    return {"sheets": len(sheets), "cells": total}
