"""M52 §2.1 - Analysis display payloads off the GUI thread, staged paint.

* ``core.analysis_payloads``: table rows, chart specs, Agg renderings and
  min-max line thinning as plain values (no Qt), built on the snapshot worker.
  Display only: thinning keeps every extreme; KPIs, exports and the cached
  values are untouched.
* UI: the scenarios in ``tests/m52_analysis_child.py`` run the real
  ``AnalysisWidget`` on a temporary FILE database in one isolated subprocess
  (offscreen Qt on Linux, not Windows desktop testing); each is one test here.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from core import analysis_payloads as ap  # noqa: E402

CHILD = HERE / "m52_analysis_child.py"
STDERR_LIMIT = 8 * 1024 * 1024
SCENARIOS = re.findall(r"^@scenario\ndef (\w+)\(", CHILD.read_text(encoding="utf-8"), re.M)


# ---- table rows ------------------------------------------------------------------------------------
def test_npt_rows_format_exactly_as_the_table_items_did():
    entries = [
        {"date": dt.date(2026, 1, 2), "from": dt.time(6, 5), "to": dt.time(7, 30), "hours": 1.4166,
         "category": "NPT-B", "description": "synthetic wait"},
        {"date": "2026-01-03", "from": None, "to": "", "hours": None, "category": "", "description": ""},
    ]
    assert ap.npt_rows(entries) == (
        ("2026-01-02", "06:05", "07:30", "1.42", "NPT-B", "synthetic wait"),
        ("2026-01-03", "", "", "—", "", ""),            # unknown hours: a dash, never 0.00
    )


# ---- display thinning ------------------------------------------------------------------------------
def test_short_lines_are_not_thinned():
    xs, ys = list(range(100)), [float(i % 7) for i in range(100)]
    assert ap.minmax_decimate(xs, ys, 400) == (xs, ys)


def test_thinning_keeps_every_spike_the_ends_and_x_order():
    n = 50_000
    xs = list(range(n))
    ys = [math.sin(i / 500.0) for i in range(n)]
    spikes = {1234: 40.0, 27_777: -35.0, 49_998: 12.0}  # one-sample spikes (NPT peaks)
    for i, v in spikes.items():
        ys[i] = v
    tx, ty = ap.minmax_decimate(xs, ys, 2000)
    assert len(tx) <= 2000 and len(tx) == len(ty)
    assert tx[0] == 0 and tx[-1] == n - 1
    assert tx == sorted(tx)
    for i, v in spikes.items():
        assert (i, v) in set(zip(tx, ty)), i
    assert max(ty) == max(ys) and min(ty) == min(ys)


def test_thinning_keeps_a_gap_and_rejects_mismatched_lengths():
    xs = list(range(10_000))
    ys = [float("nan")] * 5000 + [1.0] * 5000
    tx, ty = ap.minmax_decimate(xs, ys, 400)
    assert any(math.isnan(v) for v in ty) and 1.0 in ty
    with pytest.raises(ValueError):
        ap.minmax_decimate([1, 2], [1.0])


def test_time_depth_lines_draw_only_known_values():
    data = [{"day": 1, "depth": 100.0, "gain": None}, {"day": 2, "depth": None, "gain": 5.0},
            {"day": 3, "depth": 180.0, "gain": 80.0}]
    assert ap.time_depth_lines(data) == ((1, 3), (100.0, 180.0), (2, 3), (5.0, 80.0))


# ---- chart specs -----------------------------------------------------------------------------------
def test_pie_spec_drops_zero_and_unknown_categories():
    assert ap.pie_spec({"NPT-A": 2.0, "NPT-B": 0.0, "NPT-C": None}) == (("NPT-A", 2.0),)
    assert ap.pie_spec({"NPT-A": 0.0}) is None and ap.pie_spec(None) is None


def test_report_bands_close_at_500_m_or_30_days_and_need_one_bore():
    d = dt.date(2026, 1, 1)
    rows = [(d, 0.0, 1), (d + dt.timedelta(days=5), 300.0, 1), (d + dt.timedelta(days=9), 520.0, 1),
            (d + dt.timedelta(days=40), 700.0, 1), (d + dt.timedelta(days=41), None, 1)]
    assert ap.report_milestone_bands(rows) == (["0-520m (calendar days)", "520-700m (calendar days)"], [9, 31])
    assert ap.report_milestone_bands(rows[:2] + [(d, 900.0, 2)]) is None      # two bores: NOT ASSESSED
    assert ap.report_milestone_bands([]) is None


def test_milestones_spec_keeps_unknown_values_and_rejects_empty():
    assert ap.milestones_spec(("sections", ["A", "B"], [1.0, None], [2.0, 3.0])) == (
        ("A", "B"), (1.0, None), (2.0, 3.0))
    assert ap.milestones_spec(("sections", [], [], [])) is None
    assert ap.milestones_spec(("none",)) is None


# ---- Agg rendering (worker thread) -----------------------------------------------------------------
def test_pie_renders_identically_on_a_worker_thread():
    spec = (("NPT-A", 3.0), ("NPT-B", 1.0))
    main = ap.render_pie(spec, (500, 400))
    out = {}
    worker = threading.Thread(target=lambda: out.setdefault("chart", ap.render_pie(spec, (500, 400))))
    worker.start()
    worker.join(60)
    assert main.width == 500 and main.height == 400 and len(main.rgba) == 500 * 400 * 4
    assert out["chart"] == main                   # same pixels, same spec


def test_milestones_render_records_what_was_drawn():
    chart = ap.render_milestones((("17-1/2", "12-1/4"), (4.0, None), ()), (800, 400))
    assert chart.spec == ("milestones", ("17-1/2", "12-1/4"), (4.0, None), ())
    assert (chart.width, chart.height) == (800, 400)


def test_chart_size_never_zero_or_absurd():
    assert ap.chart_size((0, 0)) == ap.MIN_CHART_PX
    assert ap.chart_size(None) == ap.MIN_CHART_PX
    assert ap.chart_size((10_000, 50)) == (ap.MAX_CHART_PX[0], ap.MIN_CHART_PX[1])


def test_save_chart_writes_the_shown_chart(tmp_path):
    chart = ap.render_pie((("NPT-A", 1.0),), (400, 300))
    for suffix, magic in ((".png", b"\x89PNG"), (".pdf", b"%PDF"), (".svg", b"<?xm")):
        target = tmp_path / f"pie{suffix}"
        ap.save_chart(chart, str(target))
        assert target.read_bytes()[:4] == magic, suffix


# ---- one preparation per snapshot ------------------------------------------------------------------
class _Failed(Exception):
    pass


def test_prepare_builds_every_payload_and_skips_read_errors():
    values = {"npt": {"entries": [], "categories": {"NPT-A": 1.0}},
              "milestones": ("sections", ["A"], [1.0], [2.0]),
              "td": [{"day": 1, "depth": 10.0, "gain": None}]}
    out = ap.prepare(values, {"pie_size": (400, 300), "milestones_size": (600, 300)})
    assert set(out) == {"npt:rows", "npt:pie", "milestones:image", "td:lines"}
    assert out["npt:pie"][0] == ("pie", (400, 300))
    errors = {"npt": _Failed("x"), "milestones": _Failed("y"), "td": _Failed("z")}
    assert ap.prepare(errors, {}, failed_type=_Failed) == {}


def test_prepare_reports_a_failure_as_an_error_not_an_empty_chart(monkeypatch):
    def broken(spec, size):
        raise MemoryError("synthetic")
    monkeypatch.setattr(ap, "render_pie", broken)
    out = ap.prepare({"npt": {"entries": [], "categories": {"NPT-A": 1.0}}}, {})
    assert isinstance(out["npt:pie"][1], ap.PrepareError) and out["npt:pie"][1].kind == "MemoryError"
    assert out["npt:rows"][1] == ()


def test_payload_settings_key_changes_with_the_view_size():
    assert ap.settings_key("npt:pie", {"pie_size": (400, 300)}) != ap.settings_key("npt:pie", {"pie_size": (800, 600)})
    assert ap.settings_key("npt:rows", {"pie_size": (1, 1)}) == ap.settings_key("npt:rows", {})


# ---- UI scenarios (isolated subprocess) ------------------------------------------------------------
def _env():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(HERE)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    return env


@pytest.fixture(scope="module")
def ui_results():
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    proc = subprocess.Popen([sys.executable, str(CHILD)], cwd=str(ROOT), env=_env(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            encoding="utf-8", errors="replace")
    err = {"size": 0, "tail": "", "runaway": False}

    def drain_stderr():                 # bounded: keeps only a tail, kills on runaway output
        for chunk in iter(lambda: proc.stderr.read(65536), ""):
            err["size"] += len(chunk)
            err["tail"] = (err["tail"] + chunk)[-4000:]
            if err["size"] > STDERR_LIMIT and not err["runaway"]:
                err["runaway"] = True
                proc.kill()

    out = []
    readers = [threading.Thread(target=drain_stderr, daemon=True),
               threading.Thread(target=lambda: out.append(proc.stdout.read()), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        pytest.fail(f"UI child timed out after 600 s:\n{err['tail']}")
    finally:
        for reader in readers:
            reader.join(10)
        proc.stdout.close()
        proc.stderr.close()
    assert not err["runaway"], f"UI child wrote more than {STDERR_LIMIT} bytes to stderr"
    assert proc.returncode == 0, f"UI child exited with {proc.returncode}:\n{err['tail']}"
    results = {}
    for line in "".join(out).splitlines():
        if line.startswith("M52RESULT "):
            item = json.loads(line[len("M52RESULT "):])
            results[item["name"]] = item
    return results


def test_every_staged_paint_contract_has_a_scenario():
    assert len(SCENARIOS) == 12
    for needed in ("holds_young_collections_only_while_it_runs", "no_payload_on_the_gui_thread", "synchronous_paint_are_identical", "yields_to_the_event_loop",
                   "scope_change_mid_paint", "section_change_mid_paint", "refresh_mid_paint", "update_request_mid_paint",
                   "cleanup_mid_paint", "deselect_clears", "npt_export", "rerenders_after_resize"):
        assert any(needed in name for name in SCENARIOS), needed


@pytest.mark.parametrize("name", SCENARIOS)
def test_m52_analysis_scenario(ui_results, name):
    result = ui_results.get(name)
    assert result is not None, f"scenario {name} did not report (child crashed?)"
    assert result["ok"], result.get("error")
