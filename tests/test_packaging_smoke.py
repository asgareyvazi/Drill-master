"""Static and optional runtime checks for the Windows release package."""

from __future__ import annotations

import os
from pathlib import Path

import importlib.util

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _load_package_smoke():
    path = ROOT / "packaging" / "package_smoke.py"
    module_spec = importlib.util.spec_from_file_location("drillmaster_package_smoke", path)
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec.loader is not None
    module_spec.loader.exec_module(module)
    return module


def test_windows_packaging_configuration_is_explicit():
    spec = (ROOT / "packaging" / "DrillMaster.spec").read_text(encoding="utf-8")
    build_script = (ROOT / "packaging" / "build_windows.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "DrillMaster.iss").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'name="DrillMaster"' in spec
    assert 'console=False' in spec
    assert '"config" / "ai_models.json"' in spec
    assert "company_templates" in spec
    assert '"tests"' in spec
    assert '"ollama"' in spec and '"mineru"' in spec
    assert "PyInstaller" in build_script
    assert "requirements-build.txt" in build_script
    assert "package_smoke.py" in build_script
    assert "Inno Setup 6" in build_script
    assert "DefaultDirName={autopf}\\DrillMaster" in installer
    assert "{userappdata}" not in installer
    assert "BootstrapDialog" in app_source
    assert 'os.environ["DRILLMASTER_ENV"] = "production"' in app_source
    assert "--package-smoke" in app_source


def test_package_smoke_validates_a_supplied_bundle(tmp_path):
    bundle = tmp_path / "DrillMaster"
    bundle.mkdir()
    (bundle / "DrillMaster.exe").write_bytes(b"test")
    (bundle / "config" / "company_templates").mkdir(parents=True)
    (bundle / "config" / "ai_models.json").write_text("{}", encoding="utf-8")
    (bundle / "config" / "company_templates" / "oeoc.json").write_text("{}", encoding="utf-8")
    (bundle / "Qt6Core.dll").write_bytes(b"test")
    (bundle / "platforms").mkdir()
    (bundle / "platforms" / "qwindows.dll").write_bytes(b"test")
    assert _load_package_smoke().validate_bundle(bundle) == []


def test_real_windows_bundle_smoke_when_provided():
    configured = os.getenv("DRILLMASTER_BUNDLE_DIR")
    if not configured:
        pytest.skip("Windows bundle not available in this environment")
    errors = _load_package_smoke().validate_bundle(Path(configured))
    assert not errors, "\n".join(errors)
