#!/usr/bin/env python3
"""Explicitly reset the configured DrillMaster database.

This destructive utility is for local administration only. It follows the same
path configuration as the application and never assumes the current directory.
"""

from __future__ import annotations

import sys
from pathlib import Path


def reset_database() -> bool:
    from core.database import DatabaseManager

    manager = DatabaseManager()
    if manager.db_path == ":memory:":
        print("Refusing to reset an in-memory database.")
        return False

    database = Path(manager.db_path)
    print(f"Resetting configured database: {database}")
    for path in (database, Path(f"{database}-shm"), Path(f"{database}-wal")):
        try:
            path.unlink()
            print(f"Removed {path}")
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"Could not remove {path}: {exc}")
            return False

    if not manager.initialize():
        print("Database initialization failed; review the protected log.")
        return False
    try:
        print(f"Created database with {len(manager.get_hierarchy())} companies.")
        return True
    finally:
        manager.close()


if __name__ == "__main__":
    print("This permanently deletes all data in the configured database.")
    if input("Type RESET to continue: ") != "RESET":
        print("Reset cancelled.")
        raise SystemExit(0)
    raise SystemExit(0 if reset_database() else 1)
