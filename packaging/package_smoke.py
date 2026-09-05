"""Validate and optionally execute a frozen DrillMaster bundle.

This script is intentionally outside the application bundle. It is used by
Windows CI/build operators and never ships as a user-facing application file.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REQUIRED_CONFIG = (
    Path("config") / "ai_models.json",
    Path("config") / "company_templates" / "oeoc.json",
)


def _find_in_bundle(bundle: Path, relative: Path) -> Path | None:
    direct = bundle / relative
    if direct.exists():
        return direct
    matches = list(bundle.rglob(relative.name))
    for match in matches:
        if match.as_posix().endswith(relative.as_posix()):
            return match
    return None


def validate_bundle(bundle: Path) -> list[str]:
    errors = []
    executable = bundle / "DrillMaster.exe"
    if not executable.is_file():
        errors.append(f"missing executable: {executable}")
    for relative in REQUIRED_CONFIG:
        if _find_in_bundle(bundle, relative) is None:
            errors.append(f"missing package data: {relative}")
    if not any(path.name == "Qt6Core.dll" for path in bundle.rglob("Qt6Core.dll")):
        errors.append("missing PySide6 Qt6Core.dll")
    if not any(path.name == "qwindows.dll" for path in bundle.rglob("qwindows.dll")):
        errors.append("missing Qt Windows platform plugin qwindows.dll")
    if any(path.name.startswith("test_") for path in bundle.rglob("*.py")):
        errors.append("test source was included in the application bundle")
    return errors


def run_smoke(bundle: Path) -> int:
    executable = bundle / "DrillMaster.exe"
    environment = os.environ.copy()
    environment["DRILLMASTER_AI_IMPORT"] = "0"
    completed = subprocess.run(
        [str(executable), "--package-smoke"],
        cwd=bundle,
        env=environment,
        check=False,
        timeout=180,
    )
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="also execute DrillMaster.exe --package-smoke")
    args = parser.parse_args(argv)
    bundle = args.bundle_dir.resolve()
    errors = validate_bundle(bundle)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.run:
        return run_smoke(bundle)
    print(f"Package structure OK: {bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
