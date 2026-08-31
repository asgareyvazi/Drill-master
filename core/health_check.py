"""Runtime health checks for support and release diagnostics."""
import importlib.util
import sys

CORE_DEPENDENCIES = ("PySide6", "sqlalchemy", "openpyxl")
OPTIONAL_DEPENDENCIES = ("numpy", "matplotlib", "pandas", "pyqtgraph", "fitz", "camelot")

def check_dependencies():
    return {
        "python": sys.version.split()[0],
        "core": {name: importlib.util.find_spec(name) is not None for name in CORE_DEPENDENCIES},
        "optional": {name: importlib.util.find_spec(name) is not None for name in OPTIONAL_DEPENDENCIES},
    }

def is_healthy():
    return all(check_dependencies()["core"].values())
