"""Qt workers for expensive Import/AI/PDF operations."""
from PySide6.QtCore import QThread, Signal
import traceback

class FunctionWorker(QThread):
    """Run a callable off the UI thread and report result/error."""
    result_ready = Signal(object)
    failed = Signal(str)
    finished_ok = Signal()

    def __init__(self, function, *args, parent=None, **kwargs):
        super().__init__(parent)
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.result_ready.emit(self.function(*self.args, **self.kwargs))
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(f"{exc}\n{traceback.format_exc()}")
