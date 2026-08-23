"""Low-overhead timing and diagnostics for import performance."""
from contextlib import contextmanager
from time import perf_counter

class ImportProfiler:
    def __init__(self):
        self.timings = {}
    @contextmanager
    def measure(self, name):
        started = perf_counter()
        try:
            yield
        finally:
            self.timings[name] = round(perf_counter() - started, 3)
    def total(self): return round(sum(self.timings.values()), 3)
    def as_dict(self):
        result = dict(self.timings)
        result["total"] = self.total()
        return result
