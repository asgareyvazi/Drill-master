"""M178-M180: named, revisioned Well Trajectory Viewer views replace the legacy W6 "Trajectory Plot" tab.

SYNTHETIC SQLite databases (fresh and upgraded) and real offscreen Qt. Independent references: the M72 planar
J-profile stations (MD 500 m vertical, then 15 / 30 deg at 135 deg) and the exact foot (0.3048 m), so 500 m is
1640.419948 ft and 3 deg/30 m is 3.048 deg/100 ft.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3

import pytest
from sqlalchemy import text

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import survey_revisions as sr  # noqa: E402
from core import trajectory_views as tv  # noqa: E402
from core.authorization import AuthorizationError  # noqa: E402
from tests.test_database_migration_acceptance import _build_old_schema  # noqa: E402
from tests.test_m70_integrity import NEW_TABLES, _open, _seed  # noqa: E402
from tests.test_m72_surveys_solver import J_STATIONS  # noqa: E402

DEEPER = {"md": 950.0, "inc": 45.0, "azi": 135.0}


@pytest.fixture(params=["fresh", "upgraded"])
def env(request, tmp_path, monkeypatch):
    path = tmp_path / f"{request.param}.sqlite"
    if request.param == "upgraded":
        _build_old_schema(path, 5)
        with sqlite3.connect(path) as connection:
            for table in NEW_TABLES + ("survey_revisions", "trajectory_view_revisions"):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    well, _bore = ids["A"]
    assert manager.save_survey_points([dict(s, well_id=well) for s in J_STATIONS])
    yield manager, path, ids
    manager.close()


def _count(path, sql="SELECT COUNT(*) FROM trajectory_view_revisions", *args):
    with sqlite3.connect(path) as connection:
        return connection.execute(sql, args).fetchone()[0]


def _report(manager, well, day=1):
    with manager.session_scope() as session:
        session.execute(text("INSERT INTO daily_reports(well_id, report_date, report_number) "
                             "VALUES (:w, :d, :n)"), {"w": well, "d": f"2026-01-{day:02d}", "n": day})
        return session.execute(text("SELECT MAX(id) FROM daily_reports")).scalar()


# ---- save / reopen ----------------------------------------------------------------------------------------------
def test_a_saved_view_is_bound_to_well_wellbore_and_source_and_reopens_from_its_snapshot(env):
    manager, path, ids = env
    well, bore = ids["A"]
    view = tv.save_view(manager, well, "  Build   check ", {"unit": "ft"}, wellbore_id=bore, note="first")
    assert (view["name"], view["revision"], view["action"], view["status"]) == ("Build check", 1, "CREATE", "ACTIVE")
    assert (view["well_id"], view["wellbore_id"], view["source_kind"]) == (well, bore, tv.SOURCE_POINTS)
    assert view["integrity"] == "VERIFIED" and view["station_count"] == 4
    assert view["settings"]["unit"] == "ft" and view["method"] == sr.SURVEY_METHOD
    # The snapshot is exactly what the canonical composer returns (canonical metres, no new formula).
    assert [s["md"] for s in view["stations"]] == [0.0, 500.0, 650.0, 800.0]
    assert view["stations"][1]["tvd"] == pytest.approx(500.0)
    reopened = tv.get_view(manager, view["id"])
    assert reopened["stations"] == view["stations"] and tv.drift(manager, reopened).state == tv.MATCH
    assert _count(path, "SELECT COUNT(*) FROM audit_logs WHERE action='trajectory_view_create'") == 1


@pytest.mark.parametrize("name, kwargs, message", [
    ("", {}, "needs a name"),
    ("x" * 201, {}, "longer than 200"),
    ("ok", {"settings": {"unit": "yd"}}, "display unit"),
    ("ok", {"settings": {"vs_mode": "user", "vs_azimuth": float("nan")}}, "custom VS azimuth"),
    ("ok", {"settings": {"vs_mode": "user", "vs_azimuth": True}}, "custom VS azimuth"),
    ("ok", {"settings": {"colour": "red"}}, "Unknown view setting"),
    ("ok", {"settings": {"scope": "report"}}, "needs a selected daily report"),
])
def test_invalid_views_are_refused_and_nothing_is_saved(env, name, kwargs, message):
    manager, path, ids = env
    with pytest.raises(tv.TrajectoryViewError, match=message):
        tv.save_view(manager, ids["A"][0], name, kwargs.get("settings"))
    assert _count(path) == 0


def test_foreign_wellbore_duplicate_name_and_an_undrawable_scope_are_refused(env):
    manager, path, ids = env
    well, bore = ids["A"]
    with pytest.raises(tv.TrajectoryViewError, match="wellbore does not belong"):
        tv.save_view(manager, well, "V", wellbore_id=ids["B"][1])
    with pytest.raises(tv.TrajectoryViewError, match="no drawable trajectory"):
        tv.save_view(manager, ids["B"][0], "V")                     # well B has no stations
    tv.save_view(manager, well, "V", wellbore_id=bore)
    with pytest.raises(tv.TrajectoryViewError, match="already has an active view named"):
        tv.save_view(manager, well, "v")                             # case-insensitive
    assert _count(path) == 1
    assert tv.save_view(manager, well, "W")["revision"] == 1                    # another name is accepted


def test_a_report_scope_is_bound_to_its_report_and_a_report_of_another_well_is_refused(env):
    manager, _path, ids = env
    well, other = ids["A"][0], ids["B"][0]
    report = _report(manager, well)
    foreign = _report(manager, other, 2)
    assert manager.save_survey_points([dict(s, well_id=well, report_id=report) for s in J_STATIONS[:3]])
    assert manager.save_survey_points([dict(s, well_id=other, report_id=foreign) for s in J_STATIONS])
    view = tv.save_view(manager, well, "Day 1", {"scope": "report"}, report_id=report)
    assert view["source_report_id"] == report and view["station_count"] == 3
    assert all(s["report_ids"] == [report] for s in view["stations"])
    with pytest.raises(tv.TrajectoryViewError, match="another well"):
        tv.save_view(manager, well, "Foreign", {"scope": "report"}, report_id=foreign)


def test_a_view_bound_to_a_survey_revision_ignores_later_working_survey_edits(env):
    manager, _path, ids = env
    well = ids["A"][0]
    revision = sr.save_revision(manager, well, J_STATIONS, depth_datum="RKB", azimuth_reference="true")
    view = tv.save_view(manager, well, "Rev view", survey_revision_id=revision["id"])
    assert view["source_kind"] == tv.SOURCE_REVISION and view["survey_revision_id"] == revision["id"]
    assert manager.save_survey_points([dict(DEEPER, well_id=well)])
    assert tv.drift(manager, tv.get_view(manager, view["id"])).state == tv.MATCH
    other = sr.save_revision(manager, ids["B"][0], J_STATIONS, depth_datum="RKB", azimuth_reference="true")
    with pytest.raises(tv.TrajectoryViewError, match="does not belong to this well"):
        tv.save_view(manager, well, "Foreign rev", survey_revision_id=other["id"])
    with pytest.raises(tv.TrajectoryViewError, match="whole-well source"):
        tv.save_view(manager, well, "Rev report", {"scope": "report"}, survey_revision_id=revision["id"])


def test_a_survey_revision_that_fails_its_hash_is_not_used_for_a_view(env):
    manager, path, ids = env
    well = ids["A"][0]
    revision = sr.save_revision(manager, well, J_STATIONS, depth_datum="RKB", azimuth_reference="true")
    with sqlite3.connect(path) as connection:     # file-level access can drop the guard (documented limit)
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' "
                                          "AND name LIKE 'trg_survey_revision_immutable%'").fetchall():
            connection.execute(f"DROP TRIGGER {name}")
        connection.execute("UPDATE survey_revisions SET stations_json = REPLACE(stations_json, '500.0', '501.0') "
                           "WHERE id = ?", (revision["id"],))
    assert sr.get_revision(manager, revision["id"])["integrity"] == "HASH MISMATCH"
    with pytest.raises(tv.TrajectoryViewError, match="failed its integrity check"):
        tv.save_view(manager, well, "Tampered rev", survey_revision_id=revision["id"])
    assert _count(path) == 0


# ---- drift ------------------------------------------------------------------------------------------------------
def test_reopen_reports_different_and_not_reproducible_and_never_rewrites_the_snapshot(env):
    manager, path, ids = env
    well = ids["A"][0]
    view = tv.save_view(manager, well, "Drift")
    assert manager.save_survey_points([dict(DEEPER, well_id=well)])
    state = tv.drift(manager, tv.get_view(manager, view["id"]))
    assert state.state == tv.DIFFERENT and state.current_stations_sha256 != view["stations_sha256"]
    assert tv.get_view(manager, view["id"])["stations"] == view["stations"]       # snapshot unchanged
    with manager.session_scope() as session:
        session.execute(text("DELETE FROM survey_points WHERE well_id = :w"), {"w": well})
    assert tv.drift(manager, tv.get_view(manager, view["id"])).state == tv.NOT_REPRODUCIBLE
    assert _count(path) == 1


def test_a_tampered_snapshot_is_unreadable_or_a_hash_mismatch_and_is_not_drawn_compared_or_exported(env):
    manager, path, ids = env
    view = tv.save_view(manager, ids["A"][0], "Tamper")
    with sqlite3.connect(path) as connection:     # file-level access can drop the guard (documented limit)
        connection.execute("DROP TRIGGER trg_trajectory_view_immutable_v1")
        connection.execute("UPDATE trajectory_view_revisions SET stations_json = REPLACE(stations_json, "
                           "'500.0', '501.0') WHERE id = ?", (view["id"],))
    tampered = tv.get_view(manager, view["id"])
    assert tampered["integrity"] == "HASH MISMATCH" and tv.drift(manager, tampered).state == tv.UNREADABLE
    with pytest.raises(tv.TrajectoryViewError, match="HASH MISMATCH"):
        tv.export_rows(tampered, "m")
    with pytest.raises(tv.TrajectoryViewError, match="HASH MISMATCH"):
        tv.compare(view, tampered)
    with pytest.raises(tv.TrajectoryViewError, match="not copied"):
        tv.clone_view(manager, view["id"], "Copy")
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE trajectory_view_revisions SET stations_json = '{not json' WHERE id = ?",
                           (view["id"],))
    assert tv.get_view(manager, view["id"])["integrity"] == tv.UNREADABLE


# ---- revise / clone / archive / restore -------------------------------------------------------------------------
def test_revise_clone_archive_restore_are_new_revisions_with_optimistic_concurrency(env):
    manager, path, ids = env
    well = ids["A"][0]
    first = tv.save_view(manager, well, "Plan")
    second = tv.revise_view(manager, first["view_key"], expected_revision=1,
                            settings={"vs_mode": "user", "vs_azimuth": 90.0}, note="VS east")
    assert (second["revision"], second["parent_id"], second["action"]) == (2, first["id"], "REVISE")
    with pytest.raises(tv.StaleViewError, match="now at revision 2"):
        tv.revise_view(manager, first["view_key"], expected_revision=1)
    with pytest.raises(tv.StaleViewError):
        tv.archive_view(manager, first["view_key"], expected_revision=1, reason="old")
    with pytest.raises(tv.TrajectoryViewError, match="needs a reason"):
        tv.archive_view(manager, first["view_key"], expected_revision=2, reason="  ")
    archived = tv.archive_view(manager, first["view_key"], expected_revision=2, reason="superseded")
    assert archived["status"] == "ARCHIVED" and archived["stations_sha256"] == second["stations_sha256"]
    with pytest.raises(tv.TrajectoryViewError, match="restore it before revising"):
        tv.revise_view(manager, first["view_key"], expected_revision=3)
    assert tv.list_views(manager, well) == []
    assert [v["revision"] for v in tv.list_views(manager, well, include_archived=True)] == [3]
    clone = tv.clone_view(manager, archived["id"], "Plan")      # the name is free again: the old view is archived
    assert (clone["revision"], clone["action"], clone["parent_id"]) == (1, "CLONE", archived["id"])
    assert clone["stations_sha256"] == archived["stations_sha256"] and clone["view_key"] != first["view_key"]
    with pytest.raises(tv.TrajectoryViewError, match="already has an active view"):
        tv.restore_view(manager, first["view_key"], expected_revision=3, reason="back")
    tv.archive_view(manager, clone["view_key"], expected_revision=1, reason="clash")
    restored = tv.restore_view(manager, first["view_key"], expected_revision=3, reason="back")
    assert (restored["status"], restored["action"], restored["revision"]) == ("ACTIVE", "RESTORE", 4)
    assert [h["action"] for h in tv.history(manager, first["view_key"])] == ["RESTORE", "ARCHIVE", "REVISE",
                                                                             "CREATE"]
    assert tv.get_view(manager, first["id"])["settings"]["vs_mode"] == "closure"        # revision 1 unchanged
    actions = dict(sqlite3.connect(path).execute(
        "SELECT action, COUNT(*) FROM audit_logs WHERE action LIKE 'trajectory_view_%' GROUP BY action").fetchall())
    assert actions == {"trajectory_view_create": 1, "trajectory_view_revise": 1, "trajectory_view_archive": 2,
                       "trajectory_view_clone": 1, "trajectory_view_restore": 1}


def test_a_revision_saved_concurrently_with_the_same_number_is_refused_not_overwritten(env, monkeypatch):
    manager, path, ids = env
    first = tv.save_view(manager, ids["A"][0], "Race")
    real = tv._require_head
    calls = []

    def stale_once(session, key, expected):           # another writer inserts revision 2 between check and insert
        head = real(session, key, expected)
        if not calls:
            calls.append(1)
            with sqlite3.connect(path) as connection:
                columns = [r[1] for r in connection.execute("PRAGMA table_info(trajectory_view_revisions)")]
                values = connection.execute("SELECT * FROM trajectory_view_revisions WHERE id = ?",
                                            (first["id"],)).fetchone()
                row = dict(zip(columns, values), id=None, revision=2, note="other writer")
                connection.execute(f"INSERT INTO trajectory_view_revisions({', '.join(columns)}) VALUES "
                                   f"({', '.join('?' for _ in columns)})", [row[c] for c in columns])
        return head

    monkeypatch.setattr(tv, "_require_head", stale_once)
    with pytest.raises(tv.StaleViewError, match="same time|now at revision"):
        tv.revise_view(manager, first["view_key"], expected_revision=1)
    assert _count(path) == 2 and _count(path, "SELECT note FROM trajectory_view_revisions WHERE revision = 2") \
        == "other writer"


# ---- storage immutability and authorization ---------------------------------------------------------------------
@pytest.mark.parametrize("column, value", [("name", "'renamed'"), ("stations_json", "'[]'"), ("status", "'ARCHIVED'"),
                                           ("revision", "9"), ("source_sha256", "'x'"), ("note", "'edited'")])
def test_a_saved_view_revision_is_immutable_for_every_writer(env, column, value):
    manager, path, ids = env
    view = tv.save_view(manager, ids["A"][0], "Frozen")
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute(f"UPDATE trajectory_view_revisions SET {column} = {value} WHERE id = ?", (view["id"],))
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="deleted only with its owner"):
            connection.execute("DELETE FROM trajectory_view_revisions WHERE id = ?", (view["id"],))
        with pytest.raises(sqlite3.DatabaseError, match="cannot be replaced"):
            connection.execute("INSERT OR REPLACE INTO trajectory_view_revisions SELECT * FROM "
                               "trajectory_view_revisions WHERE id = ?", (view["id"],))
    assert tv.get_view(manager, view["id"])["integrity"] == "VERIFIED"


def test_views_leave_only_with_their_well_and_a_deleted_wellbore_only_unlinks(env):
    manager, path, ids = env
    well, bore = ids["A"]
    view = tv.save_view(manager, well, "Cascade", wellbore_id=bore)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM wellbores WHERE id = ?", (bore,))
    assert tv.get_view(manager, view["id"])["wellbore_id"] is None
    assert manager.delete_hierarchy_entity("well", well)
    assert _count(path) == 0


def test_a_viewer_principal_cannot_save_a_view(tmp_path, monkeypatch):
    from tests.test_data_layer_authorization import Principal
    path = tmp_path / "authz.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    assert manager.save_survey_points([dict(s, well_id=ids["A"][0]) for s in J_STATIONS])
    users = dict(sqlite3.connect(path).execute("SELECT username, id FROM users").fetchall())
    manager.enforce_authorization(Principal("viewer", users["admin"], "viewer"))
    with pytest.raises((AuthorizationError, PermissionError)):
        tv.save_view(manager, ids["A"][0], "Denied")
    manager.close()
    assert _count(path) == 0


# ---- compare (no interpolation) ---------------------------------------------------------------------------------
def test_compare_pairs_stations_by_md_and_lists_unmatched_stations_without_interpolation(env):
    manager, _path, ids = env
    well = ids["A"][0]
    first = tv.save_view(manager, well, "Cmp")
    assert manager.save_survey_points([dict(DEEPER, well_id=well)])
    second = tv.revise_view(manager, first["view_key"], expected_revision=1, settings={"unit": "ft"})
    result = tv.compare(first, second)
    assert [p["md"] for p in result["paired"]] == [0.0, 500.0, 650.0, 800.0]
    assert result["only_in_older"] == [] and result["only_in_newer"] == [950.0]
    assert result["settings_changed"] == ["unit"] and not result["identical"]
    assert result["max_abs_delta"]["tvd"] == pytest.approx(0.0, abs=1e-9)
    assert "no interpolation" in result["method"]
    with pytest.raises(tv.TrajectoryViewError, match="same well"):
        tv.compare(first, dict(second, well_id=ids["B"][0]))
    gap = tv.compare(first, dict(second, stations=[s for s in second["stations"] if s["md"] != 650.0]))
    assert [p["md"] for p in gap["paired"]] == [0.0, 500.0, 800.0]          # 650 is never paired with 800
    assert gap["only_in_older"] == [650.0] and gap["only_in_newer"] == [950.0]


# ---- export (M179) ----------------------------------------------------------------------------------------------
def _legacy_csv(path, plots):
    """The retired W6 ``TrajectoryPlotTab.export_plot_data`` CSV branch, verbatim (git 43b1115)."""
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Type', 'Index', 'X', 'Y', 'Z'])
        if '2d_plan' in plots:
            for i, (e, n) in enumerate(zip(plots['2d_plan'].get('east', []), plots['2d_plan'].get('north', []))):
                writer.writerow(['2D_Plan', i, e, n, 0])
        if '2d_side' in plots:
            for i, (h, t) in enumerate(zip(plots['2d_side'].get('hd', []), plots['2d_side'].get('tvd', []))):
                writer.writerow(['2D_Side', i, h, t, 0])


def test_export_has_units_and_provenance_and_differs_from_the_legacy_zero_z_output(env, tmp_path):
    manager, _path, ids = env
    view = tv.save_view(manager, ids["A"][0], "Export", wellbore_id=ids["A"][1])
    out = tmp_path / "view.csv"
    assert tv.export_csv(str(out), view, "ft", well_label="SYN-A") == 4
    lines = list(csv.reader(out.open(encoding="utf-8")))
    header = {row[0]: row[1:] for row in lines if row and row[0] and not row[0].startswith("MD")}
    assert header["View"] == ["Export"] and header["Well"] == ["SYN-A"] and header["Revision"][0] == "1"
    assert header["Units"] == ["lengths ft; angles deg; DLS deg/100ft"]
    assert header["Snapshot SHA-256"] == [view["stations_sha256"]]
    columns = next(row for row in lines if row and row[0].startswith("MD"))
    assert columns == tv.export_columns("ft") and columns[3] == "TVD (ft)" and columns[7] == "DLS (deg/100ft)"
    body = lines[lines.index(columns) + 1:]
    assert len(body) == 4                                            # stored stations only: no interpolation
    assert body[1][0] == "1640.419948" and body[1][3] == "1640.419948"
    assert float(body[2][7]) == pytest.approx(3.048)                 # 3 deg/30 m == 3.048 deg/100 ft exactly
    assert float(body[3][3]) == pytest.approx(view["stations"][3]["tvd"] / 0.3048)
    # Independent minimum-curvature value of the M72 J-profile at MD 800 m: 786.478898 m = 2580.311344 ft.
    assert body[3][0] == "2624.671916" and float(body[3][3]) == pytest.approx(2580.311344, abs=1e-6)
    # The legacy export of the same stations wrote Z = 0 on every row and no unit anywhere.
    legacy = tmp_path / "legacy.csv"
    stations = view["stations"]
    _legacy_csv(legacy, {"2d_plan": {"east": [s["east"] for s in stations], "north": [s["north"] for s in stations]},
                         "2d_side": {"hd": [s["hd"] for s in stations], "tvd": [s["tvd"] for s in stations]}})
    legacy_rows = list(csv.reader(legacy.open(encoding="utf-8")))
    assert legacy_rows[0] == ["Type", "Index", "X", "Y", "Z"] and {r[4] for r in legacy_rows[1:]} == {"0"}
    assert not any("ft" in c or "(m)" in c for c in legacy_rows[0])
    tvd_new = [float(r[3]) * 0.3048 for r in body]
    assert tvd_new[3] == pytest.approx(stations[3]["tvd"]) and tvd_new[3] > 0      # never the constant 0


def test_a_value_the_snapshot_does_not_hold_is_exported_empty_never_zero(env, tmp_path):
    manager, _path, ids = env
    view = tv.save_view(manager, ids["A"][0], "Gaps")
    holed = dict(view, stations=[dict(view["stations"][0], dls=None, tvd=None)] + view["stations"][1:])
    rows = tv.export_rows(holed, "m")
    assert rows[0][3] is None and rows[0][7] is None and rows[0][0] == 0.0
    out = tmp_path / "gaps.json"
    tv.export_json(str(out), holed, "m")
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract"] == tv.EXPORT_CONTRACT
    assert payload["stations"][0]["TVD (m)"] is None and payload["stations"][0]["DLS (deg/30m)"] is None
    csv_out = tmp_path / "gaps.csv"
    tv.export_csv(str(csv_out), holed, "m")
    first = [r for r in csv.reader(csv_out.open(encoding="utf-8")) if r and r[0] == "0.000000"][0]
    assert first[3] == "" and first[7] == ""
    with pytest.raises(tv.TrajectoryViewError, match="export unit"):
        tv.export_rows(view, "yd")


# ---- legacy read-compat adapter (M180) --------------------------------------------------------------------------
def test_legacy_trajectory_plot_rows_stay_and_are_listed_read_only_per_well(env):
    manager, path, ids = env
    well, other = ids["A"][0], ids["B"][0]
    report, foreign = _report(manager, well), _report(manager, other, 2)
    plots = {"2d_plan": {"east": [0.0, 1.5], "north": [0.0, -1.5]}, "2d_side": {"hd": [0, 2.1], "tvd": [0, 499]}}
    good = manager.save_trajectory_plot({"report_id": report, "plot_type": "2d_plan", "title": "Trajectory Plot X",
                                         "plot_data": json.dumps(plots)})
    bad = manager.save_trajectory_plot({"report_id": report, "plot_type": "2d_plan", "plot_data": "{broken"})
    odd = manager.save_trajectory_plot({"report_id": report, "plot_type": "2d_plan", "plot_data": "[1, 2]"})
    manager.save_trajectory_plot({"report_id": foreign, "plot_type": "2d_plan", "plot_data": json.dumps(plots)})
    before = sqlite3.connect(path).execute("SELECT * FROM trajectory_plots ORDER BY id").fetchall()
    listed = tv.legacy_plots(manager, well)
    assert [p["id"] for p in listed] == [good, bad, odd]
    assert listed[0]["readable"] and listed[0]["points"] == 2 and listed[0]["plot_data"] == plots
    assert not listed[1]["readable"] and listed[1]["points"] is None
    assert not listed[2]["readable"] and listed[2]["plot_data"] is None     # valid JSON, but not a plot payload
    assert all("read-only" in p["label"] and "Z = 0" in p["label"] for p in listed)
    assert sqlite3.connect(path).execute("SELECT * FROM trajectory_plots ORDER BY id").fetchall() == before


# ---- the viewer (real Qt + DB) ----------------------------------------------------------------------------------
@pytest.fixture
def viewer(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "ui.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    assert manager.save_survey_points([dict(s, well_id=ids["A"][0]) for s in J_STATIONS])
    from tabs.trajectory_viewer import TrajectoryViewerTab
    widget = TrajectoryViewerTab(manager)
    widget.set_context(ids["A"][0])
    yield widget, manager, ids, tmp_path / "ui.sqlite"
    widget.compare_panel.wait_until_idle()
    widget.shutdown(5000)
    widget.deleteLater()
    app.processEvents()
    manager.close()


def _answers(monkeypatch, *values):
    from PySide6.QtWidgets import QInputDialog
    queue = list(values)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (queue.pop(0), True)))
    return queue


def test_save_open_revise_compare_archive_restore_and_export_from_the_viewer(viewer, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    widget, manager, ids, path = viewer
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a[2])))
    panel = widget.saved_views
    tabs = [widget.view_tabs.tabText(i) for i in range(widget.view_tabs.count())]
    assert "Saved views" in tabs
    widget.unit_combo.setCurrentIndex(widget.unit_combo.findData("ft"))
    _answers(monkeypatch, "Morning review", "synthetic")
    saved = panel.save_current()
    assert saved is not None and saved["settings"]["unit"] == "ft" and "Saved view 'Morning review'" in \
        panel.status.text()
    assert panel.table.rowCount() == 1 and panel.selected()["id"] == saved["id"]
    # A duplicate name fails visibly: NOT SAVED and no new row.
    _answers(monkeypatch, "morning REVIEW", "")
    assert panel.save_current() is None and panel.status.text().startswith("NOT SAVED")
    assert "NOT SAVED" in warnings[-1] and _count(path) == 1
    # The surveys change; reopening shows the stored snapshot and says DIFFERENT.
    assert manager.save_survey_points([dict(DEEPER, well_id=ids["A"][0])])
    widget.unit_combo.setCurrentIndex(widget.unit_combo.findData("m"))
    widget.reload()
    assert widget.table.rowCount() == 5
    panel.select_view(saved["view_key"])
    record, state = panel.open_selected()
    assert state.state == tv.DIFFERENT and widget.saved_view[0]["id"] == saved["id"]
    assert widget.table.rowCount() == 4 and widget.unit == "ft"                 # snapshot and its settings
    assert "SAVED VIEW 'Morning review' revision 1" in widget.banner.text() and "DIFFERENT" in widget.banner.text()
    widget.reload()                                                              # back to the live data
    assert widget.saved_view is None and widget.table.rowCount() == 5
    # Revise with the current data, compare with revision 1.
    panel.select_view(saved["view_key"])
    _answers(monkeypatch, "added 950 m station")
    revised = panel.revise_selected()
    assert revised["revision"] == 2 and revised["station_count"] == 5
    panel.select_view(saved["view_key"])
    result = panel.compare_selected()
    assert result["only_in_newer"] == [950.0] and "only in newer: 1" in panel.details.toPlainText()
    # Export of the selected revision in the viewer unit.
    out = tmp_path / "export.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out), "")))
    assert panel.export_selected("csv") == 5 and "Exported 5 stored station(s)" in panel.status.text()
    assert widget.unit == "ft" and "MD (ft)" in out.read_text(encoding="utf-8")   # the viewer's display unit
    out_json = tmp_path / "export.json"                                          # the button path (bound method)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_json), "")))
    panel.export_json_btn.click()
    assert out_json.exists() and "Exported 5 stored station(s)" in panel.status.text()
    # Archive (reason required) then restore.
    _answers(monkeypatch, "")
    assert panel.archive_selected() is None and "NOT SAVED" in panel.status.text()
    _answers(monkeypatch, "replaced by the new plan")
    archived = panel.archive_selected()
    assert archived["status"] == "ARCHIVED" and panel.archived_check.isChecked()
    assert not panel.revise_btn.isEnabled() and panel.restore_btn.isEnabled()
    _answers(monkeypatch, "still needed")
    assert panel.restore_selected()["status"] == "ACTIVE"
    assert [panel.history_list.item(i).text().split(" · ")[1] for i in range(panel.history_list.count())] == \
        ["RESTORE", "ARCHIVE", "REVISE", "CREATE"]


def test_a_stale_panel_cannot_revise_a_view_another_window_changed(viewer, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    widget, manager, ids, path = viewer
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    panel = widget.saved_views
    _answers(monkeypatch, "Shared", "")
    saved = panel.save_current()
    tv.revise_view(manager, saved["view_key"], expected_revision=1, note="other window")
    panel.select_view(saved["view_key"])                    # the panel still lists revision 1
    _answers(monkeypatch, "my change")
    assert panel.revise_selected() is None
    assert "NOT SAVED" in panel.status.text() and "now at revision 2" in panel.status.text()
    assert _count(path) == 2


def test_the_legacy_trajectory_plot_tab_is_retired_and_its_rows_are_shown_read_only(viewer):
    import tabs.w6_Trajectory_Widget as w6
    from tabs.w6_Trajectory_Widget import TrajectoryWidget
    widget, manager, ids, path = viewer
    assert not hasattr(w6, "TrajectoryPlotTab") and not hasattr(w6, "TrajectoryCalculationManager")
    report = _report(manager, ids["A"][0])
    manager.save_trajectory_plot({"report_id": report, "plot_type": "2d_plan", "title": "Old plot",
                                  "plot_data": json.dumps({"2d_plan": {"east": [0, 1], "north": [0, 1]}})})
    widget.saved_views.refresh()
    assert widget.saved_views.legacy_list.count() == 1
    assert "Old plot" in widget.saved_views.legacy_list.item(0).text()
    assert "read-only" in widget.saved_views.legacy_list.item(0).text()
    w = TrajectoryWidget(manager)
    try:
        names = [w.tab_widget.tabText(i) for i in range(w.tab_widget.count())]
        assert names == ["Well Trajectory Viewer", "Trip Sheet", "Survey Data"]
        assert not hasattr(w, "plot_tab") and not hasattr(w, "calculation_manager")
    finally:
        w.cleanup()
        w.deleteLater()
