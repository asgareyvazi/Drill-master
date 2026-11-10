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
