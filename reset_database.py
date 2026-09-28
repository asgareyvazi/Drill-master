#!/usr/bin/env python3
"""Explicitly reset the configured DrillMaster database.

This destructive utility is for local administration only. It follows the same
path configuration as the application and never assumes the current directory.
"""

from __future__ import annotations



def reset_database() -> bool:
    from core.credential_policy import CredentialLifecycleError
    from core.database_reset import reset_configured_database

    try:
        database = reset_configured_database()
        print(f"Reset completed securely: {database}")
        print("Start DrillMaster and sign in with the configured bootstrap account. No passwords were printed.")
        return True
    except CredentialLifecycleError as exc:
        print(f"Reset refused before data deletion: {exc}")
    except Exception:
        # Do not stringify arbitrary backend/OS exceptions at a credential boundary.
        print("Reset failed. Close all DrillMaster instances and check filesystem access and initialization diagnostics. "
              "The existing database is retained unless replacement completed.")
    return False


if __name__ == "__main__":
    from core.runtime_config import database_path
    print(f"Configured database: {database_path()}")
    print("Close all DrillMaster instances and back up this database first.")
    print("This permanently deletes all data and users in the configured database.")
    if input("Type RESET to continue: ") != "RESET":
        print("Reset cancelled.")
        raise SystemExit(0)
    raise SystemExit(0 if reset_database() else 1)
