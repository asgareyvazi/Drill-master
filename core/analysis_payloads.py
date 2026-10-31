"""Immutable display payloads of the Analysis page (M52 §2.1).

The Analysis snapshot worker reads every value off the GUI thread (M51).  What
remained on the GUI thread was turning those values into widgets: thousands of
table items, two Matplotlib figures built and laid out on every paint, and
string formatting per row.  This module does that preparation as plain Python
(no Qt object is created or touched here), so it can run on the snapshot
worker; the GUI thread only applies the finished payload.

Contract
- Payloads are immutable (tuples, frozen dataclasses, ``bytes``) and derived
  only from the values the page already paints plus explicit ``settings``
  (pixel sizes, options) captured on the GUI thread when the cycle starts.
- Display only.  Nothing here changes a KPI, an export, the cache of values or
  the database.  ``minmax_decimate`` thins a plotted line for drawing and keeps
  every local extreme (spikes, NPT peaks); the full series stays in
  ``chart_data`` for exports and tables.
- Matplotlib rendering uses a ``Figure`` owned by the calling thread and the
  Agg canvas only (no pyplot registry, no Qt canvas).  Matplotlib keys its font
  cache by thread id for exactly this use.  The result is an RGBA buffer.
- The drawing code of the NPT pie and the milestones chart is the code the page
  used before M52 (same artists, colours, labels and layout), moved here.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

PAYLOAD_VERSION = 1
DECIMATE_ABOVE = 4000            # points per plotted line before min-max thinning applies
MIN_CHART_PX = (320, 240)        # a hidden or not yet laid-out view still gets a legible image
MAX_CHART_PX = (4096, 4096)


@dataclass(frozen=True)
class ChartImage:
    """An Agg rendering: ``rgba`` is ``width * height * 4`` bytes, row-major."""
    width: int
    height: int
    rgba: bytes
    spec: tuple                  # what was drawn (compared for golden parity and reuse)


def chart_size(size) -> tuple[int, int]:
    """A drawable pixel size for a view of ``size`` (w, h); never 0 or absurd."""
    try:
        w, h = int(size[0]), int(size[1])
    except (TypeError, ValueError, IndexError):
        w, h = MIN_CHART_PX
    return (min(max(w, MIN_CHART_PX[0]), MAX_CHART_PX[0]), min(max(h, MIN_CHART_PX[1]), MAX_CHART_PX[1]))


# ---- NPT table ---------------------------------------------------------------------------------------
def _clock(value) -> str:
    return value.strftime("%H:%M") if value and hasattr(value, "strftime") else str(value or "")


def npt_rows(entries) -> tuple:
    """The NPT table cells, formatted exactly as the page formatted its table items."""
    return tuple((str(e["date"]), _clock(e.get("from")), _clock(e.get("to")),
                  "—" if e["hours"] is None else f"{e['hours']:.2f}",
                  e["category"], e["description"]) for e in entries)


# ---- NPT pie -----------------------------------------------------------------------------------------
def pie_spec(categories):
    """``(("code", hours), ...)`` of the positive categories, or None (nothing to draw)."""
    positive = tuple((str(k), float(v)) for k, v in (categories or {}).items() if v and v > 0)
    return positive or None


def _agg_figure(size):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    width, height = chart_size(size)
    fig = Figure(figsize=(width / 100.0, height / 100.0), dpi=100, facecolor='#1e1e1e')
    return fig, FigureCanvasAgg(fig)


def pie_figure(spec, size):
    import matplotlib

    fig, canvas = _agg_figure(size)
    ax = fig.add_subplot(111)
    ax.set_facecolor('#1e1e1e')
    labels = [label for label, _ in spec]
    colors = matplotlib.colormaps["Set3"](range(len(labels)))
    _wedges, _texts, percents = ax.pie(
        [value for _, value in spec], labels=labels, autopct='%1.1f%%', colors=colors,
        textprops={'color': 'white', 'fontsize': 8},
        wedgeprops={'edgecolor': 'white', 'linewidth': 0.5})
    for text in percents:          # inside pastel (Set3) wedges: dark text
        text.set_color('#1e1e1e')
    ax.set_title('NPT hours by code (share of NPT)', color='white', fontsize=12)
    fig.tight_layout()
    return fig, canvas


def render_pie(spec, size) -> ChartImage:
    _fig, canvas = pie_figure(spec, size)
    return _rendered(canvas, ("pie", spec))


# ---- milestones --------------------------------------------------------------------------------------
def report_milestone_bands(rows):
    """Depth-band elapsed calendar days from ``(date, depth, bore)`` rows (whole well).

    ``None`` when the reports cannot establish one depth progression (no rows,
    or several / unknown bores) - NOT ASSESSED.  Bands close every >= 500 m or
    >= 30 calendar days; never report count or rig time.  PLAN is unknown here.
    """
    rows = list(rows or ())
    if not rows or len({bore for _d, _depth, bore in rows}) != 1:
        return None
    labels, fact = [], []
    last_depth = band_start = None
    for report_date, depth, _bore in rows:
        if depth is None:
            continue
        if last_depth is None:
            last_depth, band_start = depth, report_date
            continue
        elapsed = (report_date - band_start).days
        if depth - last_depth >= 500 or elapsed >= 30:
            labels.append(f"{last_depth:.0f}-{depth:.0f}m (calendar days)")
            fact.append(elapsed)
            last_depth, band_start = depth, report_date
    return labels, fact


def milestones_spec(data):
    """``(sections, fact_days, plan_days)`` to draw, or None (NOT ASSESSED) for a milestones value."""
    if not isinstance(data, tuple) or not data:
        return None
    if data[0] == "sections":
        sections, fact, plan = tuple(data[1]), tuple(data[2]), tuple(data[3])
    elif data[0] == "reports":
        bands = report_milestone_bands(data[1])
        if bands is None:
            return None
        sections, fact, plan = tuple(bands[0]), tuple(bands[1]), ()
    else:
        return None
    if not sections:
        return None
    return sections, fact, plan


def milestones_figure(spec, size):
    import numpy as np

    sections, fact_raw, plan_raw = spec
    fact_days = [v if v is not None else float("nan") for v in fact_raw]
    plan_days = [v if v is not None else float("nan") for v in plan_raw]
    fig, canvas = _agg_figure(size)
    ax = fig.add_subplot(111)
    ax.set_facecolor('#1e1e1e')
    x = np.arange(len(sections))
    # When PLAN is unknown (empty series) draw FACT full-width and omit the
    # PLAN bars entirely rather than plotting a fabricated plan.
    has_plan = bool(plan_days) and len(plan_days) == len(sections)
    width_bar = 0.35 if has_plan else 0.6
    fact_x = (x - width_bar / 2) if has_plan else x
    bars1 = ax.bar(fact_x, fact_days, width_bar, label='FACT', color='#3498db', edgecolor='white', linewidth=0.5)
    bars2 = ax.bar(x + width_bar / 2, plan_days, width_bar, label='PLAN', color='#e74c3c', edgecolor='white',
                   linewidth=0.5) if has_plan else []
    ax.set_xlabel('Section', color='white', fontsize=11)
    ax.set_ylabel('Days', color='white', fontsize=11)
    ax.set_title('Milestones - FACT vs PLAN (unknown values omitted)', color='white', fontsize=14,
                 fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(sections, rotation=45, ha='right', color='white')
    ax.tick_params(axis='y', colors='white')
    ax.legend(loc='upper right', facecolor='#2c3e50', edgecolor='white', labelcolor='white')
    ax.grid(True, alpha=0.3, color='white')
    for bar in list(bars1) + list(bars2):           # value labels; unknown (NaN) bars get none
        bar_height = bar.get_height()
        if not np.isfinite(bar_height):
            continue
        ax.annotate(f'{bar_height:.1f}', xy=(bar.get_x() + bar.get_width() / 2, bar_height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', color='white',
                    fontsize=8)
    fig.tight_layout()
    return fig, canvas


def render_milestones(spec, size) -> ChartImage:
    sections, fact_raw, plan_raw = spec
    _fig, canvas = milestones_figure(spec, size)
    return _rendered(canvas, ("milestones", tuple(sections), tuple(fact_raw), tuple(plan_raw)))


def save_chart(chart: ChartImage, filename: str) -> None:
    """Write the chart a view shows to ``filename`` (PNG, PDF, SVG... by suffix), drawn again
    from its spec at the shown size - the exported chart is the painted one."""
    kind = chart.spec[0]
    if kind == "pie":
        fig, _canvas = pie_figure(chart.spec[1], (chart.width, chart.height))
    elif kind == "milestones":
        fig, _canvas = milestones_figure(chart.spec[1:], (chart.width, chart.height))
    else:
        raise ValueError(f"unknown chart kind {kind!r}")
    fig.savefig(filename, facecolor=fig.get_facecolor())


def _rendered(canvas, spec) -> ChartImage:
    canvas.draw()
    buffer = canvas.buffer_rgba()
    height, width = buffer.shape[0], buffer.shape[1]
    return ChartImage(width, height, bytes(buffer), spec)


# ---- plotted lines -----------------------------------------------------------------------------------
def minmax_decimate(xs, ys, max_points: int = DECIMATE_ABOVE):
    """Thin a line for DRAWING only: per bucket keep the first, min, max and last point.

    Every local extreme survives (a one-sample spike is a bucket min or max), x
    order is kept, and lines at or below ``max_points`` are returned unchanged.
    NaN values are dropped from min/max selection but a bucket of only NaN keeps
    its first point, so a gap stays a gap.
    """
    xs, ys = list(xs), list(ys)
    if len(xs) != len(ys):
        raise ValueError("x and y lengths differ")
    if len(xs) <= max_points or max_points < 8:
        return xs, ys
    buckets = max_points // 4
    size = len(xs) / buckets
    keep = set()
    for b in range(buckets):
        lo, hi = int(b * size), int((b + 1) * size) if b < buckets - 1 else len(xs)
        if lo >= hi:
            continue
        keep.update((lo, hi - 1))
        finite = [i for i in range(lo, hi) if ys[i] is not None and not math.isnan(ys[i])]
        if finite:
            keep.add(min(finite, key=lambda i: ys[i]))
            keep.add(max(finite, key=lambda i: ys[i]))
    order = sorted(keep)
    return [xs[i] for i in order], [ys[i] for i in order]


def time_depth_lines(data):
    """``(depth_days, depth_vals, gain_days, gain_vals)`` of KNOWN values, thinned for drawing."""
    depth = [(d["day"], d["depth"]) for d in data if d["depth"] is not None]
    gain = [(d["day"], d["gain"]) for d in data if d["gain"] is not None]
    depth_days, depth_vals = minmax_decimate([d for d, _ in depth], [v for _, v in depth])
    gain_days, gain_vals = minmax_decimate([d for d, _ in gain], [v for _, v in gain])
    return tuple(depth_days), tuple(depth_vals), tuple(gain_days), tuple(gain_vals)


# ---- one call per snapshot ---------------------------------------------------------------------------
def settings_key(kind: str, settings: dict):
    """The part of ``settings`` a payload ``kind`` depends on (cache dimension)."""
    if kind == "npt:pie":
        return ("pie", chart_size(settings.get("pie_size")))
    if kind == "milestones:image":
        return ("milestones", chart_size(settings.get("milestones_size")))
    return (kind,)


def prepare(values: dict, settings: dict, failed_type=Exception) -> dict:
    """``{kind: (settings_key, payload)}`` for the values of one snapshot (worker thread).

    A value that is a read error (``failed_type``) or missing gets no payload;
    the page then shows the error state as before.  A preparation failure is
    reported per kind as ``(settings_key, exception type name)`` wrapped in
    ``PrepareError`` - never as an empty chart.
    """
    out = {}

    def put(kind, build):
        key = settings_key(kind, settings)
        try:
            out[kind] = (key, build())
        except Exception as exc:              # the GUI shows "chart not drawn: <type>"
            out[kind] = (key, PrepareError(type(exc).__name__))

    npt = values.get("npt")
    if isinstance(npt, dict):
        put("npt:rows", lambda: npt_rows(npt["entries"]))
        spec = pie_spec(npt.get("categories"))
        if spec is not None:
            put("npt:pie", lambda: render_pie(spec, settings.get("pie_size")))
    milestones = values.get("milestones")
    if milestones is not None and not isinstance(milestones, failed_type):
        spec_m = milestones_spec(milestones)
        if spec_m is not None:
            put("milestones:image", lambda: render_milestones(spec_m, settings.get("milestones_size")))
    td = values.get("td")
    if isinstance(td, list) and td:
        put("td:lines", lambda: time_depth_lines(td))
    return out


@dataclass(frozen=True)
class PrepareError:
    kind: str
