"""Local edit snapshots. No Qt, database comparisons, or global signal patches.

A baseline is established at editor creation/load, never at first Save All.
Readers must describe persisted input, including raw invalid text, not selection
or derived displays. The existing coordinator owns outcomes and partial success.
"""

from copy import deepcopy
from functools import wraps
from core.save_outcome import SaveIssue, SaveOutcome, save_all


class EditSection:
    def __init__(self, name, reader, writer, read_only=lambda: False, validate=lambda: None, context=lambda: None):
        self.name, self.reader, self.writer, self.read_only = name, reader, writer, read_only
        self.validate = validate
        self.context = context
        self.checkpoint()

    def checkpoint(self):
        self.load_error = ""
        self.baseline = deepcopy(self.reader())
        self.loaded_context = deepcopy(self.context())

    @property
    def dirty(self):
        return not self.read_only() and self.reader() != self.baseline

    def save(self):
        if self.read_only():
            return SaveOutcome()
        if self.load_error or self.context() != self.loaded_context:
            return SaveOutcome(
                issues=[
                    SaveIssue(
                        self.name,
                        "This section has not loaded the selected context successfully; no saver was invoked.",
                        status="REVIEW_REQUIRED",
                        code="CONTEXT_BLOCKED",
                        corrective_action="Reload this section and resolve its load error before saving.",
                    )
                ]
            )
        if not self.dirty:
            return SaveOutcome()
        self.validate()
        outcome = save_all([(self.name, self.writer)])
        if outcome.saved and outcome.status in ("SUCCESS", "REVIEW_REQUIRED"):
            self.checkpoint()
        return outcome


def editor_loaded(*names):
    """Explicit load boundary; exceptions/False never acknowledge an editor."""

    def decorate(method):
        @wraps(method)
        def load(self, *args, **kwargs):
            try:
                value = method(self, *args, **kwargs)
            except Exception as exc:
                for section in getattr(self, "_tracked_edit_sections", ()):
                    if not names or section.name in names:
                        section.load_error = str(exc)
                raise
            if value is False:
                for section in getattr(self, "_tracked_edit_sections", ()):
                    if not names or section.name in names:
                        section.load_error = "Load did not succeed"
            else:
                for section in getattr(self, "_tracked_edit_sections", ()):
                    if not names or section.name in names:
                        section.checkpoint()
            return value

        return load

    return decorate


def editor_saved(*names):
    """A direct local successful save shares the global snapshot boundary."""

    def decorate(method):
        @wraps(method)
        def save(self, *args, **kwargs):
            self.last_save_outcome = None
            value = method(self, *args, **kwargs)
            detail = value if isinstance(value, SaveOutcome) else getattr(self, "last_save_outcome", None)
            confirmed = value is True or type(value) is int and value > 0
            if isinstance(detail, SaveOutcome):
                confirmed = detail.saved > 0 and detail.status in ("SUCCESS", "REVIEW_REQUIRED")
            if confirmed:
                for section in getattr(self, "_tracked_edit_sections", ()):
                    if not names or section.name in names:
                        section.checkpoint()
            return value

        return save

    return decorate


def reset_form_edit_tracking(owner, fields):
    """Track explicit scalar edits, including entering zero into a NULL display.

    Qt signals are connected at this declared form boundary, not patched globally.
    Programmatic loading completes before this reset; source/display stay separate.
    """
    owner._form_touched = set()
    connected = getattr(owner, "_form_connected", set())
    for key, widget in fields:
        widget.setProperty("explicitly_edited", False)
        if key in connected:
            continue
        line = widget.lineEdit() if callable(getattr(widget, "lineEdit", None)) else None
        signal = getattr(line, "textEdited", None)
        if signal is not None:

            def touched(_text, key=key, widget=widget):
                owner._form_touched.add(key)
                widget.setProperty("explicitly_edited", True)

            signal.connect(touched)
            connected.add(key)
    owner._form_connected = connected
