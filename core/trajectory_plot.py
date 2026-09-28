"""Shared Matplotlib 3D draw boundary; no Qt and no engineering calculations."""
from core.survey_records import plot_series


def draw_trajectory_3d(axes, records):
    series = plot_series(records)
    axes.clear()
    if not series["md"]:
        state = "NO_DATA" if not records else "INSUFFICIENT_DATA"
        axes.text2D(0.05, 0.5, state + ": no complete calculated survey stations", transform=axes.transAxes)
    else:
        state = "READY"
        axes.plot(series["east"], series["north"], series["tvd"], marker="o")
        axes.set(xlabel="East (m)", ylabel="North (m)", zlabel="TVD (m)")
        axes.invert_zaxis()
    return {"status": state, "series": series}
