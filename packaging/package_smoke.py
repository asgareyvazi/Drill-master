"""Validate and execute a frozen DrillMaster bundle in isolated temporary state.

This script is intentionally outside the application bundle. A smoke run uses
an explicit temporary data/log root and clears inherited credentials so the
frozen executable cannot touch an operator profile or database.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REQUIRED_CONFIG = (
    Path("config") / "ai_models.json",
    Path("config") / "company_templates" / "oeoc.json",
    Path("config") / "company_templates" / "example_company.json",
    Path("templates") / "OEOC_DDR_General.json",
    Path("templates") / "OEOC_DDR_v3.json",
    Path("templates") / "OEOC_DDR_full_extraction.json",
)
REQUIRED_QT_DLLS = (
    "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll", "Qt6PrintSupport.dll", "Qt6Svg.dll",
)
FORBIDDEN_MODULES = {
    "camelot", "gekko", "magic_pdf", "mineru", "ollama", "pytesseract",
    "pdf2image", "torque_drag", "welleng", "pytest", "ruff",
}
BOOTSTRAP_ENV = (
    "DRILLMASTER_ADMIN_PASSWORD", "DRILLMASTER_USER_PASSWORD", "DRILLMASTER_VIEWER_PASSWORD",
)


def _find_in_bundle(bundle: Path, relative: Path) -> Path | None:
    direct = bundle / relative
    if direct.is_file():
        return direct
    for match in bundle.rglob(relative.name):
        if match.as_posix().endswith(relative.as_posix()):
            return match
    return None


def validate_bundle(bundle: Path) -> list[str]:
    errors = []
    if not bundle.is_dir():
        return [f"missing bundle directory: {bundle}"]
    executable = bundle / "DrillMaster.exe"
    if not executable.is_file():
        errors.append(f"missing executable: {executable}")
    for relative in REQUIRED_CONFIG:
        if _find_in_bundle(bundle, relative) is None:
            errors.append(f"missing package data: {relative}")
    names = {path.name.casefold() for path in bundle.rglob("*") if path.is_file()}
    for dll in REQUIRED_QT_DLLS:
        if dll.casefold() not in names:
            errors.append(f"missing Qt runtime DLL: {dll}")
    if "qwindows.dll" not in names:
        errors.append("missing Qt Windows platform plugin qwindows.dll")
    for path in bundle.rglob("*"):
        if not path.is_file():
            continue
        components = {part.casefold() for part in path.parts}
        stem = path.stem.casefold()
        if any(module in components or stem == module for module in FORBIDDEN_MODULES):
            errors.append(f"forbidden optional/development module included: {path.relative_to(bundle)}")
        if path.suffix.casefold() == ".py" and (stem.startswith("test_") or stem == "conftest"):
            errors.append(f"test source was included in the application bundle: {path.relative_to(bundle)}")
    return errors


def _smoke_environment(root: Path) -> tuple[dict[str, str], list[str]]:
    environment = os.environ.copy()
    secret_values = []
    for key in tuple(environment):
        upper = key.upper()
        if any(token in upper for token in ("PASSWORD", "API_KEY", "TOKEN", "SECRET", "CREDENTIAL")):
            if environment[key]:
                secret_values.append(environment[key])
            environment.pop(key, None)
    for key in BOOTSTRAP_ENV:
        value = os.environ.get(key)
        if value:
            secret_values.append(value)
        environment.pop(key, None)
    for key in ("DRILLMASTER_ENVIRONMENT", "DRILLMASTER_AUTO_LOGIN"):
        environment.pop(key, None)
    data_root = root / "data"
    log_root = root / "logs"
    environment.update({
        "DRILLMASTER_ENV": "test",
        "DRILLMASTER_DATA_DIR": str(data_root),
        "DRILLMASTER_DB_PATH": str(data_root / "package-smoke.db"),
        "DRILLMASTER_LOG_DIR": str(log_root),
        "DRILLMASTER_BACKUP_DIR": str(data_root / "backups"),
        "DRILLMASTER_AI_IMPORT": "0",
        "QT_QPA_PLATFORM": "offscreen",
    })
    return environment, secret_values


def run_smoke(bundle: Path, log_path: Path | None = None) -> int:
    executable = bundle / "DrillMaster.exe"
    if not executable.is_file():
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="drillmaster-package-smoke-") as directory:
            root = Path(directory)
            environment, secret_values = _smoke_environment(root)
            try:
                completed = subprocess.run(
                    [str(executable), "--package-smoke"],
                    cwd=bundle,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                output = (completed.stdout or "") + (completed.stderr or "")
                leaked = [value for value in secret_values if value and value in output]
                log_file = root / "logs" / "drillmaster.log"
                log_exists = log_file.is_file()
                log_content = log_file.read_text(encoding="utf-8", errors="replace") if log_exists else ""
                leaked.extend(value for value in secret_values if value and value in log_content)
                sanitized_output = output
                sanitized_log = log_content
                for value in secret_values:
                    if value:
                        sanitized_output = sanitized_output.replace(value, "[REDACTED]")
                        sanitized_log = sanitized_log.replace(value, "[REDACTED]")
                if log_path is not None:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_path.write_text(
                        "exit_code=" + str(completed.returncode) + "\n"
                        + "log_generated=" + str(log_exists).lower() + "\n"
                        + "secret_leak_detected=" + str(bool(leaked)).lower() + "\n"
                        + sanitized_output + "\nAPPLICATION LOG\n" + sanitized_log,
                        encoding="utf-8",
                    )
                forbidden_persisted = (root / "data" / "package-smoke.db").exists()
                if completed.returncode != 0 or not log_exists or leaked or forbidden_persisted:
                    return 1
                return 0
            except subprocess.TimeoutExpired:
                if log_path is not None:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_path.write_text("smoke_timeout=true\n", encoding="utf-8")
                return 1
    except OSError as exc:
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(f"smoke_execution_error={type(exc).__name__}\n", encoding="utf-8")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="execute DrillMaster.exe --package-smoke")
    parser.add_argument("--log-path", type=Path, help="write a sanitized smoke log outside the bundle")
    args = parser.parse_args(argv)
    bundle = args.bundle_dir.resolve()
    errors = validate_bundle(bundle)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.run:
        result = run_smoke(bundle, args.log_path.resolve() if args.log_path else None)
        print(f"Frozen executable smoke: {'PASS' if result == 0 else 'FAIL'}")
        return result
    print(f"Package structure OK: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
