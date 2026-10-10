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
    assert '[string]$Python = ""' in build_script and "Legacy -Python" in build_script
    assert "Invoke-Expression" not in build_script
    assert "DefaultDirName={autopf}\\DrillMaster" in installer
    assert "{userappdata}" not in installer
    assert "BootstrapDialog" in app_source
    assert 'os.environ["DRILLMASTER_ENV"] = "production"' in app_source
    assert "--package-smoke" in app_source


def _valid_bundle(tmp_path):
    bundle = tmp_path / "DrillMaster"
    bundle.mkdir()
    (bundle / "DrillMaster.exe").write_bytes(b"test")
    (bundle / "config" / "company_templates").mkdir(parents=True)
    (bundle / "config" / "ai_models.json").write_text("{}", encoding="utf-8")
    (bundle / "config" / "company_templates" / "oeoc.json").write_text("{}", encoding="utf-8")
    (bundle / "config" / "company_templates" / "example_company.json").write_text("{}", encoding="utf-8")
    (bundle / "templates").mkdir()
    for name in ("OEOC_DDR_General.json", "OEOC_DDR_v3.json", "OEOC_DDR_full_extraction.json"):
        (bundle / "templates" / name).write_text("{}", encoding="utf-8")
    for dll in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6PrintSupport.dll", "Qt6Svg.dll"):
        (bundle / dll).write_bytes(b"test")
    (bundle / "platforms").mkdir()
    (bundle / "platforms" / "qwindows.dll").write_bytes(b"test")
    return bundle


def test_package_smoke_validates_a_supplied_bundle(tmp_path):
    bundle = _valid_bundle(tmp_path)
    assert _load_package_smoke().validate_bundle(bundle) == []


def test_package_smoke_rejects_optional_or_test_modules(tmp_path):
    bundle = _valid_bundle(tmp_path)
    (bundle / "_internal" / "mineru").mkdir(parents=True)
    (bundle / "_internal" / "mineru" / "__init__.py").write_text("")
    assert any("forbidden optional" in error for error in _load_package_smoke().validate_bundle(bundle))


def test_package_smoke_launch_isolated_and_requires_log(tmp_path, monkeypatch):
    from types import SimpleNamespace

    bundle = _valid_bundle(tmp_path)
    monkeypatch.setenv("DRILLMASTER_ENVIRONMENT", "production")
    monkeypatch.setenv("DRILLMASTER_ADMIN_PASSWORD", "never-forward-this-secret")
    observed = {}
    smoke = _load_package_smoke()

    def fake_run(command, *, cwd, env, check, capture_output, text, timeout):
        observed.update(command=command, cwd=cwd, env=env, check=check, capture_output=capture_output,
                        text=text, timeout=timeout)
        Path(env["DRILLMASTER_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
        Path(env["DRILLMASTER_LOG_DIR"], "drillmaster.log").write_text("smoke initialized\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(smoke.subprocess, "run", fake_run)
    log = tmp_path / "smoke.log"
    assert smoke.run_smoke(bundle, log) == 0
    assert observed["env"]["DRILLMASTER_ENV"] == "test"
    assert "DRILLMASTER_ENVIRONMENT" not in observed["env"]
    assert "DRILLMASTER_ADMIN_PASSWORD" not in observed["env"]
    assert observed["env"]["DRILLMASTER_AI_IMPORT"] == "0"
    assert Path(observed["env"]["DRILLMASTER_DATA_DIR"]).parent.name.startswith("drillmaster-package-smoke-")
    assert observed["cwd"] == bundle and observed["timeout"] == 180
    assert "never-forward-this-secret" not in log.read_text(encoding="utf-8")


def test_package_release_metadata_records_hashes_and_refuses_external_artifacts(tmp_path):
    import hashlib
    import json
    metadata_module_spec = importlib.util.spec_from_file_location(
        "drillmaster_release_metadata", ROOT / "packaging" / "release_metadata.py"
    )
    metadata_module = importlib.util.module_from_spec(metadata_module_spec)
    assert metadata_module_spec.loader is not None
    metadata_module_spec.loader.exec_module(metadata_module)

    root = tmp_path / "release"
    root.mkdir()
    archive = root / "bundle.zip"
    archive.write_bytes(b"portable bundle")
    installer = root / "setup.exe"
    installer.write_bytes(b"installer")
    metadata = metadata_module.write_manifest(
        root, source_sha="a" * 40, version="1.0.0", python_version="3.12.1",
        pyinstaller_version="6.11.1", pip_version="24.3.1", innosetup_version="6.4.3",
        bundle_zip=archive, installer=installer,
    )
    value = json.loads(metadata.read_text(encoding="utf-8"))
    assert value["git_sha"] == "a" * 40 and value["platform"] == "windows-x64"
    assert {item["filename"]: item["sha256"] for item in value["artifacts"]} == {
        "bundle.zip": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "setup.exe": hashlib.sha256(installer.read_bytes()).hexdigest(),
    }
    assert (root / "SHA256SUMS.txt").is_file()
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError, match="inside the release directory"):
        metadata_module.write_manifest(
            root, source_sha="a" * 40, version="1.0.0", python_version="3.12.1",
            pyinstaller_version="6.11.1", pip_version="24.3.1", innosetup_version="NOT_BUILT",
            bundle_zip=outside, installer=None,
        )


def test_real_windows_bundle_smoke_when_provided():
    configured = os.getenv("DRILLMASTER_BUNDLE_DIR")
    if not configured:
        pytest.skip("Windows bundle not available in this environment")
    smoke = _load_package_smoke()
    errors = smoke.validate_bundle(Path(configured))
    assert not errors, "\n".join(errors)
    assert os.name == "nt", "ENVIRONMENT-BLOCKED: a Windows runtime is required"
    assert smoke.run_smoke(Path(configured).resolve()) == 0


def test_wheel_includes_desktop_ui_and_builtin_templates():
    import tomllib
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "ui*" in config["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "templates*" in config["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "OEOC_DDR_v3.json" in config["tool"]["setuptools"]["package-data"]["templates"]
