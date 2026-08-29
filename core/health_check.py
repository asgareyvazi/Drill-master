"""Runtime health checks for support and release diagnostics."""
import importlib.util
import sys
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CORE_DEPENDENCIES = ("PySide6", "sqlalchemy", "openpyxl")
OPTIONAL_DEPENDENCIES = ("numpy", "matplotlib", "pandas", "pyqtgraph", "fitz", "camelot")


def check_dependencies():
    return {
        "python": sys.version.split()[0],
        "core": {name: importlib.util.find_spec(name) is not None for name in CORE_DEPENDENCIES},
        "optional": {name: importlib.util.find_spec(name) is not None for name in OPTIONAL_DEPENDENCIES},
    }


def check_database(db_path: str = None) -> dict:
    """Check database connectivity and basic stats."""
    if db_path is None:
        base_dir = Path(__file__).resolve().parent.parent
        db_path = str(base_dir / "drillmaster.db")
    
    result = {"path": db_path, "exists": os.path.exists(db_path)}
    
    if not result["exists"]:
        result["status"] = "not_found"
        return result
    
    try:
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        result["size_mb"] = round(size_mb, 2)
        
        from core.database import DatabaseManager
        db = DatabaseManager()
        db.db_path = db_path
        if db.initialize():
            result["status"] = "connected"
            try:
                hierarchy = db.get_hierarchy()
                result["companies"] = len(hierarchy)
                result["projects"] = sum(len(c.get("projects", [])) for c in hierarchy)
                result["wells"] = sum(
                    len(p.get("wells", []))
                    for c in hierarchy
                    for p in c.get("projects", [])
                )
            except Exception as e:
                result["query_error"] = str(e)
            db.close()
        else:
            result["status"] = "init_failed"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


def check_modules() -> dict:
    """Check that all core modules can be imported."""
    modules = [
        "core.database", "core.db_models", "core.canonical_schema",
        "core.unit_manager", "core.universal_import", "core.managers",
        "core.permissions", "core.selection_manager", "core.lineage",
        "core.engineering", "core.engineering.core",
        "core.validators", "core.import_quality",
    ]
    results = {}
    for mod in modules:
        try:
            importlib.import_module(mod)
            results[mod] = "ok"
        except Exception as e:
            results[mod] = f"error: {e}"
    return results


def is_healthy():
    return all(check_dependencies()["core"].values())


def full_health_check() -> dict:
    """Comprehensive health check for release verification."""
    return {
        "dependencies": check_dependencies(),
        "database": check_database(),
        "modules": check_modules(),
        "healthy": is_healthy(),
        "python_version": sys.version,
        "platform": sys.platform,
    }
