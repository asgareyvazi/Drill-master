"""D46: the M122 CPU-load cancel cycles, run in a fresh interpreter.

Not collected in the suite (the name does not match ``test_*.py``);
``test_m122_assistant_worker_lifecycle.test_cancel_under_cpu_load_releases_every_worker`` runs this file
explicitly with ``pytest`` in a subprocess, so no widget left alive by another test module shares its event
loop. The body, assertions and bounds are those of M122 (``_cpu_load_body``).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_m122_assistant_worker_lifecycle import _cpu_load_body, app, world  # noqa: E402,F401


def test_cancel_under_cpu_load_in_a_fresh_interpreter(app, world):  # noqa: F811
    _cpu_load_body(app, world)
