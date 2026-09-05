# PyInstaller one-folder specification for the Windows DrillMaster desktop app.
# Build from the repository root with packaging/build_windows.ps1.
from pathlib import Path
import sys


PROJECT_ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.version import __version__


BUILD_ROOT = PROJECT_ROOT / "build"
VERSION_FILE = BUILD_ROOT / "generated_version_info.txt"


def _module_names(package_root: Path, package_name: str) -> list[str]:
    """Enumerate only application Python modules, never tests or dev files."""
    modules = []
    for source in sorted(package_root.rglob("*.py")):
        if any(part in {"__pycache__", "tests", "test"} for part in source.parts):
            continue
        relative = source.relative_to(PROJECT_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts.pop()
        modules.append(".".join(parts))
    return modules


def _write_version_file() -> str:
    parts = tuple(int(part) for part in __version__.split("."))
    file_version = parts + (0,) if len(parts) == 3 else parts
    escaped_version = ".".join(str(part) for part in file_version)
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(
        f'''# UTF-8\nVSVersionInfo(\n  ffi=FixedFileInfo(\n    filevers={file_version},\n    prodvers={file_version},\n    mask=0x3f,\n    flags=0x0,\n    OS=0x40004,\n    fileType=0x1,\n    subtype=0x0,\n    date=(0, 0)\n  ),\n  kids=[\n    StringFileInfo([\n      StringTable(\n        "040904B0",\n        [StringStruct("CompanyName", "DrillMaster Inc."),\n         StringStruct("FileDescription", "DrillMaster drilling operations desktop application"),\n         StringStruct("FileVersion", "{escaped_version}"),\n         StringStruct("InternalName", "DrillMaster"),\n         StringStruct("OriginalFilename", "DrillMaster.exe"),\n         StringStruct("ProductName", "DrillMaster"),\n         StringStruct("ProductVersion", "{escaped_version}")]\n      )\n    ]),\n    VarFileInfo([VarStruct("Translation", [1033, 1200])])\n  ]\n)\n''',
        encoding="utf-8",
    )
    return str(VERSION_FILE)


# Application packages are explicit. PyInstaller's Qt hook supplies the Qt
# platform plugins; these hidden imports cover imports resolved dynamically by
# optional adapters and data/export libraries.
hiddenimports = sorted(
    set(
        _module_names(PROJECT_ROOT / "core", "core")
        + _module_names(PROJECT_ROOT / "dialogs", "dialogs")
        + _module_names(PROJECT_ROOT / "tabs", "tabs")
        + [
            "bcrypt",
            "fitz",
            "matplotlib.backends.backend_qtagg",
            "numpy",
            "openpyxl",
            "pandas",
            "pyqtgraph",
            "shiboken6",
            "sqlalchemy.dialects.sqlite",
        ]
    )
)

datas = [
    (str(PROJECT_ROOT / "config" / "ai_models.json"), "config"),
]
for template in sorted((PROJECT_ROOT / "config" / "company_templates").glob("*.json")):
    datas.append((str(template), "config/company_templates"))

excludes = [
    # Optional integrations are detected and installed separately. Excluding
    # them prevents accidental redistribution and keeps the core bundle small.
    "camelot",
    "gekko",
    "magic_pdf",
    "mineru",
    "ollama",
    "pytesseract",
    "pdf2image",
    "torque_drag",
    "welleng",
    "pytest",
    "ruff",
]

a = Analysis(
    [str(PROJECT_ROOT / "app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DrillMaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
    version=_write_version_file(),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=False,
    name="DrillMaster",
)
