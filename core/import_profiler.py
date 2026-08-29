"""Import Profiler - measures actual bottlenecks as per spec.

Spec requires measuring:
- Excel parsing time
- workbook inspection time
- region detection
- parameter extraction
- serialization
- LLM calls
- prompt size
- number of LLM calls
- database writes

Avoid sending unnecessary Excel content to AI.
Use caching, batch requests, confidence-based AI escalation.
"""

import time
from typing import Dict, List, Any
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class TimingEntry:
    name: str
    duration_ms: float
    detail: str = ""


class ImportProfiler:
    """Professional profiler for import pipeline."""

    def __init__(self):
        self.timings: List[TimingEntry] = []
        self._start_times: Dict[str, float] = {}
        self.llm_calls: List[Dict[str, Any]] = []
        self.prompt_sizes: List[int] = []

    def start(self, name: str):
        self._start_times[name] = time.time()

    def end(self, name: str, detail: str = ""):
        start = self._start_times.pop(name, None)
        if start is None:
            return
        duration = (time.time() - start) * 1000
        self.timings.append(TimingEntry(name, round(duration, 2), detail))
        logger.debug(f"Profiler {name}: {duration:.1f}ms {detail}")

    def measure(self, name: str, detail: str = ""):
        """Context manager for measuring."""
        return _MeasureContext(self, name, detail)

    def record_llm_call(self, model: str, prompt_size: int, response_size: int, duration_ms: float, proposals: int = 0):
        """Record LLM call metrics."""
        self.llm_calls.append(
            {
                "model": model,
                "prompt_size": prompt_size,
                "response_size": response_size,
                "duration_ms": round(duration_ms, 2),
                "proposals": proposals,
            }
        )
        self.prompt_sizes.append(prompt_size)

    def total(self) -> float:
        return sum(t.duration_ms for t in self.timings)

    def as_dict(self) -> Dict[str, Any]:
        total = self.total()
        result = {
            "total_ms": round(total, 2),
            "total": round(total, 2),
            "timings": [t.__dict__ for t in self.timings],
            "llm_calls": self.llm_calls,
            "llm_call_count": len(self.llm_calls),
            "avg_prompt_size": round(sum(self.prompt_sizes) / len(self.prompt_sizes), 1) if self.prompt_sizes else 0,
            "max_prompt_size": max(self.prompt_sizes, default=0),
            "bottleneck": max(self.timings, key=lambda x: x.duration_ms).__dict__ if self.timings else None,
            "recommendations": self._recommendations(),
        }
        # Backward compat: include timing names as keys
        for t in self.timings:
            result[t.name] = t.duration_ms
            result[f"{t.name}_detail"] = t.detail
        return result

    def _recommendations(self) -> List[str]:
        recs = []
        total_llm_time = sum(c["duration_ms"] for c in self.llm_calls)
        total_time = sum(t.duration_ms for t in self.timings)

        if total_llm_time > total_time * 0.5 and total_time > 0:
            recs.append(f"LLM calls take {total_llm_time/total_time*100:.0f}% of total time - consider confidence-based escalation and caching")

        for t in self.timings:
            if "workbook_load" in t.name and t.duration_ms > 5000:
                recs.append(f"Workbook load {t.duration_ms:.0f}ms - large file, consider streaming or limiting scan rows")
            if "ai_request" in t.name and t.duration_ms > 10000:
                recs.append(f"AI request {t.duration_ms:.0f}ms - check Ollama availability and model size")

        if not recs:
            recs.append("No major bottlenecks detected - performance OK")

        return recs


class _MeasureContext:
    def __init__(self, profiler: ImportProfiler, name: str, detail: str = ""):
        self.profiler = profiler
        self.name = name
        self.detail = detail

    def __enter__(self):
        self.profiler.start(self.name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.end(self.name, self.detail)
