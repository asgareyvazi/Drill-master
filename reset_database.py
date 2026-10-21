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


USAGE = """usage: python reset_database.py

Permanently deletes all data and users in the configured DrillMaster database
and re-creates it with the bootstrap account. Takes no arguments: it asks you
to type RESET before anything is deleted. Back up the database first.
"""


def _refuse_arguments(argv) -> None:
    """Never let an argument (e.g. --help) fall through to the destructive prompt."""
    if not argv:
        return
    if argv in (["-h"], ["--help"]):
        print(USAGE, end="")
        raise SystemExit(0)
    print(f"reset_database.py takes no arguments (got {len(argv)}); nothing was changed.\n{USAGE}", end="")
    raise SystemExit(2)


if __name__ == "__main__":
    import sys

    _refuse_arguments(sys.argv[1:])
    from core.runtime_config import database_path
    print(f"Configured database: {database_path()}")
    print("Close all DrillMaster instances and back up this database first.")
    print("This permanently deletes all data and users in the configured database.")
    if input("Type RESET to continue: ") != "RESET":
        print("Reset cancelled.")
        raise SystemExit(0)
    raise SystemExit(0 if reset_database() else 1)
