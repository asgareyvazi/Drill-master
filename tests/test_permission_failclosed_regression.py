"""W5 equipment save: the permission control must fail CLOSED.

The gate at the top of ``EquipmentWidget.save_all_data`` protects a mutation path
(``save_all(steps)`` -> ``db.save_equipment_records`` / ``db.save_inventory_items``).
Its contract is stated in the comment at the site ("Read-only roles must never mutate
equipment/inventory ... Backend persistence is the authority") and is implemented
fail-closed everywhere else in the repository:

* ``core.permissions.require_permission`` - on exception it logs and sets
  ``allowed = False``, then returns without calling the guarded function;
* ``tabs/w16_Cost_Management.save_data`` - on exception it returns a
  ``SaveOutcome(..., status="SYSTEM_ERROR")`` without writing.

These tests drive the real ``save_all_data`` (no re-implementation of the gate) with a
stub persistence layer and assert the invariant that matters for a safety control:

    permission that cannot be evaluated  ->  falsy result, nothing persisted, user told

The test is mutation-sensitive: with the original ``except Exception: pass`` the call
reaches ``save_all(steps)`` and the persistence recorder is non-empty, so it fails.
"""
from __future__ import annotations

import pytest

import core.permissions as permissions_module
import core.save_outcome as save_outcome_module
from tabs.w5_Equipment_Widget import EquipmentWidget


class _Perms:
    """Stand-in for the permissions singleton, with a controllable failure mode."""

    def __init__(self, *, viewer=False, allowed=True, raises=None, user_id=7):
        self._viewer = viewer
        self._allowed = allowed
        self._raises = raises
        self.user_id = user_id

    def is_viewer(self):
        if self._raises is not None:
            raise self._raises
        return self._viewer

    def has_permission(self, _name):
        if self._raises is not None:
            raise self._raises
        return self._allowed


class _Table:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def get_table_data(self):
        return list(self._rows)


class _Persistence:
    """Records every attempt to persist, so 'nothing was written' is observable."""

    def __init__(self):
        self.writes = []

    def save_equipment_records(self, *args, **kwargs):
        self.writes.append(("equipment", args))
        return True

    def save_inventory_items(self, *args, **kwargs):
        self.writes.append(("inventory", args))
        return True

    def get_daily_report_by_id(self, _report_id):
        return None


class _Outcome:
    def summary(self):
        return "stub outcome"

    def __bool__(self):
        return True


@pytest.fixture()
def persistence():
    return _Persistence()


@pytest.fixture()
def save_all_calls(monkeypatch):
    """Intercept the mutation entry point itself."""
    calls = []

    def _recorder(steps):
        calls.append(steps)
        return _Outcome()

    monkeypatch.setattr(save_outcome_module, "save_all", _recorder, raising=True)
    return calls


def _make_widget(persistence_layer):
    """A real EquipmentWidget instance with the UI and persistence stubbed out."""
    widget = object.__new__(EquipmentWidget)
    widget.db = persistence_layer
    widget.current_well = 1
    widget.current_report_id = None
    widget.rig_tab = _Table()
    widget.pipe_tab = _Table()
    widget.solid_tab = _Table()
    widget.inventory_tab = _Table()
    widget.messages = []
    widget.show_message = lambda *a, **k: widget.messages.append(a)
    widget.show_success = lambda *a, **k: widget.messages.append(a)
    widget.show_error = lambda *a, **k: widget.messages.append(a)
    return widget


def test_unevaluable_permission_control_blocks_save(monkeypatch, persistence, save_all_calls):
    """The control raising must not authorise the write (the fail-open defect)."""
    monkeypatch.setattr(permissions_module, "permissions",
                        _Perms(raises=RuntimeError("permission backend unavailable")))
    widget = _make_widget(persistence)

    result = widget.save_all_data()

    assert not result, "a save whose permission control failed must not report success"
    assert save_all_calls == [], "the persistence entry point must never be reached"
    assert persistence.writes == [], "nothing may be written to the database"
    assert widget.messages, "the refusal must be reported to the user"
    assert "permission" in " ".join(str(m) for m in widget.messages).lower()


def test_denied_permission_blocks_save(monkeypatch, persistence, save_all_calls):
    """A control that evaluates to 'denied' blocks the same path."""
    monkeypatch.setattr(permissions_module, "permissions", _Perms(allowed=False))
    widget = _make_widget(persistence)

    result = widget.save_all_data()

    assert not result
    assert save_all_calls == []
    assert persistence.writes == []
    assert widget.messages


def test_viewer_role_blocks_save(monkeypatch, persistence, save_all_calls):
    """Read-only roles never mutate, whatever the widget state is."""
    monkeypatch.setattr(permissions_module, "permissions", _Perms(viewer=True))
    widget = _make_widget(persistence)

    result = widget.save_all_data()

    assert not result
    assert save_all_calls == []
    assert persistence.writes == []
    assert widget.messages


def test_allowed_save_still_reaches_persistence(monkeypatch, persistence, save_all_calls):
    """Control case: with the permission granted the path is NOT blocked.

    Without this, the three tests above would also pass if save_all_data simply
    refused every save.
    """
    monkeypatch.setattr(permissions_module, "permissions", _Perms(allowed=True))
    widget = _make_widget(persistence)

    result = widget.save_all_data()

    assert save_all_calls, "the save path must be reachable when permission is granted"
    assert result
