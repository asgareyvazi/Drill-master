"""D59 / residual R2: '.partial' folders that outlive a build, and the audited package that was deleted.

Defect (reproduced at 74c81d6): ``finalize_package`` commits the audit record and only then renames the folder;
when that rename failed (a folder held open on Windows, a name that appeared meanwhile) the panel called
``discard_package`` - deleting a package the audit log records - and said "The unaudited folder was removed".

A '.partial' folder also outlives a process killed while writing (no ``finally`` runs) or killed between the
audit commit and the rename. The two kills are simulated by their end states: a build that is never finalized,
and a finalize whose rename does not happen. The audit log alone decides what may be done with such a folder.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QMessageBox  # noqa: E402

from core import well_package as wp  # noqa: E402
from core.context_jobs import CANCELLED  # noqa: E402
from tests.test_m123_mse_lineage import _raw  # noqa: E402
from tests import test_m135_well_package as m135  # noqa: E402

app, env = m135.app, m135.env               # the M135 fixtures (synthetic well SYN-A with two wellbores)
_audits, _request = m135._audits, m135._request

_REAL_RENAME = os.rename


def _rename_fails(monkeypatch):
    def failing(src, dst, *args, **kwargs):
        if str(src).endswith(wp.PARTIAL_SUFFIX):
            raise PermissionError(13, "folder in use")
        return _REAL_RENAME(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "rename", failing)


def _actions(env, action):
    return _raw(env["path"], "SELECT details FROM audit_logs WHERE action=?", action)


def _audited_not_renamed(env, monkeypatch, name="pkg"):
    """End state of a process killed after the audit commit and before the rename."""
    result = wp.build_package(env["manager"], _request(env, name))
    _rename_fails(monkeypatch)
    with pytest.raises(wp.PackageAuditedNotRenamed) as caught:
        wp.finalize_package(env["manager"], result)
    monkeypatch.setattr(os, "rename", _REAL_RENAME)
    assert caught.value.partial_dir == result.partial_dir and os.path.isdir(result.partial_dir)
    return result


def _panel(env):
    from tabs import w11_Export
    tab = w11_Export.ExportWidget(db_manager=env["manager"])
    panel = tab.package_panel
    tab.on_well_changed(env["well"], {"name": "SYN-A"})
    assert panel.wait()
    return tab, panel


# ---- the defect, through the real panel ------------------------------------------------------------------------
def test_a_rename_failure_after_the_audit_keeps_the_audited_package_and_offers_the_rename(app, env, monkeypatch):
    _rename_fails(monkeypatch)
    tab, panel = _panel(env)
    try:
        assert panel.build_into(str(env["out"])) is not None and panel.wait()
        left = os.listdir(env["out"])
        assert len(_audits(env)) == 1 and len(left) == 1 and left[0].endswith(wp.PARTIAL_SUFFIX)
        assert panel.final_dir is None
        assert panel.status.text().startswith("AUDITED — NOT RENAMED: ") and "was kept" in panel.status.text()
        assert "unaudited folder was removed" not in panel.status.text()
        assert [f.state for f in panel.stale] == [wp.STALE_AUDITED]
        assert panel.recover_stale_btn.isEnabled() and not panel.remove_stale_btn.isEnabled()
        monkeypatch.setattr(os, "rename", _REAL_RENAME)            # the folder is no longer held open
        panel.recover_stale_btn.click()
        assert panel.final_dir and os.path.isdir(panel.final_dir) and not panel.final_dir.endswith(wp.PARTIAL_SUFFIX)
        assert wp.verify_package(panel.final_dir, env["manager"]).ok
        assert len(_audits(env)) == 1 and len(_actions(env, wp.AUDIT_STALE_RENAMED)) == 1
        assert panel.stale == [] and not panel.recover_stale_btn.isEnabled()
    finally:
        tab.cleanup()
        tab.deleteLater()


def test_discard_refuses_a_folder_whose_manifest_is_audited(env, monkeypatch):
    result = _audited_not_renamed(env, monkeypatch)
    with pytest.raises(wp.PackageError, match="never removed"):
        wp.discard_package(result, env["manager"])
    assert os.path.isdir(result.partial_dir)


def test_a_build_error_before_the_audit_still_removes_its_folder(app, env, monkeypatch):
    """The pre-audit path is unchanged: nothing was recorded, so the folder is an interrupted build."""
    real = wp.finalize_package

    def manifest_changed(db, result):
        with open(os.path.join(result.partial_dir, wp.MANIFEST), "ab") as handle:
            handle.write(b" ")
        return real(db, result)
    monkeypatch.setattr(wp, "finalize_package", manifest_changed)
    tab, panel = _panel(env)
    try:
        assert panel.build_into(str(env["out"])) is not None and panel.wait()
        assert os.listdir(env["out"]) == [] and _audits(env) == []
        assert panel.status.text().endswith("The unaudited folder was removed.")
    finally:
        tab.cleanup()
        tab.deleteLater()


def test_the_cancel_message_no_longer_says_a_partial_folder_is_never_audited(app, env):
    tab, panel = _panel(env)
    try:
        panel._job_state(CANCELLED, "Cancelled.")
        assert "never audited" not in panel.status.text() and "Stale folders" in panel.status.text()
    finally:
        tab.cleanup()
        tab.deleteLater()


# ---- classification ----------------------------------------------------------------------------------------------
def test_a_build_killed_before_finalize_is_unaudited_and_removed_with_an_audit_record(app, env, monkeypatch):
    seconds = iter(range(60))                       # distinct generation times: distinct manifests
    monkeypatch.setattr(wp, "_now", lambda: wp.datetime(2026, 4, 3, 12, 0, next(seconds), tzinfo=wp.timezone.utc))
    kept = wp.build_package(env["manager"], _request(env, "killed"))          # never finalized
    finished = _audited_not_renamed(env, monkeypatch, "finished")
    final = wp.finalize_package(env["manager"], wp.build_package(env["manager"], _request(env, "done")))
    tab, panel = _panel(env)
    try:
        found = {os.path.basename(f.path): f for f in panel.scan_stale(str(env["out"]))}
        assert sorted(found) == ["finished.partial", "killed.partial"]          # the finalized folder is not listed
        assert found["killed.partial"].state == wp.STALE_UNAUDITED and found["killed.partial"].files == 7
        assert found["finished.partial"].state == wp.STALE_AUDITED
        assert panel.remove_stale_btn.isEnabled() and panel.recover_stale_btn.isEnabled()
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
        panel.remove_stale_btn.click()
        assert os.path.isdir(kept.partial_dir)                                   # declined: nothing removed
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
        panel.remove_stale_btn.click()
        assert not os.path.exists(kept.partial_dir) and os.path.isdir(finished.partial_dir) and os.path.isdir(final)
        removed = [json.loads(r[0]) for r in _actions(env, wp.AUDIT_STALE_REMOVED)]
        assert removed == [{"files": 7, "manifest_sha256": kept.manifest_sha256, "package": "killed"}]
        assert [f.state for f in panel.stale] == [wp.STALE_AUDITED] and not panel.remove_stale_btn.isEnabled()
    finally:
        tab.cleanup()
        tab.deleteLater()


def test_an_identical_manifest_audited_under_another_name_is_refused_not_classified_audited(env, monkeypatch):
    """Two builds in the same second write byte-identical manifests (the folder name is not in it)."""
    monkeypatch.setattr(wp, "_now", lambda: wp.datetime(2026, 4, 3, 12, 0, 0, tzinfo=wp.timezone.utc))
    twin = wp.build_package(env["manager"], _request(env, "twin"))
    audited = _audited_not_renamed(env, monkeypatch, "audited")
    assert twin.manifest_sha256 == audited.manifest_sha256
    stale = wp.inspect_stale_folder(twin.partial_dir, env["manager"])
    assert stale.state == wp.STALE_REFUSED and "under the package name 'audited'" in stale.reason
    assert wp.inspect_stale_folder(audited.partial_dir, env["manager"]).state == wp.STALE_AUDITED
    with pytest.raises(wp.PackageError):
        wp.recover_stale_folder(twin.partial_dir, env["manager"])
    assert os.path.isdir(twin.partial_dir) and not os.path.exists(twin.final_dir)


def test_a_build_killed_while_writing_has_no_manifest_and_is_unaudited(env):
    result = wp.build_package(env["manager"], _request(env, "torn"))
    os.remove(os.path.join(result.partial_dir, wp.MANIFEST))
    stale = wp.inspect_stale_folder(result.partial_dir, env["manager"])
    assert stale.state == wp.STALE_UNAUDITED and stale.manifest_sha256 is None
    wp.remove_stale_folder(result.partial_dir, env["manager"])
    assert not os.path.exists(result.partial_dir)


def test_an_audited_folder_is_never_removed(env, monkeypatch):
    result = _audited_not_renamed(env, monkeypatch)
    with pytest.raises(wp.PackageError, match="not removed: audit record"):
        wp.remove_stale_folder(result.partial_dir, env["manager"])
    assert os.path.isdir(result.partial_dir) and _actions(env, wp.AUDIT_STALE_REMOVED) == []


def test_an_audited_folder_with_a_changed_manifest_is_refused_not_removed(env, monkeypatch):
    """Its manifest hash no longer matches, but the audit record names the package: never 'unaudited'."""
    result = _audited_not_renamed(env, monkeypatch)
    with open(os.path.join(result.partial_dir, wp.MANIFEST), "ab") as handle:
        handle.write(b"\n")
    stale = wp.inspect_stale_folder(result.partial_dir, env["manager"])
    assert stale.state == wp.STALE_REFUSED and "names this package" in stale.reason and "differs" in stale.reason
    os.remove(os.path.join(result.partial_dir, wp.MANIFEST))
    assert "is missing" in wp.inspect_stale_folder(result.partial_dir, env["manager"]).reason
    for action in (wp.remove_stale_folder, wp.recover_stale_folder):
        with pytest.raises(wp.PackageError):
            action(result.partial_dir, env["manager"])
    assert os.path.isdir(result.partial_dir)


def test_a_changed_file_or_an_existing_final_name_blocks_the_rename(env, monkeypatch):
    result = _audited_not_renamed(env, monkeypatch)
    os.mkdir(result.final_dir)
    with pytest.raises(wp.PackageError, match="not overwritten"):
        wp.recover_stale_folder(result.partial_dir, env["manager"])
    os.rmdir(result.final_dir)
    with open(os.path.join(result.partial_dir, "eowr.html"), "ab") as handle:
        handle.write(b"<!-- edited -->")
    with pytest.raises(wp.PackageError, match="changed: eowr.html"):
        wp.recover_stale_folder(result.partial_dir, env["manager"])
    assert os.path.isdir(result.partial_dir) and not os.path.exists(result.final_dir)
    assert _actions(env, wp.AUDIT_STALE_RENAMED) == []


def test_links_folders_with_subfolders_finalized_packages_and_no_database_are_refused(env, tmp_path):
    out = env["out"]
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("synthetic")
    os.symlink(target, out / "link.partial")
    nested = out / "nested.partial"
    nested.mkdir()
    (nested / "sub").mkdir()
    final = wp.finalize_package(env["manager"], wp.build_package(env["manager"], _request(env, "done")))
    torn = wp.build_package(env["manager"], _request(env, "torn"))
    reasons = {
        "link": wp.inspect_stale_folder(str(out / "link.partial"), env["manager"]),
        "nested": wp.inspect_stale_folder(str(nested), env["manager"]),
        "final": wp.inspect_stale_folder(final, env["manager"]),
        "no db": wp.inspect_stale_folder(torn.partial_dir, None),
    }
    assert {k: v.state for k, v in reasons.items()} == dict.fromkeys(reasons, wp.STALE_REFUSED)
    assert "link" in reasons["link"].reason and "not a plain file" in reasons["nested"].reason
    assert "finalized package is never touched" in reasons["final"].reason and "no database" in reasons["no db"].reason
    for path in (out / "link.partial", nested, final):
        with pytest.raises(wp.PackageError):
            wp.remove_stale_folder(str(path), env["manager"])
    assert (target / "keep.txt").exists() and (nested / "sub").is_dir() and wp.verify_package(final, env["manager"]).ok


def test_a_failing_audit_record_removes_nothing(env, monkeypatch):
    result = wp.build_package(env["manager"], _request(env, "killed"))

    def refuse(*_a, **_k):
        raise RuntimeError("audit store unavailable")
    monkeypatch.setattr(env["manager"], "_add_mandatory_audit", refuse)
    with pytest.raises(RuntimeError):
        wp.remove_stale_folder(result.partial_dir, env["manager"])
    assert sorted(os.listdir(result.partial_dir)) == sorted([p.file for p in result.parts if p.sha256] + [wp.MANIFEST])
