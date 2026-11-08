"""M137: dependency / licence / packaging reconciliation.

The reconciliation runs on a temporary copy of the declaration and packaging files, so every drift is a real
edit of those files; the bundle smoke check runs on synthetic bundle folders (the real bundle is validated by
the Windows release job).
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import dependency_audit as da  # noqa: E402

FILES = ("pyproject.toml", "requirements.txt", "requirements-lock.txt", "requirements-optional.txt",
         "requirements-build.txt", "packaging/DrillMaster.spec", "packaging/package_smoke.py",
         "THIRD_PARTY_NOTICES.md")


def _smoke():
    spec = importlib.util.spec_from_file_location("m137_package_smoke", ROOT / "packaging" / "package_smoke.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root(tmp_path):
    for rel in FILES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, tmp_path / rel)
    return tmp_path


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def _findings(root):
    return [f["finding"] for f in da.reconcile(root)["findings"]]


def test_the_repository_declarations_and_packaging_agree():
    result = da.reconcile(ROOT)
    assert result["findings"] == []
    assert {"qtribbon", "rapidocr", "onnxruntime", "torch", "PyQt5", "PyQt6"} <= set(da.BUNDLE_EXCLUDED)
    assert set(da.BUNDLE_EXCLUDED) <= set(result["packaging"]["spec_excludes"])
    assert result["optional_pins"]["camelot-py"]["version"] == "0.11.0"       # the pinned version, not 2.0.0
    assert "bootloader exception" in result["build_pins"]["pyinstaller"]["licence"]


def test_a_dependency_added_to_pyproject_only_is_a_failure(root):
    _edit(root / "pyproject.toml", '"PyMuPDF>=1.23,<2",', '"PyMuPDF>=1.23,<2",\n    "lasio>=0.32",')
    assert any("dependencies differ from requirements.txt: lasio>=0.32" in f for f in _findings(root))


def test_a_declared_distribution_without_a_lock_pin_is_a_failure(root):
    for rel in ("requirements.txt",):
        _edit(root / rel, "PyMuPDF>=1.23,<2", "PyMuPDF>=1.23,<2\nlasio>=0.32")
    _edit(root / "pyproject.toml", '"PyMuPDF>=1.23,<2",', '"PyMuPDF>=1.23,<2",\n    "lasio>=0.32",')
    assert _findings(root) == ["declared lasio has no pin"]


def test_an_optional_or_build_pin_needs_a_licence_read_for_exactly_that_version(root):
    _edit(root / "requirements-optional.txt", "camelot-py[cv]==0.11.0", "camelot-py[cv]==1.0.0")
    _edit(root / "requirements-build.txt", "pefile==2023.2.7", "pefile==2023.2.7\nwheel==0.45.1")
    found = _findings(root)
    assert "camelot-py==1.0.0: licence recorded for 0.11.0 (re-read the published metadata of the pinned version)" \
        in found
    assert "wheel==0.45.1 has no recorded licence" in found


def test_a_gated_module_missing_from_the_spec_or_the_smoke_check_is_a_failure(root):
    _edit(root / "packaging/DrillMaster.spec", '    "qtribbon",\n', "")
    _edit(root / "packaging/package_smoke.py", '"rapidocr", ', "")
    found = _findings(root)
    assert "gated module qtribbon is not excluded from the PyInstaller bundle" in found
    assert "gated module rapidocr is not rejected by the bundle smoke check" in found


def test_the_notices_section_is_generated_current_and_names_every_bundled_distribution():
    lock = da.build()["lock"]
    current = (ROOT / da.NOTICES).read_text(encoding="utf-8")
    assert current == da.notices_text(ROOT, lock)                              # --check would pass
    section = current.split(da.NOTICES_BEGIN, 1)[1].split(da.NOTICES_END, 1)[0]
    for row in lock:
        assert f"| {row['distribution']} | {row['pinned']} |" in section
    assert "| PyMuPDF | 1.24.14 |" in section and "PyMuPDF (AGPL-3.0)" in section
    assert "does not by itself meet AGPL or LGPL" in section
    assert "## cement-calc (method reference)" in current                      # hand-written part kept


def test_a_stale_notices_section_is_replaced_not_duplicated(root):
    lock = da.build()["lock"]
    text = (root / da.NOTICES).read_text(encoding="utf-8")
    head, rest = text.split(da.NOTICES_BEGIN, 1)
    tail = rest.split(da.NOTICES_END, 1)[1]
    (root / da.NOTICES).write_text(head + da.NOTICES_BEGIN + "\nstale\n" + da.NOTICES_END + tail, encoding="utf-8")
    regenerated = da.notices_text(root, lock)
    assert "stale" not in regenerated and regenerated.count(da.NOTICES_BEGIN) == 1
    assert regenerated == text


def _bundle(tmp_path, smoke, *, skip=()):
    bundle = tmp_path / "DrillMaster"
    (bundle / "_internal").mkdir(parents=True)
    for name, version in smoke.locked_distributions():
        if name not in skip:
            (bundle / "_internal" / f"{name.replace('-', '_')}-{version}.dist-info").mkdir()
    return bundle


def test_the_bundle_smoke_requires_the_notices_and_every_locked_distributions_metadata(tmp_path):
    smoke = _smoke()
    assert Path("THIRD_PARTY_NOTICES.md") in smoke.REQUIRED_CONFIG
    bundle = _bundle(tmp_path, smoke, skip=("PyMuPDF",))
    assert smoke.missing_licence_metadata(bundle) == ["PyMuPDF==1.24.14"]
    errors = smoke.validate_bundle(bundle)
    assert "missing licence metadata of the bundled distribution PyMuPDF==1.24.14" in errors
    assert "missing package data: THIRD_PARTY_NOTICES.md" in errors
    (bundle / "_internal" / "pymupdf-1.24.14.dist-info").mkdir()             # wheel names vary in case / separators
    assert smoke.missing_licence_metadata(bundle) == []
    (bundle / "_internal" / "python_dateutil-2.9.0.post0.dist-info").rename(
        bundle / "_internal" / "python_dateutil-2.8.0.dist-info")              # another version is not evidence
    assert smoke.missing_licence_metadata(bundle) == ["python-dateutil==2.9.0.post0"]


@pytest.mark.parametrize("path", ["_internal/torch/__init__.pyc", "_internal/PyQt5/QtCore.pyd",
                                  "_internal/qtribbon/__init__.pyc", "_internal/rapidocr/models/x.onnx",
                                  "_internal/onnxruntime/capi/onnxruntime.dll"])
def test_the_bundle_smoke_rejects_every_gated_module(tmp_path, path):
    smoke = _smoke()
    bundle = _bundle(tmp_path, smoke)
    target = bundle / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    assert any("forbidden optional/development module included" in e for e in smoke.validate_bundle(bundle))


def test_the_spec_ships_the_notices_and_the_locked_metadata():
    source = (ROOT / "packaging" / "DrillMaster.spec").read_text(encoding="utf-8")
    assert 'datas.append((str(PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"), "."))' in source
    assert "datas += copy_metadata(_line.split(\"==\", 1)[0])" in source
    assert '(PROJECT_ROOT / "requirements-lock.txt")' in source
