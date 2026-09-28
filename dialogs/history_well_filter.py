"""Shared, minimal well-scoping helper for calculation-history dialogs.

The six engineering-calculation history dialogs (Casing, Cement, MSE, Mud
Volume, Torque & Drag, Well Control Kill Sheet) each list persisted runs via
``repo.all()``. Those lists are global — every well's runs are mixed together —
which is confusing and error-prone when an engineer opens history for a
specific well (mission §13/§24: well-scoped history / isolation).

This helper is deliberately NOT a generic dialog framework. It only:

* filters an already-loaded list of saved runs by ``well_id`` (in Python, using
  the ``well_id`` each record already carries — no repo/schema change), and
* builds a small "This well only / All wells" toggle the dialog can drop into
  its layout.

Each dialog keeps its own table columns, detail rendering and verification.
When no ``well_id`` is supplied the behaviour is unchanged (shows everything),
so existing callers and tests are unaffected.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import QCheckBox


def filter_saved_by_well(saved: List, well_id: Optional[int],
                         this_well_only: bool) -> List:
    """Return the subset of ``saved`` attributed to ``well_id``.

    * ``well_id is None``  -> no active well context, return everything.
    * ``this_well_only`` False -> user asked for all wells, return everything.
    * otherwise keep only runs whose ``well_id`` equals the active well.
    """
    if well_id is None or not this_well_only:
        return list(saved)
    return [s for s in saved if getattr(s, "well_id", None) == well_id]


def make_scope_checkbox(well_label: Optional[str]) -> QCheckBox:
    """Checkbox that scopes the list to the current well (checked by default).

    Returns a checkbox that is only meaningful when a well is active; callers
    hide it when there is no current well.
    """
    text = "Show this well only"
    if well_label:
        text = f"Show this well only ({well_label})"
    box = QCheckBox(text)
    box.setChecked(True)
    box.setToolTip(
        "When checked, only calculations saved against the current well are "
        "listed. Uncheck to browse saved calculations across all wells."
    )
    return box
