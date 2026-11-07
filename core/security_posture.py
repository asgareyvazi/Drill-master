"""M136: what this build protects, read from the running state — and what it does not.

``posture(db, environ=None)`` returns rows (area, status, detail). Live rows are read from the database
manager (credential hashing, authorization principal, installed audit guards, database file permissions, idle
lock); the NOT PROVIDED rows state limits of this build that no setting changes. Shown in Tools › Security
status; no row is a certification.
"""
from __future__ import annotations

import os
from typing import List, Mapping, Optional, Tuple

POSTURE_VERSION = "M136 security posture v1"
PROVIDED, PARTIAL, NOT_PROVIDED, OFF = "PROVIDED", "PARTIAL", "NOT PROVIDED", "OFF"
AUDIT_TRIGGER_PREFIX = "trg_audit_log_"

NON_CLAIMS: Tuple[Tuple[str, str, str], ...] = (
    ("Encryption at rest", NOT_PROVIDED,
     "the database and backups are plain SQLite files; SQLCipher or Windows DPAPI need the owner's approval "
     "(dependency, key custody, recovery) — design only"),
    ("Tamper evidence against file access", NOT_PROVIDED,
     "the storage guards stop every application writer, but anyone who can write the file can drop them; an "
     "HMAC chain over audit records needs an external key outside the database — design only, owner gate"),
    ("Signatures", NOT_PROVIDED,
     "nothing is signed; reports and packages are UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"),
    ("Windows file access", NOT_PROVIDED,
     "this build does not set or verify Windows ACLs; the folder's ACL (normally the user profile) applies"),
    ("Network exposure", PROVIDED, "desktop application on a local file; no network service is opened"),
)


def _audit_guards(db) -> List[str]:
    from sqlalchemy import text
    with db.session_scope() as session:
        rows = session.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE :p"),
                               {"p": AUDIT_TRIGGER_PREFIX + "%"}).fetchall()
    return sorted(r[0] for r in rows)


def posture(db, environ: Optional[Mapping[str, str]] = None) -> List[Tuple[str, str, str]]:
    from core import database, file_protection
    from core.session_lock import idle_minutes

    rows: List[Tuple[str, str, str]] = []
    rows.append(("Credential hashing", PROVIDED if database._BCRYPT_AVAILABLE else PARTIAL,
                 "bcrypt, 12 rounds; repeated failures lock the account temporarily" if database._BCRYPT_AVAILABLE
                 else "bcrypt is NOT installed: development-only SHA-256 fallback (refused in production)"))
    state = db._authorization_state()
    principal = getattr(state.principal, "username", None) if state.principal is not None else None
    rows.append(("Authorization in the data layer", PROVIDED if state.enforced else OFF,
                 f"every write is checked for '{principal}'" if state.enforced and principal
                 else "not enforced in this session (no signed-in principal)"))
    guards = _audit_guards(db)
    rows.append(("Audit log append-only (storage)", PROVIDED if len(guards) >= 3 else PARTIAL,
                 ("UPDATE, DELETE and REPLACE of audit records are refused for every writer: " + ", ".join(guards))
                 if guards else "no audit guard installed in this database"))
    path = getattr(db, "db_path", ":memory:")
    if path == ":memory:":
        rows.append(("Database file permissions", OFF, "in-memory database (tests): no file"))
    else:
        real = str(os.path.expanduser(path))
        state_text = file_protection.describe(real)
        rows.append(("Database file permissions",
                     PROVIDED if state_text.startswith("owner-only") else
                     NOT_PROVIDED if not file_protection.is_posix() else PARTIAL, state_text))
    rows.append(("Backups", PROVIDED if file_protection.is_posix() else PARTIAL,
                 "each backup is created as a new file, owner-only (0600) on POSIX, verified (integrity check, "
                 "SHA-256)" if file_protection.is_posix() else "verified backups; Windows ACL not set or verified"))
    minutes, note = idle_minutes(environ)
    rows.append(("Session lock", PROVIDED if minutes else PARTIAL,
                 "File › Lock session (Ctrl+Shift+L); " + note))
    rows.extend(NON_CLAIMS)
    return rows
