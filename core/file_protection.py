"""M136: owner-only file permissions for the live database and generated packages (POSIX).

``restrict_to_owner(path)`` sets ``0600`` on a file (``0700`` on a folder) when the current user owns it and
returns what was done, in words. Nothing is changed:

* on Windows — access is governed by the ACL of the folder (normally the user profile); this build neither
  changes nor verifies Windows ACLs, and says so;
* for a path owned by another user (a shared database is the administrator's decision);
* for a path that does not exist.

SQLite creates the ``-wal``/``-shm``/``-journal`` files with the permissions of the database file, so
restricting the database file covers them from then on; existing ones are restricted too.
"""
from __future__ import annotations

import logging
import os
import stat
from typing import Dict

logger = logging.getLogger(__name__)

FILE_MODE = 0o600
DIR_MODE = 0o700
SQLITE_COMPANIONS = ("-wal", "-shm", "-journal")
WINDOWS_NOTE = ("not changed on Windows (the folder's ACL applies, normally the user profile; this build does not "
                "change or verify Windows ACLs)")


def is_posix() -> bool:
    return os.name == "posix"


def describe(path: str) -> str:
    """The current permission state of ``path`` in words (no change)."""
    if not os.path.exists(path):
        return "does not exist"
    if not is_posix():
        return WINDOWS_NOTE
    mode = stat.S_IMODE(os.stat(path).st_mode)
    others = mode & (stat.S_IRWXG | stat.S_IRWXO)
    return f"{'owner-only' if not others else 'readable by group/others'} ({mode:04o})"


def restrict_to_owner(path: str) -> str:
    if not os.path.exists(path):
        return "does not exist"
    if not is_posix():
        return WINDOWS_NOTE
    info = os.stat(path)
    if info.st_uid != os.getuid():
        return f"not changed (owned by uid {info.st_uid}, not by this user)"
    wanted = DIR_MODE if stat.S_ISDIR(info.st_mode) else FILE_MODE
    if stat.S_IMODE(info.st_mode) != wanted:
        try:
            os.chmod(path, wanted)
        except OSError as exc:   # e.g. a file system without POSIX modes: reported, the database still opens
            logger.warning("Could not restrict %s to its owner: %s", os.path.basename(path), type(exc).__name__)
            return f"not changed ({type(exc).__name__}: the file system refused the permission change)"
        return f"restricted to the owner ({wanted:04o})"
    return f"owner-only ({wanted:04o})"


def protect_database_files(db_path: str) -> Dict[str, str]:
    """Restrict the database file and its existing SQLite companions; returns path -> outcome."""
    out = {db_path: restrict_to_owner(db_path)}
    for suffix in SQLITE_COMPANIONS:
        companion = db_path + suffix
        if os.path.exists(companion):
            out[companion] = restrict_to_owner(companion)
    return out
